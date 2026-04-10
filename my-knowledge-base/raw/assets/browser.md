# Browser Automation SOP — X/Twitter Scraping

**Purpose:** This SOP guides Claude through extracting content from X (Twitter) — including tweets, threads, articles, videos, and images — using browser automation (Glance MCP) and video transcription (ScrapeCreators + Whisper).

**When to use:** Claude reads this file when Adam says "Read and act on browser.md" or when the task involves X/Twitter content extraction.

---

## PREREQUISITES

Before starting any extraction task:

1. **Inject cookies** into the browser session (see Authentication section below)
2. **Confirm output directories exist:**
   - `raw/x-article-images/`
   - `raw/articles/`
   - `raw/x-threads/`
   - `raw/x-video-transcripts/`
   - `raw/x-external-links/`
   - `raw/x-github-repos/`
3. **Verify ffmpeg is installed** — run `ffmpeg -version` to confirm
4. **Check OpenAI API key is available** — check environment or `~/.ft-bookmarks/.env`
5. **Check Gemini API key is available** — check environment or `~/.ft-bookmarks/.env`

---

## OUTPUT LOCATIONS

```
raw/
├── x-article-images/       # All images from tweets and articles
├── x-image-analyses/       # Gemini Vision JSON analysis for images
├── x-video-analyses/       # Gemini Vision JSON analysis for videos (≤2 min)
├── articles/               # Full X native article content (markdown)
├── x-threads/              # Thread snapshots (text only)
└── x-video-transcripts/   # Video transcripts (from videos >2 min)
```

### File Naming Conventions

**Images** (`raw/x-article-images/`):
```
{author-handle}-{tweet-id}-image-{sequence-number}.{extension}
```
Example: `godofprompt-2041853939302461554-image-1.jpg`

**Articles** (`raw/articles/`):
```
{author-handle}-{tweet-id}-article.md
```
Example: `noisyb0y1-2041454862425047268-article.md`

**Threads** (`raw/x-threads/`):
```
{author-handle}-{tweet-id}-thread.md
```
Example: `HeyGen-2041893905042743425-thread.md`

**Video Transcripts** (`raw/x-video-transcripts/`):
```
{author-handle}-{tweet-id}-transcript.txt
```
Example: `HeyGen-2041893905042743425-transcript.txt`

**External Links** (`raw/x-external-links/`):
```
{author-handle}-{tweet-id}-link-{link-domain}.txt
```
Example: `noisyb0y1-2041454862425047268-link-telegram.txt`

**GitHub Repos** (`raw/x-github-repos/`):
```
{author-handle}-{tweet-id}-github-{repo-name}.md
```
Example: `noisyb0y1-2041454862425047268-github-langchain.md`

**Image Analyses** (`raw/x-image-analyses/`):
```
{author-handle}-{tweet-id}-image-{sequence-number}-analysis.json
```
Example: `godofprompt-2041853939302461554-image-1-analysis.json`

**Video Analyses** (`raw/x-video-analyses/`):
```
{author-handle}-{tweet-id}-video-analysis.json
```
Example: `HeyGen-2041893905042743425-video-analysis.json`

---

## AUTHENTICATION

### Cookie Injection (REQUIRED — Do not skip)

Every new browser session MUST have cookies injected before navigating to X. Without this, you will be redirected to the login page.

**Root Cause of Past Failures:**
The error `SecurityError: Failed to set the 'cookie' property on 'Document'` happens because:
1. HttpOnly cookies — auth_token and ct0 are marked HttpOnly, blocking JavaScript access
2. Sandboxed context — headless browser restricts cookie manipulation
3. Order of operations — cookies must be set AFTER navigating to the domain

**Solution: Navigate First, Then Inject (Recommended)**

```javascript
// FIRST: Navigate to x.com (any page)
await page.goto('https://x.com/home');

// THEN: Set cookies while on that domain (note the dot prefix)
document.cookie = "auth_token=26ca60db2aadb0b91122ed6f2f27dce52fd42041; path=/; domain=.x.com";
document.cookie = "ct0=2e3355290bfba48e20614bceba7afc33553bf4c381a2ccc4b886ae76d59e57575bf7105548ba89696c75c2c29daf5d26bf3471641e7e7feda168e3a955d1e332e9407caffcb75a0b86eccadff0911022; path=/; domain=.x.com";
```

Key changes:
1. Navigate to `x.com/home` FIRST (or any x.com page)
2. Use `.x.com` (with dot prefix) as the domain
3. Inject cookies AFTER navigation, not before

**If this method fails:**
- Re-inject cookies from the ones stored in this file
- If re-injection continues to fail, inform the user and ask them to provide new cookies from DevTools → Application → Cookies → x.com
- **DO NOT attempt to login manually** — always re-inject cookies instead

---

## COMPLETE WORKFLOW (Steps 1-8)

### STEP 1: Navigate to Tweet URL

**Action:**
1. Inject cookies (see Authentication section)
2. Navigate to the tweet URL using `mcp__glance__browser_navigate`

**Expected result:** Tweet page loads with full content visible

**If page doesn't load or redirects to login:**
- Re-inject cookies (session expired)
- Wait 3 seconds
- Navigate again
- Take a snapshot to verify login form is not present

**CRITICAL:** You MUST navigate in browser FIRST before using any other tools. This allows you to detect whether images or videos exist on the page.

---

### STEP 2: Analyze What Content Exists on Page

**CRITICAL:** ALWAYS take a snapshot FIRST, then evaluate. Do not skip the snapshot — it reveals content that JavaScript evaluation may miss.

**Action:**
1. **First:** Take a snapshot to visually understand the page
2. **Then:** Run evaluation script to extract structured data

**What to look for in the snapshot (visual indicators):**

| Indicator | What It Means |
|-----------|---------------|
| "Quote" or "Repost" label before a username | This is a repost/quote tweet |
| "RT @username" in the text | Classic repost format |
| Multiple posts visible | Thread present |
| Video thumbnail or "Play Video" text | Video content |
| "Article" badge | X native article |
| External link (non-x.com URL) | External link to process |

**Use this evaluation script:**
```javascript
// Check for main tweet content
const tweet = document.querySelector('[data-testid="tweet"]');
const tweetText = tweet?.textContent || '';

// Check for repost (RT @)
const isRepost = tweetText.includes('RT @') || tweetText.match(/^RT\s+@/);
let originalAuthor = null;
let originalTweetId = null;

if (isRepost) {
  // Extract original author and tweet ID from repost
  const rtMatch = tweetText.match(/RT\s+@(\w+):.*\/status\/(\d+)/);
  if (rtMatch) {
    originalAuthor = rtMatch[1];
    originalTweetId = rtMatch[2];
  }
}

// Check for thread (multiple posts)
const allPosts = document.querySelectorAll('[data-testid="cellInnerDiv"]');
const postCount = allPosts.length;

// Check for images
const images = document.querySelectorAll('img[src*="twimg.com"]');
const imageCount = images.length;

// Check for videos
const videoElements = document.querySelectorAll('video');
const hasVideo = videoElements.length > 0 || tweetText.includes('Embedded video') || tweetText.includes('Play Video');

// Check for article/link
const links = document.querySelectorAll('[data-testid="tweet"] a[href*="://"]');
const externalLink = links.length > 0 ? links[0].href : null;

console.log(JSON.stringify({
  isRepost: isRepost,
  originalAuthor: originalAuthor,
  originalTweetId: originalTweetId,
  hasThread: postCount > 1,
  postCount: postCount,
  imageCount: imageCount,
  hasVideo: hasVideo,
  externalLink: externalLink,
  tweetText: tweetText.substring(0, 200)
}));
```

**Decision tree based on results:**

| If... | Then... |
|-------|---------|
| isRepost = true | Process as repost: create 2 wiki entries (repost spin + original), use Step 2.1 |
| postCount > 1 | Go to STEP 3: Extract Thread |
| hasVideo = true | Use ScrapeCreators to get video URLs → Go to STEP 4: Handle Video |
| externalLink exists AND is NOT x.com | Go to STEP 5: Handle External Link |
| Content appears to be X Article | Go to STEP 6: Handle Articles |
| imageCount > 0 | Use ScrapeCreators to get image URLs → Go to STEP 7: Extract Images |
| Single tweet only (no media, no links) | Go to STEP 8: Confirm & Exit (already in FT bookmarks) |

---

### STEP 2.1: Handle Reposts

**When to use:** When `isRepost = true` in Step 2 evaluation

**CRITICAL:** A repost = TWO wiki entries:
1. **Repost entry** — The reposter's spin/commentary (what they added)
2. **Original entry** — The original tweet content (processed as standalone)

**Process:**

1. **Extract original tweet info:**
   - `originalAuthor` = the @handle before the colon
   - `originalTweetId` = the tweet ID in the embedded URL

2. **Create repost source summary** in `wiki/sources/`:
   - Filename: `{reposter-handle}-{repost-tweet-id}.md`
   - Content includes reposter's commentary + link to `[[original-author-tweet-id]]`
   - Add `type: source`, `tags: [repost, {category}]`

3. **Process the original tweet** (create separate source):
   - Navigate to `https://x.com/{originalAuthor}/status/{originalTweetId}`
   - Process through Steps 1-8 as normal
   - Add backlink to reposter's spin in the original's summary
   - This counts as an ADDITIONAL item in the batch (batch_size = 10 + reposts)

4. **Cross-reference both entries:**
   - Repost summary links to `[[original-author-tweet-id]]`
   - Original summary links back to `[[reposter-handle-tweet-id]]`

**Batch sizing:** If batch has 3 reposts among 10 bookmarks, process 13 items total (10 originals + 3 originals from reposts).

---

### STEP 3: Extract Thread Content

**When to use:** When there are multiple posts in the conversation (postCount > 1)

**Action:**

1. **Scroll to load all replies:**
   ```javascript
   // Scroll until user comments (outside the thread) appear
   // Look for comment indicators like "Replying to..." ending and new user posts starting
   let scrollCount = 0;
   const maxScrolls = 10;
   
   async function scrollUntilCommentsLoad() {
     const initialCount = document.querySelectorAll('[data-testid="cellInnerDiv"]').length;
     
     while (scrollCount < maxScrolls) {
       window.scrollBy(0, 2000);
       await new Promise(r => setTimeout(r, 1500));
       
       const newCount = document.querySelectorAll('[data-testid="cellInnerDiv"]').length;
       
       // Check if we've reached the end (no new content loading)
       if (newCount === initialCount && scrollCount > 2) break;
       if (newCount > initialCount) {
         // New posts loaded, continue to see if more exist
         scrollCount++;
       } else {
         // No new posts after waiting - we've likely reached the end
         break;
       }
     }
   }
   await scrollUntilCommentsLoad();
   ```
   - **End condition:** When scrolling no longer loads new posts, or you see user comments that are NOT part of the thread (different authors, not the main thread poster)

2. **Extract all posts in thread:**
   ```javascript
   const posts = document.querySelectorAll('[data-testid="cellInnerDiv"]');
   let threadContent = '';
   
   posts.forEach((post, index) => {
     const text = post.textContent.substring(0, 500);
     threadContent += `--- Post ${index + 1} ---\n${text}\n\n`;
   });
   console.log(threadContent);
   ```

3. **Check for external links in any post:**
   ```javascript
   const posts = document.querySelectorAll('[data-testid="cellInnerDiv"]');
   const externalLinks = [];
   
   posts.forEach((post, idx) => {
     const links = post.querySelectorAll('a[href]');
     links.forEach(link => {
       const href = link.href;
       // External = not x.com, not twitter.com, has protocol
       if (href && !href.includes('x.com') && !href.includes('twitter.com') && href.includes('://')) {
         externalLinks.push({ postIndex: idx, url: href });
       }
     });
   });
   console.log(JSON.stringify(externalLinks));
   ```

4. **Save to file** using naming convention: `raw/x-threads/{author}-{tweet-id}-thread.md`

**Edge cases:**
- **Thread doesn't load fully:** Scroll more times (some threads have 20+ posts)
- **"Show more" appears:** Click it and continue extracting
- **Images in thread:** Note which posts have images for later extraction
- **Videos in thread:** Handle each video separately (go to STEP 4 for each)

---

### STEP 4: Handle Video Content (ScrapeCreators + Whisper + Gemini Vision)

**When to use:** When `hasVideo = true` or when the tweet mentions "Embedded video" or "Play Video"

**CRITICAL:** Do NOT try to transcribe via browser. Use ScrapeCreators API + Whisper OR Gemini Vision.

#### Step 4a: Get Video URL via ScrapeCreators

**Action:** Use `mcp__scrape-creators__v1_twitter_tweet` to get the tweet data, then extract video URL.

```bash
# Use the MCP tool - it returns JSON with video_info.variants[]
```

**Extract from response:**
```
legacy.extended_entities.media[].video_info.variants[]
```

**ALWAYS use the lowest bitrate** — quality doesn't matter for audio transcription.

**Bitrate values:**
- 256000 (480x270) — lowest, use this
- 832000 (640x360) — second option
- Higher bitrates — avoid, unnecessary cost

#### Step 4b: Check Video Duration (Decision Point)

**Action:** Before downloading or transcribing, determine video duration to choose the right approach.

```bash
# Get video duration using ffprobe
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "/tmp/{author}-video.mp4"
```

**Decision Logic:**

| Video Duration | Processing Method |
|---------------|-------------------|
| ≤ 2 minutes (120 sec) | **Gemini 2.5 Pro Vision** — provides transcript + visual analysis |
| > 2 minutes | **Whisper only** — audio transcription only |

**Go to appropriate section:**
- **If ≤2 min:** Skip to STEP 4g: Gemini Vision Analysis
- **If >2 min:** Continue to STEP 4c: Download Video → Whisper transcription

#### Step 4b: Download Video

```bash
curl -L "VIDEO_URL" -o /tmp/{author}-video.mp4
```

**If download fails:**
- Check URL is complete (not truncated)
- Try with `-L` flag for redirects
- Verify internet connection

#### Step 4c: Extract Audio

```bash
ffmpeg -i /tmp/{author}-video.mp4 -vn -acodec libmp3lame -q:a 2 /tmp/{author}-audio.mp3
```

**If ffmpeg fails:**
- Verify ffmpeg is installed: `ffmpeg -version`
- Check video file exists and is valid: `ls -la /tmp/{author}-video.mp4`
- Try different audio codec: `-acodec aac` instead of `libmp3lame`

#### Step 4d: Transcribe with Whisper

```bash
curl -s -X POST https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F "file=@/tmp/{author}-audio.mp3" \
  -F "model=whisper-1" \
  -F "response_format=text"
```

**If Whisper fails:**
- Verify OPENAI_API_KEY is set: `echo $OPENAI_API_KEY`
- Check API key is valid
- Verify audio file exists: `ls -la /tmp/{author}-audio.mp3`
- If "file too large" — audio file may be too long; Whisper supports up to 25MB

#### Step 4e: Save Transcript

```bash
# Save to raw/x-video-transcripts/
echo "$TRANSCRIPT" > "raw/x-video-transcripts/{author}-{tweet-id}-transcript.txt"
```

#### Step 4f: CLEANUP (MANDATORY)

**Delete temp files after every transcription:**
```bash
rm /tmp/{author}-video.mp4 /tmp/{author}-audio.mp3
```

**If cleanup fails:**
- Files may be in use — check with `lsof /tmp/{author}-*`
- Manual delete if needed: `rm -f /tmp/{author}-*`

---

#### Step 4g: Gemini Vision Video Analysis (Videos ≤2 min ONLY)

**When to use:** When video duration is ≤2 minutes (120 seconds)

**CRITICAL:** For short videos, Gemini 2.5 Pro Vision provides both transcript + visual analysis. No need to run Whisper separately.

**Prerequisites:**
- `$GEMINI_API_KEY` environment variable must be set (check `~/.ft-bookmarks/.env` if not in environment)
- Video has been downloaded to `/tmp/{author}-video.mp4`

**Action:**

1. **Check API key is set:**
```bash
echo $GEMINI_API_KEY
# If empty, check .env file:
cat ~/.ft-bookmarks/.env | grep GEMINI
```
If empty, source from .env or ask user for the API key.

2. **Send video to Gemini Vision:**
```bash
curl -s -X POST "https://generativelanguage.googleapis.com/v1/models/gemini-2.5-pro-preview-06-05:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{
      "parts": [
        {"text": "Analyze this video thoroughly. Provide: 1) A complete transcript of any spoken content, 2) Description of all visual elements, 3) Any text visible in the video, 4) Overall context and topic. Return as JSON with keys: transcript, visual_description, visible_text, summary."},
        {"video_data": "'"$(base64 -w0 /tmp/${author}-video.mp4)"'"}
      ]
    }],
    "generationConfig": {
      "responseMimeType": "application/json",
      "temperature": 0.2
    }
  }'
```

3. **Save raw JSON response:**
```bash
# Save to raw/x-video-analyses/
curl_output > "raw/x-video-analyses/{author}-{tweet-id}-video-analysis.json"
```

**File naming:** `{author-handle}-{tweet-id}-video-analysis.json`

4. **Create wiki page from analysis:**
```markdown
---
title: "Video Analysis: {author} - {tweet-id}"
date_created: YYYY-MM-DD
date_modified: YYYY-MM-DD
summary: "Gemini Vision analysis of {tweet-id} video from {author}"
tags: [video-analysis, {category}]
type: source
status: draft
---

# Video Analysis: {author} - {tweet-id}

**Source:** [Tweet](https://x.com/{author}/status/{tweet-id})

## Transcript
{transcript_from_json}

## Visual Description
{visual_description_from_json}

## Visible Text
{visible_text_from_json}

## Summary
{summary_from_json}
```

5. **Cleanup temp files:**
```bash
rm /tmp/{author}-video.mp4
```

**Note:** For videos >2 minutes, continue with Whisper-only transcription (Steps 4c-4f) — skip this step.

---

### STEP 5: Handle External Links

**When to use:** When `externalLink` is present and is NOT an x.com link

**First, determine link type:**

```javascript
const link = document.querySelector('[data-testid="tweet"] a[href*="://"]');
const href = link?.href || '';

// Categorize the link
const isGitHub = href.includes('github.com') || href.includes('github.io');
const isTelegram = href.includes('t.me');
const isXArticle = href.includes('x.com') || link?.textContent?.includes('Article') || document.body.textContent.includes('Article');
const isGeneralExternal = !isGitHub && !isTelegram && !isXArticle;

console.log(JSON.stringify({ 
  href: href, 
  isGitHub: isGitHub, 
  isTelegram: isTelegram,
  isXArticle: isXArticle,
  isGeneralExternal: isGeneralExternal 
}));
```

**If GITHUB link:**
1. **Navigate to the repo:**
   ```javascript
   const link = document.querySelector('[data-testid="tweet"] a[href*="://"]');
   if (link) link.click();
   ```

2. **Wait for page load** (2-3 seconds)

3. **Extract repo info:**
   ```javascript
   // Get repo name from URL
   const repoPath = window.location.href.replace('https://github.com/', '').split('/');
   const repoName = repoPath[1] || repoPath[0];
   const owner = repoPath[0];
   
   // Get README or description
   const readme = document.querySelector('[data-testid="readme"]')?.textContent || 
                  document.querySelector('.markdown-body')?.textContent ||
                  document.body.innerText.substring(0, 3000);
   
   console.log(JSON.stringify({
     owner: owner,
     repo: repoName,
     url: window.location.href,
     description: readme.substring(0, 2000)
   }));
   ```

4. **Save to `raw/x-github-repos/`:**
   ```
   Filename: {author}-{tweet-id}-github-{repo-name}.md
   
   Content:
   # {owner}/{repo}
   
   URL: {url}
   
   Description/Tools: {extracted text}
   
   Source Tweet: https://x.com/{author}/status/{tweet-id}
   ```

**If TELEGRAM link (t.me):**
1. **Note the channel** — Cannot extract content from Telegram without API access
2. **Save to `raw/x-external-links/`:**
   ```
   Filename: {author}-{tweet-id}-link-telegram.txt
   
   Content:
   Telegram Channel: {channel-username}
   Source Tweet: https://x.com/{author}/status/{tweet-id}
   Note: Content not accessible without Telegram API
   ```

**If GENERAL EXTERNAL link:**
1. **Click the link:**
   ```javascript
   const link = document.querySelector('[data-testid="tweet"] a[href*="://"]');
   if (link) link.click();
   ```

2. **Wait for navigation** (2-3 seconds)

3. **Capture what's available:**
   ```javascript
   console.log('Title: ' + document.title);
   console.log('URL: ' + window.location.href);
   console.log('Content preview: ' + document.body.innerText.substring(0, 2000));
   ```

4. **Save to `raw/x-external-links/`:**
   ```
   Filename: {author}-{tweet-id}-link-{domain}.txt
   
   Content:
   Title: {page title}
   URL: {actual URL}
   Content Preview: {extracted text}
   Source Tweet: https://x.com/{author}/status/{tweet-id}
   ```

**Also check thread comments for external links:**
Sometimes links are posted in replies, not in the main tweet.

```javascript
const posts = document.querySelectorAll('[data-testid="cellInnerDiv"]');
const allLinks = [];

posts.forEach((post, idx) => {
  const links = post.querySelectorAll('a[href]');
  links.forEach(link => {
    const href = link.href;
    if (href && !href.includes('x.com') && !href.includes('twitter.com') && href.includes('://')) {
      allLinks.push({ postIndex: idx, url: href, text: link.textContent });
    }
  });
});
console.log(JSON.stringify(allLinks));
```

---

### STEP 6: Handle Articles (X Native)

**When to use:** When the content is an X native article (has "Article" text or appears as article preview card)

**Indicators:**
- "Article" text visible in tweet
- Article cover image (not a regular image)
- Quote tweet with article preview
- External link that is from x.com article domain

**Action:**

1. **Identify the article element:**
   ```javascript
   // Look for Article text or article preview card
   const articleElement = document.querySelector('text=Article')?.closest('a') || 
                          document.querySelector('[data-testid="tweet"] a[href*="://"]');
   if (articleElement) articleElement.click();
   ```

2. **Wait for article page to load** (2-3 seconds)

3. **Extract article content:**
   ```javascript
   console.log('Article title: ' + document.title);
   console.log('Article body: ' + document.body.innerText.substring(0, 8000));
   ```

4. **Extract any inline images** in the article:
   ```javascript
   document.querySelectorAll('img[src*="twimg.com"], img[src*="pbs.twimg.com"]').forEach((img, i) => {
     console.log(`Article image ${i+1}: ${img.src}`);
   });
   ```

5. **Save as markdown** to `raw/articles/{author}-{tweet-id}-article.md`
   - Include title, full article text, any inline images found
   - Note any external links in the article body

---

### STEP 7: Extract Images

**When to use:** When `imageCount > 0` OR when returning from handling an Article (Step 6) — images can exist in both tweets AND articles.

**CRITICAL:** Use ScrapeCreators to get actual image URLs. Browser snapshot only shows relative links like `/photo/1`, NOT actual image URLs.

**Action:**

1. **Use ScrapeCreators `twitter_tweet` endpoint to get image URLs:**
   ```
   mcp__scrape-creators__v1_twitter_tweet
   ```
   With parameter: `url: "https://twitter.com/{author_handle}/status/{tweet_id}"`

2. **Extract image URLs from response:**
   The API returns `media` array with actual image URLs:
   ```json
   {
     "media": [
       {
         "type": "photo",
         "media_url": "https://pbs.twimg.com/media/xxx.jpg?format=jpg&name=large",
         "url": "https://twitter.com/i/spaces/..."
       }
     ]
   }
   ```

   Extract from:
   - `media[].media_url` — direct image URL
   - Or build from: `https://pbs.twimg.com/media/{id}.jpg`

3. **Download each image:**
   ```bash
   curl -L "IMAGE_URL" -o "raw/x-article-images/{author}-{tweet-id}-image-{n}.{ext}"
   ```

**Naming:** `{author-handle}-{tweet-id}-image-{sequence-number}.{extension}`

**DO NOT use browser snapshot for image URLs** — it only shows relative links like `/photo/1`, not downloadable URLs.

**Edge cases:**
- **Image download fails:** Retry once, check URL is complete
- **Multiple images in one tweet:** Number sequentially (image-1, image-2, etc.)
- **Thread has images in multiple posts:** Use ScrapeCreators for each post to get images
- **Article has inline images:** Same process — use ScrapeCreators to get URLs

---

### STEP 7b: Image Analysis with Gemini Vision

**When to use:** After Step 7 when images have been successfully extracted

**CRITICAL:** Analyze ALL extracted images with Gemini 2.5 Pro Vision. Each image gets its own analysis.

**Prerequisites:**
- `$GEMINI_API_KEY` environment variable must be set (check `~/.ft-bookmarks/.env` if not in environment)
- Images have been downloaded to `raw/x-article-images/`
- `image-analysis` skill is available

**Action:**

1. **Check API key is set:**
```bash
echo $GEMINI_API_KEY
# If empty, check .env file:
cat ~/.ft-bookmarks/.env | grep GEMINI
```
If empty, source from .env or ask user for the API key.

2. **Invoke the image-analysis skill:**

For each extracted image, invoke the `image-analysis` skill with:
- `image_path`: Path to the downloaded image
- `author`: Author handle
- `tweet_id`: Tweet ID
- `image_number`: Sequence number (1, 2, 3, etc.)
- `category`: Primary category from the bookmark

```bash
# The skill will:
# 1. Read the analysis prompt from .claude/skills/image-analysis/prompts/analysis.md
# 2. Send image + prompt to Gemini 2.5 Pro Vision
# 3. Save raw JSON to raw/x-image-analyses/{author}-{tweet-id}-image-{n}-analysis.json
# 4. Create wiki page in wiki/x-image-analyses/{author}-{tweet-id}-image-{n}-analysis.md
```

**File naming:** `{author-handle}-{tweet-id}-image-{n}-analysis.json`

**Output locations:**
- Raw JSON: `raw/x-image-analyses/{author}-{tweet-id}-image-{n}-analysis.json`
- Wiki page: `wiki/x-image-analyses/{author}-{tweet-id}-image-{n}-analysis.md`

**Note:** The image-analysis skill uses the comprehensive analysis framework from [image-analysis skill](.claude/skills/image-analysis/) which includes:
- Metadata (confidence_score, image_type, primary_purpose)
- Composition (rule_applied, focal_points, visual_hierarchy, balance)
- Color profile (dominant_colors with hex values, palette, temperature, saturation)
- Lighting (type, direction, quality, shadows, highlights)
- Technical specs (medium, style, texture, sharpness, depth_of_field)
- Subject analysis (primary_subject, facial_expression, hair, hands, body_positioning)
- Background (setting_type, elements_detailed, wall_surface)
- Generation parameters (prompts, keywords, technical_settings)

4. **Create wiki page from analysis:**
```markdown
---
title: "Image Analysis: {author} - {tweet-id} - Image {n}"
date_created: YYYY-MM-DD
date_modified: YYYY-MM-DD
summary: "Gemini Vision analysis of image {n} from {tweet-id} by {author}"
tags: [image-analysis, {category}]
type: source
status: draft
---

# Image Analysis: {author} - {tweet-id} - Image {n}

**Source:** [Tweet](https://x.com/{author}/status/{tweet-id})

## Visual Description
{visual_description_from_json}

## Visible Text
{visible_text_from_json}

## Context
{context_from_json}

## Notable Details
{notable_details_from_json}
```

**Note:** Process ALL images — don't skip any. If tweet has 4 images, create 4 separate analysis files.

---

### STEP 8: Confirm Single Tweet (No Storage Needed)

**When to use:** When it's a single tweet with no replies, no images, no video, and no external links.

**Rationale:** Single tweets are already stored in FT bookmarks and indexed. Only content that does NOT appear in FT bookmarks (threads, articles, videos, external links, images) needs special storage.

**Action:**

1. **Analyze the tweet:**
   ```javascript
   const tweet = document.querySelector('[data-testid="tweet"]');
   const tweetText = tweet?.textContent || '';
   
   // Check what's present
   const hasImages = document.querySelectorAll('img[src*="twimg.com"]').length > 0;
   const hasVideo = tweetText.includes('Embedded video') || tweetText.includes('Play Video');
   const hasExternalLink = document.querySelector('[data-testid="tweet"] a[href*="://"]') !== null;
   
   console.log(JSON.stringify({
     text: tweetText.substring(0, 100),
     hasImages: hasImages,
     hasVideo: hasVideo,
     hasExternalLink: hasExternalLink
   }));
   ```

2. **Decision:**
   - **If hasVideo = true:** Go to STEP 4: Handle Video
   - **If hasExternalLink = true:** Go to STEP 5: Handle External Links
   - **If hasImages = true:** Go to STEP 7: Extract Images
   - **If all false:** This is a simple single tweet. DO NOT save to vault. ~ft-bookmarks already has it.
   - **If all false:** This is a simple single tweet. DO NOT save to vault. ~ft-bookmarks already has it.

3. **Exit early (no file creation):**
   ```
   Single tweet confirmed. Already stored in ~ft-bookmarks. No vault storage needed.
   Move to source summary creation.
   ```

**Summary:** Single tweets → ~ft-bookmarks has them → skip vault storage. Only threads, articles, videos, images, and external links → vault storage required.

---

## ERROR HANDLING REFERENCE

### If Session Expired (Redirected to Login)

1. Re-inject cookies (get fresh from DevTools if needed)
2. Navigate to URL again
3. Take snapshot to verify login form is NOT present
4. If still login page → cookies are invalid, need new session

### If Rate Limited (429 Error)

1. Wait 5-10 seconds
2. Retry navigation
3. If persists, consider using ScrapeCreators API instead of browser

### If Content Doesn't Load

1. Scroll down multiple times (at least 3)
2. Click "Show more" buttons if present
3. Wait for lazy-loaded content (2-3 seconds after scroll)
4. Take snapshot to diagnose

### If Video Download Fails

1. Verify URL is complete (not truncated in response)
2. Try with curl `-L` flag for redirects
3. Check network connectivity
4. Try alternative video variant (different bitrate)

### If Whisper Transcription Fails

1. Verify `OPENAI_API_KEY` environment variable is set
2. Check API key is valid and has credits
3. Verify audio file exists and is not corrupted
4. Try with smaller audio file or shorter clip

### If ffmpeg Fails

1. Verify ffmpeg is installed: `ffmpeg -version`
2. Check video file exists and is valid format
3. Try alternative codec: `aac` instead of `libmp3lame`

---

## COMPLETION CRITERIA

**You are finished when ALL of the following are true:**

1. ✅ Tweet/thread has been analyzed (Step 2 evaluation completed)
2. ✅ All identified content types have been processed:
   - Thread content → saved to `raw/x-threads/`
   - Video(s) → transcribed and saved to `raw/x-video-transcripts/`
   - External links → saved to `raw/x-external-links/`
   - GitHub repos → saved to `raw/x-github-repos/`
   - X Articles → saved to `raw/articles/`
   - Images → saved to `raw/x-article-images/`
3. ✅ All temp files deleted (Step 4f cleanup completed)
4. ✅ Files named correctly per naming conventions

---

## WHAT NOT TO DO

- ❌ Do NOT transcribe videos via browser — use ScrapeCreators + Whisper only
- ❌ Do NOT skip cookie injection — session will fail
- ❌ Do NOT leave temp files (video.mp4, audio.mp3) on disk — always cleanup
- ❌ Do NOT use high bitrate videos — unnecessary cost, lowest bitrate works for audio
- ❌ Do NOT mix output directories — follow naming conventions exactly
- ❌ Do NOT try to login manually — always re-inject cookies

---

## AFTER COMPLETION

**When you finish extracting ALL content from ALL tweets in the batch:**

➡️ **Return to wiki-backlog skill for Step 3: wiki-ingest**

(wiki-backlog will create source summaries in wiki/sources/)