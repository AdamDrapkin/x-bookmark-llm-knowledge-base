#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

BASE_URL = "https://api.x.com/2"
POST_URL_RE = re.compile(r"https?://(?:www\.)?(?:x\.com|twitter\.com)/([A-Za-z0-9_]+)/status/(\d+)")


class XApiError(Exception):
    pass


def parse_post_input(value: str) -> Tuple[Optional[str], str]:
    value = value.strip()
    if value.isdigit():
        return None, value
    m = POST_URL_RE.search(value)
    if not m:
        raise ValueError("Input must be a post ID or a valid X/Twitter status URL")
    return m.group(1), m.group(2)


class XClient:
    def __init__(self, bearer_token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "x-post-extractor/1.0",
        })

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{BASE_URL}{path}"
        resp = self.session.get(url, params=params, timeout=30)
        if resp.status_code >= 400:
            raise XApiError(f"{resp.status_code} {resp.text}")
        return resp.json()

    def lookup_posts(self, ids: List[str]) -> Dict[str, Any]:
        return self.get(
            "/tweets",
            params={
                "ids": ",".join(ids),
                "tweet.fields": "id,text,author_id,attachments,entities,referenced_tweets,conversation_id,created_at,in_reply_to_user_id",
                "expansions": "attachments.media_keys,author_id,referenced_tweets.id,referenced_tweets.id.author_id",
                "media.fields": "media_key,type,url,preview_image_url,variants,duration_ms,height,width,alt_text",
                "user.fields": "id,name,username",
            },
        )

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

    def retweeted_by(self, post_id: str) -> Dict[str, Any]:
        return self.get(
            f"/tweets/{post_id}/retweeted_by",
            params={
                "user.fields": "id,name,username",
                "max_results": 100,
            },
        )


def index_includes(includes: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    media_by_key = {m["media_key"]: m for m in includes.get("media", []) if "media_key" in m}
    users_by_id = {u["id"]: u for u in includes.get("users", []) if "id" in u}
    tweets_by_id = {t["id"]: t for t in includes.get("tweets", []) if "id" in t}
    return media_by_key, users_by_id, tweets_by_id


def extract_urls(entities: Optional[Dict[str, Any]]) -> List[str]:
    urls = []
    for item in (entities or {}).get("urls", []):
        expanded = item.get("expanded_url") or item.get("unwound_url") or item.get("url")
        if expanded:
            urls.append(expanded)
    return list(dict.fromkeys(urls))


def extract_media(post: Dict[str, Any], media_by_key: Dict[str, Dict[str, Any]]) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
    image_urls: List[str] = []
    video_urls: List[str] = []
    media_objects: List[Dict[str, Any]] = []
    for key in post.get("attachments", {}).get("media_keys", []):
        media = media_by_key.get(key)
        if not media:
            continue
        media_objects.append(media)
        mtype = media.get("type")
        if mtype == "photo" and media.get("url"):
            image_urls.append(media["url"])
        elif mtype in {"video", "animated_gif"}:
            variants = media.get("variants", []) or []
            mp4_variants = [v for v in variants if v.get("content_type") == "video/mp4" and v.get("url")]
            mp4_variants.sort(key=lambda v: v.get("bit_rate", -1), reverse=True)
            for v in mp4_variants:
                video_urls.append(v["url"])
    return list(dict.fromkeys(image_urls)), list(dict.fromkeys(video_urls)), media_objects


def post_url(post: Dict[str, Any], users_by_id: Dict[str, Dict[str, Any]], fallback_username: Optional[str] = None) -> Optional[str]:
    author = users_by_id.get(post.get("author_id", ""), {})
    username = author.get("username") or fallback_username
    if username and post.get("id"):
        return f"https://x.com/{username}/status/{post['id']}"
    return None


def normalize_post(post: Dict[str, Any], includes: Dict[str, Any], fallback_username: Optional[str] = None) -> Dict[str, Any]:
    media_by_key, users_by_id, _ = index_includes(includes)
    images, videos, media_objects = extract_media(post, media_by_key)
    return {
        "id": post.get("id"),
        "created_at": post.get("created_at"),
        "conversation_id": post.get("conversation_id"),
        "text": post.get("text"),
        "author_id": post.get("author_id"),
        "author_username": users_by_id.get(post.get("author_id", ""), {}).get("username") or fallback_username,
        "url": post_url(post, users_by_id, fallback_username),
        "referenced_tweets": post.get("referenced_tweets", []),
        "image_urls": images,
        "video_urls": videos,
        "hyperlinks": extract_urls(post.get("entities")),
        "media": media_objects,
    }


def fetch_single_post(client: XClient, post_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    payload = client.lookup_posts([post_id])
    data = payload.get("data", [])
    if not data:
        raise XApiError(f"Post {post_id} not found or unavailable")
    return data[0], payload.get("includes", {})


def fetch_full_thread(client: XClient, root_post: Dict[str, Any], root_includes: Dict[str, Any], fallback_username: Optional[str]) -> List[Dict[str, Any]]:
    conversation_id = root_post.get("conversation_id") or root_post.get("id")
    items: Dict[str, Dict[str, Any]] = {}
    items[root_post["id"]] = normalize_post(root_post, root_includes, fallback_username)
    next_token = None
    seen: Set[str] = set()
    while True:
        payload = client.recent_search_conversation(conversation_id, next_token=next_token)
        includes = payload.get("includes", {})
        for post in payload.get("data", []):
            if post["id"] in seen:
                continue
            seen.add(post["id"])
            items[post["id"]] = normalize_post(post, includes)
        next_token = payload.get("meta", {}).get("next_token")
        if not next_token:
            break
    ordered = sorted(items.values(), key=lambda p: (p.get("created_at") or "", p.get("id") or ""))
    return ordered


def fetch_repost_links(client: XClient, post_id: str) -> List[str]:
    payload = client.retweeted_by(post_id)
    users = payload.get("data", [])
    links = []
    for user in users:
        username = user.get("username")
        if username:
            links.append(f"https://x.com/{username}/status/{post_id}")
    return list(dict.fromkeys(links))


def aggregate_comment_links(thread: List[Dict[str, Any]], root_id: str) -> List[str]:
    links: List[str] = []
    for post in thread:
        if post.get("id") == root_id:
            continue
        links.extend(post.get("hyperlinks", []))
    return list(dict.fromkeys(links))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch an X post and extract media, thread, repost links, and hyperlinks as JSON.")
    parser.add_argument("post", help="X post ID or full post URL")
    parser.add_argument("--bearer-token", default=os.getenv("X_BEARER_TOKEN"), help="X API bearer token, or set X_BEARER_TOKEN")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    if not args.bearer_token:
        raise SystemExit("Missing bearer token. Pass --bearer-token or set X_BEARER_TOKEN")

    fallback_username, post_id = parse_post_input(args.post)
    client = XClient(args.bearer_token)

    root_post, root_includes = fetch_single_post(client, post_id)
    root_normalized = normalize_post(root_post, root_includes, fallback_username)
    thread = fetch_full_thread(client, root_post, root_includes, fallback_username)
    repost_links = fetch_repost_links(client, post_id)

    result = {
        "post": root_normalized,
        "thread": thread,
        "repost_links": repost_links,
        "all_thread_hyperlinks": list(dict.fromkeys(root_normalized.get("hyperlinks", []) + aggregate_comment_links(thread, post_id))),
        "comment_hyperlinks": aggregate_comment_links(thread, post_id),
    }

    json.dump(result, sys.stdout, indent=2 if args.pretty else None)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
