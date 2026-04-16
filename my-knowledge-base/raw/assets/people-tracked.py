#!/usr/bin/env python3
"""
people-tracked.py — Fetches and stores profile info for monitored accounts.

Updates raw/assets/people-tracked.md with current profile data for:
- X List members (from pipeline_monitor.py)
- Watchlist accounts (from watchlist.md)

Run: python3 raw/assets/people-tracked.py
"""

import os
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use TwitterAPI.io client from pipeline_core
from pipeline_core import TwitterAPIioClient, load_watchlist, LIST_ID

OUTPUT_FILE = "people-tracked.md"
OUTPUT_JSON = "people-tracked.json"

LIST_FIELDS = "id,username,name,description,public_metrics,verified,created_at"
USER_FIELDS = "id,username,name,description,public_metrics,verified,created_at,location,url,profile_image_url,protected"


def load_api() -> XTwitterAPI:
    """Get TwitterAPI.io client."""
    api_key = os.environ.get("TWITTER_API_KEY")
    if not api_key:
        raise RuntimeError("Missing TWITTER_API_KEY env var")
    return XTwitterAPI(api_key)


def fetch_list_members(client: XTwitterAPI, list_id: str) -> List[Dict]:
    """Fetch all members of a list."""
    members = []
    pagination_token = None

    while True:
        params = {
            "max_results": 100,
            "user.fields": LIST_FIELDS,
        }
        if pagination_token:
            params["pagination_token"] = pagination_token

        try:
            payload = client.get(f"/lists/{list_id}/members", params=params)
            data = payload.get("data", [])
            members.extend(data)

            pagination_token = payload.get("meta", {}).get("next_token")
            if not pagination_token:
                break
        except Exception as e:
            print(f"  ⚠ List fetch error: {e}")
            break

    return members


def fetch_user_profile(client: XTwitterAPI, username: str) -> Optional[Dict]:
    """Fetch full profile for a user."""
    try:
        params = {"user.fields": USER_FIELDS}
        payload = client.get(f"/users/by/username/{username}", params=params)
        return payload.get("data")
    except Exception as e:
        print(f"  ⚠ @{username}: {e}")
        return None


def get_source_type(username: str, list_members: set, watchlist: List[str]) -> str:
    """Determine if user is from list or watchlist."""
    if username.lower() in list_members:
        return "list"
    if username.lower() in [w.lower() for w in watchlist]:
        return "watchlist"
    return "unknown"


def format_metrics(metrics: Dict) -> str:
    """Format public metrics nicely."""
    if not metrics:
        return "N/A"
    return f"{metrics.get('followers_count', 0):,} followers, {metrics.get('following_count', 0):,} following"


def build_markdown(profiles: List[Dict], list_members: set, watchlist: List[str]) -> str:
    """Build Markdown output."""
    lines = [
        "---",
        'title: "People Tracked"',
        f"date_created: {datetime.now().strftime('%Y-%m-%d')}",
        f"date_modified: {datetime.now().strftime('%Y-%m-%d')}",
        'summary: "Profile data for X list + watchlist accounts"',
        'tags: [monitoring, accounts, x]',
        'type: output',
        'status: draft',
        "---",
        "",
        "# People Tracked",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} EST",
        "",
        f"Total: {len(profiles)} accounts",
        "",
        "## By Source",
        "",
        f"- **List**: {len([p for p in profiles if p.get('source') == 'list'])} accounts",
        f"- **Watchlist**: {len([p for p in profiles if p.get('source') == 'watchlist'])} accounts",
        "",
        "---",
        "",
        "## Accounts",
        "",
    ]

    # Sort by followers (descending)
    sorted_profiles = sorted(
        profiles,
        key=lambda p: p.get("public_metrics", {}).get("followers_count", 0),
        reverse=True
    )

    for p in sorted_profiles:
        username = p.get("username", "")
        name = p.get("name", "")
        desc = p.get("description", "") or ""
        metrics = p.get("public_metrics", {})
        verified = p.get("verified", False)
        created = p.get("created_at", "")[:10] if p.get("created_at") else ""
        source = p.get("source", "unknown")

        # Clean description
        desc = desc.replace("\n", " ")[:200]

        lines.extend([
            f"### @{username}",
            "",
            f"**Name:** {name}",
            f"**Source:** {source}",
            f"**Followers:** {format_metrics(metrics)}",
            f"**Verified:** {'Yes' if verified else 'No'}",
            f"**Joined:** {created}",
            "",
        ])

        if desc:
            lines.append(f"_{desc}_")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    wiki_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(wiki_root)

    print("📋 Fetching people tracked...")

    client = load_api()

    # Get watchlist
    watchlist = load_watchlist(wiki_root)
    print(f"  Watchlist: {len(watchlist)} accounts")

    # Get list members
    print("  Fetching list members...")
    list_members_raw = fetch_list_members(client, LIST_ID)
    list_members = set(m.get("username", "").lower() for m in list_members_raw)
    print(f"  List: {len(list_members_raw)} members")

    # Build list of all usernames
    all_usernames = list(list_members) + [w for w in watchlist if w.lower() not in list_members]
    print(f"  Total unique: {len(all_usernames)}")

    # Fetch profile for each
    profiles = []
    for i, username in enumerate(all_usernames):
        print(f"  [{i+1}/{len(all_usernames)}] @{username}...")
        profile = fetch_user_profile(client, username)
        if profile:
            profile["source"] = get_source_type(username, list_members, watchlist)
            profiles.append(profile)

    print(f"  Fetched: {len(profiles)} profiles")

    # Save JSON
    with open(OUTPUT_JSON, "w") as f:
        json.dump(profiles, f, indent=2, default=str)
    print(f"  Saved: {OUTPUT_JSON}")

    # Save Markdown
    md = build_markdown(profiles, list_members, watchlist)
    with open(OUTPUT_FILE, "w") as f:
        f.write(md)
    print(f"  Saved: {OUTPUT_FILE}")

    print("✅ Done")


if __name__ == "__main__":
    main()