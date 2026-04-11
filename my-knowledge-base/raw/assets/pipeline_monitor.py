#!/usr/bin/env python3
"""
pipeline_monitor.py — Monitors X list + watchlist accounts, inserts new posts into bookmarks.db.

Location: raw/assets/pipeline_monitor.py

How it works:
    - Reads new tweets from your X list (47 accounts, one API call)
    - Reads new tweets from watchlist.md accounts (8 accounts, individual calls)
    - Inserts into ~/.ft-bookmarks/bookmarks.db WITHOUT "processed" tag
    - pipeline_live.py picks them up at 10 AM / 8 PM for full extraction + wikification

Schedule (via cron):
    List:      Every 30 min, 10 AM - 7:30 PM EST (20 runs/day)
    Watchlist: 5 runs/day at 10:00, 12:00, 14:00, 16:30, 19:00 EST

Usage:
    python raw/assets/pipeline_monitor.py                           # Normal run
    python raw/assets/pipeline_monitor.py --backfill --since 2025-03-01  # One-time backfill

Cost:
    ~$1.25/day = ~$38/month at normal volume
    Backfill (March 1 onward): ~$27-50 one-time
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add script directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline_core import (
    init_environment,
    XClient,
    index_includes,
    extract_urls_from_entities,
    retry,
    full_path,
    append_to_file,
    today_str,
)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

LIST_ID = "2043011631098077526"
STATE_FILE = os.path.expanduser("~/.ft-bookmarks/monitor-state.json")
WATCHLIST_HOURS = {10, 12, 14, 16, 19}  # Hours (EST) when watchlist runs: 10am, 12pm, 2pm, 4:30pm→4pm, 7pm

# ─────────────────────────────────────────────
# STATE MANAGEMENT
# ─────────────────────────────────────────────


def load_state() -> Dict:
    if os.path.exists(STATE_FILE):
        return json.loads(Path(STATE_FILE).read_text())
    return {
        "list_since_id": None,
        "watchlist_since_ids": {},
        "user_id_cache": {},
        "last_run": None,
        "total_inserted_today": 0,
        "today_date": None,
    }


def save_state(state: Dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


# ─────────────────────────────────────────────
# WATCHLIST PARSING
# ─────────────────────────────────────────────


def load_watchlist(wiki_root: str) -> List[str]:
    """Read watchlist.md and return list of handles (no @ prefix)."""
    path = full_path(wiki_root, "raw/assets/watchlist.md")
    if not os.path.exists(path):
        print(f"  ⚠ watchlist.md not found at {path}")
        return []

    handles = []
    for line in Path(path).read_text().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-") or ":" in line:
            continue
        handle = line.lstrip("@").strip()
        if handle and re.match(r'^[A-Za-z0-9_]+$', handle):
            handles.append(handle)
    return handles


def should_run_watchlist() -> bool:
    """Check if current hour (EST) is one of the watchlist run times."""
    now = datetime.now()
    # Simple check: current hour in the allowed set
    # This works if Mac timezone is EST. For other timezones, adjust.
    return now.hour in WATCHLIST_HOURS


# ─────────────────────────────────────────────
# X API: LIST TWEETS
# ─────────────────────────────────────────────


def fetch_list_tweets(client: XClient, list_id: str, since_id: Optional[str] = None,
                       start_time: Optional[str] = None) -> List[Dict]:
    """Fetch tweets from a list. Returns normalized tweet dicts."""
    params = {
        "max_results": 100,
        "tweet.fields": "id,text,author_id,attachments,entities,referenced_tweets,conversation_id,created_at",
        "expansions": "attachments.media_keys,author_id",
        "media.fields": "media_key,type,url,preview_image_url,variants,duration_ms",
        "user.fields": "id,name,username",
    }
    if since_id:
        params["since_id"] = since_id
    if start_time:
        params["start_time"] = start_time

    all_tweets = []
    next_token = None
    pages = 0

    while pages < 10:  # Safety cap
        if next_token:
            params["pagination_token"] = next_token

        try:
            payload = client.get(f"/lists/{list_id}/tweets", params=params)
        except Exception as e:
            print(f"  ⚠ List fetch failed: {e}")
            break

        data = payload.get("data", [])
        includes = payload.get("includes", {})

        if not data:
            break

        _, users_by_id, _ = index_includes(includes)

        for tweet in data:
            author = users_by_id.get(tweet.get("author_id", ""), {})
            all_tweets.append({
                "id": tweet["id"],
                "text": tweet.get("text", ""),
                "author_handle": author.get("username", "unknown"),
                "author_id": tweet.get("author_id"),
                "created_at": tweet.get("created_at"),
                "conversation_id": tweet.get("conversation_id"),
                "entities": tweet.get("entities"),
                "referenced_tweets": tweet.get("referenced_tweets", []),
                "attachments": tweet.get("attachments", {}),
            })

        next_token = payload.get("meta", {}).get("next_token")
        if not next_token:
            break
        pages += 1

    return all_tweets


# ─────────────────────────────────────────────
# X API: USER TIMELINE
# ─────────────────────────────────────────────


def resolve_user_id(client: XClient, username: str, cache: Dict) -> Optional[str]:
    """Get user ID from username, with caching."""
    if username in cache:
        return cache[username]

    try:
        payload = client.get(f"/users/by/username/{username}", params={"user.fields": "id"})
        data = payload.get("data", {})
        user_id = data.get("id")
        if user_id:
            cache[username] = user_id
        return user_id
    except Exception as e:
        print(f"  ⚠ Could not resolve @{username}: {e}")
        return None


def fetch_user_tweets(client: XClient, user_id: str, since_id: Optional[str] = None,
                       start_time: Optional[str] = None) -> List[Dict]:
    """Fetch tweets from a user's timeline."""
    params = {
        "max_results": 100,
        "tweet.fields": "id,text,author_id,attachments,entities,referenced_tweets,conversation_id,created_at",
        "expansions": "attachments.media_keys,author_id",
        "media.fields": "media_key,type,url,preview_image_url,variants,duration_ms",
        "user.fields": "id,name,username",
        "exclude": "replies",  # Only original tweets and retweets, not replies to others
    }
    if since_id:
        params["since_id"] = since_id
    if start_time:
        params["start_time"] = start_time

    all_tweets = []
    next_token = None
    pages = 0

    while pages < 10:
        if next_token:
            params["pagination_token"] = next_token

        try:
            payload = client.get(f"/users/{user_id}/tweets", params=params)
        except Exception as e:
            print(f"  ⚠ User timeline fetch failed: {e}")
            break

        data = payload.get("data", [])
        includes = payload.get("includes", {})

        if not data:
            break

        _, users_by_id, _ = index_includes(includes)

        for tweet in data:
            author = users_by_id.get(tweet.get("author_id", ""), {})
            all_tweets.append({
                "id": tweet["id"],
                "text": tweet.get("text", ""),
                "author_handle": author.get("username", "unknown"),
                "author_id": tweet.get("author_id"),
                "created_at": tweet.get("created_at"),
                "conversation_id": tweet.get("conversation_id"),
                "entities": tweet.get("entities"),
                "referenced_tweets": tweet.get("referenced_tweets", []),
                "attachments": tweet.get("attachments", {}),
            })

        next_token = payload.get("meta", {}).get("next_token")
        if not next_token:
            break
        pages += 1

    return all_tweets


# ─────────────────────────────────────────────
# BOOKMARKS DB INSERT
# ─────────────────────────────────────────────


def get_existing_ids(db_path: str) -> Set[str]:
    """Get all existing tweet IDs from bookmarks.db."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT id FROM bookmarks")
        ids = {row[0] for row in cursor.fetchall()}
    except Exception:
        ids = set()
    conn.close()
    return ids


def get_db_columns(db_path: str) -> List[str]:
    """Discover the actual column names in bookmarks table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("PRAGMA table_info(bookmarks)")
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    return columns


def insert_tweets(db_path: str, tweets: List[Dict], existing_ids: Set[str]) -> int:
    """Insert new tweets into bookmarks.db. Returns count of inserted tweets."""
    if not tweets:
        return 0

    # Discover schema
    columns = get_db_columns(db_path)
    conn = sqlite3.connect(db_path)
    inserted = 0

    for tweet in tweets:
        if tweet["id"] in existing_ids:
            continue

        # Build row based on available columns
        row = {}
        if "id" in columns:
            row["id"] = tweet["id"]
        if "text" in columns:
            row["text"] = tweet.get("text", "")
        if "author_handle" in columns:
            row["author_handle"] = tweet.get("author_handle", "unknown")
        if "author_id" in columns:
            row["author_id"] = tweet.get("author_id", "")
        if "created_at" in columns:
            row["created_at"] = tweet.get("created_at", "")
        if "synced_at" in columns:
            row["synced_at"] = datetime.now(timezone.utc).isoformat()
        if "primary_category" in columns:
            row["primary_category"] = None  # Will be classified by pipeline_live
        if "categories" in columns:
            row["categories"] = "[]"  # No "processed" tag — pipeline_live picks it up
        if "conversation_id" in columns:
            row["conversation_id"] = tweet.get("conversation_id", "")
        if "source" in columns:
            row["source"] = "pipeline_monitor"

        if not row:
            continue

        col_names = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))

        try:
            conn.execute(
                f"INSERT OR IGNORE INTO bookmarks ({col_names}) VALUES ({placeholders})",
                list(row.values())
            )
            inserted += 1
            existing_ids.add(tweet["id"])
        except Exception as e:
            print(f"  ⚠ Insert failed for {tweet['id']}: {e}")

    conn.commit()
    conn.close()
    return inserted


# ─────────────────────────────────────────────
# BACKFILL MODE
# ─────────────────────────────────────────────


def run_backfill(client: XClient, since_date: str, config: Dict, state: Dict):
    """One-time backfill: fetch all tweets from list members + watchlist since a date."""
    wiki_root = config["wiki_root"]
    db_path = config["bookmarks_db"]
    start_time = f"{since_date}T00:00:00Z"
    existing_ids = get_existing_ids(db_path)

    print(f"═══ BACKFILL MODE: Since {since_date} ═══\n")

    # First: get list member IDs
    # The list tweets endpoint doesn't go back far enough for backfill
    # We need to fetch each member's timeline individually
    print("  Fetching list members...")
    try:
        payload = client.get(f"/lists/{LIST_ID}/members", params={
            "max_results": 100,
            "user.fields": "id,username",
        })
        members = payload.get("data", [])
        print(f"  Found {len(members)} list members")
    except Exception as e:
        print(f"  ⚠ Could not fetch list members: {e}")
        members = []

    # Add watchlist accounts
    watchlist = load_watchlist(wiki_root)
    all_accounts = []

    for member in members:
        all_accounts.append({
            "username": member.get("username"),
            "user_id": member.get("id"),
            "source": "list",
        })
        state["user_id_cache"][member["username"]] = member["id"]

    for handle in watchlist:
        user_id = resolve_user_id(client, handle, state["user_id_cache"])
        if user_id:
            all_accounts.append({
                "username": handle,
                "user_id": user_id,
                "source": "watchlist",
            })

    print(f"  Total accounts to backfill: {len(all_accounts)}")

    total_inserted = 0
    total_read = 0

    for i, account in enumerate(all_accounts):
        username = account["username"]
        user_id = account["user_id"]
        print(f"\n  [{i+1}/{len(all_accounts)}] @{username}...")

        tweets = fetch_user_tweets(client, user_id, start_time=start_time)
        total_read += len(tweets)

        if tweets:
            count = insert_tweets(db_path, tweets, existing_ids)
            total_inserted += count
            print(f"    {len(tweets)} tweets read, {count} new inserted")

            # Update since_id for this user
            latest_id = max(t["id"] for t in tweets)
            state["watchlist_since_ids"][username] = latest_id
        else:
            print(f"    No tweets since {since_date}")

        # Rate limit courtesy: small delay between users
        time.sleep(1)

    # Update list since_id to the most recent tweet we've seen
    if total_inserted > 0:
        all_ids = [t["id"] for acc in all_accounts for t in
                   fetch_list_tweets(client, LIST_ID, start_time=start_time)]
        if all_ids:
            state["list_since_id"] = max(all_ids)

    save_state(state)

    est_cost = total_read * 0.005
    print(f"\n{'='*50}")
    print(f"  ✅ Backfill complete!")
    print(f"  Tweets read: {total_read}")
    print(f"  New inserted: {total_inserted}")
    print(f"  Estimated cost: ${est_cost:.2f}")
    print(f"{'='*50}")


# ─────────────────────────────────────────────
# NORMAL MODE (cron runs)
# ─────────────────────────────────────────────


def run_normal(client: XClient, config: Dict, state: Dict):
    """Normal 30-minute run: fetch new list tweets + watchlist (if scheduled)."""
    wiki_root = config["wiki_root"]
    db_path = config["bookmarks_db"]
    existing_ids = get_existing_ids(db_path)

    # Reset daily counter
    today = today_str()
    if state.get("today_date") != today:
        state["total_inserted_today"] = 0
        state["today_date"] = today

    total_inserted = 0
    total_read = 0

    # ── LIST TWEETS ──
    print("  Fetching list tweets...")
    list_tweets = fetch_list_tweets(client, LIST_ID, since_id=state.get("list_since_id"))
    total_read += len(list_tweets)

    if list_tweets:
        count = insert_tweets(db_path, list_tweets, existing_ids)
        total_inserted += count
        # Update since_id to latest
        state["list_since_id"] = max(t["id"] for t in list_tweets)
        print(f"    List: {len(list_tweets)} read, {count} new")
    else:
        print(f"    List: no new tweets")

    # ── WATCHLIST (only at scheduled hours) ──
    if should_run_watchlist():
        watchlist = load_watchlist(wiki_root)
        print(f"  Fetching watchlist ({len(watchlist)} accounts)...")

        for handle in watchlist:
            user_id = resolve_user_id(client, handle, state.setdefault("user_id_cache", {}))
            if not user_id:
                continue

            since_id = state.get("watchlist_since_ids", {}).get(handle)
            tweets = fetch_user_tweets(client, user_id, since_id=since_id)
            total_read += len(tweets)

            if tweets:
                count = insert_tweets(db_path, tweets, existing_ids)
                total_inserted += count
                state.setdefault("watchlist_since_ids", {})[handle] = max(t["id"] for t in tweets)
                if count > 0:
                    print(f"    @{handle}: {count} new")
            
            time.sleep(0.5)  # Rate limit courtesy
    else:
        print(f"  Watchlist: skipped (not a scheduled hour)")

    state["total_inserted_today"] = state.get("total_inserted_today", 0) + total_inserted
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    # Log
    log_path = full_path(wiki_root, "wiki/outputs/pipeline-monitor.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_msg = f"[{timestamp}] Read {total_read}, inserted {total_inserted}, daily total {state['total_inserted_today']}\n"
    append_to_file(log_path, log_msg)

    if total_inserted > 0:
        print(f"\n  ✓ Inserted {total_inserted} new tweets (daily total: {state['total_inserted_today']})")
    else:
        print(f"\n  — No new tweets this run")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="X Bookmark Pipeline — Monitor Mode")
    parser.add_argument("--backfill", action="store_true", help="One-time backfill from a date")
    parser.add_argument("--since", type=str, default="2025-03-01", help="Backfill start date (YYYY-MM-DD)")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config = init_environment(args.config)

    # Init X client
    bearer_token = os.environ.get("X_BEARER_TOKEN")
    if not bearer_token:
        print("✗ Missing X_BEARER_TOKEN")
        sys.exit(1)

    client = XClient(bearer_token)
    state = load_state()

    if args.backfill:
        run_backfill(client, args.since, config, state)
    else:
        run_normal(client, config, state)


if __name__ == "__main__":
    main()
