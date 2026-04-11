# Bookmark Classification

## Overview
Tag taxonomy for X bookmarks in `~/.ft-bookmarks/bookmarks.db`. The pipeline script reads this file at runtime to classify bookmarks. Add new tags here — never hardcode them in Python.

## Source
- **Database**: `~/.ft-bookmarks/bookmarks.db` (SQLite)
- **Query**: `sqlite3 ~/.ft-bookmarks/bookmarks.db "<SQL>"`
- **Pipeline reads**: This file is loaded by `pipeline.py` at startup for topic classification.

---

## Primary Categories

```
ai-agents
ai-business
ai-research
ai-tools-comparison
claude-code
content-creation
image-generation
learning
local-ai
n8n-automation
open-source
philosophy
pricing-costs
productivity
prompt-engineering
seo-marketing
tool-releases
unclassified
video-generation
web-development
```

## Sub-Tags

```
ai-business, marketing-automation, growth
productivity, self-improvement, career
prompt-engineering, ai-prompts, tutorial
n8n, workflow-automation, automation
open-source, tools, github
claude-code, ai-development, vibe-coding
ai-tools, comparison, reviews
content-creation, video-editing, short-form
image-generation, midjourney, stable-diffusion, dall-e
ai-research, papers, benchmarks
learning, courses, resources
local-ai, ollama, self-hosted
philosophy, mindset, strategy
pricing-costs, api-pricing, token-costs
seo-marketing, social-media, analytics
tool-releases, announcements, updates
video-generation, sora, runway, kling
web-development, frontend, backend, deployment
```

---

## Content Type Classification (API-derived)

These are NOT tags — they describe WHAT the tweet contains. Detected automatically from X API response signals. The pipeline handles this internally.

| Content Type | API Signal | Processing |
|---|---|---|
| standalone | No refs, conversation_id == tweet_id | Text only |
| thread_starter | conversation_id == tweet_id, has self-replies | Walk thread |
| thread_reply | conversation_id != tweet_id | Walk upward |
| retweet | referenced_tweets contains type: retweeted | Fetch original, 2 entries |
| quote_tweet | referenced_tweets contains type: quoted | Include quoted content |
| reply | referenced_tweets replied_to, different author | Walk to parent |

| Content Flag | API Signal | Processing |
|---|---|---|
| has_images | media type photo | Download + Gemini Flash |
| has_video | media type video | Download + Gemini Pro (≤2m) or Whisper (>2m) |
| has_gif | media type animated_gif | Skip |
| has_youtube | entities.urls youtube.com/youtu.be | ScrapeCreators transcript |
| has_github | entities.urls github.com | Fetch README |
| has_x_article | entities.urls x.com article | Fetch content |
| has_external_link | entities.urls non-X domain | Fetch + extract |
| no_media | No attachments, no links | Text-only source |

---

## Classification Rules

### For Already-Classified Bookmarks
If `primary_category` exists in bookmarks.db, use it. The pipeline does not reclassify.

### For Unclassified Bookmarks
1. Check tweet text against Primary Categories above
2. Check against Sub-Tags for more specific classification
3. If no existing tag fits, add a new sub-tag to this file
4. Update bookmarks.db: `UPDATE bookmarks SET primary_category = 'X', categories = '["X", "Y"]' WHERE id = '...';`

### Adding New Tags
When the pipeline encounters content that doesn't fit existing categories:
1. The pipeline appends the new tag to the Sub-Tags section above
2. The tag follows naming convention: `lowercase-hyphenated`
3. Tags are never removed — only added
4. New primary categories require manual review (rare)

---

## Query Commands

```bash
# Get unclassified bookmarks
sqlite3 ~/.ft-bookmarks/bookmarks.db "SELECT id, text, author_handle FROM bookmarks WHERE primary_category IS NULL OR primary_category = '' LIMIT 10;"

# Get bookmarks by category
sqlite3 ~/.ft-bookmarks/bookmarks.db "SELECT id, text, author_handle FROM bookmarks WHERE primary_category = 'ai-agents' LIMIT 10;"

# Count by category
sqlite3 ~/.ft-bookmarks/bookmarks.db "SELECT primary_category, COUNT(*) FROM bookmarks GROUP BY primary_category ORDER BY COUNT(*) DESC;"

# Update classification
sqlite3 ~/.ft-bookmarks/bookmarks.db "UPDATE bookmarks SET primary_category = 'prompt-engineering', categories = '[\"prompt-engineering\", \"tutorial\"]' WHERE id = 'TWEET_ID';"
```

---

## Keyword Clusters

Used by the pipeline's auto-classification. URL signals (strongest) + multi-word keyword matches (additive).
Edit these to tune classification accuracy. The pipeline reads this section at runtime.

```
ai-agents: ai agent, autonomous agent, agent framework, agentic, multi-agent, crew ai, autogen
ai-business: ai startup, saas, monetize ai, ai service, ai agency, client acquisition
ai-research: arxiv, research paper, benchmark, state of the art, fine-tuning, fine tuning, transformer, attention mechanism
ai-tools-comparison: vs , versus, compared to, alternative to, better than, which is better
claude-code: claude code, claude.ai, anthropic, claude sonnet, claude opus, claude haiku
content-creation: video editing, short form, content creator, tiktok, reels, content strategy, hook
image-generation: midjourney, stable diffusion, dall-e, flux, image generation, comfyui, controlnet
learning: tutorial, course, learn how, step by step, beginner guide, explained, walkthrough
local-ai: ollama, self-hosted, local llm, run locally, on-device, llama.cpp, private ai
n8n-automation: n8n, workflow automation, automation workflow, zapier alternative, make.com
open-source: open source, open-source, github.com, self hosted, foss, mit license, apache license
philosophy: mindset, philosophy, stoic, first principles, mental model, think and grow rich
pricing-costs: pricing, api cost, token cost, per month, free tier, pay as you go
productivity: productivity, time management, workflow, second brain, notion, obsidian, pkm
prompt-engineering: system prompt, prompt engineering, chain of thought, few-shot, prompt template, jailbreak
seo-marketing: seo, marketing, growth hack, social media strategy, analytics, conversion
tool-releases: just launched, now available, announcing, introducing, new release, just shipped
video-generation: sora, runway, kling, video generation, text to video, luma, pika
web-development: react, nextjs, next.js, frontend, backend, api endpoint, typescript, tailwind, vercel
```

### URL Signal Overrides (highest priority)

```
github.com → open-source
arxiv.org → ai-research
huggingface.co → ai-research
n8n.io → n8n-automation
youtube.com → content-creation (weak signal, 0.5)
```

### Processed Tag

After a bookmark completes the full pipeline, the script adds `"processed"` to its `categories` JSON array in bookmarks.db. Query for unprocessed:

```sql
SELECT * FROM bookmarks WHERE categories NOT LIKE '%processed%' OR categories IS NULL;
```