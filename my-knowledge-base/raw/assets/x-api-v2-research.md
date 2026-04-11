# X API v2 Research - Complete Reference for Content Extraction

**Purpose:** Complete research on X API v2 for building a robust, unbreakable extraction pipeline that replaces browser automation.

**Date:** 2026-04-11

---

## 1. Core API Structure

### Base URL
```
https://api.x.com/2
```

### Authentication
- **Bearer Token** (OAuth 2.0 App-Only) - required for all endpoints
- Set via header: `Authorization: Bearer $BEARER_TOKEN`

### Default Response (Minimal)
By default, endpoints return only `id` and `text`. You MUST request additional fields.

---

## 2. All Relevant Endpoints

### 2.1 Tweet Lookup (Primary)
| Method | Endpoint | Use Case |
|--------|----------|----------|
| GET | `/2/tweets` | Lookup multiple posts by ID (up to 100) |
| GET | `/2/tweets/:id` | Lookup single post by ID |

**Request parameters:**
- `ids` - comma-separated list of IDs (for `/2/tweets`)
- `tweet.fields` - fields to include
- `expansions` - related objects to include
- `media.fields` - media object fields
- `user.fields` - user object fields

### 2.2 Quote Tweets (Reposts/Quotes)
| Method | Endpoint | Use Case |
|--------|----------|----------|
| GET | `/2/tweets/:id/quote_tweets` | Get posts that quote a specific post |

**Parameters:**
- `max_results` - up to 100 (default 10)
- `pagination_token` - for pagination
- `tweet.fields` - fields to include
- `expansions` - objects to expand
- `user.fields` - user fields

**Example:**
```
/2/tweets/1234567890/quote_tweets?tweet.fields=created_at,public_metrics,author_id&expansions=author_id&user.fields=username,verified&max_results=10
```

### 2.3 Retweets (Who Reposted)
| Method | Endpoint | Use Case |
|--------|----------|----------|
| GET | `/2/tweets/:id/retweeted_by` | Get users who retweeted a post |

**Note:** Returns user objects, NOT actual retweet posts. Only gives you the count and usernames.

### 2.4 Search Recent (Thread/Conversation Retrieval)
| Method | Endpoint | Use Case |
|--------|----------|----------|
| GET | `/2/tweets/search/recent` | Search recent posts (last 7 days) |

**Key operator:** `conversation_id:{id}` - returns all posts in a thread

**Parameters:**
- `query` - search query (use `conversation_id:{id}`)
- `max_results` - up to 100
- `next_token` - pagination
- `tweet.fields` - fields to include
- `expansions` - objects to expand

---

## 3. Fields Reference

### 3.1 Tweet Fields (`tweet.fields`)

| Field | Type | Description | Use for |
|-------|------|-------------|---------|
| `id` | string | Post ID | Always |
| `text` | string | Full post text | Always |
| `created_at` | ISO8601 | Creation timestamp | Timestamps |
| `author_id` | string | Author's user ID | User lookup |
| `public_metrics` | object | like, retweet, reply, quote counts | Engagement |
| `attachments` | object | media_keys, poll_ids | Media detection |
| `conversation_id` | string | Thread identifier | Thread retrieval |
| `referenced_tweets` | array | [{type, id}] | Repost/quote detection |
| `in_reply_to_user_id` | string | User being replied to | Reply detection |
| `entities` | object | hashtags, mentions, urls, cashtags | Link extraction |
| `lang` | string | Detected language | Classification |
| `source` | string | Posting client | Bot detection |
| `possibly_sensitive` | boolean | Sensitive content flag | Filtering |
| `reply_settings` | string | Who can reply | Settings |
| `context_annotations` | array | Topic/entity classifications | Topic tagging |
| `geo` | object | Location data | Geo tagging |
| `edit_history_tweet_ids` | array | Edit history | Version tracking |

### 3.2 User Fields (`user.fields`)

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | User ID |
| `username` | string | @handle |
| `name` | string | Display name |
| `created_at` | ISO8601 | Account creation |
| `description` | string | Bio |
| `profile_image_url` | string | Avatar URL |
| `verified` | boolean | Verification status |
| `protected` | boolean | Protected account |
| `public_metrics` | object | follower/following counts |

### 3.3 Media Fields (`media.fields`)

| Field | Type | Description |
|-------|------|-------------|
| `media_key` | string | Media identifier |
| `type` | string | photo, video, animated_gif |
| `url` | string | Direct media URL |
| `preview_image_url` | string | Thumbnail URL |
| `variants` | array | Video variants with bitrate |
| `duration_ms` | number | Video duration |
| `height` | number | Height |
| `width` | number | Width |
| `alt_text` | string | Accessibility text |

---

## 4. Expansions Reference

### 4.1 Post Expansions

| Expansion | Returns | Required For |
|-----------|---------|--------------|
| `author_id` | User object | Author details |
| `attachments.media_keys` | Media object | Images/videos/GIFs |
| `referenced_tweets.id` | Tweet object | Quote/repost original |
| `referenced_tweets.id.author_id` | User object | Original author |
| `in_reply_to_user_id` | User object | Reply target |
| `entities.mentions.username` | User object | Mentioned users |
| `geo.place_id` | Place object | Location |
| `attachments.poll_ids` | Poll object | Polls |

### 4.2 Usage Pattern

```
/2/tweets/:id?
  tweet.fields=created_at,public_metrics,entities,referenced_tweets,conversation_id,attachments,author_id,in_reply_to_user_id,lang&
  expansions=author_id,attachments.media_keys,referenced_tweets.id,referenced_tweets.id.author_id,in_reply_to_user_id&
  user.fields=username,name,verified,profile_image_url,description&
  media.fields=url,preview_image_url,type,duration_ms,height,width,alt_text,variants
```

---

## 5. Content Type Detection

### 5.1 Is Repost (Retweet)

**How to detect:**
- Check `referenced_tweets` array
- Look for: `{type: "retweeted", id: "..."}`

**What to do:**
1. Extract `id` from referenced_tweets
2. Fetch original post separately
3. Process both as separate sources

### 5.2 Is Quote Tweet

**How to detect:**
- Check `referenced_tweets` array
- Look for: `{type: "quoted", id: "..."}`

**What to do:**
1. Extract `id` from referenced_tweets
2. Use `/2/tweets/:id/quote_tweets` to get all quotes
3. Process original AND quotes

### 5.3 Is Reply

**How to detect:**
- `in_reply_to_user_id` is not null, OR
- `referenced_tweets` contains `{type: "replied_to", id: "..."}`

**What to do:**
1. Get `conversation_id`
2. Use search with `conversation_id:{id}` to get full thread

### 5.4 Has Images

**How to detect:**
- `attachments.media_keys` exists
- Media object in `includes` has `type: "photo"`

**What to do:**
1. Map media_keys to includes.media
2. Filter where `type === "photo"`
3. Extract `url` field

### 5.5 Has Video

**How to detect:**
- `attachments.media_keys` exists
- Media object in `includes` has `type: "video"` or `"animated_gif"`

**What to do:**
1. Map media_keys to includes.media
2. Filter where `type === "video"` or `"animated_gif"`
3. Extract from `variants` array
4. Filter for `content_type: "video/mp4"`
5. Sort by `bit_rate` (lowest for transcription)

### 5.6 Has External Links

**How to detect:**
- `entities.urls` exists in post
- Extract `expanded_url` from each

**What to do:**
1. Map each URL to domain
2. Categorize: GitHub, Telegram, YouTube, general

### 5.7 Is X Article

**How to detect:**
- Check for `article` field in response, OR
- `entities.urls` contains `x.com/article` domain, OR
- Text contains "Article" badge metadata

**What to do:**
1. Extract article content
2. Save to `raw/articles/`

### 5.8 Is Thread

**How to detect:**
- `conversation_id` exists, AND
- Multiple posts in conversation (need to fetch)

**What to do:**
1. Get `conversation_id`
2. Use `/2/tweets/search/recent?query=conversation_id:{id}`
3. Sort by `created_at` for chronological order

---

## 6. Complete Request Builder

### Single Post with All Data

```python
def fetch_post(post_id: str, bearer_token: str) -> dict:
    """Fetch a post with ALL possible useful data."""
    url = f"https://api.x.com/2/tweets/{post_id}"
    params = {
        # All tweet fields
        "tweet.fields": (
            "created_at,public_metrics,entities,referenced_tweets,"
            "conversation_id,attachments,author_id,in_reply_to_user_id,"
            "lang,source,possibly_sensitive,reply_settings,"
            "context_annotations,geo,edit_history_tweet_ids"
        ),
        # Expand all related objects
        "expansions": (
            "author_id,attachments.media_keys,"
            "referenced_tweets.id,referenced_tweets.id.author_id,"
            "in_reply_to_user_id,entities.mentions.username"
        ),
        # User fields
        "user.fields": (
            "username,name,verified,protected,"
            "profile_image_url,description,public_metrics,created_at"
        ),
        # Media fields
        "media.fields": (
            "url,preview_image_url,type,duration_ms,"
            "height,width,alt_text,variants"
        ),
    }
    headers = {"Authorization": f"Bearer {bearer_token}"}
    response = requests.get(url, params=params, headers=headers)
    return response.json()
```

### Full Thread (Conversation)

```python
def fetch_thread(conversation_id: str, bearer_token: str) -> list:
    """Fetch all posts in a conversation thread."""
    url = "https://api.x.com/2/tweets/search/recent"
    params = {
        "query": f"conversation_id:{conversation_id}",
        "tweet.fields": (
            "created_at,public_metrics,entities,referenced_tweets,"
            "conversation_id,attachments,author_id,in_reply_to_user_id,lang"
        ),
        "expansions": (
            "author_id,attachments.media_keys,"
            "entities.mentions.username"
        ),
        "user.fields": "username,name,verified",
        "media.fields": "url,preview_image_url,type",
        "max_results": 100,
    }
    headers = {"Authorization": f"Bearer {bearer_token}"}

    all_posts = []
    next_token = None

    while True:
        if next_token:
            params["next_token"] = next_token

        response = requests.get(url, params=params, headers=headers)
        data = response.json()

        all_posts.extend(data.get("data", []))

        next_token = data.get("meta", {}).get("next_token")
        if not next_token:
            break

    # Sort chronologically
    all_posts.sort(key=lambda x: x.get("created_at", ""))
    return all_posts
```

### Quote Tweets

```python
def fetch_quotes(post_id: str, bearer_token: str) -> list:
    """Fetch all quote tweets of a post."""
    url = f"https://api.x.com/2/tweets/{post_id}/quote_tweets"
    params = {
        "tweet.fields": "created_at,public_metrics,entities,author_id",
        "expansions": "author_id",
        "user.fields": "username,verified",
        "max_results": 100,
    }
    headers = {"Authorization": f"Bearer {bearer_token}"}

    all_quotes = []
    next_token = None

    while True:
        if next_token:
            params["pagination_token"] = next_token

        response = requests.get(url, params=params, headers=headers)
        data = response.json()

        all_quotes.extend(data.get("data", []))

        next_token = data.get("meta", {}).get("next_token")
        if not next_token:
            break

    return all_quotes
```

---

## 7. Response Processing Logic

### 7.1 Extracted Data Structure

```python
def extract_content(post: dict, includes: dict) -> dict:
    """Extract all content from a normalized post response."""

    # Index includes for lookup
    media_by_key = {m["media_key"]: m for m in includes.get("media", [])}
    users_by_id = {u["id"]: u for u in includes.get("users", [])}

    # Basic info
    result = {
        "id": post["id"],
        "text": post["text"],
        "created_at": post.get("created_at"),
        "author": users_by_id.get(post.get("author_id", {}),
        "url": f"https://x.com/{users_by_id.get(post.get('author_id', {})).get('username')}/status/{post['id']}",
    }

    # Public metrics
    if "public_metrics" in post:
        result["metrics"] = post["public_metrics"]

    # Media detection
    media_keys = post.get("attachments", {}).get("media_keys", [])
    images = []
    videos = []

    for key in media_keys:
        media = media_by_key.get(key)
        if not media:
            continue

        if media.get("type") == "photo":
            images.append({
                "url": media.get("url"),
                "alt_text": media.get("alt_text"),
            })
        elif media.get("type") in ("video", "animated_gif"):
            # Get lowest bitrate mp4
            variants = media.get("variants", [])
            mp4s = [v for v in variants
                   if v.get("content_type") == "video/mp4"]
            mp4s.sort(key=lambda x: x.get("bit_rate", float("inf")))
            videos.append({
                "url": mp4s[0].get("url") if mp4s else None,
                "duration_ms": media.get("duration_ms"),
                "preview": media.get("preview_image_url"),
            })

    result["images"] = images
    result["videos"] = videos

    # External links
    links = []
    for url_obj in post.get("entities", {}).get("urls", []):
        expanded = url_obj.get("expanded_url")
        if expanded and "x.com" not in expanded:
            links.append(expanded)

    result["external_links"] = links

    # Referenced tweets (reposts/quotes)
    referenced = post.get("referenced_tweets", [])
    repost_of = None
    quote_of = None
    reply_to = None

    for ref in referenced:
        if ref.get("type") == "retweeted":
            repost_of = ref.get("id")
        elif ref.get("type") == "quoted":
            quote_of = ref.get("id")
        elif ref.get("type") == "replied_to":
            reply_to = ref.get("id")

    result["repost_of"] = repost_of
    result["quote_of"] = quote_of
    result["reply_to"] = reply_to
    result["conversation_id"] = post.get("conversation_id")

    return result
```

---

## 8. What's Missing from API (Limitations)

### 8.1 Cannot Get Actual Retweet Posts

**Limitation:** `/2/tweets/:id/retweeted_by` only returns user objects, not the actual retweet posts.

**Workaround:** Not possible via API. Need to search for quotes or use search.

### 8.2 Search Only Returns Last 7 Days

**Limitation:** `/2/tweets/search/recent` only covers last 7 days.

**Workaround:** For old threads, use the tweet lookup first, then conversation search.

### 8.3 Rate Limits

**Limits (basic tier):**
- Tweet lookup: 300 requests/15 min
- Search: 450 requests/15 min
- User lookup: 900 requests/15 min

---

## 9. Complete Field Matrix

| Content Type | Detection Method | API Data Needed |
|--------------|-----------------|----------------|
| Is Retweet | `referenced_tweets[].type === "retweeted"` | `referenced_tweets.id` |
| Is Quote | `referenced_tweets[].type === "quoted"` | `referenced_tweets.id` + quote_tweets |
| Is Reply | `in_reply_to_user_id` or `referenced_tweets` | `conversation_id` + search |
| Has Images | `type === "photo"` in media | `attachments.media_keys` + includes |
| Has Video | `type === "video"` or `"animated_gif"` | `attachments.media_keys` + includes |
| Has Thread | `conversation_id` with multiple | search + conversation_id |
| External Links | `entities.urls[].expanded_url` | `entities.urls` |
| Is X Article | `text` contains article metadata | `text` + entities |
| Has Poll | `attachments.poll_ids` exists | `attachments.poll_ids` |
| Has Location | `geo.place_id` exists | `geo.place_id` + includes |

---

## 10. Endpoints Summary

| Goal | Endpoint | Parameters |
|------|----------|------------|
| Get single post | `GET /2/tweets/:id` | tweet.fields + expansions |
| Get multiple posts | `GET /2/tweets` | ids parameter |
| Get quotes | `GET /2/tweets/:id/quote_tweets` | max_results, pagination |
| Get who retweeted | `GET /2/tweets/:id/retweeted_by` | user.fields, max_results |
| Search conversation | `GET /2/tweets/search/recent` | query: `conversation_id:ID` |
| Get user info | `GET /2/users/by/username/:handle` | user.fields |

---

## Sources

- [Expansions - X Developer Platform](https://docs.x.com/x-api/fundamentals/expansions)
- [Data Dictionary - X](https://docs.x.com/x-api/fundamentals/data-dictionary)
- [Fields - X](https://docs.x.com/x-api/fundamentals/fields)
- [Quote Posts - X](https://docs.x.com/x-api/posts/quote-tweets/introduction)
- [Retweets - X](https://docs.x.com/x-api/posts/retweets/introduction)
- [Conversation ID - X](https://docs.x.com/x-api/fundamentals/conversation-id)
- [Search Recent Posts - X](https://docs.x.com/x-api/posts/search-recent-posts)
- [Integration Guide - X](https://docs.x.com/x-api/posts/lookup/integrate)
- [Explore User Posts - X](https://docs.x.com/tutorials/explore-a-users-posts)