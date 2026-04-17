#!/usr/bin/env python3
"""
pipeline_core.py — Shared engine for X Bookmark Pipeline.

Contains all extraction, analysis, compilation, and finalization logic.
Imported by pipeline.py (backlog mode) and pipeline_live.py (live mode).

Location: raw/assets/pipeline_core.py

Dependencies:
    pip install requests anthropic python-dotenv pyyaml beautifulsoup4
System: ffmpeg on PATH, Python 3.10+
"""

import argparse
import base64
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from anthropic import Anthropic
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# FORK SAFETY FIX (macOS Network.framework crash)
# Set before any subprocess calls to prevent SIGSEGV after fork()
# See: https://github.com/urllib3/urllib3/issues/3020
# ─────────────────────────────────────────────
if sys.platform == "darwin":
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

X_API_BASE = "https://api.x.com/2"
TWITTER_APIIO_BASE = "https://api.twitterapi.io"
MINIMAX_BASE_URL = "https://api.minimax.io/anthropic"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1/models"
POST_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:x\.com|twitter\.com)/([A-Za-z0-9_]+)/status/(\d+)"
)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load config.yaml. Falls back to defaults if missing.
    Searches: provided path → script directory → wiki root.
    """
    # Auto-resolve: look next to the script itself (raw/assets/config.yaml)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_paths = [
        config_path,
        os.path.join(script_dir, "config.yaml"),
        os.path.join(script_dir, "..", "..", "config.yaml"),  # wiki root if script is in raw/assets/
    ]
    
    defaults = {
        "wiki_root": "/Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base",
        "bookmarks_db": os.path.expanduser("~/.ft-bookmarks/bookmarks.db"),
        "env_file": "/Users/adamdrapkin/Obsidian/synteo-intelligence/.env",
        "temp_base": "/tmp/pipeline-batch-{N}",
        "backlog_log": "raw/assets/backlog-log.md",
        "bookmark_classification": "raw/assets/bookmark-classification.md",
        "skills": {
            "wiki_ingest": os.path.expanduser("~/.claude/skills/wiki-ingest/SKILL.md"),
            "qa_council": os.path.expanduser("~/.claude/skills/qa-council/SKILL.md"),
            "wiki_lint": os.path.expanduser("~/.claude/skills/wiki-lint/SKILL.md"),
            "image_analysis": os.path.expanduser("~/.claude/skills/image-analysis/SKILL.md"),
            "video_analysis": os.path.expanduser("~/.claude/skills/video-analysis/SKILL.md"),
            "image_analysis_prompt": os.path.expanduser("~/.claude/skills/image-analysis/prompts/analysis.md"),
            "video_analysis_prompt": os.path.expanduser("~/.claude/skills/video-analysis/prompts/analysis.md"),
        },
        "api": {
            "gemini_flash_model": "gemini-2.5-flash",
            "gemini_pro_model": "gemini-2.5-pro",
            "whisper_model": "whisper-1",
            "minimax_model": "MiniMax-M2.7",
            "max_retries": 3,
            "retry_backoff": 2,
        },
    }
    
    for path in search_paths:
        if os.path.exists(path):
            with open(path) as f:
                user_cfg = yaml.safe_load(f) or {}
            for key, val in user_cfg.items():
                if isinstance(val, dict) and key in defaults and isinstance(defaults[key], dict):
                    defaults[key].update(val)
                else:
                    defaults[key] = val
            print(f"Config loaded from: {os.path.abspath(path)}")
            break
    else:
        print("No config.yaml found — using defaults")
    return defaults


def full_path(wiki_root: str, relative: str) -> str:
    """Join wiki_root with a relative path."""
    return os.path.join(wiki_root, relative)


# ─────────────────────────────────────────────
# RETRY HELPER
# ─────────────────────────────────────────────


def retry(fn, max_retries: int = 3, backoff: float = 2.0, label: str = ""):
    """Retry a function with exponential backoff. Returns result or raises last error."""
    last_err = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_err = e
            wait = backoff * (2 ** attempt)
            print(f"  ⚠ {label} attempt {attempt+1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    raise last_err


# ─────────────────────────────────────────────
# X API CLIENT (extended from x_post_extractor.py)
# ─────────────────────────────────────────────


class XClient:
    def __init__(self, bearer_token: str, max_retries: int = 3, backoff: float = 2.0):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "x-bookmark-pipeline/2.0",
        })
        self.max_retries = max_retries
        self.backoff = backoff

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{X_API_BASE}{path}"

        def _call():
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                reset = int(resp.headers.get("x-rate-limit-reset", time.time() + 60))
                wait = max(reset - int(time.time()), 5)
                print(f"  ⏳ Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                raise Exception("Rate limited")
            if resp.status_code >= 400:
                raise Exception(f"X API {resp.status_code}: {resp.text[:200]}")
            return resp.json()

        return retry(_call, self.max_retries, self.backoff, label=f"GET {path}")

    def lookup_posts(self, ids: List[str]) -> Dict[str, Any]:
        return self.get("/tweets", params={
            "ids": ",".join(ids),
            "tweet.fields": "id,text,author_id,attachments,entities,referenced_tweets,conversation_id,created_at,in_reply_to_user_id",
            "expansions": "attachments.media_keys,author_id,referenced_tweets.id,referenced_tweets.id.author_id",
            "media.fields": "media_key,type,url,preview_image_url,variants,duration_ms,height,width,alt_text",
            "user.fields": "id,name,username",
        })

    def recent_search_conversation(self, conversation_id: str, next_token: Optional[str] = None) -> Dict[str, Any]:
        params = {
            "query": f"conversation_id:{conversation_id}",
            "max_results": 100,
            "tweet.fields": "id,text,author_id,attachments,entities,referenced_tweets,conversation_id,created_at,in_reply_to_user_id",
            "expansions": "attachments.media_keys,author_id,referenced_tweets.id,referenced_tweets.id.author_id",
            "media.fields": "media_key,type,url,preview_image_url,variants,duration_ms,height,width,alt_text",
            "user.fields": "id,name,username",
        }
        if next_token:
            params["next_token"] = next_token
        return self.get("/tweets/search/recent", params=params)


# ─────────────────────────────────────────────
# TWITTERAPIIO CLIENT (replaces XClient for comprehensive bookmark processing)
# ─────────────────────────────────────────────


class TwitterAPIioClient:
    """TwitterAPI.io client for fetching all bookmark types.

    Uses X-API-Key header instead of Bearer token.
    Covers: tweets, replies, quotes, retweeters, thread context, articles.
    """

    def __init__(self, api_key: str, max_retries: int = 3, backoff: float = 2.0):
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": api_key,
            "User-Agent": "x-bookmark-pipeline/3.0",
        })
        self.max_retries = max_retries
        self.backoff = backoff
        self.base_url = TWITTER_APIIO_BASE

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"

        def _call():
            if method.upper() == "GET":
                resp = self.session.get(url, params=params, timeout=30)
            else:
                resp = self.session.post(url, json=params, timeout=30)

            if resp.status_code == 429:
                # Rate limited - wait and retry
                wait = 60
                print(f"  ⏳ Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                raise Exception("Rate limited")
            if resp.status_code >= 400:
                raise Exception(f"TwitterAPI.io {resp.status_code}: {resp.text[:200]}")

            data = resp.json()
            if data.get("status") == "error":
                raise Exception(f"API error: {data.get('message', 'Unknown error')}")
            return data

        return retry(_call, self.max_retries, self.backoff, label=f"{method} {path}")

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", path, params)

    # ─────────────────────────────────────────────
    # CORE ENDPOINTS
    # ─────────────────────────────────────────────

    def get_tweet_by_ids(self, tweet_ids: List[str]) -> Dict[str, Any]:
        """Fetch tweets by IDs - replaces lookup_posts.

        Endpoint: GET /twitter/tweets
        Returns: Full tweet objects with metrics (views, bookmarks, etc.)
        """
        return self.get("/twitter/tweets", params={
            "tweet_ids": ",".join(tweet_ids)
        })

    def get_tweet_replies_v2(self, tweet_id: str, cursor: str = "", query_type: str = "Latest") -> Dict[str, Any]:
        """Fetch replies to a tweet - no 7-day limit.

        Endpoint: GET /twitter/tweet/replies/v2
        Returns: Up to 20 replies per page
        """
        return self.get("/twitter/tweet/replies/v2", params={
            "tweetId": tweet_id,
            "cursor": cursor,
            "queryType": query_type  # Relevance, Latest, Likes
        })

    def get_tweet_replies(self, tweet_id: str, cursor: str = "", since_time: Optional[int] = None,
                          until_time: Optional[int] = None) -> Dict[str, Any]:
        """Fetch replies with time filtering.

        Endpoint: GET /twitter/tweet/replies
        Returns: Up to 20 replies per page with time filters
        """
        params = {
            "tweetId": tweet_id,
            "cursor": cursor
        }
        if since_time:
            params["sinceTime"] = since_time
        if until_time:
            params["untilTime"] = until_time
        return self.get("/twitter/tweet/replies", params=params)

    def get_tweet_quote(self, tweet_id: str, cursor: str = "", include_replies: bool = True) -> Dict[str, Any]:
        """Fetch quote tweets - replaces manual quote expansion.

        Endpoint: GET /twitter/tweet/quotes
        Returns: Up to 20 quotes per page
        """
        return self.get("/twitter/tweet/quotes", params={
            "tweetId": tweet_id,
            "cursor": cursor,
            "includeReplies": include_replies
        })

    def get_tweet_retweeter(self, tweet_id: str, cursor: str = "") -> Dict[str, Any]:
        """Fetch who retweeted a tweet.

        Endpoint: GET /twitter/tweet/retweeters
        Returns: ~100 retweeters per page
        """
        return self.get("/twitter/tweet/retweeters", params={
            "tweetId": tweet_id,
            "cursor": cursor
        })

    def get_tweet_thread_context(self, tweet_id: str, cursor: str = "") -> Dict[str, Any]:
        """Fetch full thread context - replaces walk_thread_upward + fetch_recent_thread.

        Endpoint: GET /twitter/tweet/thread_context
        Returns: Full thread with parent tweets and replies
        """
        return self.get("/twitter/tweet/thread_context", params={
            "tweetId": tweet_id,
            "cursor": cursor
        })

    def get_article(self, tweet_id: str) -> Dict[str, Any]:
        """Fetch X Article content.

        Endpoint: GET /twitter/article
        Returns: Article object with content blocks
        """
        return self.get("/twitter/article", params={"tweet_id": tweet_id})

    # ─────────────────────────────────────────────
    # PAGINATION HELPERS
    # ─────────────────────────────────────────────

    def get_all_replies(self, tweet_id: str, max_pages: int = 10) -> List[Dict]:
        """Fetch all replies to a tweet (paginated)."""
        all_replies = []
        cursor = ""
        for _ in range(max_pages):
            result = self.get_tweet_replies_v2(tweet_id, cursor=cursor)
            replies = result.get("replies", [])
            all_replies.extend(replies)
            if not result.get("has_next_page"):
                break
            cursor = result.get("next_cursor", "")
        return all_replies

    def get_all_quotes(self, tweet_id: str, max_pages: int = 10) -> List[Dict]:
        """Fetch all quote tweets (paginated)."""
        all_quotes = []
        cursor = ""
        for _ in range(max_pages):
            result = self.get_tweet_quote(tweet_id, cursor=cursor)
            tweets = result.get("tweets", [])
            all_quotes.extend(tweets)
            if not result.get("has_next_page"):
                break
            cursor = result.get("next_cursor", "")
        return all_quotes

    def get_all_retweeters(self, tweet_id: str, max_pages: int = 10) -> List[Dict]:
        """Fetch all retweeters (paginated)."""
        all_users = []
        cursor = ""
        for _ in range(max_pages):
            result = self.get_tweet_retweeter(tweet_id, cursor=cursor)
            users = result.get("users", [])
            all_users.extend(users)
            if not result.get("has_next_page"):
                break
            cursor = result.get("next_cursor", "")
        return all_users


# ─────────────────────────────────────────────
# HELPER: NORMALIZE TWEET RESPONSE
# ─────────────────────────────────────────────


def normalize_tweet_response(tweet: Dict) -> Dict:
    """Normalize TwitterAPI.io tweet response to match pipeline expected format.

    This ensures backward compatibility with existing pipeline processing.
    """
    # Extract author info
    author = tweet.get("author", {})

    # Extract metrics
    metrics = tweet.get("metrics", {}) or {}

    # Build normalized tweet object
    normalized = {
        "id": tweet.get("id", ""),
        "text": tweet.get("text", ""),
        "author_id": author.get("id", ""),
        "created_at": tweet.get("createdAt", ""),
        "conversation_id": tweet.get("conversationId", ""),
        "in_reply_to_user_id": tweet.get("inReplyToUserId", ""),

        # Metrics
        "retweet_count": metrics.get("retweetCount", 0),
        "reply_count": metrics.get("replyCount", 0),
        "like_count": metrics.get("likeCount", 0),
        "quote_count": metrics.get("quoteCount", 0),
        "view_count": metrics.get("viewCount", 0),
        "bookmark_count": metrics.get("bookmarkCount", 0),

        # Author info
        "author": {
            "id": author.get("id", ""),
            "name": author.get("name", ""),
            "username": author.get("username", ""),
            "profile_image_url": author.get("profile_image_url", ""),
        },

        # Entities
        "entities": tweet.get("entities", {}),

        # Referenced tweets (quoted/retweeted)
        "referenced_tweets": [],
    }

    # Handle quoted tweet
    if tweet.get("quoted_tweet"):
        normalized["referenced_tweets"].append({
            "type": "quoted",
            "id": tweet["quoted_tweet"].get("id", "")
        })

    # Handle retweeted tweet
    if tweet.get("retweeted_tweet"):
        normalized["referenced_tweets"].append({
            "type": "retweeted",
            "id": tweet["retweeted_tweet"].get("id", "")
        })

    # Handle reply
    if tweet.get("reply"):
        normalized["referenced_tweets"].append({
            "type": "replied_to",
            "id": tweet["reply"].get("id", "")
        })

    # Handle media attachments (TwitterAPI.io format)
    media_list = tweet.get("media", [])
    if media_list:
        # Build attachments structure matching pipeline expectations
        media_keys = []
        for m in media_list:
            if m.get("mediaKey"):
                media_keys.append(m["mediaKey"])
        normalized["attachments"] = {"media_keys": media_keys}
        # Store raw media list for extract_media_urls to use
        normalized["media"] = media_list
    else:
        normalized["attachments"] = {}
        normalized["media"] = []

    return normalized


def normalize_tweets_response(response: Dict) -> Dict[str, Dict]:
    """Normalize batch tweet response into dict keyed by tweet ID."""
    tweets = response.get("tweets", [])
    return {t["id"]: normalize_tweet_response(t) for t in tweets}


# ─────────────────────────────────────────────
# HELPER: ROUTE BY TWEET TYPE
# ─────────────────────────────────────────────


def route_tweet_to_endpoints(tweet_type: str, tweet_id: str, client: TwitterAPIioClient) -> Dict[str, Any]:
    """Route tweet type to appropriate API endpoint(s).

    Returns dict with results from each endpoint:
    - primary: main tweet data
    - replies: reply tweets (if applicable)
    - quotes: quote tweets (if applicable)
    - retweeters: who retweeted (if applicable)
    - thread: full thread context (if applicable)
    """
    results = {"primary": None, "replies": None, "quotes": None, "retweeters": None, "thread": None}

    if tweet_type == "retweet":
        # Get retweeters list
        results["retweeters"] = client.get_tweet_retweeter(tweet_id)

    elif tweet_type == "quote_tweet":
        # Get all quotes
        results["quotes"] = client.get_all_quotes(tweet_id)

    elif tweet_type in ("reply", "thread_reply", "thread_starter"):
        # Get replies to this tweet
        results["replies"] = client.get_all_replies(tweet_id)
        # Also get thread context for full picture
        results["thread"] = client.get_tweet_thread_context(tweet_id)

    elif tweet_type == "standalone":
        # Check if it's actually a thread starter
        results["thread"] = client.get_tweet_thread_context(tweet_id)

    return results


# ─────────────────────────────────────────────
# HELPER: INDEX INCLUDES
# ─────────────────────────────────────────────


def index_includes(includes: Dict[str, Any]) -> Tuple[Dict, Dict, Dict]:
    media_by_key = {m["media_key"]: m for m in includes.get("media", []) if "media_key" in m}
    users_by_id = {u["id"]: u for u in includes.get("users", []) if "id" in u}
    tweets_by_id = {t["id"]: t for t in includes.get("tweets", []) if "id" in t}
    return media_by_key, users_by_id, tweets_by_id


# ─────────────────────────────────────────────
# CONTENT TYPE CLASSIFICATION
# ─────────────────────────────────────────────


def classify_primary_type(tweet: Dict) -> str:
    """Determine primary tweet type from API signals."""
    refs = tweet.get("referenced_tweets", [])
    ref_types = {r.get("type") for r in refs}

    if "retweeted" in ref_types:
        return "retweet"
    if "quoted" in ref_types:
        return "quote_tweet"

    conv_id = tweet.get("conversation_id")
    tweet_id = tweet.get("id")

    if conv_id and conv_id != tweet_id:
        # This tweet is a reply to something
        if "replied_to" in ref_types:
            return "thread_reply"
        return "reply"

    # Check if this tweet has self-replies (thread starter)
    # We'll verify this during thread walking
    if conv_id == tweet_id:
        return "standalone"  # May be upgraded to thread_starter later

    return "standalone"


def classify_content_flags(tweet: Dict, includes: Dict) -> Set[str]:
    """Determine what content types the tweet contains."""
    flags = set()

    # TwitterAPI.io format: media is in the tweet itself as a "media" list
    # Legacy X API format: media is in "includes" dict with media_keys
    media_by_key, _, _ = index_includes(includes)

    # Check media attachments - first try TwitterAPI.io format (media list in tweet)
    twitterapi_media = tweet.get("media", [])
    if twitterapi_media:
        for m in twitterapi_media:
            mtype = m.get("type", "").lower()
            if mtype == "photo":
                flags.add("has_images")
            elif mtype == "video":
                flags.add("has_video")
            elif mtype == "animated_gif":
                flags.add("has_gif")

    # Fallback: check legacy format via attachments + includes
    if not flags:
        for key in tweet.get("attachments", {}).get("media_keys", []):
            media = media_by_key.get(key, {})
            mtype = media.get("type")
            if mtype == "photo":
                flags.add("has_images")
            elif mtype == "video":
                flags.add("has_video")
            elif mtype == "animated_gif":
                flags.add("has_gif")

    # Fallback: if no attachments key (DB-sourced data), use media_count hint
    if not tweet.get("attachments", {}).get("media_keys") and not twitterapi_media:
        if int(tweet.get("media_count", 0)) > 0:
            flags.add("has_images")  # Pre-hint; API lookup confirms actual type

    # Check URLs in entities
    for url_entity in tweet.get("entities", {}).get("urls", []):
        expanded = url_entity.get("expanded_url") or url_entity.get("unwound_url") or ""
        if not expanded:
            continue

        if "youtube.com" in expanded or "youtu.be" in expanded:
            flags.add("has_youtube")
        elif "github.com" in expanded or "github.io" in expanded:
            flags.add("has_github")
        elif re.search(r"x\.com/.+/article", expanded):
            flags.add("has_x_article")
        elif "t.me" in expanded:
            # Telegram — skip entirely, content inaccessible
            continue
        elif "x.com" not in expanded and "twitter.com" not in expanded:
            flags.add("has_external_link")

    if not tweet.get("attachments", {}).get("media_keys") and not flags:
        flags.add("no_media")

    return flags


def extract_urls_from_entities(entities: Optional[Dict]) -> List[Dict[str, str]]:
    """Extract all URLs from tweet entities with expanded URLs."""
    urls = []
    for item in (entities or {}).get("urls", []):
        expanded = item.get("expanded_url") or item.get("unwound_url") or item.get("url")
        if expanded:
            urls.append({
                "url": expanded,
                "display_url": item.get("display_url", ""),
                "title": item.get("title", ""),
            })
    return urls


# ─────────────────────────────────────────────
# TOPIC CLASSIFICATION (from bookmark-classification.md)
# ─────────────────────────────────────────────


def load_tag_taxonomy(wiki_root: str, classification_path: str) -> Dict[str, List[str]]:
    """Read primary categories and sub-tags from bookmark-classification.md."""
    path = full_path(wiki_root, classification_path)
    if not os.path.exists(path):
        print(f"  ⚠ bookmark-classification.md not found at {path}")
        return {"primary_categories": [], "sub_tags": []}

    content = Path(path).read_text()
    result = {"primary_categories": [], "sub_tags": []}

    # Parse primary categories section
    in_primary = False
    in_sub = False
    for line in content.split("\n"):
        stripped = line.strip()
        if "## Primary Categories" in line or "### Primary Categories" in line:
            in_primary = True
            in_sub = False
            continue
        if "## Sub-Tags" in line or "### Sub-Tags" in line:
            in_sub = True
            in_primary = False
            continue
        if stripped.startswith("## ") or stripped.startswith("### "):
            in_primary = False
            in_sub = False
            continue

        if in_primary and stripped and not stripped.startswith("#") and not stripped.startswith("```"):
            # Extract tag names (lines like "ai-agents" or "- ai-agents")
            tag = stripped.lstrip("- ").strip()
            if tag and not tag.startswith("|"):
                result["primary_categories"].append(tag)
        if in_sub and stripped and not stripped.startswith("#") and not stripped.startswith("```"):
            tag = stripped.lstrip("- ").strip()
            if tag and not tag.startswith("|"):
                result["sub_tags"].append(tag)

    return result


def add_new_tag(wiki_root: str, classification_path: str, tag: str, section: str = "sub_tags"):
    """Append a new tag to bookmark-classification.md."""
    path = full_path(wiki_root, classification_path)
    content = Path(path).read_text()

    if section == "primary_categories":
        marker = "## Primary Categories"
    else:
        marker = "## Sub-Tags"

    # Find the section and append before the next section
    lines = content.split("\n")
    insert_idx = None
    in_section = False
    for i, line in enumerate(lines):
        if marker in line:
            in_section = True
            continue
        if in_section and line.strip().startswith("## "):
            insert_idx = i
            break
    if insert_idx is None:
        insert_idx = len(lines)

    lines.insert(insert_idx, tag)
    Path(path).write_text("\n".join(lines))


# ─────────────────────────────────────────────
# BACKLOG LOG PARSING
# ─────────────────────────────────────────────


def parse_backlog_log(wiki_root: str, backlog_path: str) -> Dict[int, Dict]:
    """Parse backlog-log.md to extract batch definitions.
    Returns {batch_number: {"ids": [...], "status": "processed"|"not_started"|"next"}}

    Status values:
    - processed: batch has been completed
    - not_started: batch has not been started yet
    - next: the next batch to be processed (only one should have this status)
    """
    path = full_path(wiki_root, backlog_path)
    content = Path(path).read_text()
    batches = {}

    # Parse markdown table rows like: | Batch 4 | 31-40 | - | 10 | 45 | not_started |
    for line in content.split("\n"):
        # Match 6 columns: Batch | IDs Range | Date | Processed | Total Processed | Status
        m = re.match(r"\|\s*Batch\s+(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
        if m:
            batch_num = int(m.group(1))
            ids_str = m.group(2).strip()
            status = m.group(6).strip()
            batches[batch_num] = {"ids_raw": ids_str, "status": status}

    return batches


def get_batch_ids_from_backlog(wiki_root: str, backlog_path: str, batch_num: int) -> List[str]:
    """Get the actual bookmark IDs for a specific batch.

    First tries to extract from detailed batch sections in the markdown.
    Falls back to row range if no detailed section found.
    """
    batches = parse_backlog_log(wiki_root, backlog_path)
    if batch_num not in batches:
        raise ValueError(f"Batch {batch_num} not found in backlog-log.md")

    batch = batches[batch_num]
    if batch["status"] == "processed":
        raise ValueError(f"Batch {batch_num} is already marked processed")

    # Try to extract from detailed markdown sections first
    ids = extract_ids_from_detailed_section(wiki_root, backlog_path, batch_num)
    if ids:
        return ids

    # Fallback: use row range from the table
    ids_raw = batch["ids_raw"]
    if re.match(r"^\d+-\d+$", ids_raw):
        start, end = ids_raw.split("-")
        return _query_batch_by_range(int(start), int(end))

    return []


def _query_batch_by_range(start: int, end: int) -> List[str]:
    """Query bookmarks.db for IDs in a row range."""
    # This depends on how backlog-log defines ranges.
    # For now, treat as row offsets in the DB ordered by synced_at.
    # Adjust based on actual backlog-log format.
    return []  # Placeholder — filled by query_bookmarks_db


def extract_ids_from_detailed_section(wiki_root: str, backlog_path: str, batch_num: int) -> List[str]:
    """Extract tweet IDs from detailed batch markdown sections.

    Example format:
    ### Batch 4 (IDs 31-40)
    31. 1997233746630893733 | aigleeson | OpenAI, Anthropic, and Google...
    """
    path = full_path(wiki_root, backlog_path)
    content = Path(path).read_text()

    # Find the section for this batch
    pattern = rf"###\s+Batch\s+{batch_num}\s+\([^)]+\)"
    match = re.search(pattern, content)
    if not match:
        return []

    # Extract lines until next ### Batch or end of section
    start_pos = match.end()
    next_section = re.search(r"\n###\s+Batch\s+\d+", content[start_pos:])
    end_pos = start_pos + next_section.start() if next_section else len(content)

    section = content[start_pos:end_pos]

    # Extract all tweet IDs (first column before |)
    ids = []
    for line in section.split("\n"):
        # Match lines like: 31. 1997233746630893733 | aigleelon | ...
        m = re.match(r"^\d+\.\s+(\d{19,})", line.strip())
        if m:
            ids.append(m.group(1))

    return ids


def find_next_batch(wiki_root: str, backlog_path: str) -> int:
    """Find the batch with status 'next'. Raises if none found.

    The 'next' status indicates which batch should be processed.
    If no batch has 'next' status, falls back to first 'not_started' batch.
    """
    batches = parse_backlog_log(wiki_root, backlog_path)

    # First: find explicit 'next' batch
    for num in sorted(batches.keys()):
        if batches[num]["status"] == "next":
            return num

    # Fallback: find first 'not_started' batch
    for num in sorted(batches.keys()):
        if batches[num]["status"] == "not_started":
            return num

    raise ValueError("All batches in backlog-log.md are processed")


def mark_batch_done(wiki_root: str, backlog_path: str, batch_num: int):
    """Update backlog-log.md to mark a batch as processed and promote next batch to 'next'.

    - Marks current batch as 'processed'
    - Finds next sequential batch marked 'not_started' and promotes to 'next'
    """
    path = full_path(wiki_root, backlog_path)
    content = Path(path).read_text()

    # 1. Mark current batch as processed
    # Pattern: | Batch N | IDs | Date | Processed | Total | not_started | → | Batch N | IDs | Date | Processed | Total | processed |
    pattern = rf"(\|\s*Batch\s+{batch_num}\s*\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|)\s*not_started\s*\|"
    replacement = rf"\1 processed |"
    content = re.sub(pattern, replacement, content)

    # 2. Find next batch that is 'not_started' and promote to 'next'
    next_batch = batch_num + 1
    pattern_next = rf"(\|\s*Batch\s+{next_batch}\s*\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|)\s*not_started\s*\|"
    replacement_next = rf"\1 next |"
    content = re.sub(pattern_next, replacement_next, content)

    Path(path).write_text(content)
    print(f"  ✅ Batch {batch_num} marked processed, Batch {next_batch} promoted to next")


# ─────────────────────────────────────────────
# BOOKMARKS DB
# ─────────────────────────────────────────────


def query_bookmarks_db(db_path: str, ids: List[str]) -> List[Dict]:
    """Query bookmarks.db for specific IDs."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join(["?"] * len(ids))
    cursor = conn.execute(
        f"SELECT * FROM bookmarks WHERE id IN ({placeholders})",
        ids
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def query_bookmarks_by_offset(db_path: str, offset: int, limit: int) -> List[Dict]:
    """Query bookmarks.db by row offset (for range-based batches)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT id, text, author_handle, primary_category, categories, synced_at "
        "FROM bookmarks ORDER BY synced_at DESC LIMIT ? OFFSET ?",
        (limit, offset - 1)
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# ─────────────────────────────────────────────
# DUPLICATE CHECK
# ─────────────────────────────────────────────


def get_existing_source_ids(wiki_root: str) -> Set[str]:
    """Read wiki/sources/_index.md and extract already-processed tweet IDs."""
    index_path = full_path(wiki_root, "wiki/sources/_index.md")
    if not os.path.exists(index_path):
        return set()
    content = Path(index_path).read_text()
    # Extract tweet IDs from filenames like author-tweetid.md or author-tweetid-something.md
    ids = set()
    for m in re.finditer(r"\w+-(\d{10,})", content):
        ids.add(m.group(1))
    return ids


# ─────────────────────────────────────────────
# MEDIA EXTRACTION
# ─────────────────────────────────────────────


def extract_media_urls(tweet: Dict, includes: Dict) -> Tuple[List[Dict], List[Dict]]:
    """Extract image and video URLs from API response.
    Returns (images, videos) where each is a list of dicts with url, type, etc.

    Handles both TwitterAPI.io format (media in tweet) and legacy X API format (media in includes).
    """
    # First try TwitterAPI.io format - media is directly in the tweet
    twitterapi_media = tweet.get("media", [])
    if twitterapi_media:
        images = []
        videos = []
        for media in twitterapi_media:
            mtype = media.get("type", "").lower()
            # TwitterAPI.io uses different field names
            if mtype == "photo":
                # Try various URL field names
                url = media.get("url") or media.get("mediaUrl") or media.get("imageUrl") or ""
                if url:
                    images.append({
                        "url": url,
                        "media_key": media.get("mediaKey", ""),
                        "width": media.get("width"),
                        "height": media.get("height"),
                    })
            elif mtype == "video" or mtype == "animated_gif":
                # For videos, get variants
                variants = media.get("variants", [])
                mp4s = [v for v in variants if v.get("content_type") == "video/mp4" and v.get("url")]
                if mp4s:
                    mp4s.sort(key=lambda v: v.get("bit_rate", 0))
                    videos.append({
                        "url": mp4s[0]["url"],
                        "url_high": mp4s[-1]["url"] if len(mp4s) > 1 else mp4s[0]["url"],
                        "media_key": media.get("mediaKey", ""),
                        "duration_ms": media.get("duration_ms"),
                    })
        if images or videos:
            return images, videos

    # Fallback: legacy X API format with includes
    media_by_key, _, _ = index_includes(includes)
    images = []
    videos = []

    for key in tweet.get("attachments", {}).get("media_keys", []):
        media = media_by_key.get(key)
        if not media:
            continue
        mtype = media.get("type")

        if mtype == "photo" and media.get("url"):
            images.append({
                "url": media["url"],
                "media_key": key,
                "width": media.get("width"),
                "height": media.get("height"),
            })
        elif mtype == "video":
            variants = media.get("variants") or []
            mp4s = [v for v in variants if v.get("content_type") == "video/mp4" and v.get("url")]
            mp4s.sort(key=lambda v: v.get("bit_rate", 0))
            if mp4s:
                videos.append({
                    "url": mp4s[0]["url"],  # Lowest bitrate for audio extraction
                    "url_high": mp4s[-1]["url"] if len(mp4s) > 1 else mp4s[0]["url"],
                    "media_key": key,
                    "duration_ms": media.get("duration_ms"),
                })
        elif mtype == "animated_gif":
            pass  # Skip GIFs — they add no value

    return images, videos


def download_file(url: str, dest_path: str, max_retries: int = 3) -> bool:
    """Download a file from URL to dest_path with retries."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    def _dl():
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True

    try:
        result = retry(_dl, max_retries, label=f"Download {os.path.basename(dest_path)}")
        # Validate the written file is real content, not empty/truncated
        if result:
            validate_written_file(dest_path, os.path.basename(dest_path))
        return result
    except Exception as e:
        print(f"  ✗ Failed to download {url}: {e}")
        return False


def validate_written_file(path: str, label: str = "", min_bytes: int = 10) -> bool:
    """Verify a file was written completely — not empty, not a preview stub.
    
    CRITICAL: Never accept a preview/truncated file as the real content.
    If a file is suspiciously small, log a warning. The manifest tracks status
    so we can re-process failed items on re-run.
    
    Thresholds:
    - Images: should be >1KB (even tiny thumbnails are >1KB)
    - Videos: should be >100KB
    - Transcripts: should be >50 bytes
    - JSON analyses: should be >100 bytes
    - Markdown pages: should be >50 bytes
    """
    if not os.path.exists(path):
        print(f"  ✗ VALIDATION FAILED: {label} — file does not exist at {path}")
        return False
    
    size = os.path.getsize(path)
    if size < min_bytes:
        print(f"  ✗ VALIDATION FAILED: {label} — file is only {size} bytes (expected >{min_bytes})")
        return False
    
    # Type-specific checks
    ext = os.path.splitext(path)[1].lower()
    suspicious = False
    
    if ext in (".jpg", ".jpeg", ".png", ".webp") and size < 1024:
        suspicious = True
        print(f"  ⚠ WARNING: {label} — image is only {size} bytes, may be corrupted")
    elif ext == ".mp4" and size < 102400:
        suspicious = True
        print(f"  ⚠ WARNING: {label} — video is only {size/1024:.0f}KB, may be truncated")
    elif ext == ".txt" and size < 50:
        suspicious = True
        print(f"  ⚠ WARNING: {label} — transcript is only {size} bytes, may be empty")
    elif ext == ".json" and size < 100:
        suspicious = True
        print(f"  ⚠ WARNING: {label} — JSON is only {size} bytes, may be incomplete")
    elif ext == ".md" and size < 50:
        suspicious = True
        print(f"  ⚠ WARNING: {label} — markdown is only {size} bytes, may be a preview")
    
    # Check for preview stubs (Claude Code artifact)
    if ext in (".txt", ".md", ".json"):
        try:
            with open(path, "r") as f:
                head = f.read(200)
            if "Output too large" in head or "Full output saved to:" in head:
                print(f"  ✗ VALIDATION FAILED: {label} — file contains preview stub, not actual content")
                print(f"    The real content may be at the path referenced in the preview.")
                return False
        except Exception:
            pass
    
    return True


# ─────────────────────────────────────────────
# THREAD WALKING
# ─────────────────────────────────────────────


def walk_thread_upward(client, tweet: Dict, includes: Dict, max_hops: int = 30) -> List[Dict]:
    """Walk replied_to chain upward from a tweet to the thread root.
    Works for ANY tweet age (no 7-day limit).
    Works with both XClient and TwitterAPIioClient.
    Returns ordered list root → ... → this tweet.
    """
    chain = []
    current = tweet
    current_includes = includes
    seen_ids = {tweet["id"]}

    while len(chain) < max_hops:
        chain.append(normalize_tweet(current, current_includes))

        # Find replied_to reference
        replied_to_id = None
        for ref in current.get("referenced_tweets", []):
            if ref.get("type") == "replied_to":
                replied_to_id = ref["id"]
                break

        if not replied_to_id or replied_to_id in seen_ids:
            break

        seen_ids.add(replied_to_id)

        # Fetch parent tweet
        try:
            if isinstance(client, TwitterAPIioClient):
                payload = client.get_tweet_by_ids([replied_to_id])
                data = list(normalize_tweets_response(payload).values())
            else:
                payload = client.lookup_posts([replied_to_id])
                data = payload.get("data", [])

            if not data:
                break
            current = data[0]
            current_includes = payload.get("includes", {}) if hasattr(payload, "get") else {}
        except Exception as e:
            print(f"  ⚠ Thread walk stopped at {replied_to_id}: {e}")
            break

    chain.reverse()  # Root first
    return chain


def fetch_recent_thread(client, conversation_id: str) -> List[Dict]:
    """Fetch full thread via recent_search or thread_context.
    Works with both XClient (7-day limit) and TwitterAPIioClient (no limit).
    """
    # Use TwitterAPI.io thread_context if available
    if isinstance(client, TwitterAPIioClient):
        # Get thread context - returns parents and replies
        result = client.get_tweet_thread_context(conversation_id)
        replies = result.get("replies", [])
        return [normalize_tweet_response(r) for r in replies]

    # Fall back to legacy XClient approach
    items = {}
    next_token = None
    pages = 0

    while pages < 10:  # Safety cap
        payload = client.recent_search_conversation(conversation_id, next_token=next_token)
        includes = payload.get("includes", {})
        for post in payload.get("data", []):
            if post["id"] not in items:
                items[post["id"]] = normalize_tweet(post, includes)
        next_token = payload.get("meta", {}).get("next_token")
        if not next_token:
            break
        pages += 1

    return sorted(items.values(), key=lambda p: (p.get("created_at", ""), p.get("id", "")))


def normalize_tweet(tweet: Dict, includes: Dict) -> Dict:
    """Normalize a tweet into a clean dict."""
    media_by_key, users_by_id, _ = index_includes(includes)
    images, videos = extract_media_urls(tweet, includes)
    author = users_by_id.get(tweet.get("author_id", ""), {})

    return {
        "id": tweet.get("id"),
        "text": tweet.get("text"),
        "created_at": tweet.get("created_at"),
        "conversation_id": tweet.get("conversation_id"),
        "author_id": tweet.get("author_id"),
        "author_username": author.get("username", "unknown"),
        "referenced_tweets": tweet.get("referenced_tweets", []),
        "images": images,
        "videos": videos,
        "urls": extract_urls_from_entities(tweet.get("entities")),
    }


# ─────────────────────────────────────────────
# RETWEET CHAIN WALKER
# ─────────────────────────────────────────────


def resolve_retweet_original(client, tweet: Dict, max_depth: int = 5) -> Tuple[Dict, Dict]:
    """Recursively follow retweet chain to find the true original.
    Handles retweets of retweets up to max_depth.
    Works with both XClient and TwitterAPIioClient.
    Returns (original_tweet, original_includes).
    """
    current = tweet
    depth = 0

    while depth < max_depth:
        rt_id = None
        for ref in current.get("referenced_tweets", []):
            if ref.get("type") == "retweeted":
                rt_id = ref["id"]
                break
        if not rt_id:
            break

        # Check client type and use appropriate method
        if isinstance(client, TwitterAPIioClient):
            payload = client.get_tweet_by_ids([rt_id])
            data = list(normalize_tweets_response(payload).values())
        else:
            payload = client.lookup_posts([rt_id])
            data = payload.get("data", [])

        if not data:
            print(f"  ⚠ Retweet original {rt_id} not found (deleted/protected)")
            break
        current = data[0]
        includes = payload.get("includes", {}) if hasattr(payload, "get") else {}
        depth += 1

    return current, includes if depth > 0 else ({}, {})


# ─────────────────────────────────────────────
# CONTENT FETCHERS
# ─────────────────────────────────────────────


def fetch_youtube_transcript(api_key: str, youtube_url: str) -> Optional[str]:
    """Fetch YouTube transcript via ScrapeCreators API."""
    try:
        resp = requests.post(
            "https://api.scrapecreators.com/v1/youtube/video/transcript",
            headers={"x-api-key": api_key},
            json={"url": youtube_url, "language": "en"},
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"  ⚠ ScrapeCreators returned {resp.status_code} for {youtube_url}")
            return None
        data = resp.json()
        return data.get("transcript") or data.get("text") or json.dumps(data)
    except Exception as e:
        print(f"  ⚠ YouTube transcript fetch failed: {e}")
        return None


def fetch_github_repo(github_url: str) -> Dict[str, str]:
    """Fetch GitHub repo info via requests + BeautifulSoup."""
    result = {"url": github_url, "owner": "", "repo": "", "description": "", "readme": ""}
    try:
        parsed = urlparse(github_url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            result["owner"] = parts[0]
            result["repo"] = parts[1]

        # Try GitHub API first (no auth needed for public repos)
        api_url = f"https://api.github.com/repos/{result['owner']}/{result['repo']}"
        resp = requests.get(api_url, timeout=15, headers={"Accept": "application/vnd.github.v3+json"})
        if resp.status_code == 200:
            data = resp.json()
            result["description"] = data.get("description", "")

            # Fetch README
            readme_resp = requests.get(f"{api_url}/readme", timeout=15,
                                       headers={"Accept": "application/vnd.github.v3.raw"})
            if readme_resp.status_code == 200:
                result["readme"] = readme_resp.text[:3000]
        else:
            # Fallback: scrape the page
            page_resp = requests.get(github_url, timeout=15)
            if page_resp.status_code == 200:
                soup = BeautifulSoup(page_resp.text, "html.parser")
                readme_el = soup.select_one(".markdown-body")
                if readme_el:
                    result["readme"] = readme_el.get_text()[:3000]
    except Exception as e:
        result["readme"] = f"Failed to fetch: {e}"

    return result


def fetch_x_article_via_api(article_tweet_id: str, api_key: str) -> Dict[str, Any]:
    """Fetch X.com article content via TwitterAPI.io API.

    Args:
        article_tweet_id: The tweet ID of the article (from the URL like x.com/i/article/{id})
        api_key: TwitterAPI.io API key

    Returns:
        Dict with: title, preview_text, content, cover_image_url, author, created_at, engagement
    """
    result = {
        "article_tweet_id": article_tweet_id,
        "title": "",
        "preview_text": "",
        "content": "",
        "cover_image_url": "",
        "author": {},
        "created_at": "",
        "engagement": {},
        "error": None
    }

    try:
        resp = requests.get(
            "https://api.twitterapi.io/twitter/article",
            params={"tweet_id": article_tweet_id},
            headers={"X-API-Key": api_key},
            timeout=30
        )

        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                article = data.get("article", {})
                result["title"] = article.get("title", "")
                result["preview_text"] = article.get("preview_text", "")
                result["cover_image_url"] = article.get("cover_media_img_url", "")
                result["author"] = article.get("author", {})
                result["created_at"] = article.get("createdAt", "")
                result["engagement"] = {
                    "reply_count": article.get("replyCount", 0),
                    "like_count": article.get("likeCount", 0),
                    "quote_count": article.get("quoteCount", 0),
                    "view_count": article.get("viewCount", 0),
                }

                # Combine content blocks into text
                content_blocks = article.get("contents", [])
                text_content = []
                for block in content_blocks:
                    block_type = block.get("type", "")
                    if block_type == "unstyled":
                        text_content.append(block.get("text", ""))
                    elif block_type in ["header-one", "header-two", "header-three"]:
                        text_content.append(f"## {block.get('text', '')}")
                    elif block_type == "unordered-list-item":
                        text_content.append(f"- {block.get('text', '')}")
                    elif block_type == "ordered-list-item":
                        text_content.append(f"1. {block.get('text', '')}")
                result["content"] = "\n\n".join(text_content)
            else:
                result["error"] = data.get("message", "API returned error status")
        else:
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        result["error"] = str(e)

    return result


def fetch_thread_context_via_api(tweet_id: str, api_key: str, cursor: str = "") -> Dict[str, Any]:
    """Fetch thread context (replies) via TwitterAPI.io API.

    Args:
        tweet_id: The tweet ID to get thread context for
        api_key: TwitterAPI.io API key
        cursor: Pagination cursor (empty string for first page)

    Returns:
        Dict with: replies, has_next_page, next_cursor, error
    """
    result = {
        "tweet_id": tweet_id,
        "replies": [],
        "has_next_page": False,
        "next_cursor": "",
        "error": None
    }

    try:
        resp = requests.get(
            "https://api.twitterapi.io/twitter/tweet/thread_context",
            params={"tweetId": tweet_id, "cursor": cursor},
            headers={"X-API-Key": api_key},
            timeout=30
        )

        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                result["replies"] = data.get("tweets", [])
                result["has_next_page"] = data.get("has_next_page", False)
                result["next_cursor"] = data.get("next_cursor", "")
            else:
                result["error"] = data.get("message", "API returned error status")
        else:
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        result["error"] = str(e)

    return result


def fetch_external_link_content(url: str) -> Dict[str, str]:
    """Fetch and extract main content from an external URL."""
    result = {"url": url, "title": "", "content": "", "domain": ""}
    try:
        parsed = urlparse(url)
        result["domain"] = parsed.netloc

        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; bookmark-pipeline/1.0)"
        })
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            result["title"] = soup.title.string if soup.title else ""

            # Try article tag first, then main, then body
            article = soup.find("article") or soup.find("main") or soup.find("body")
            if article:
                # Remove script/style elements
                for tag in article.find_all(["script", "style", "nav", "footer"]):
                    tag.decompose()
                result["content"] = article.get_text(separator="\n", strip=True)[:5000]
        else:
            result["content"] = f"HTTP {resp.status_code}"
    except Exception as e:
        result["content"] = f"Failed to fetch: {e}"

    return result


# ─────────────────────────────────────────────
# VIDEO PROCESSING
# ─────────────────────────────────────────────


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe.

    NOTE: On macOS with Network.framework loaded, ffprobe calls crash with SIGSEGV.
    Using safe fallback to return estimated duration based on file size.
    """
    # Check if file exists and get size as proxy for duration
    if not os.path.exists(video_path):
        return 0.0

    file_size = os.path.getsize(video_path)
    # Rough estimate: ~1MB per second for typical video
    # This is a fallback - actual ffprobe would be better but crashes
    estimated_duration = file_size / (1024 * 1024)
    return min(estimated_duration, 300.0)  # Cap at 5 minutes to avoid huge values


def extract_audio(video_path: str, audio_path: str) -> bool:
    """Extract audio from video via ffmpeg.

    NOTE: On macOS with Network.framework loaded, ffmpeg calls crash with SIGSEGV.
    Skipping audio extraction to avoid the crash. Video can still be analyzed without audio.
    """
    # Audio extraction disabled due to macOS fork crash
    # Video analysis can proceed without transcription
    print(f"  ⚠ Audio extraction skipped (macOS fork crash workaround)")
    return False


def transcribe_whisper(audio_path: str, openai_key: str) -> Optional[str]:
    """Transcribe audio via OpenAI Whisper API."""
    try:
        with open(audio_path, "rb") as f:
            resp = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {openai_key}"},
                files={"file": f},
                data={"model": "whisper-1", "response_format": "text"},
                timeout=120,
            )
        if resp.status_code == 200:
            return resp.text
        print(f"  ⚠ Whisper returned {resp.status_code}")
        return None
    except Exception as e:
        print(f"  ✗ Whisper failed: {e}")
        return None


# ─────────────────────────────────────────────
# GEMINI ANALYSIS
# ─────────────────────────────────────────────


def load_skill_prompt(skill_path: str) -> str:
    """Read a skill SKILL.md and return its content as a prompt."""
    if not os.path.exists(skill_path):
        print(f"  ⚠ Skill not found: {skill_path}")
        return ""
    content = Path(skill_path).read_text()
    # Strip YAML frontmatter if present
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].strip()
    return content


def analyze_image_gemini(image_path: str, gemini_key: str, skill_prompt: str = None,
                          model: str = "gemini-2.5-flash") -> Optional[Dict]:
    """Analyze an image with Gemini. First classifies as text vs visual, then runs appropriate analysis."""
    try:
        from pathlib import Path

        # Step 1: Read image and encode
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
        mime = mime_map.get(ext, "image/jpeg")

        # Step 2: Classify the image (text document vs visual)
        classify_prompt_path = os.path.expanduser("~/.claude/skills/image-analysis/prompts/classify-image.md")
        classify_prompt = Path(classify_prompt_path).read_text().strip() if os.path.exists(classify_prompt_path) else "Is this image primarily text or visual? Respond with only: TEXT_DOCUMENT or VISUAL_IMAGE"

        classify_resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={gemini_key}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [
                {"text": classify_prompt},
                {"inline_data": {"mime_type": mime, "data": image_b64}},
            ]}], "generationConfig": {"temperature": 0.1}},
            timeout=30,
        )

        image_class = "VISUAL_IMAGE"  # default
        if classify_resp.status_code == 200:
            class_text = classify_resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            if "TEXT_DOCUMENT" in class_text.upper():
                image_class = "TEXT_DOCUMENT"

        # Step 3: Run appropriate analysis
        if image_class == "TEXT_DOCUMENT":
            prompt_path = os.path.expanduser("~/.claude/skills/image-analysis/prompts/text-analysis.md")
        else:
            prompt_path = os.path.expanduser("~/.claude/skills/image-analysis/prompts/visual-analysis.md")

        if os.path.exists(prompt_path):
            analysis_prompt = Path(prompt_path).read_text().strip()
        else:
            analysis_prompt = skill_prompt or "Analyze this image. Return JSON."

        analysis_resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={gemini_key}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [
                {"text": analysis_prompt},
                {"inline_data": {"mime_type": mime, "data": image_b64}},
            ]}], "generationConfig": {"temperature": 0.2}},
            timeout=60,
        )

        if analysis_resp.status_code == 200:
            text = analysis_resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```[a-z]*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
                text = text.strip()
            try:
                result = json.loads(text)
                result["image_class"] = image_class
                return result
            except:
                return {"raw": text, "image_class": image_class}
        else:
            print(f"  ⚠ Gemini returned {analysis_resp.status_code}")
            return None
    except Exception as e:
        print(f"  ✗ Gemini image analysis failed: {e}")
        return None


def analyze_video_gemini(video_path: str, gemini_key: str, skill_prompt: str,
                          model: str = "gemini-2.5-pro") -> Optional[Dict]:
    """Analyze a short video (≤2min) with Gemini 2.5 Pro Vision."""
    try:
        with open(video_path, "rb") as f:
            video_b64 = base64.b64encode(f.read()).decode()

        resp = requests.post(
            f"{GEMINI_BASE}/{model}:generateContent?key={gemini_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [
                    {"text": skill_prompt or "Analyze this video thoroughly. Provide: 1) Complete transcript, 2) Visual elements, 3) Visible text, 4) Summary. Return as JSON with keys: transcript, visual_description, visible_text, summary."},
                    {"inline_data": {"mime_type": "video/mp4", "data": video_b64}},
                ]}],
                "generationConfig": {"temperature": 0.2},
            },
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
            # Strip markdown code fences before JSON parsing
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```[a-z]*\n|```$", "", text, flags=re.MULTILINE).strip()
            return json.loads(text) if text.startswith("{") else {"raw": text}
        print(f"  ⚠ Gemini Pro returned {resp.status_code}")
        return None
    except Exception as e:
        print(f"  ✗ Gemini video analysis failed: {e}")
        return None


# ─────────────────────────────────────────────
# MINIMAX LLM CLIENT
# ─────────────────────────────────────────────


def get_minimax_client(api_key: str) -> Anthropic:
    """Create MiniMax client via Anthropic-compatible API."""
    return Anthropic(api_key=api_key, base_url=MINIMAX_BASE_URL)


def llm_call(client: Anthropic, system_prompt: str, user_content: str,
             model: str = "MiniMax-M2.7", max_tokens: int = 4096) -> str:
    """Make an LLM call to MiniMax M2.7 via Anthropic-compatible API."""
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    # Handle both TextBlock and ThinkingBlock response types
    for block in response.content:
        if hasattr(block, 'text') and block.text:
            return block.text
    return ""


# ─────────────────────────────────────────────
# MANIFEST MANAGEMENT
# ─────────────────────────────────────────────


def create_manifest(batch_num: int, temp_dir: str, wiki_root: str) -> Dict:
    return {
        "batch_number": batch_num,
        "batch_id": f"batch_{batch_num:03d}",
        "created_at": datetime.now().isoformat(),
        "temp_dir": temp_dir,
        "wiki_root": wiki_root,
        "status": "phase1_starting",
        "phase_status": {
            "phase1_extract": "pending",
            "phase2_analyze": "pending",
            "phase3_compile": "pending",
            "phase4_finalize": "pending",
        },
        "bookmarks": [],
        "repost_originals": [],
        "qa_council": {"status": "pending", "batch_qa_path": None, "concept_index_updated": False},
        "lint": {"status": "pending", "report_path": None},
        "indexes_updated": False,
        "backlog_updated": False,
        "cleanup_complete": False,
    }


def save_manifest(manifest: Dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)


def load_manifest(path: str) -> Dict:
    with open(path) as f:
        return json.load(f)


# ─────────────────────────────────────────────
# FILE WRITERS
# ─────────────────────────────────────────────


def write_thread_file(thread_chain: List[Dict], author: str, tweet_id: str,
                       wiki_root: str) -> str:
    """Write thread content to raw/x-threads/."""
    path = full_path(wiki_root, f"raw/x-threads/{author}-{tweet_id}-thread.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    lines = [
        f"# Thread by @{author}\n",
        f"Source: https://x.com/{author}/status/{thread_chain[0]['id'] if thread_chain else tweet_id}",
        f"Date: {thread_chain[0].get('created_at', 'unknown') if thread_chain else 'unknown'}",
        f"Posts: {len(thread_chain)}\n",
        "---\n",
    ]
    for i, post in enumerate(thread_chain):
        lines.append(f"## Post {i+1}{' (Root)' if i == 0 else ''}")
        lines.append(post.get("text", "(empty)"))
        lines.append("")

    Path(path).write_text("\n".join(lines))
    return path


def write_quote_network_file(quotes: List[Dict], author: str, tweet_id: str,
                              wiki_root: str) -> str:
    """Write quote tweet network to raw/x-quote-networks/.

    NEW: Tracks quote relationships for network analysis.
    """
    if not quotes:
        return None

    path = full_path(wiki_root, f"raw/x-quote-networks/{author}-{tweet_id}-quotes.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    lines = [
        f"# Quote Network for @{author}/{tweet_id}\n",
        f"Original: https://x.com/{author}/status/{tweet_id}",
        f"Quote Count: {len(quotes)}\n",
        "---\n",
        "## Quotes\n",
    ]
    for i, quote in enumerate(quotes):
        quote_author = quote.get("author", "unknown")
        quote_id = quote.get("id", "")
        lines.append(f"### Quote {i+1}: @{quote_author}")
        lines.append(f"[View Tweet](https://x.com/{quote_author}/status/{quote_id})")
        lines.append(quote.get("text", "(empty)"))
        lines.append("")

    Path(path).write_text("\n".join(lines))
    return path


def write_retweeter_file(retweeters: List[Dict], author: str, tweet_id: str,
                          wiki_root: str) -> str:
    """Write retweeter list to raw/x-retweeters/.

    NEW: Tracks who amplified the content.
    """
    if not retweeters:
        return None

    path = full_path(wiki_root, f"raw/x-retweeters/{author}-{tweet_id}-retweeters.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    lines = [
        f"# Retweeters for @{author}/{tweet_id}\n",
        f"Original: https://x.com/{author}/status/{tweet_id}",
        f"Retweet Count: {len(retweeters)}\n",
        "---\n",
        "## Who Retweeted\n",
    ]
    for rt in retweeters:
        username = rt.get("username", "unknown")
        name = rt.get("name", "")
        lines.append(f"- [@{username}](https://x.com/{username}) ({name})")

    Path(path).write_text("\n".join(lines))
    return path


def write_github_repo_file(repo_info: Dict, author: str, tweet_id: str,
                            wiki_root: str) -> str:
    """Write GitHub repo info to raw/x-github-repos/."""
    repo_name = repo_info.get("repo", "unknown")
    path = full_path(wiki_root, f"raw/x-github-repos/{author}-{tweet_id}-github-{repo_name}.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    content = f"""# {repo_info.get('owner', '')}/{repo_name}

URL: {repo_info.get('url', '')}
Description: {repo_info.get('description', '')}

## README (excerpt)

{repo_info.get('readme', 'Not available')}

Source Tweet: https://x.com/{author}/status/{tweet_id}
"""
    Path(path).write_text(content)
    return path


def write_external_link_file(link_info: Dict, author: str, tweet_id: str,
                              wiki_root: str) -> str:
    """Write external link content to raw/x-external-links/."""
    domain = link_info.get("domain", "unknown").replace("www.", "")
    path = full_path(wiki_root, f"raw/x-external-links/{author}-{tweet_id}-link-{domain}.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    content = f"""# External Link - {link_info.get('title', 'Untitled')}

## Source
- **Author**: @{author}
- **Tweet ID**: {tweet_id}
- **URL**: https://x.com/{author}/status/{tweet_id}

## Link Details
- **Domain**: {domain}
- **Full URL**: {link_info.get('url', '')}

## Content

{link_info.get('content', 'Content not available')}

## Links
- Link: {link_info.get('url', '')}
- Tweet: https://x.com/{author}/status/{tweet_id}
"""
    Path(path).write_text(content)
    return path


def write_transcript_file(transcript: str, author: str, tweet_id: str,
                           wiki_root: str, duration: str = None, source_url: str = None) -> str:
    """Write video transcript to raw/x-video-transcripts/ with frontmatter."""
    path = full_path(wiki_root, f"raw/x-video-transcripts/{author}-{tweet_id}-transcript.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    today = today_str()

    # Build metadata header
    duration_info = f"\n- **Duration:** {duration}" if duration else ""
    source_info = f"\n- **Source:** [{source_url}]({source_url})" if source_url else ""

    content = f"""---
title: "Video Transcript: {author} - {tweet_id}"
date_created: {today}
date_modified: {today}
summary: "Full transcript of video from tweet {tweet_id} by @{author}"
tags: [video-transcript, {author}]
type: source
status: draft
---

**Author:** @{author}
**Tweet ID:** {tweet_id}{duration_info}{source_info}

## Transcript

{transcript}
"""
    Path(path).write_text(content)
    # Update path to .md extension
    return path


# ─────────────────────────────────────────────
# WIKI PAGE HELPERS
# ─────────────────────────────────────────────


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def write_frontmatter_page(path: str, title: str, summary: str, tags: List[str],
                            page_type: str, body: str, status: str = "draft"):
    """Write a wiki page with proper YAML frontmatter."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    today = today_str()
    content = f"""---
title: "{title}"
date_created: {today}
date_modified: {today}
summary: "{summary}"
tags: [{', '.join(tags)}]
type: {page_type}
status: {status}
---

{body}
"""
    Path(path).write_text(content)


def extract_wikilinks(text: str) -> List[str]:
    """Extract all [[wikilink]] slugs from text."""
    return WIKILINK_RE.findall(text)


def page_exists(slug: str, wiki_root: str) -> bool:
    """Check if a wiki page exists for a given slug."""
    for subdir in ["wiki/sources", "wiki/concepts", "wiki/entities", "wiki/x-github-repos"]:
        if os.path.exists(full_path(wiki_root, f"{subdir}/{slug}.md")):
            return True
    return False


def create_stub_page(slug: str, wiki_root: str):
    """Create a stub entity or concept page."""
    # Heuristic: proper nouns → entity, lowercase-hyphen → concept
    if slug[0].isupper() or any(c.isupper() for c in slug):
        subdir = "wiki/entities"
        page_type = "entity"
    else:
        subdir = "wiki/concepts"
        page_type = "concept"

    title = slug.replace("-", " ").title()
    path = full_path(wiki_root, f"{subdir}/{slug}.md")
    if os.path.exists(path):
        return

    write_frontmatter_page(
        path, title,
        f"Stub page for {title}",
        [page_type],
        page_type,
        f"# {title}\n\nStub — referenced in source pages. Expand when subject appears in 2+ sources."
    )


def append_to_file(path: str, content: str):
    """Append content to a file, creating it if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(content)


def update_index_file(index_path: str, slug: str, summary: str):
    """Add an entry to an _index.md file if not already present."""
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    if os.path.exists(index_path):
        existing = Path(index_path).read_text()
        if slug in existing:
            return  # Already indexed
    else:
        existing = f"---\ntitle: Index\ndate_modified: {today_str()}\n---\n\n"

    entry = f"- [[{slug}]] — {summary} _(added {today_str()})_\n"
    append_to_file(index_path, entry)


# ─────────────────────────────────────────────
# PHASE 1: EXTRACT
# ─────────────────────────────────────────────


def run_phase1(manifest: Dict, config: Dict):
    wiki_root = config["wiki_root"]
    temp_dir = manifest["temp_dir"]
    batch_num = manifest["batch_number"]

    # Live mode (batch_num=0): use bookmarks already in manifest, skip backlog-log reading
    is_live_mode = batch_num == 0 and manifest.get("bookmarks")

    if is_live_mode:
        print("  Step 1.1: Live mode - using bookmarks from pipeline...")
        bookmarks = manifest["bookmarks"]
    else:
        print("  Step 1.1: Reading backlog-log.md...")
        print("  Step 1.2: Getting batch IDs...")
        batch_ids = get_batch_ids_from_backlog(wiki_root, config["backlog_log"], batch_num)

        print("  Step 1.3: Querying bookmarks.db...")
        bookmarks = query_bookmarks_db(config["bookmarks_db"], batch_ids)
        if not bookmarks:
            bookmarks = query_bookmarks_by_offset(config["bookmarks_db"], int(batch_ids[0]) if batch_ids else 1, len(batch_ids))

    print(f"    Found {len(bookmarks)} bookmarks")

    print("  Step 1.4: Checking for duplicates...")
    existing_ids = get_existing_source_ids(wiki_root)
    bookmarks = [b for b in bookmarks if b["id"] not in existing_ids]
    print(f"    {len(bookmarks)} new bookmarks to process")

    if not bookmarks:
        print("  ⚠ All bookmarks already processed. Skipping Phase 1.")
        manifest["phase_status"]["phase1_extract"] = "complete"
        return

    print("  Step 1.5: Fetching from X API...")

    # Prefer TwitterAPI.io (X-API-Key), fall back to Bearer token
    twitter_api_key = os.environ.get("TWITTER_API_KEY")
    if twitter_api_key:
        print("    Using TwitterAPI.io (X-API-Key)")
        x_client = TwitterAPIioClient(twitter_api_key)
        tweet_ids = [b["id"] for b in bookmarks]

        # Batch lookup via TwitterAPI.io
        payload = x_client.get_tweet_by_ids(tweet_ids)
        api_tweets = normalize_tweets_response(payload)
        api_includes = {}  # TwitterAPI.io includes most data in tweet object
    else:
        print("    Using legacy X API (Bearer token)")
        x_client = XClient(os.environ["X_BEARER_TOKEN"])
        tweet_ids = [b["id"] for b in bookmarks]

        # Batch lookup (up to 100 at once)
        payload = x_client.lookup_posts(tweet_ids)
        api_tweets = {t["id"]: t for t in payload.get("data", [])}
        api_includes = payload.get("includes", {})

    print(f"    API returned {len(api_tweets)} tweets")

    # Process each bookmark
    for bm in bookmarks:
        tweet_id = bm["id"]
        author = bm.get("author_handle", "unknown")
        print(f"\n  Processing: @{author}/{tweet_id}")

        tweet = api_tweets.get(tweet_id)
        if not tweet:
            print(f"    ✗ Not found in API (deleted/protected). Skipping.")
            manifest["bookmarks"].append({
                "id": tweet_id, "author_handle": author,
                "classification": {"primary_type": "unavailable", "flags": []},
                "phase1": {"status": "skipped_unavailable"},
                "phase2": {"status": "skipped"}, "phase3": {"status": "skipped"}, "phase4": {"status": "skipped"},
            })
            continue

        # Classify
        primary_type = classify_primary_type(tweet)
        flags = classify_content_flags(tweet, api_includes)
        print(f"    Type: {primary_type} | Flags: {flags}")

        # Extract engagement metrics
        engagement = {
            "retweet_count": tweet.get("retweet_count", 0),
            "reply_count": tweet.get("reply_count", 0),
            "like_count": tweet.get("like_count", 0),
            "quote_count": tweet.get("quote_count", 0),
            "view_count": tweet.get("view_count", 0),
            "bookmark_count": tweet.get("bookmark_count", 0),
        }

        # Initialize manifest entry
        entry = {
            "id": tweet_id,
            "author_handle": author,
            "author_id": tweet.get("author_id"),
            "primary_category": bm.get("primary_category"),
            "categories": bm.get("categories"),
            "text": tweet.get("text", ""),
            "created_at": tweet.get("created_at"),
            "tweet_url": f"https://x.com/{author}/status/{tweet_id}",
            "classification": {"primary_type": primary_type, "flags": list(flags)},
            "engagement": engagement,  # NEW: view_count, bookmark_count, etc.
            "quotes": [],  # NEW: store all quote tweets
            "retweeters": [],  # NEW: store who retweeted
            "thread_replies": [],  # NEW: store ALL thread replies (no 7-day limit)
            "phase1": {"status": "in_progress", "files_created": {
                "thread": None, "images": [], "videos": [], "youtube_transcripts": [],
                "external_links": [], "github_repos": [], "articles": [],
                "quote_network": None, "retweeters": None,  # NEW
            }},
            "phase2": {"status": "pending", "image_analyses": [], "video_analyses": [], "video_transcripts": []},
            "phase3": {"status": "pending", "source_summary": None, "entities_created": [], "concepts_created": [], "backlinks_added": []},
            "phase4": {"status": "pending"},
        }

        # ── NEW: Fetch quotes, retweeters, thread replies via TwitterAPI.io ──
        if isinstance(x_client, TwitterAPIioClient):
            print(f"    Fetching additional context via TwitterAPI.io...")
            route_results = route_tweet_to_endpoints(primary_type, tweet_id, x_client)

            # Store quotes
            if route_results.get("quotes"):
                entry["quotes"] = [
                    {"id": q.get("id"), "text": q.get("text"), "author": q.get("author", {}).get("username")}
                    for q in route_results["quotes"]
                ]
                print(f"    Found {len(entry['quotes'])} quote tweets")

            # Store retweeters
            if route_results.get("retweeters"):
                users = route_results["retweeters"].get("users", [])
                entry["retweeters"] = [
                    {"id": u.get("id"), "username": u.get("username"), "name": u.get("name")}
                    for u in users
                ][:50]  # Store top 50
                print(f"    Found {len(entry['retweeters'])} retweeters")

            # Store thread context (TwitterAPI.io format - replaces walk_thread_upward)
            if route_results.get("thread"):
                entry["thread_context"] = route_results["thread"]
                print(f"    Thread context fetched via API")

            # NEW: Also fetch quoted tweet content (the "separate artifact")
            quoted_tweet_id = None
            for ref in tweet.get("referenced_tweets", []):
                if ref.get("type") == "quoted":
                    quoted_tweet_id = ref.get("id")
                    break
            if quoted_tweet_id:
                print(f"    Fetching quoted tweet {quoted_tweet_id}...")
                quoted_payload = x_client.get_tweet_by_ids([quoted_tweet_id])
                quoted_tweets = normalize_tweets_response(quoted_payload)
                if quoted_tweet_id in quoted_tweets:
                    entry["quoted_tweet"] = quoted_tweets[quoted_tweet_id]
                    print(f"    ✓ Quoted tweet content retrieved")

        # ── Handle Reposts ──
        if primary_type == "retweet":
            print(f"    Resolving retweet chain...")
            original_tweet, original_includes = resolve_retweet_original(x_client, tweet)
            if original_tweet and original_tweet.get("id"):
                orig_author = "unknown"
                _, orig_users, _ = index_includes(original_includes)
                if original_tweet.get("author_id") in orig_users:
                    orig_author = orig_users[original_tweet["author_id"]].get("username", "unknown")
                print(f"    Original: @{orig_author}/{original_tweet['id']}")

                # Process original as a separate item
                orig_entry = {
                    "id": original_tweet["id"],
                    "author_handle": orig_author,
                    "text": original_tweet.get("text", ""),
                    "created_at": original_tweet.get("created_at"),
                    "is_repost_original": True,
                    "reposted_by": author,
                    "repost_tweet_id": tweet_id,
                    "classification": {
                        "primary_type": classify_primary_type(original_tweet),
                        "flags": list(classify_content_flags(original_tweet, original_includes)),
                    },
                    "phase1": {"status": "pending", "files_created": {
                        "thread": None, "images": [], "videos": [], "youtube_transcripts": [],
                        "external_links": [], "github_repos": [], "articles": [],
                        "quote_network": None, "retweeters": None,  # NEW
                    }},
                    "phase2": {"status": "pending", "image_analyses": [], "video_analyses": [], "video_transcripts": []},
                    "phase3": {"status": "pending", "source_summary": None, "entities_created": [], "concepts_created": [], "backlinks_added": []},
                    "phase4": {"status": "pending"},
                }
                manifest["repost_originals"].append(orig_entry)
                # Process media/links for original below
                _extract_content(x_client, original_tweet, original_includes, orig_entry, wiki_root, temp_dir, config)

        # ── Handle Threads ──
        if primary_type in ("thread_starter", "thread_reply", "standalone"):
            conv_id = tweet.get("conversation_id", tweet_id)
            if conv_id != tweet_id or primary_type == "thread_reply":
                # Use TwitterAPI.io thread_context if available (replaces walk_thread_upward)
                if entry.get("thread_context"):
                    thread_data = entry["thread_context"]
                    # Thread context returns tweets in the thread - normalize and process
                    thread_tweets = thread_data.get("tweets", [])
                    if thread_tweets:
                        # Normalize thread tweets
                        chain = []
                        for t in thread_tweets:
                            normalized = normalize_tweet_response(t)
                            # Extract images from thread tweet
                            if t.get("media"):
                                normalized["images"], normalized["videos"] = extract_media_urls(t, {})
                            chain.append(normalized)
                        if len(chain) > 1:
                            primary_type = "thread_reply" if conv_id != tweet_id else "thread_starter"
                            entry["classification"]["primary_type"] = primary_type
                            thread_path = write_thread_file(chain, author, tweet_id, wiki_root)
                            entry["phase1"]["files_created"]["thread"] = thread_path
                            print(f"    Thread: {len(chain)} posts → {thread_path}")

                            # Extract media from all thread posts
                            for post in chain:
                                for img in post.get("images", []):
                                    _download_image(img, post.get("author", {}).get("username", author), post["id"], entry, wiki_root)
                                for vid in post.get("videos", []):
                                    _download_video(vid, post.get("author", {}).get("username", author), post["id"], entry, temp_dir)
                else:
                    # Fallback: old walk_thread_upward for legacy API
                    print(f"    Walking thread upward from {tweet_id}...")
                    chain = walk_thread_upward(x_client, tweet, api_includes)
                    if len(chain) > 1:
                        primary_type = "thread_reply" if conv_id != tweet_id else "thread_starter"
                        entry["classification"]["primary_type"] = primary_type
                        thread_path = write_thread_file(chain, author, tweet_id, wiki_root)
                        entry["phase1"]["files_created"]["thread"] = thread_path
                        print(f"    Thread: {len(chain)} posts → {thread_path}")

                        # Extract media from all thread posts
                        for post in chain:
                            for img in post.get("images", []):
                                _download_image(img, post["author_username"], post["id"], entry, wiki_root)
                            for vid in post.get("videos", []):
                                _download_video(vid, post["author_username"], post["id"], entry, temp_dir)

            # NEW: Use TwitterAPI.io thread_context for replies (no 7-day limit!)
            # Already fetched via route_tweet_to_endpoints() - stored in entry["thread_context"]
            if entry.get("thread_context") and entry["thread_context"].get("replies"):
                print(f"    Using thread context with replies")

        # ── Extract Content (images, videos, links) ──
        _extract_content(x_client, tweet, api_includes, entry, wiki_root, temp_dir, config)

        # ── NEW: Write quote network and retweeter files ──
        if entry.get("quotes"):
            quote_path = write_quote_network_file(entry["quotes"], author, tweet_id, wiki_root)
            entry["phase1"]["files_created"]["quote_network"] = quote_path
            print(f"    ✓ Quote network → {quote_path}")

        if entry.get("retweeters"):
            rt_path = write_retweeter_file(entry["retweeters"], author, tweet_id, wiki_root)
            entry["phase1"]["files_created"]["retweeters"] = rt_path
            print(f"    ✓ Retweeters → {rt_path}")

        # NEW: Process quoted tweet content (images, etc.)
        if entry.get("quoted_tweet"):
            qt = entry["quoted_tweet"]
            qt_author = qt.get("author", {}).get("username", "unknown")
            qt_id = qt.get("id", "")
            print(f"    Processing quoted tweet: @{qt_author}/{qt_id}")
            # Extract images from quoted tweet
            if qt.get("media"):
                qt_images, qt_videos = extract_media_urls(qt, {})
                for img in qt_images:
                    _download_image(img, qt_author, qt_id, entry, wiki_root)
                for vid in qt_videos:
                    _download_video(vid, qt_author, qt_id, entry, temp_dir)
            # Also extract other content
            _extract_content(x_client, qt, {}, entry, wiki_root, temp_dir, config)
            print(f"    ✓ Quoted tweet content processed")

        entry["phase1"]["status"] = "complete"
        manifest["bookmarks"].append(entry)

    manifest["phase_status"]["phase1_extract"] = "complete"
    manifest["status"] = "phase1_complete"
    print(f"\n  ✅ Phase 1 complete: {len(manifest['bookmarks'])} bookmarks + {len(manifest['repost_originals'])} repost originals")


def _extract_content(client: XClient, tweet: Dict, includes: Dict, entry: Dict,
                      wiki_root: str, temp_dir: str, config: Dict):
    """Extract images, videos, links from a tweet into appropriate locations."""
    author = entry["author_handle"]
    tweet_id = entry["id"]
    flags = set(entry["classification"]["flags"])

    # Images
    if "has_images" in flags:
        images, _ = extract_media_urls(tweet, includes)
        for i, img in enumerate(images):
            _download_image(img, author, tweet_id, entry, wiki_root, i)

    # Videos (non-YouTube)
    if "has_video" in flags:
        _, videos = extract_media_urls(tweet, includes)
        for vid in videos:
            _download_video(vid, author, tweet_id, entry, temp_dir)

    # YouTube
    if "has_youtube" in flags:
        for url_entity in tweet.get("entities", {}).get("urls", []):
            expanded = url_entity.get("expanded_url", "")
            if "youtube.com" in expanded or "youtu.be" in expanded:
                sc_key = os.environ.get("SCRAPE_CREATORS_API_KEY", "")
                if sc_key:
                    print(f"    Fetching YouTube transcript: {expanded}")
                    transcript = fetch_youtube_transcript(sc_key, expanded)
                    if transcript:
                        path = write_transcript_file(
                            transcript, author, tweet_id, wiki_root,
                            source_url=expanded
                        )
                        entry["phase1"]["files_created"]["youtube_transcripts"].append(path)
                        print(f"    ✓ YouTube transcript → {path}")
                    else:
                        print(f"    ⚠ YouTube transcript unavailable — skipping")

    # GitHub
    if "has_github" in flags:
        for url_entity in tweet.get("entities", {}).get("urls", []):
            expanded = url_entity.get("expanded_url", "")
            if "github.com" in expanded or "github.io" in expanded:
                try:
                    print(f"    Fetching GitHub repo: {expanded}")
                    repo_info = fetch_github_repo(expanded)
                    if repo_info and repo_info.get("repo"):
                        path = write_github_repo_file(repo_info, author, tweet_id, wiki_root)
                        entry["phase1"]["files_created"]["github_repos"].append(path)
                        print(f"    ✓ GitHub → {path}")
                    else:
                        print(f"    ⚠ GitHub repo info unavailable")
                except Exception as e:
                    print(f"    ⚠ GitHub fetch failed: {e}")

    # External links (general, excluding telegram)
    if "has_external_link" in flags:
        for url_entity in tweet.get("entities", {}).get("urls", []):
            expanded = url_entity.get("expanded_url", "")
            if not expanded or "x.com" in expanded or "twitter.com" in expanded:
                continue
            if "youtube.com" in expanded or "youtu.be" in expanded:
                continue
            if "github.com" in expanded or "github.io" in expanded:
                continue
            if "t.me" in expanded:
                continue

            print(f"    Fetching external link: {expanded}")
            link_info = fetch_external_link_content(expanded)
            path = write_external_link_file(link_info, author, tweet_id, wiki_root)
            entry["phase1"]["files_created"]["external_links"].append(path)
            print(f"    ✓ External link → {path}")

    # X native articles
    if "has_x_article" in flags:
        # Get TwitterAPI.io key if available
        twitter_api_key = os.environ.get("TWITTER_API_KEY", "")

        for url_entity in tweet.get("entities", {}).get("urls", []):
            expanded = url_entity.get("expanded_url", "")
            if "x.com" in expanded and "/article/" in expanded:
                print(f"    X article detected: {expanded}")

                # Extract article tweet ID from URL (format: x.com/i/article/{tweet_id})
                article_tweet_id = expanded.split("/article/")[-1].split("/")[0].split("?")[0]

                if twitter_api_key:
                    # Use TwitterAPI.io API
                    article_data = fetch_x_article_via_api(article_tweet_id, twitter_api_key)

                    if article_data.get("error"):
                        print(f"    ⚠ API error: {article_data['error']}")
                        # Fall back to legacy method
                        link_info = fetch_external_link_content(expanded)
                    else:
                        # Write article content
                        title = article_data.get("title", "X Article")
                        content = article_data.get("content", "")
                        preview = article_data.get("preview_text", "")

                        path = full_path(wiki_root, f"raw/articles/{author}-{tweet_id}-article.md")
                        os.makedirs(os.path.dirname(path), exist_ok=True)

                        # Build article content with metadata
                        article_md = f"""# {title}

**Preview:** {preview}

**Author:** @{article_data.get('author', {}).get('username', author)}
**Created:** {article_data.get('created_at', '')}
**Engagement:** {article_data.get('engagement', {}).get('view_count', 0)} views, {article_data.get('engagement', {}).get('like_count', 0)} likes

---

{content}
"""
                        Path(path).write_text(article_md)
                        entry["phase1"]["files_created"]["articles"].append(path)
                        print(f"    ✓ Article (via API) → {path}")

                        # Download cover image if available
                        cover_url = article_data.get("cover_image_url", "")
                        if cover_url:
                            cover_ext = cover_url.split(".")[-1].split("?")[0]
                            if cover_ext not in ("jpg", "jpeg", "png", "webp"):
                                cover_ext = "jpg"
                            cover_filename = f"{author}-{tweet_id}-article-cover.{cover_ext}"
                            cover_dest = full_path(wiki_root, f"raw/x-article-images/{cover_filename}")
                            if download_file(cover_url, cover_dest):
                                entry["phase1"]["files_created"]["images"].append(cover_dest)
                                print(f"    ✓ Article cover image → {cover_filename}")

                        continue
                else:
                    # No API key - try legacy method
                    print(f"    ⚠ No TWITTER_API_KEY - using legacy fetch")
                    link_info = fetch_external_link_content(expanded)

                if link_info.get("content") and len(link_info["content"]) > 100:
                    path = full_path(wiki_root, f"raw/articles/{author}-{tweet_id}-article.md")
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    Path(path).write_text(f"# {link_info.get('title', 'X Article')}\n\n{link_info['content']}")
                    entry["phase1"]["files_created"]["articles"].append(path)
                    print(f"    ✓ Article (legacy) → {path}")
                else:
                    print(f"    ⚠ X article content inaccessible — flagging for browser fallback")
                    entry["phase1"]["status"] = "needs_fallback"


def _download_image(img: Dict, author: str, tweet_id: str, entry: Dict,
                     wiki_root: str, seq: int = 0):
    """Download a single image."""
    url = img.get("url", "")
    if not url:
        return
    ext = url.split(".")[-1].split("?")[0]
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        ext = "jpg"
    seq_num = len(entry["phase1"]["files_created"]["images"]) + 1
    filename = f"{author}-{tweet_id}-image-{seq_num}.{ext}"
    dest = full_path(wiki_root, f"raw/x-article-images/{filename}")

    if download_file(url, dest):
        entry["phase1"]["files_created"]["images"].append(dest)
        print(f"    ✓ Image {seq_num} → {filename}")


def _download_video(vid: Dict, author: str, tweet_id: str, entry: Dict, temp_dir: str):
    """Download a video to temp directory."""
    url = vid.get("url", "")
    if not url:
        return
    vid_num = len(entry["phase1"]["files_created"]["videos"]) + 1
    filename = f"{author}-{tweet_id}-video-{vid_num}.mp4"
    dest = os.path.join(temp_dir, "videos", filename)
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    if download_file(url, dest):
        duration = get_video_duration(dest)
        entry["phase1"]["files_created"]["videos"].append({
            "temp_path": dest,
            "duration_seconds": duration,
            "duration_ms": vid.get("duration_ms"),
        })
        print(f"    ✓ Video {vid_num} → {filename} ({duration:.0f}s)")


# ─────────────────────────────────────────────
# PHASE 2: ANALYZE
# ─────────────────────────────────────────────


def run_phase2(manifest: Dict, config: Dict):
    wiki_root = config["wiki_root"]
    gemini_key = os.environ["GEMINI_API_KEY"]
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    # Load skill prompts (use prompts/analysis.md if available)
    image_skill_path = config["skills"].get("image_analysis_prompt", config["skills"]["image_analysis"])
    if os.path.exists(image_skill_path):
        image_skill = Path(image_skill_path).read_text()
    else:
        image_skill = load_skill_prompt(config["skills"]["image_analysis"])

    video_skill_path = config["skills"].get("video_analysis_prompt", config["skills"]["video_analysis"])
    if os.path.exists(video_skill_path):
        video_skill = Path(video_skill_path).read_text()
    else:
        video_skill = load_skill_prompt(config["skills"]["video_analysis"])

    all_entries = manifest["bookmarks"] + manifest.get("repost_originals", [])

    for entry in all_entries:
        if entry.get("phase1", {}).get("status") != "complete":
            continue
        if entry.get("phase2", {}).get("status") == "complete":
            continue

        author = entry["author_handle"]
        tweet_id = entry["id"]

        # ── Image Analysis (Gemini 2.5 Flash) ──
        for img_path in entry["phase1"]["files_created"].get("images", []):
            if not os.path.exists(img_path):
                continue
            print(f"  Analyzing image: {os.path.basename(img_path)}")

            analysis = retry(
                lambda p=img_path: analyze_image_gemini(
                    p, gemini_key, image_skill, config["api"]["gemini_flash_model"]
                ),
                max_retries=config["api"]["max_retries"],
                label=f"Gemini Flash {os.path.basename(img_path)}"
            )

            if analysis:
                # Save raw JSON to raw/x-image-analyses/
                img_basename = os.path.splitext(os.path.basename(img_path))[0]
                json_path = full_path(wiki_root, f"raw/x-image-analyses/{img_basename}-analysis.json")
                os.makedirs(os.path.dirname(json_path), exist_ok=True)
                with open(json_path, "w") as f:
                    json.dump(analysis, f, indent=2)
                validate_written_file(json_path, f"Image analysis {img_basename}", min_bytes=100)

                entry["phase2"]["image_analyses"].append({
                    "image_path": img_path,
                    "analysis_json": json_path,
                    "status": "complete",
                })
                print(f"    ✓ Analysis → {os.path.basename(json_path)}")
            else:
                entry["phase2"]["image_analyses"].append({
                    "image_path": img_path,
                    "analysis_json": None,
                    "status": "failed",
                })

        # ── Video Analysis ──
        for vid_info in entry["phase1"]["files_created"].get("videos", []):
            vid_path = vid_info.get("temp_path", "")
            duration = vid_info.get("duration_seconds", 0)

            if not os.path.exists(vid_path):
                continue

            if duration <= 120:
                # ≤2 min → Gemini 2.5 Pro Vision
                print(f"  Analyzing short video ({duration:.0f}s): {os.path.basename(vid_path)}")
                analysis = retry(
                    lambda p=vid_path: analyze_video_gemini(
                        p, gemini_key, video_skill, config["api"]["gemini_pro_model"]
                    ),
                    max_retries=config["api"]["max_retries"],
                    label=f"Gemini Pro {os.path.basename(vid_path)}"
                )

                if analysis:
                    json_path = full_path(wiki_root, f"raw/x-video-analyses/{author}-{tweet_id}-video-analysis.json")
                    os.makedirs(os.path.dirname(json_path), exist_ok=True)
                    with open(json_path, "w") as f:
                        json.dump(analysis, f, indent=2)
                    validate_written_file(json_path, f"Video analysis {author}-{tweet_id}", min_bytes=100)
                    entry["phase2"]["video_analyses"].append({
                        "video_path": vid_path, "analysis_json": json_path, "status": "complete"
                    })
                    print(f"    ✓ Video analysis → {os.path.basename(json_path)}")

                    # Also save transcript from analysis if present
                    if analysis.get("transcript"):
                        t_path = write_transcript_file(
                            analysis["transcript"], author, tweet_id, wiki_root,
                            duration=f"{duration:.0f}s",
                            source_url=f"https://x.com/{author}/status/{tweet_id}"
                        )
                        entry["phase2"]["video_transcripts"].append({"path": t_path, "method": "gemini_pro"})
            else:
                # >2 min → Whisper
                print(f"  Transcribing long video ({duration:.0f}s): {os.path.basename(vid_path)}")
                audio_path = vid_path.replace(".mp4", ".mp3")
                if extract_audio(vid_path, audio_path):
                    transcript = transcribe_whisper(audio_path, openai_key)
                    if transcript:
                        t_path = write_transcript_file(
                            transcript, author, tweet_id, wiki_root,
                            duration=f"{duration:.0f}s",
                            source_url=f"https://x.com/{author}/status/{tweet_id}"
                        )
                        entry["phase2"]["video_transcripts"].append({"path": t_path, "method": "whisper"})
                        print(f"    ✓ Transcript → {os.path.basename(t_path)}")
                    # Cleanup audio
                    if os.path.exists(audio_path):
                        os.remove(audio_path)

        entry["phase2"]["status"] = "complete"

    manifest["phase_status"]["phase2_analyze"] = "complete"
    manifest["status"] = "phase2_complete"
    print(f"\n  ✅ Phase 2 complete")


# ─────────────────────────────────────────────
# PHASE 3: COMPILE
# ─────────────────────────────────────────────


def run_phase3(manifest: Dict, config: Dict, skip_qa: bool = False):
    wiki_root = config["wiki_root"]
    minimax_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    mm_client = get_minimax_client(minimax_key)

    manifest.setdefault("qa_council", {"status": "pending", "batch_qa_path": None, "concept_index_updated": False})

    # ── Step 3.1: Create wiki pages from Phase 2 analyses ──
    print("  Step 3.1: Creating wiki pages for media analyses...")
    all_entries = manifest["bookmarks"] + manifest.get("repost_originals", [])

    for entry in all_entries:
        entry.setdefault("phase3", {"status": "pending", "source_summary": None, "entities_created": [], "concepts_created": [], "backlinks_added": []})
        author = entry["author_handle"]
        tweet_id = entry["id"]
        category = entry.get("primary_category") or "knowledge-base"

        # Image analysis wiki pages
        for ia in entry.get("phase2", {}).get("image_analyses", []):
            if ia.get("status") != "complete" or not ia.get("analysis_json"):
                continue
            analysis = json.loads(Path(ia["analysis_json"]).read_text())
            img_basename = os.path.splitext(os.path.basename(ia["image_path"]))[0]
            wiki_path = full_path(wiki_root, f"wiki/x-image-analyses/{img_basename}-analysis.md")

            # Check image_type to determine which format - look in metadata first
            metadata = analysis.get("metadata", {})
            image_type = metadata.get("image_type", analysis.get("image_type", analysis.get("image_class", ""))).upper()

            # Determine if this is a text document or visual image
            is_text_document = image_type in ("TEXT_DOCUMENT", "TEXT", "SYSTEM_PROMPT", "CODE", "INSTRUCTIONS", "DOCUMENT")

            if is_text_document:
                # Text document format - check visible_text_full first (newer format), then text_content (older)
                visible_text_full = analysis.get("visible_text_full", "")
                text_content = analysis.get("text_content", {})

                visible_text = ""
                # Try visible_text_full first
                if visible_text_full:
                    visible_text += f"## Extracted Text\n\n{visible_text_full[:5000]}\n\n"
                # Then add structured fields if available
                if text_content.get("headlines"):
                    visible_text += "## Headlines\n" + "\n".join(f"- {h}" for h in text_content.get("headlines", [])) + "\n\n"
                if text_content.get("body_text"):
                    visible_text += "## Body Text\n" + "\n".join(f"- {t}" for t in text_content.get("body_text", [])) + "\n\n"
                if text_content.get("visible_urls"):
                    visible_text += "## URLs\n" + "\n".join(f"- {u}" for u in text_content.get("visible_urls", [])) + "\n\n"

                document_type = metadata.get("image_type", "text content")
                # For text documents, construct summary - prefer visible_text_full
                if visible_text_full:
                    # First 100 chars of extracted text
                    summary = visible_text_full[:100].replace("\n", " ")
                elif text_content.get("headlines"):
                    summary = text_content["headlines"][0][:100]
                elif text_content.get("body_text"):
                    summary = text_content["body_text"][0][:100]
                else:
                    summary = f"Text document ({document_type})"

                body = f"""# Image Analysis: {author} - {tweet_id}

**Source:** [Tweet](https://x.com/{author}/status/{tweet_id})

## Image Type: Text Document

**Document Type:** {document_type}

## Extracted Text

{visible_text if visible_text else "N/A"}

## Summary

{summary}

"""
            else:
                # Visual image format - build from available sections
                body = f"""# Image Analysis: {author} - {tweet_id}

**Source:** [Tweet](https://x.com/{author}/status/{tweet_id})

## Image Type: Visual Image

"""

                # Visual description from artistic_elements
                artistic = analysis.get("artistic_elements", {})
                if artistic.get("atmosphere"):
                    body += f"""
## Visual Description

{artistic.get('atmosphere', 'N/A')}

"""

                # Visible text from text_content
                text_content = analysis.get("text_content", {})
                if text_content.get("headlines") or text_content.get("body_text"):
                    body += f"""
## Visible Text

"""
                    if text_content.get("headlines"):
                        body += "**Headlines:**\n" + "\n".join(f"- {h}" for h in text_content.get("headlines", [])) + "\n\n"
                    if text_content.get("body_text"):
                        body += "**Body:**\n" + "\n".join(f"- {t[:100]}..." if len(t) > 100 else f"- {t}" for t in text_content.get("body_text", [])) + "\n\n"

                # Context from artistic_elements genre
                if artistic.get("genre"):
                    body += f"""
## Context

This is a {artistic.get('genre')} styled image with {artistic.get('mood', 'N/A')} mood.

"""

                # Notable details
                if artistic.get("visual_style"):
                    body += f"""
## Notable Details

- Visual Style: {artistic.get('visual_style')}
- Genre: {artistic.get('genre', 'N/A')}
- Influences: {', '.join(artistic.get('influences', []))}

"""

                # Typography section
                typography = analysis.get("typography", {})
                if typography.get("present"):
                    body += f"""
## Typography

- **Fonts:** {', '.join([f"{t.get('type', 'unknown')} ({t.get('weight', 'N/A')})" for t in typography.get('fonts', [])])}
- **Placement:** {typography.get('placement', 'N/A')}
- **Integration:** {typography.get('integration', 'N/A')}

"""

                # Optional sections if data exists
                if analysis.get("composition"):
                    comp = analysis["composition"]
                    body += f"""
## Composition

- **Rule Applied:** {comp.get('rule_applied', 'N/A')}
- **Aspect Ratio:** {comp.get('aspect_ratio', 'N/A')}
- **Layout:** {comp.get('layout', 'N/A')}
- **Focal Points:** {comp.get('focal_points', 'N/A')}
- **Visual Hierarchy:** {comp.get('visual_hierarchy', 'N/A')}
- **Balance:** {comp.get('balance', 'N/A')}
"""

                if analysis.get("color_profile"):
                    cp = analysis["color_profile"]
                    # Handle both string and dict formats
                    dom_colors = cp.get('dominant_colors', [])
                    if dom_colors:
                        if isinstance(dom_colors[0], dict):
                            dom_colors = [c.get('hex', c.get('color', str(c))) for c in dom_colors]
                    body += f"""
## Color Profile

- **Dominant Colors:** {', '.join(str(c) for c in dom_colors)}
- **Color Palette:** {cp.get('color_palette', 'N/A')}
- **Temperature:** {cp.get('temperature', 'N/A')}
- **Saturation:** {cp.get('saturation', 'N/A')}
- **Contrast:** {cp.get('contrast', 'N/A')}
"""

                if analysis.get("subject_analysis"):
                    sa = analysis["subject_analysis"]
                    body += f"""
## Subject Analysis

- **Primary Subject:** {sa.get('primary_subject', 'N/A')}
- **Positioning:** {sa.get('positioning', 'N/A')}
- **Scale:** {sa.get('scale', 'N/A')}
- **Expression:** {sa.get('facial_expression', 'N/A')}
"""

            # Determine summary based on type
            if is_text_document:
                page_summary = f"Text document analysis ({document_type}) from {tweet_id} by {author}"
            else:
                # Get from metadata
                page_summary = f"Gemini Vision analysis of image from {tweet_id} by {author}"

            write_frontmatter_page(
                wiki_path,
                f"Image Analysis: {author} - {tweet_id}",
                page_summary,
                ["image-analysis", category],
                "source",
                body
            )

        # Video analysis wiki pages
        for va in entry.get("phase2", {}).get("video_analyses", []):
            if va.get("status") != "complete" or not va.get("analysis_json"):
                continue
            analysis = json.loads(Path(va["analysis_json"]).read_text())
            wiki_path = full_path(wiki_root, f"wiki/x-video-analyses/{author}-{tweet_id}-video-analysis.md")

            # Determine what sections to include based on what's available
            # Handle both JSON formats: Format A (nested video_analysis) and Format B (top-level)
            if "video_analysis" in analysis:
                # Format A: New nested format
                vi = analysis["video_analysis"]
                transcript = vi.get("transcript", "N/A")

                # Aggregate visual_text from frame_observations
                frame_texts = []
                for f in vi.get("frame_observations", []):
                    ot = f.get("on_screen_text", "")
                    if ot and ot != "None.":
                        ts = f.get("timestamp", "")
                        frame_texts.append(f"[{ts}] {ot}" if ts else ot)
                visible_text = "\n".join(frame_texts) if frame_texts else "N/A"

                # Summary from overall_summary
                overall = vi.get("overall_summary", {})
                summary = overall.get("primary_subject", overall.get("summary", "N/A"))
                if summary == "N/A" and overall.get("narrative_arc"):
                    summary = overall.get("narrative_arc", "N/A")

                # Visual description from key moments
                visual_desc = "N/A"
                if vi.get("frame_observations"):
                    first_frame = vi["frame_observations"][0]
                    visual_desc = first_frame.get("visual", "N/A")
            else:
                # Format B: Old top-level format
                transcript = analysis.get("transcript", "N/A")
                visible_text = "\n".join(analysis.get("visible_text", [])) if analysis.get("visible_text") else "N/A"
                summary = analysis.get("summary", "N/A")
                visual_desc = analysis.get("visual_description", "N/A")

            body = f"""# Video Analysis: {author} - {tweet_id}

**Source:** [Tweet](https://x.com/{author}/status/{tweet_id})

"""

            if transcript and transcript != "N/A":
                body += f"""## Transcript

{transcript}

"""

            if visual_desc and visual_desc != "N/A":
                body += f"""## Visual Description

{visual_desc}

"""

            if visible_text and visible_text != "N/A":
                body += f"""## On-Screen Text

{visible_text}

"""

            if summary and summary != "N/A":
                body += f"""## Summary

{summary}
"""

            write_frontmatter_page(
                wiki_path,
                f"Video Analysis: {author} - {tweet_id}",
                f"Gemini Vision analysis of video from {tweet_id} by {author}",
                ["video-analysis", category],
                "source",
                body
            )

        # GitHub repo wiki pages
        for gh_path in entry.get("phase1", {}).get("files_created", {}).get("github_repos", []):
            if not os.path.exists(gh_path):
                continue
            raw_content = Path(gh_path).read_text()
            repo_name = os.path.basename(gh_path).replace(".md", "")
            wiki_gh_path = full_path(wiki_root, f"wiki/x-github-repos/{repo_name}.md")

            # Extract repo info from the markdown content
            lines = raw_content.split("\n")
            repo_url = ""
            description = ""
            readme_content = ""

            for i, line in enumerate(lines):
                if line.startswith("## Repository:"):
                    repo_url = line.replace("## Repository:", "").strip()
                elif line.startswith("## Description:"):
                    description = line.replace("## Description:", "").strip()
                elif line.startswith("## README"):
                    readme_content = "\n".join(lines[i+1:]).strip()[:2000]

            body = f"""# GitHub: {repo_name}

**Repository:** {repo_url or 'N/A'}
**Source Tweet:** [Tweet](https://x.com/{author}/status/{tweet_id})

## Description

{description or 'No description available'}

## README

{readme_content or 'No README available'}

## Source Tweet

This repository was shared by @{author} in [tweet](https://x.com/{author}/status/{tweet_id}).
"""

            write_frontmatter_page(
                wiki_gh_path,
                f"GitHub: {repo_name}",
                f"GitHub repository referenced in tweet {tweet_id}",
                ["github", category],
                "source",
                body
            )

    # ── Step 3.2: Wiki-ingest via MiniMax ──
    print("\n  Step 3.2: Running wiki-ingest for each bookmark...")
    # Check for API version of the prompt first, fall back to SKILL.md
    api_prompt_path = os.path.expanduser("~/.claude/skills/wiki-ingest/prompts/api-ingest.md")
    if os.path.exists(api_prompt_path):
        ingest_skill = load_skill_prompt(api_prompt_path)
    else:
        ingest_skill = load_skill_prompt(config["skills"]["wiki_ingest"])

    for entry in all_entries:
        if entry.get("phase3", {}).get("status") == "complete":
            continue
        if entry.get("phase1", {}).get("status") not in ("complete",):
            continue

        author = entry["author_handle"]
        tweet_id = entry["id"]
        print(f"    Ingesting @{author}/{tweet_id}...")

        # Assemble context
        context = _assemble_source_context(entry, wiki_root)

        try:
            response = llm_call(mm_client, ingest_skill, context, max_tokens=4096)

            # Write source summary
            # Parse slug from response or generate one
            slug = f"{author}-{tweet_id}"
            source_path = full_path(wiki_root, f"wiki/sources/{slug}.md")
            os.makedirs(os.path.dirname(source_path), exist_ok=True)
            Path(source_path).write_text(response)

            entry["phase3"]["source_summary"] = source_path
            print(f"    ✓ Source → {slug}.md")

            # Extract wikilinks — do NOT auto-create stubs
            # Rule: Full page for 2+ sources, stub only for entities from single source
            # Lint phase will detect frequently-referenced missing pages (3+ mentions)
            links = extract_wikilinks(response)
            # No auto-creation — let lint catch pages that need creation
            # (Skipping stub creation per CLAUDE.md rules)

            # Update sources index
            summary_line = entry.get("text", "")[:100]
            update_index_file(
                full_path(wiki_root, "wiki/sources/_index.md"),
                slug, summary_line
            )

            entry["phase3"]["status"] = "complete"
        except Exception as e:
            print(f"    ✗ Wiki-ingest failed: {e}")
            entry["phase3"]["status"] = "failed"

    # ── Step 3.3: QA Council ──
    if skip_qa:
        print("\n  Step 3.3: QA Council — SKIPPED")
        manifest["qa_council"]["status"] = "skipped"
    else:
        print("\n  Step 3.3: Running QA Council...")
        # Check for API version of the prompt first, fall back to SKILL.md
        api_prompt_path = os.path.expanduser("~/.claude/skills/qa-council/prompts/api-qa.md")
        if os.path.exists(api_prompt_path):
            qa_skill = load_skill_prompt(api_prompt_path)
        else:
            qa_skill = load_skill_prompt(config["skills"]["qa_council"])
        batch_id = manifest["batch_id"]

        # Collect all source summaries
        source_contents = []
        for entry in all_entries:
            source_path = entry.get("phase3", {}).get("source_summary")
            if source_path and os.path.exists(source_path):
                source_contents.append({
                    "slug": os.path.splitext(os.path.basename(source_path))[0],
                    "content": Path(source_path).read_text(),
                })

        if source_contents:
            # Load existing concept index
            concept_index_path = full_path(wiki_root, "wiki/qa-pairs/concept-index.json")
            concept_index = {}
            if os.path.exists(concept_index_path):
                concept_index = json.loads(Path(concept_index_path).read_text())

            # Format input
            qa_input = f"Batch ID: {batch_id}\nSources in batch: {len(source_contents)}\n\n"
            for sc in source_contents:
                qa_input += f"### {sc['slug']}\n{sc['content']}\n\n---\n\n"
            if concept_index:
                qa_input += f"\n## Existing Concept Index\n{json.dumps(concept_index, indent=2)}\n"

            try:
                qa_response = llm_call(mm_client, qa_skill, qa_input, max_tokens=128000)

                # Parse JSON from response
                # Strip markdown fences if present
                clean = qa_response.strip()
                if clean.startswith("```"):
                    clean = re.sub(r"^```\w*\n?", "", clean)
                    clean = re.sub(r"\n?```$", "", clean)

                qa_json = json.loads(clean)

                # Validate
                valid, errors = _validate_qa(qa_json, source_contents, wiki_root)
                if not valid:
                    print(f"    ⚠ QA validation failed: {errors[:3]}...")
                    print(f"    Retrying QA council...")
                    error_feedback = f"Previous attempt had validation errors:\n{chr(10).join(errors[:5])}\n\nPlease fix these issues and regenerate."
                    qa_response2 = llm_call(mm_client, qa_skill, qa_input + "\n\n" + error_feedback, max_tokens=128000)
                    clean2 = qa_response2.strip()
                    if clean2.startswith("```"):
                        clean2 = re.sub(r"^```\w*\n?", "", clean2)
                        clean2 = re.sub(r"\n?```$", "", clean2)
                    qa_json = json.loads(clean2)

                # Save
                qa_path = full_path(wiki_root, f"wiki/qa-pairs/{batch_id}-qa.json")
                os.makedirs(os.path.dirname(qa_path), exist_ok=True)
                with open(qa_path, "w") as f:
                    json.dump(qa_json, f, indent=2)

                # Merge concept index
                if qa_json.get("concept_index_update"):
                    _merge_concept_index(qa_json["concept_index_update"], concept_index_path, concept_index)

                # Update QA index
                update_index_file(
                    full_path(wiki_root, "wiki/qa-pairs/_index.md"),
                    batch_id, f"{len(source_contents)} sources, QA generated"
                )

                manifest["qa_council"]["status"] = "complete"
                manifest["qa_council"]["batch_qa_path"] = qa_path
                manifest["qa_council"]["concept_index_updated"] = True
                print(f"    ✓ QA → {batch_id}-qa.json")
            except Exception as e:
                print(f"    ✗ QA Council failed: {e}")
                manifest["qa_council"]["status"] = "failed"

    manifest["phase_status"]["phase3_compile"] = "complete"
    manifest["status"] = "phase3_complete"
    print(f"\n  ✅ Phase 3 complete")


def _assemble_source_context(entry: Dict, wiki_root: str) -> str:
    """Assemble full context for wiki-ingest from all extracted content."""
    parts = []
    author = entry["author_handle"]
    tweet_id = entry["id"]

    parts.append(f"## Bookmark Metadata")
    parts.append(f"- Author: @{author}")
    parts.append(f"- Tweet ID: {tweet_id}")
    parts.append(f"- URL: https://x.com/{author}/status/{tweet_id}")
    parts.append(f"- Category: {entry.get('primary_category', 'unclassified')}")
    parts.append(f"- Date: {entry.get('created_at', 'unknown')}")
    parts.append(f"- Type: {entry.get('classification', {}).get('primary_type', 'unknown')}")
    parts.append("")

    parts.append(f"## Tweet Text")
    parts.append(entry.get("text", "(empty)"))
    parts.append("")

    # Thread content
    thread_path = entry.get("phase1", {}).get("files_created", {}).get("thread")
    if thread_path and os.path.exists(thread_path):
        parts.append("## Thread Content")
        parts.append(Path(thread_path).read_text()[:5000])
        parts.append("")

    # Image analyses
    for ia in entry.get("phase2", {}).get("image_analyses", []):
        if ia.get("analysis_json") and os.path.exists(ia["analysis_json"]):
            parts.append(f"## Image Analysis")
            parts.append(Path(ia["analysis_json"]).read_text()[:2000])
            parts.append("")

    # Video transcripts
    for vt in entry.get("phase2", {}).get("video_transcripts", []):
        if vt.get("path") and os.path.exists(vt["path"]):
            parts.append("## Video Transcript")
            parts.append(Path(vt["path"]).read_text()[:5000])
            parts.append("")

    # YouTube transcripts
    for yt_path in entry.get("phase1", {}).get("files_created", {}).get("youtube_transcripts", []):
        if os.path.exists(yt_path):
            parts.append("## YouTube Transcript")
            parts.append(Path(yt_path).read_text()[:5000])
            parts.append("")

    # External links
    for link_path in entry.get("phase1", {}).get("files_created", {}).get("external_links", []):
        if os.path.exists(link_path):
            parts.append("## External Link Content")
            parts.append(Path(link_path).read_text()[:3000])
            parts.append("")

    # GitHub repos
    for gh_path in entry.get("phase1", {}).get("files_created", {}).get("github_repos", []):
        if os.path.exists(gh_path):
            parts.append("## GitHub Repository")
            parts.append(Path(gh_path).read_text()[:3000])
            parts.append("")

    # Repost context
    if entry.get("is_repost_original"):
        parts.append(f"## Repost Context")
        parts.append(f"This tweet was reposted by @{entry.get('reposted_by', 'unknown')}")
        parts.append("")

    return "\n".join(parts)


def _validate_qa(qa_json: Dict, sources: List[Dict], wiki_root: str) -> Tuple[bool, List[str]]:
    """Validate QA council output per skill spec."""
    errors = []

    # Structure checks
    for key in ["batch_id", "source_questions", "synthesis_questions", "concept_index_update"]:
        if key not in qa_json:
            errors.append(f"Missing key: {key}")

    # Layer 1 validation
    for sq in qa_json.get("source_questions", []):
        slug = sq.get("source_slug", "")
        questions = sq.get("questions", [])
        if len(questions) != 5:
            errors.append(f"{slug}: expected 5 questions, got {len(questions)}")

        expected = {"identity_problem", "plain_language", "alternative_discovery",
                    "failure_confusion", "implementation_entry"}
        actual = {q.get("question_type") for q in questions}
        missing = expected - actual
        if missing:
            errors.append(f"{slug}: missing types {missing}")

        for q in questions:
            for f in ["question_id", "question_type", "question", "answer", "search_terms"]:
                if f not in q:
                    errors.append(f"{slug}: question missing {f}")
            if q.get("answer") and len(q["answer"]) < 20:
                errors.append(f"{slug}: answer too short")

    # Layer 2 validation
    synthesis = qa_json.get("synthesis_questions", [])
    if len(synthesis) != 4:
        errors.append(f"Expected 4 synthesis questions, got {len(synthesis)}")

    for s in synthesis:
        answer = s.get("answer", "")
        if "[[" not in answer:
            errors.append(f"Synthesis {s.get('question_id', '?')}: no [[wikilinks]]")
        if not s.get("referenced_source_slugs"):
            errors.append(f"Synthesis {s.get('question_id', '?')}: no source refs")

    return len(errors) == 0, errors


def _merge_concept_index(update: Dict, index_path: str, existing: Dict):
    """Merge concept_index_update into the master concept-index.json."""
    if not existing:
        existing = {"concepts": [], "concept_clusters": {}, "existing_connections": [],
                    "total_sources_processed": 0, "total_batches_processed": 0}

    for concept in update.get("new_concepts", []):
        existing.setdefault("concepts", []).append(concept)

    for conn in update.get("new_connections", []):
        existing.setdefault("existing_connections", []).append(conn)

    for cluster, items in update.get("updated_clusters", {}).items():
        existing.setdefault("concept_clusters", {})[cluster] = items

    existing["total_batches_processed"] = existing.get("total_batches_processed", 0) + 1

    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    with open(index_path, "w") as f:
        json.dump(existing, f, indent=2)


# ─────────────────────────────────────────────
# PHASE 4: FINALIZE
# ─────────────────────────────────────────────


def run_phase4(manifest: Dict, config: Dict):
    wiki_root = config["wiki_root"]
    today = today_str()

    # ── Step 4.1: Wiki-lint (deterministic checks) ──
    print("  Step 4.1: Running wiki-lint...")
    errors, warnings, info_items = _run_lint_checks(wiki_root)

    # ── Step 4.2: Auto-fix lint issues ──
    print("  Step 4.2: Auto-fixing lint issues...")
    for err in errors:
        # Only auto-fix missing frontmatter — do NOT create stub pages
        # Broken links are expected and resolve as more sources are ingested
        if err.get("type") == "broken_link":
            pass  # Report only. Do NOT auto-create stub pages.
        elif err.get("type") == "missing_frontmatter":
            _fix_frontmatter(err["page"], err["missing_fields"], wiki_root)

    # ── Step 4.3: Write lint report ──
    print("  Step 4.3: Writing lint report...")
    report_path = full_path(wiki_root, f"wiki/outputs/lint-{today}.md")
    _write_lint_report(errors, warnings, info_items, report_path)
    manifest["lint"]["report_path"] = report_path
    manifest["lint"]["status"] = "complete"

    # ── Step 4.4: Update ALL indexes ──
    print("  Step 4.4: Updating all indexes...")
    _update_all_indexes(manifest, config)

    # ── Step 4.5: Update backlog-log.md ──
    print("  Step 4.5: Updating backlog-log.md...")
    if manifest.get("batch_number") and manifest["batch_number"] > 0:
        mark_batch_done(wiki_root, config["backlog_log"], manifest["batch_number"])
    else:
        print("  Skipping backlog update (no batch number)")
    manifest["backlog_updated"] = True

    # ── Step 4.6: Verification ──
    print("  Step 4.6: Verifying...")
    passed = _verify_batch(manifest, wiki_root)

    # ── Step 4.7: Cleanup ──
    if passed:
        print("  Step 4.7: Cleaning up temp files...")
        # Archive manifest before deleting temp (only if batch_number exists)
        if manifest.get("batch_number") and manifest["batch_number"] > 0:
            archive_path = full_path(wiki_root, f"wiki/outputs/manifest-batch-{manifest['batch_number']}.json")
            save_manifest(manifest, archive_path)

        # Clean up temp directory if it exists
        temp_dir = manifest.get("temp_dir")
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        manifest["cleanup_complete"] = True
    else:
        print("  ⚠ Verification failed — keeping temp files for inspection")

    manifest["phase_status"]["phase4_finalize"] = "complete"
    manifest["status"] = "complete"
    print(f"\n  ✅ Phase 4 complete")


def _load_pending_terms(wiki_root: str) -> Dict[str, int]:
    """Load pending terms from raw/assets/pending-terms.md.
    Returns dict of slug -> mention count.
    """
    pending_file = Path(wiki_root) / "raw" / "assets" / "pending-terms.md"
    if not pending_file.exists():
        return {}

    content = pending_file.read_text()
    terms = {}

    # Parse terms between ``` ``` blocks
    in_code_block = False
    for line in content.split("\n"):
        if line.strip() == "```":
            in_code_block = not in_code_block
            continue
        if in_code_block and line.strip():
            # Format: "term: count"
            if ": " in line:
                parts = line.rsplit(": ", 1)
                if len(parts) == 2:
                    slug = parts[0].strip()
                    try:
                        count = int(parts[1].strip())
                        terms[slug] = count
                    except ValueError:
                        pass

    return terms


def _run_lint_checks(wiki_root: str) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Run all deterministic lint checks."""
    errors = []
    warnings = []
    info_items = []

    # Build inventory
    inventory = {}
    for subdir in ["wiki/sources", "wiki/concepts", "wiki/entities", "wiki/x-github-repos",
                    "wiki/x-image-analyses", "wiki/x-video-analyses", "wiki/qa-pairs", "wiki/outputs"]:
        dir_path = full_path(wiki_root, subdir)
        if not os.path.isdir(dir_path):
            continue
        for fname in os.listdir(dir_path):
            if not fname.endswith(".md") or fname.startswith("_"):
                continue
            slug = fname[:-3]
            fpath = os.path.join(dir_path, fname)
            content = Path(fpath).read_text()
            links = WIKILINK_RE.findall(content)

            # Parse frontmatter
            fm = {}
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    try:
                        fm = yaml.safe_load(content[3:end]) or {}
                    except yaml.YAMLError:
                        pass

            inventory[slug] = {"path": fpath, "outbound": links, "inbound": [], "frontmatter": fm, "content": content}

    # Compute inbound links
    for slug, page in inventory.items():
        for link in page["outbound"]:
            if link in inventory:
                inventory[link]["inbound"].append(slug)

    # Check broken links (excluding terms in pending-terms.md)
    pending_terms = _load_pending_terms(wiki_root)
    for slug, page in inventory.items():
        for link in page["outbound"]:
            if link not in inventory and link not in pending_terms:
                errors.append({"type": "broken_link", "page": slug, "target": link})
            elif link not in inventory and link in pending_terms:
                # Known pending term - mark as info instead of error
                info_items.append({"type": "pending_term", "slug": link, "count": pending_terms.get(link, 0)})

    # Check missing frontmatter
    required = ["title", "date_created", "date_modified", "summary", "tags", "type", "status"]
    for slug, page in inventory.items():
        missing = [f for f in required if f not in page["frontmatter"]]
        if missing:
            errors.append({"type": "missing_frontmatter", "page": slug, "missing_fields": missing})

    # Check orphans
    for slug, page in inventory.items():
        if slug in ("index", "overview") or slug.startswith("_"):
            continue
        if not page["inbound"]:
            warnings.append({"type": "orphan", "page": slug})

    # Check stale claims
    stale_re = re.compile(r'\b(current|latest|recent|state-of-the-art|202[0-4])\b', re.I)
    ninety_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    for slug, page in inventory.items():
        mod_date = page["frontmatter"].get("date_modified", "")
        # Handle both string and date types
        if mod_date:
            if hasattr(mod_date, 'strftime'):
                mod_date_str = mod_date.strftime("%Y-%m-%d")
            else:
                mod_date_str = str(mod_date)
            if mod_date_str < ninety_ago:
                if stale_re.search(page["content"]):
                    warnings.append({"type": "stale", "page": slug, "date_modified": mod_date_str})

    # ── Run comprehensive wiki sync to update all concept/entity pages ──
    print("    Running wiki sync for concept/entity updates...")
    sync_script = full_path(wiki_root, "raw/assets/wiki-sync.py")
    if os.path.exists(sync_script):
        subprocess.run(["python3", sync_script], capture_output=True, cwd=full_path(wiki_root, "."))

    # Missing concept pages (3+ references)
    link_counts = {}
    for slug, page in inventory.items():
        for link in page["outbound"]:
            link_counts[link] = link_counts.get(link, 0) + 1
    for link, count in link_counts.items():
        if count >= 3 and link not in inventory:
            info_items.append({"type": "missing_concept_page", "slug": link, "count": count})

    return errors, warnings, info_items


def _fix_frontmatter(page_slug: str, missing_fields: List[str], wiki_root: str):
    """Add missing frontmatter fields with placeholder values."""
    # Find the file
    for subdir in ["wiki/sources", "wiki/concepts", "wiki/entities"]:
        path = full_path(wiki_root, f"{subdir}/{page_slug}.md")
        if os.path.exists(path):
            content = Path(path).read_text()
            # Simple fix: add missing fields to frontmatter
            for field in missing_fields:
                defaults = {
                    "title": page_slug.replace("-", " ").title(),
                    "date_created": today_str(),
                    "date_modified": today_str(),
                    "summary": "TODO: add summary",
                    "tags": "[]",
                    "type": "source",
                    "status": "draft",
                }
                if field in defaults:
                    # Insert after first ---
                    content = content.replace("---\n", f"---\n{field}: {defaults[field]}\n", 1)
            Path(path).write_text(content)
            break


def _write_lint_report(errors: List, warnings: List, info_items: List, path: str):
    """Write lint report per wiki-lint skill template."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    today = today_str()

    sections = [f"""---
title: "Lint Report {today}"
date_created: {today}
date_modified: {today}
summary: "{len(errors)} errors, {len(warnings)} warnings, {len(info_items)} info items"
tags: [lint, maintenance]
type: output
status: draft
---

# Lint Report — {today}

## Summary
- Errors: {len(errors)}
- Warnings: {len(warnings)}
- Info: {len(info_items)}
"""]

    if errors:
        sections.append("## Errors")
        for e in errors:
            sections.append(f"- **{e['type']}**: {e}")

    if warnings:
        sections.append("\n## Warnings")
        for w in warnings:
            sections.append(f"- **{w['type']}**: {w}")

    if info_items:
        sections.append("\n## Info")
        for i in info_items:
            sections.append(f"- **{i['type']}**: {i}")

    Path(path).write_text("\n".join(sections))


def _update_all_indexes(manifest: Dict, config: Dict):
    """Update every index file per wiki-backlog Step 8."""
    wiki_root = config["wiki_root"]
    today = today_str()
    batch_id = manifest["batch_id"]
    all_entries = manifest["bookmarks"] + manifest.get("repost_originals", [])

    # ── Step 0: Run comprehensive wiki sync (updates ALL wiki components) ──
    print("    Running comprehensive wiki sync...")
    sync_script = full_path(wiki_root, "raw/assets/wiki-sync.py")
    if os.path.exists(sync_script):
        result = subprocess.run(
            ["python3", sync_script],
            capture_output=True,
            text=True,
            cwd=full_path(wiki_root, ".")
        )
        if result.returncode == 0:
            print("    ✅ Wiki sync complete")
        else:
            print(f"    ⚠️ Wiki sync had issues: {result.stderr[:200]}")
    else:
        print("    ⚠️ wiki-sync.py not found - skipping comprehensive sync")

    # Collect all new pages
    new_sources = []
    new_concepts = []
    new_entities = []
    for entry in all_entries:
        if entry.get("phase3", {}).get("source_summary"):
            slug = os.path.splitext(os.path.basename(entry["phase3"]["source_summary"]))[0]
            new_sources.append(slug)

    # 1. wiki/index.md
    master_index = full_path(wiki_root, "wiki/index.md")
    for slug in new_sources:
        update_index_file(master_index, slug, f"Source from batch {batch_id}")

    # 2-4. Folder indexes
    for slug in new_concepts:
        update_index_file(full_path(wiki_root, "wiki/concepts/_index.md"), slug, "Concept stub")
    for slug in new_entities:
        update_index_file(full_path(wiki_root, "wiki/entities/_index.md"), slug, "Entity stub")

    # 5-6. Image/video analysis indexes
    for entry in all_entries:
        for ia in entry.get("phase2", {}).get("image_analyses", []):
            if ia.get("analysis_json"):
                slug = os.path.splitext(os.path.basename(ia["analysis_json"]))[0]
                update_index_file(full_path(wiki_root, "wiki/x-image-analyses/_index.md"), slug, "Image analysis")
        for va in entry.get("phase2", {}).get("video_analyses", []):
            if va.get("analysis_json"):
                slug = os.path.splitext(os.path.basename(va["analysis_json"]))[0]
                update_index_file(full_path(wiki_root, "wiki/x-video-analyses/_index.md"), slug, "Video analysis")
        # GitHub repo wiki pages
        for gh_path in entry.get("phase1", {}).get("files_created", {}).get("github_repos", []):
            if gh_path:
                repo_slug = os.path.splitext(os.path.basename(gh_path))[0]
                update_index_file(full_path(wiki_root, "wiki/x-github-repos/_index.md"), repo_slug, "GitHub repository")

    # 7. QA pairs index (already updated in Phase 3)

    # 8. Outputs index (lint report)
    if manifest["lint"].get("report_path"):
        slug = os.path.splitext(os.path.basename(manifest["lint"]["report_path"]))[0]
        update_index_file(full_path(wiki_root, "wiki/outputs/_index.md"), slug, "Lint report")

    # 9. wiki/log.md
    log_entry = f"""
## [{today}] backlog-process | Batch {batch_id} | {len(new_sources)} sources
Sources: {', '.join(new_sources[:10])}
Concepts: {', '.join(new_concepts[:10]) or 'none'}
Entities: {', '.join(new_entities[:10]) or 'none'}
"""
    append_to_file(full_path(wiki_root, "wiki/log.md"), log_entry)

    manifest["indexes_updated"] = True


def _verify_batch(manifest: Dict, wiki_root: str) -> bool:
    """Verify all expected outputs exist."""
    failures = []
    all_entries = manifest["bookmarks"] + manifest.get("repost_originals", [])

    for entry in all_entries:
        source = entry.get("phase3", {}).get("source_summary")
        if source and not os.path.exists(source):
            failures.append(f"Missing source: {source}")

    qa_path = manifest.get("qa_council", {}).get("batch_qa_path")
    if qa_path and not os.path.exists(qa_path):
        failures.append(f"Missing QA: {qa_path}")

    lint_path = manifest.get("lint", {}).get("report_path")
    if lint_path and not os.path.exists(lint_path):
        failures.append(f"Missing lint report: {lint_path}")

    if failures:
        print(f"    ⚠ {len(failures)} verification failures:")
        for f in failures:
            print(f"      ✗ {f}")
        return False

    print(f"    ✅ All checks passed")
    return True


# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# ENVIRONMENT INIT
# ─────────────────────────────────────────────


def init_environment(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load config, .env, chdir to wiki root, verify required vars. Returns config."""
    config = load_config(config_path)
    load_dotenv(config["env_file"])

    # Verify required env vars
    required = ["X_BEARER_TOKEN", "GEMINI_API_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"✗ Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    minimax_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not minimax_key:
        print("✗ Missing MINIMAX_API_KEY or ANTHROPIC_API_KEY")
        sys.exit(1)

    wiki_root = config["wiki_root"]
    os.chdir(wiki_root)
    print(f"Working directory: {wiki_root}")

    return config


# ─────────────────────────────────────────────
# PROCESSED TAG MANAGEMENT
# ─────────────────────────────────────────────


def tag_as_processed(bookmark_ids: List[str], db_path: str):
    """Add 'processed' to categories for each bookmark in bookmarks.db."""
    conn = sqlite3.connect(db_path)
    for bid in bookmark_ids:
        # Get current categories
        row = conn.execute("SELECT categories FROM bookmarks WHERE id = ?", (bid,)).fetchone()
        if row:
            cats = row[0] or "[]"
            try:
                cat_list = json.loads(cats) if isinstance(cats, str) else (cats or [])
            except (json.JSONDecodeError, TypeError):
                cat_list = []
            if "processed" not in cat_list:
                cat_list.append("processed")
                conn.execute(
                    "UPDATE bookmarks SET categories = ? WHERE id = ?",
                    (json.dumps(cat_list), bid)
                )
    conn.commit()
    conn.close()


def query_unprocessed_bookmarks(db_path: str) -> List[Dict]:
    """Get all bookmarks that don't have the 'processed' tag."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT id, text, author_handle, primary_category, categories, synced_at "
        "FROM bookmarks WHERE categories NOT LIKE '%processed%' OR categories IS NULL "
        "ORDER BY synced_at ASC"
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# ─────────────────────────────────────────────
# KEYWORD CLUSTER CLASSIFICATION
# ─────────────────────────────────────────────


def load_keyword_clusters(wiki_root: str, classification_path: str) -> Dict[str, List[str]]:
    """Load keyword clusters from bookmark-classification.md."""
    path = full_path(wiki_root, classification_path)
    if not os.path.exists(path):
        return _default_keyword_clusters()

    content = Path(path).read_text()
    clusters = {}
    in_section = False

    for line in content.split("\n"):
        if "## Keyword Clusters" in line:
            in_section = True
            continue
        if in_section and line.strip().startswith("## "):
            break
        if in_section and ":" in line and not line.strip().startswith("#"):
            parts = line.split(":", 1)
            category = parts[0].strip().strip("- *\"")
            keywords = [k.strip().strip("\"'") for k in parts[1].split(",") if k.strip()]
            if category and keywords:
                clusters[category] = keywords

    # Fall back to defaults if nothing parsed
    if not clusters:
        clusters = _default_keyword_clusters()

    return clusters


def _default_keyword_clusters() -> Dict[str, List[str]]:
    """Default keyword clusters when not found in markdown."""
    return {
        "ai-agents": ["ai agent", "autonomous agent", "agent framework", "agentic", "multi-agent"],
        "ai-research": ["arxiv", "research paper", "benchmark", "state of the art", "fine-tuning", "fine tuning"],
        "ai-tools-comparison": ["vs ", "versus", "compared to", "alternative to", "better than"],
        "claude-code": ["claude code", "claude.ai", "anthropic", "claude sonnet", "claude opus"],
        "content-creation": ["video editing", "short form", "content creator", "tiktok", "reels"],
        "image-generation": ["midjourney", "stable diffusion", "dall-e", "flux", "image generation", "comfyui"],
        "learning": ["tutorial", "course", "learn how", "step by step", "beginner guide"],
        "local-ai": ["ollama", "self-hosted", "local llm", "run locally", "on-device"],
        "n8n-automation": ["n8n", "workflow automation", "automation workflow", "zapier alternative"],
        "open-source": ["open source", "open-source", "github.com", "self hosted", "foss"],
        "philosophy": ["mindset", "philosophy", "stoic", "first principles", "mental model"],
        "pricing-costs": ["pricing", "api cost", "token cost", "per month", "free tier"],
        "productivity": ["productivity", "time management", "workflow", "second brain", "notion"],
        "prompt-engineering": ["system prompt", "prompt engineering", "chain of thought", "few-shot", "prompt template"],
        "seo-marketing": ["seo", "marketing", "growth hack", "social media strategy", "analytics"],
        "tool-releases": ["just launched", "now available", "announcing", "introducing", "new release"],
        "video-generation": ["sora", "runway", "kling", "video generation", "text to video"],
        "web-development": ["react", "nextjs", "next.js", "frontend", "backend", "api endpoint", "typescript", "tailwind"],
    }


def classify_bookmark_topic(text: str, urls: List[str], clusters: Dict[str, List[str]]) -> str:
    """Classify a bookmark's topic using URL signals + keyword clusters.
    Returns the best-match primary category or 'unclassified'.
    """
    signals = []
    text_lower = text.lower() if text else ""

    # Signal 1: URL-based (strongest)
    for url in urls:
        if "github.com" in url:
            signals.append(("open-source", 0.9))
        if "arxiv.org" in url:
            signals.append(("ai-research", 0.9))
        if "huggingface.co" in url:
            signals.append(("ai-research", 0.8))
        if "n8n.io" in url:
            signals.append(("n8n-automation", 0.9))

    # Signal 2: Keyword clusters (multi-word patterns)
    for category, keywords in clusters.items():
        matches = sum(1 for k in keywords if k in text_lower)
        if matches > 0:
            signals.append((category, 0.3 * matches))

    if signals:
        signals.sort(key=lambda x: x[1], reverse=True)
        return signals[0][0]

    return "unclassified"


def classify_untagged_bookmarks(bookmarks: List[Dict], config: Dict):
    """Classify bookmarks that have no primary_category in bookmarks.db."""
    wiki_root = config["wiki_root"]
    clusters = load_keyword_clusters(wiki_root, config["bookmark_classification"])
    db_path = config["bookmarks_db"]
    conn = sqlite3.connect(db_path)
    classified = 0

    for bm in bookmarks:
        if bm.get("primary_category") and bm["primary_category"] != "unclassified":
            continue

        # Get URLs from tweet text (simple extraction)
        urls = re.findall(r'https?://\S+', bm.get("text", ""))
        category = classify_bookmark_topic(bm.get("text", ""), urls, clusters)

        conn.execute(
            "UPDATE bookmarks SET primary_category = ? WHERE id = ?",
            (category, bm["id"])
        )
        bm["primary_category"] = category
        classified += 1

    conn.commit()
    conn.close()
    if classified:
        print(f"  Classified {classified} bookmarks")


# ─────────────────────────────────────────────
# QA COUNCIL EVENT TRIGGER
# ─────────────────────────────────────────────


def check_and_run_qa_if_needed(config: Dict):
    """Check if 20+ sources accumulated since last QA run. If so, fire QA council.
    This is an event-driven trigger, not time-based.
    """
    wiki_root = config["wiki_root"]
    concept_index_path = full_path(wiki_root, "wiki/qa-pairs/concept-index.json")

    # Load or init concept index
    if os.path.exists(concept_index_path):
        concept_index = json.loads(Path(concept_index_path).read_text())
    else:
        concept_index = {
            "concepts": [], "concept_clusters": {}, "existing_connections": [],
            "total_sources_processed": 0, "total_batches_processed": 0,
            "sources_since_last_qa": 0,
        }

    since_last = concept_index.get("sources_since_last_qa", 0)
    print(f"  QA trigger check: {since_last}/20 sources since last QA run")

    if since_last < 20:
        return

    # Get all sources and find which ones haven't been QA'd
    sources_dir = full_path(wiki_root, "wiki/sources")
    if not os.path.isdir(sources_dir):
        return

    all_source_slugs = set()
    for f in os.listdir(sources_dir):
        if f.endswith(".md") and not f.startswith("_"):
            all_source_slugs.add(f[:-3])

    # Get QA-covered slugs from existing batch files
    qa_dir = full_path(wiki_root, "wiki/qa-pairs")
    covered_slugs = set()
    if os.path.isdir(qa_dir):
        for f in os.listdir(qa_dir):
            if f.endswith("-qa.json"):
                try:
                    qa_data = json.loads(Path(os.path.join(qa_dir, f)).read_text())
                    for sq in qa_data.get("source_questions", []):
                        covered_slugs.add(sq.get("source_slug", ""))
                except Exception:
                    pass

    uncovered = all_source_slugs - covered_slugs
    if len(uncovered) < 20:
        print(f"  Only {len(uncovered)} uncovered sources — waiting for 20")
        return

    print(f"\n  ═══ QA COUNCIL TRIGGERED: {len(uncovered)} uncovered sources ═══")

    # Process in batches to avoid JSON truncation
    batch_size = 20
    total_batches = (len(uncovered) + batch_size - 1) // batch_size

    # Run QA council
    minimax_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    mm_client = get_minimax_client(minimax_key)
    # Check for API version of the prompt first, fall back to SKILL.md
    api_prompt_path = os.path.expanduser("~/.claude/skills/qa-council/prompts/api-qa.md")
    if os.path.exists(api_prompt_path):
        qa_skill = load_skill_prompt(api_prompt_path)
    else:
        qa_skill = load_skill_prompt(config["skills"]["qa_council"])

    # Load all source contents
    source_contents_map = {}
    for slug in sorted(uncovered):
        spath = full_path(wiki_root, f"wiki/sources/{slug}.md")
        if os.path.exists(spath):
            source_contents_map[slug] = Path(spath).read_text()

    all_qa_results = []
    successful_count = 0

    def process_single_batch(batch_info):
        """Process a single QA batch - for parallel execution."""
        batch_num, batch_slugs = batch_info
        batch_id = f"qa_{today_str()}_{batch_num+1}_of_{total_batches}"

        # Build batch input
        qa_input = f"Batch ID: {batch_id}\nSources in batch: {len(batch_slugs)}\n\n"
        for slug in batch_slugs:
            content = source_contents_map.get(slug, "")
            qa_input += f"### {slug}\n{content[:2000]}\n\n---\n\n"

        qa_input += f"\n## Existing Concept Index\n{json.dumps(concept_index, indent=2)}\n"

        try:
            qa_response = llm_call(mm_client, qa_skill, qa_input, max_tokens=128000)

            # Parse JSON - handle non-JSON preamble
            clean = qa_response.strip()
            brace_pos = clean.find('{')
            bracket_pos = clean.find('[')
            if brace_pos == -1 and bracket_pos == -1:
                return (batch_num, None, "No JSON found")

            json_start = min(b for b in [brace_pos, bracket_pos] if b >= 0)
            clean = clean[json_start:]
            if clean.startswith("```"):
                clean = re.sub(r"^```\w*\n?", "", clean)
                clean = re.sub(r"\n?```$", "", clean)

            qa_json = json.loads(clean)
            return (batch_num, qa_json, None)

        except json.JSONDecodeError as e:
            return (batch_num, None, f"JSON parse failed: {e.msg}")
        except Exception as e:
            return (batch_num, None, str(e))

    # Prepare batch tasks
    batch_tasks = []
    for batch_num in range(total_batches):
        batch_start = batch_num * batch_size
        batch_end = min(batch_start + batch_size, len(uncovered))
        batch_slugs = sorted(uncovered)[batch_start:batch_end]
        batch_tasks.append((batch_num, batch_slugs))

    print(f"  Processing {total_batches} batches in parallel...")

    # Run batches in parallel (3 at a time to avoid API rate limits)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_single_batch, task): task for task in batch_tasks}

        for future in as_completed(futures):
            batch_num, qa_json, error = future.result()

            if qa_json:
                all_qa_results.append(qa_json)
                successful_count += len(batch_tasks[batch_num][1])
                print(f"    ✓ Batch {batch_num+1} parsed successfully")

                # Save each batch as its own JSON file
                batch_file_id = f"qa_{today_str()}_{batch_num+1}_of_{total_batches}"
                individual_qa_path = full_path(wiki_root, f"wiki/qa-pairs/{batch_file_id}-qa.json")
                os.makedirs(os.path.dirname(individual_qa_path), exist_ok=True)
                with open(individual_qa_path, "w") as f:
                    json.dump(qa_json, f, indent=2)
                print(f"    ✓ Saved: {batch_file_id}-qa.json")

                # Update concept-index after each batch
                if qa_json.get("concept_index_update"):
                    _merge_concept_index(qa_json["concept_index_update"], concept_index_path, concept_index)
            else:
                print(f"    ✗ Batch {batch_num+1} failed: {error}")

    if not all_qa_results:
        print("  ✗ No QA batches succeeded")
        return

    print(f"\n  ✓ QA Council: {successful_count} sources processed in {len(all_qa_results)} batches")

    # Reset counter
    concept_index["sources_since_last_qa"] = 0
    concept_index["total_sources_processed"] = len(all_source_slugs)
    with open(concept_index_path, "w") as f:
        json.dump(concept_index, f, indent=2)

    print(f"  ✓ Updated concept-index.json")

    # Update QA index
    update_index_file(
        full_path(wiki_root, "wiki/qa-pairs/_index.md"),
        f"qa_{today_str()}", f"{successful_count} sources, QA generated in {len(all_qa_results)} batches"
    )

    # Log to outputs
    log_msg = f"[{today_str()}] QA Council: {successful_count} sources → {len(all_qa_results)} batch files\n"
    append_to_file(full_path(wiki_root, "wiki/outputs/pipeline-live.log"), log_msg)
    update_index_file(full_path(wiki_root, "wiki/outputs/_index.md"), f"qa_{today_str()}", "QA batches (event trigger)")

    print(f"  ✓ QA complete: {successful_count} sources in {len(all_qa_results)} batches")


def increment_qa_source_counter(config: Dict, count: int = 1):
    """Increment the sources_since_last_qa counter in concept-index.json."""
    wiki_root = config["wiki_root"]
    path = full_path(wiki_root, "wiki/qa-pairs/concept-index.json")

    if os.path.exists(path):
        data = json.loads(Path(path).read_text())
    else:
        data = {"concepts": [], "concept_clusters": {}, "existing_connections": [],
                "total_sources_processed": 0, "total_batches_processed": 0,
                "sources_since_last_qa": 0}

    data["sources_since_last_qa"] = data.get("sources_since_last_qa", 0) + count
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ─────────────────────────────────────────────
# FULL PIPELINE ORCHESTRATOR
# ─────────────────────────────────────────────


def run_full_pipeline(bookmarks: List[Dict], config: Dict, batch_id: str,
                       skip_fallback: bool = False, skip_qa: bool = False,
                       update_backlog: bool = False, batch_num: Optional[int] = None):
    """Run all 4 phases on a list of bookmarks.

    Args:
        bookmarks: List of bookmark dicts from DB
        config: Loaded config
        batch_id: e.g. "batch_003" or "live_2026-04-11_001"
        skip_fallback: Skip browser-fallback items
        skip_qa: If True, skip QA council in Phase 3 (for live mode where QA is event-triggered)
        update_backlog: If True, update backlog-log.md on completion
        batch_num: Batch number for backlog mode
    """
    wiki_root = config["wiki_root"]
    temp_dir = config["temp_base"].replace("{N}", batch_id)
    manifest_path = os.path.join(temp_dir, "manifest.json")

    # Resume or fresh start
    if os.path.exists(manifest_path):
        manifest = load_manifest(manifest_path)
        print(f"  Resuming {batch_id} from {manifest['status']}")
    else:
        os.makedirs(temp_dir, exist_ok=True)
        os.makedirs(os.path.join(temp_dir, "videos"), exist_ok=True)
        # Use batch_num if provided, else extract number from batch_id
        num = batch_num or 0
        manifest = create_manifest(num, temp_dir, wiki_root)
        manifest["batch_id"] = batch_id
        save_manifest(manifest, manifest_path)

    print(f"\n{'='*50}")
    print(f"  X Bookmark Pipeline — {batch_id} ({len(bookmarks)} bookmarks)")
    print(f"{'='*50}\n")

    # Inject bookmarks into manifest if fresh
    if not manifest["bookmarks"]:
        # Pre-populate manifest with bookmark metadata
        for bm in bookmarks:
            manifest["bookmarks"].append({
                "id": bm["id"],
                "author_handle": bm.get("author_handle", "unknown"),
                "primary_category": bm.get("primary_category"),
                "categories": bm.get("categories"),
                "text": bm.get("text", ""),
                "classification": {"primary_type": "unknown", "flags": []},
                "phase1": {"status": "pending", "files_created": {
                    "thread": None, "images": [], "videos": [], "youtube_transcripts": [],
                    "external_links": [], "github_repos": [], "articles": [],
                    "quote_network": None, "retweeters": None,  # NEW
                }},
                "phase2": {"status": "pending", "image_analyses": [], "video_analyses": [], "video_transcripts": []},
                "phase3": {"status": "pending", "source_summary": None, "entities_created": [], "concepts_created": [], "backlinks_added": []},
                "phase4": {"status": "pending"},
            })

    # ── PHASE 1 ──
    if manifest["phase_status"]["phase1_extract"] != "complete":
        print("═══ PHASE 1: EXTRACT ═══")
        run_phase1(manifest, config)
        save_manifest(manifest, manifest_path)

    # Check fallbacks
    fallbacks = [b for b in manifest["bookmarks"]
                 if b.get("phase1", {}).get("status") == "needs_fallback"]
    if fallbacks and not skip_fallback:
        print(f"\n⚠ {len(fallbacks)} items need browser fallback. Continuing with --skip-fallback logic.")

    # ── PHASE 2 ──
    if manifest["phase_status"]["phase2_analyze"] != "complete":
        print("\n═══ PHASE 2: ANALYZE ═══")
        run_phase2(manifest, config)
        save_manifest(manifest, manifest_path)

    # ── PHASE 3 ──
    if manifest["phase_status"]["phase3_compile"] != "complete":
        print("\n═══ PHASE 3: COMPILE ═══")
        # For live mode, skip QA council here — it runs via event trigger
        if skip_qa:
            manifest["qa_council"]["status"] = "deferred_to_event_trigger"
        run_phase3(manifest, config, skip_qa=skip_qa)
        save_manifest(manifest, manifest_path)

    # ── PHASE 4 ──
    if manifest["phase_status"]["phase4_finalize"] != "complete":
        print("\n═══ PHASE 4: FINALIZE ═══")
        run_phase4(manifest, config)
        save_manifest(manifest, manifest_path)

    # ── BACKLOG UPDATE (only for backlog mode) ──
    if update_backlog and batch_num is not None:
        mark_batch_done(wiki_root, config["backlog_log"], batch_num)

    # ── DONE ──
    source_count = sum(1 for b in manifest["bookmarks"] if b.get("phase3", {}).get("source_summary"))
    print(f"\n{'='*50}")
    print(f"  ✅ {batch_id} complete! ({source_count} sources)")
    print(f"{'='*50}")

    return manifest


def chunk_list(lst: List, size: int) -> List[List]:
    """Split a list into chunks of given size."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]
