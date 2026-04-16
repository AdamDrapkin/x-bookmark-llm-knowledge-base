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
│   ├── pipeline_monitor.py     # Monitors X list + watchlist
│   ├── watchlist.md             # Extra accounts to track
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
│   ├── pipeline-monitor.log      # Append-only log of monitor runs
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

## Cron Jobs
All cron jobs are stored in the system crontab and managed via `crontab -e`.

### Job Reference Table
| Job | Script | Schedule (EST) | Purpose |
|-----|--------|----------------|---------|
| QA Orchestrator | `qa_orchestrator.py` | Every 15 min (`*/15 * * * *`) | Generates QA pairs for wiki sources |
| Pipeline Live | `pipeline_live.py` | 10:15 AM – 7:45 PM, every 30 min (`15,45 10-19 * * *`) | Processes new bookmarks through Phases 1-4 |
| QA Council Check | `qa_check.py` | 10 AM and 8 PM daily (`0 10 * * *`, `0 20 * * *`) | Runs QA validation checks |
| Wiki Lint | `lint_check.py` | 8 PM daily (`0 20 * * *`) | Runs lint_check.py for quality assurance |
| Pipeline Monitor | `pipeline_monitor.py` | 10 AM – 7:30 PM, every 30 min (`*/30 10-19 * * *`) | Monitors X list + watchlist, inserts new bookmarks |

### Pipeline Flow
```
pipeline_monitor.py (every 30 min)
        │
        ▼
bookmarks.db (new unprocessed bookmarks)
        │
        ▼
pipeline_live.py (every 30 min at :15/:45)
        │
        ├── Phase 1: Extract
        ├── Phase 2: Analyze
        ├── Phase 3: Compile (wiki/sources/, wiki/concepts/)
        └── Phase 4: Finalize (wikilinks, cross-references)
        │
        ▼
qa_check.py (10 AM + 8 PM) ── QA validation
        │
        ▼
qa_orchestrator.py (every 15 min) ── QA pairs generation
        │
        ▼
lint_check.py (8 PM) ── Quality report
```

### Cron Management Commands
- View current crontab: `crontab -l`
- Edit crontab: `crontab -e`
- Pause all jobs: `crontab -r` (removes all jobs)
- Restore jobs: Apply the cron configuration file
