# Wiki Schema

## Identity
- **Path:** /Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base/
- **Domain:** Personal knowledge base from X/Twitter bookmarks
- **Source types:** Bookmarks, URLs, articles, transcripts, images, videos
- **Created:** 2026-04-09

## Directory Structure

### Raw/ — Source material (immutable - skills never modify)
```
raw/
├── assets/                      # SOPs and reference documents
│   ├── bookmark-classification.md
│   ├── browser.md               # Browser automation SOP
│   ├── backlog-log.md           # Batch tracking for backlog processing
│   ├── pipeline.py             # Main pipeline orchestration
│   ├── pipeline_core.py         # Core pipeline logic and API client
│   ├── pipeline_live.py         # Live pipeline runner
│   ├── phase-startup-prompts.md # Startup prompts for each phase
│   ├── x-api-v2-research.md    # X API v2 research and documentation
│   └── hooeem-llm-knowledge-base-guide.md  # Reference guide
├── bookmarks.md                # Raw bookmark data
├── x-article-images/            # All images extracted from tweets and articles
├── x-image-analyses/            # Gemini Vision JSON analysis for images
├── x-video-analyses/            # Gemini Vision JSON analysis for videos (≤2 min)
├── x-articles/                  # Full X native article content (markdown)
├── x-external-links/            # External link content
├── x-github-repos/             # GitHub repository information
├── x-threads/                   # Thread snapshots (text only)
└── x-video-transcripts/        # Video transcripts (Whisper for videos >2 min)
```

### Wiki/ — Compiled knowledge (LLM-maintained)
```
wiki/
├── index.md                     # Master index with one-line summaries
├── log.md                       # Append-only changelog
├── backlog-log.md               # Tracking processed bookmarks
├── decisions/                   # Decision log for process changes
├── sources/                     # Source summaries (one per file)
├── concepts/                    # Concept articles
├── entities/                    # People, organisations, tools
├── syntheses/                   # Cross-cutting analysis
├── outputs/                     # Filed query answers
│   ├── pipeline-live.log        # Append-only log of live pipeline runs
│   └── manifest-batch-*.json   # Archived batch manifests from completed pipeline runs
├── qa-pairs/                    # QA pairs for fine-tuning
├── attachments/                  # Wiki attachments
├── x-image-analyses/            # Gemini Vision analysis wiki pages for images
├── x-video-analyses/            # Gemini Vision analysis wiki pages for videos
└── x-github-repos/             # GitHub repository analysis pages
```

## Page Frontmatter
Every wiki page must have:
```yaml
---
title: "Page Title"
date_created: YYYY-MM-DD
date_modified: YYYY-MM-DD
summary: "One to two sentences describing this page"
tags: [topic-tag, domain-tag]
type: concept | entity | source | synthesis | output
status: draft | review | final
---
```

## Cross-References
Use `[[wikilinks]]` where slug = filename without `.md`
Example: `[[attention-is-all-you-need]]` → `wiki/concepts/attention-is-all-you-need.md`

## Log Entry Format
```
## [YYYY-MM-DD] <operation> | <title>
```
Operations: init, ingest, query, update, lint, backlog-process

## Index Categories
- Sources
- Entities
- Concepts
- Syntheses
- Outputs
- Maintenance (for lint reports)

## Key File Locations
- Bookmark database: `~/.ft-bookmarks/bookmarks.db`
- Raw assets: `raw/assets/` (includes pipeline scripts, SOPs, and backlog-log)
