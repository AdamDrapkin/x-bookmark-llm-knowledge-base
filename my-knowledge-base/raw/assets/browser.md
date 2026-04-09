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
4. **Check OpenAI API key is available** in environment variables

---

## OUTPUT LOCATIONS

```
raw/
├── x-article-images/       # All images from tweets and articles
├── articles/               # Full X native article content (markdown)
├── x-threads/              # Thread snapshots (text only)
└── x-video-transcripts/   # Video transcripts (from any source)
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

---

### STEP 2: Analyze What Content Exists on Page

**Action:** Take a snapshot and evaluate the page to determine content types present.

**Use this evaluation script:**
```javascript
// Check for main tweet content
const tweet = document.querySelector('[data-testid="tweet"]');
const tweetText = tweet?.textContent || '';

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
| postCount > 1 | Go to STEP 3: Extract Thread |
| hasVideo = true | Go to STEP 4: Handle Video |
| externalLink exists AND is NOT x.com | Go to STEP 5: Handle External Link |
| Content appears to be X Article | Go to STEP 6: Handle Articles |
| imageCount > 0 | Go to STEP 7: Extract Images |
| Single tweet only (no media, no links) | Go to STEP 8: Confirm & Exit (already in FT bookmarks) |

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

### STEP 4: Handle Video Content (ScrapeCreators + Whisper)

**When to use:** When `hasVideo = true` or when the tweet mentions "Embedded video" or "Play Video"

**CRITICAL:** Do NOT try to transcribe via browser. Use ScrapeCreators API + Whisper.

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

**CRITICAL:** Extract images BEFORE navigating away from any page. If you just opened an article, extract images from that page first before switching tabs.

**Action:**

1. **Check for multiple tabs (if article opened in new tab):**
   ```javascript
   // First, check if there's more than one tab
   console.log('Current URL: ' + window.location.href);
   console.log('Page title: ' + document.title);
   ```
   
   **If article opened in new tab and you need to switch:**
   - Use `mcp__glance__browser_tab_list` to see actual open tabs
   - If there are 2 tabs but only 1 shows, try switching to the second tab using `mcp__glance__browser_tab_select` with the tab ID
   - If tabs cannot be reliably detected, navigate directly to the article URL instead

2. **Get all image URLs from current page:**
   ```javascript
   const images = document.querySelectorAll('img[src*="twimg.com"], img[src*="pbs.twimg.com"], img[src*="pic.x.com"]');
   images.forEach((img, i) => {
     const ext = img.src.split('.').pop().split('?')[0] || 'jpg';
     console.log(`${i+1}|${ext}|${img.src}`);
   });
   ```

3. **Download each image:**
   ```bash
   curl -L "IMAGE_URL" -o "raw/x-article-images/{author}-{tweet-id}-image-{n}.{ext}"
   ```

**Naming:** `{author-handle}-{tweet-id}-image-{sequence-number}.{extension}`

**Workflow for Article Images:**

| If... | Then... |
|-------|---------|
| Click article → opens in same tab | Extract images BEFORE navigating back |
| Click article → opens in new tab | Switch to new tab, extract images, then close it |
| Multiple tabs detected | Use `tab_list` to find the article tab, extract images, close article tab |
| Can't detect article tab | Navigate back to original tweet, note that article images need manual extraction |

**Edge cases:**
- **Image download fails:** Retry once, check URL is complete
- **Multiple images in one tweet:** Number sequentially (image-1, image-2, etc.)
- **Thread has images in multiple posts:** Extract all from each post
- **Article has inline images:** Extract these separately, append to the same image sequence
- **Tab mismatch:** If `tab_list` shows wrong count, try navigating directly to the URL you clicked instead of relying on tab switching

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

**When you finish extracting all content from the tweet:**

➡️ **Move on to creating a source summary in `wiki/sources/`**

Follow the wiki sources step in CLAUDE.md to create the source summary markdown file.

This source summary becomes part of the LLM Knowledge Base for future reference.