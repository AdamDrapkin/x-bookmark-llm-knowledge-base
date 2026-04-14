# Synteo Intelligence — X Bookmark Pipeline

> AI-powered knowledge base built from your X/Twitter bookmarks. Transform saved content into a searchable, interconnected wiki with automated extraction, analysis, synthesis, and quality assurance.

## Status

| Component | Status | Notes |
|-----------|--------|-------|
| **Field Theory CLI** | ✅ Required | `npm install -g fieldtheory` |
| **Python Pipeline** | ✅ Active | 6 scripts in `raw/assets/` |
| **Wiki Structure** | ✅ Active | `wiki/sources/`, `wiki/concepts/`, `wiki/entities/` |
| **Skills Integration** | ✅ Active | 5 Claude skills for processing |
| **API Integration** | ✅ Active | MiniMax, Anthropic, Gemini |

---

## Overview

This pipeline transforms X/Twitter bookmarks into a personal knowledge wiki through a four-phase process:

1. **Phase 1 — Extract**: Fetch tweet content, download images/videos, save external links
2. **Phase 2 — Analyze**: Run image-analysis and video-analysis skills on media
3. **Phase 3 — Compile**: Generate source summaries, extract concepts/entities, create wiki pages
4. **Phase 4 — Finalize**: Run wiki-lint, QA council, update indexes, cleanup

### Two Operating Modes

| Mode | Command | Purpose |
|------|---------|---------|
| **Backlog** | `python raw/assets/pipeline.py` | Process next unprocessed batch from `backlog-log.md` |
| **Live** | `python raw/assets/pipeline_live.py` | Sync new bookmarks, process in batches of 10 |

---

## Prerequisites

### System Requirements

- **OS**: macOS (primary), Linux (supported)
- **Python**: 3.10+
- **System Tools**: `ffmpeg` (on PATH)
- **Browser**: Chrome (logged into X) — for session-based bookmark sync

### Required Installations

```bash
# Field Theory CLI (primary bookmark sync tool)
npm install -g fieldtheory

# Python dependencies
pip install requests anthropic python-dotenv pyyaml beautifulsoup4
```

### Required API Keys

| Environment Variable | Provider | Purpose | Required |
|---------------------|----------|---------|----------|
| `MINIMAX_API_KEY` | MiniMax | Primary LLM for wiki generation | **Yes** |
| `ANTHROPIC_API_KEY` | Anthropic | Claude for complex reasoning | Optional |
| `GEMINI_API_KEY` | Google | Gemini 2.5 for specific tasks | Optional |
| `X_API_BEARER_TOKEN` | X API v2 | Direct API access (alternative to session) | Optional |
| `FT_CT0` | Field Theory | Direct cookie auth (optional) | Optional |
| `FT_AUTH_TOKEN` | Field Theory | Direct cookie auth (optional) | Optional |

> **Note**: Primary operation uses MiniMax API. Other APIs provide fallback capabilities and specific feature support.

---

## Architecture

```
synteo-intelligence/
├── .env                          # API keys (not committed)
├── raw/
│   └── assets/
│       ├── pipeline.py           # Backlog mode entry point
│       ├── pipeline_live.py       # Live mode entry point
│       ├── pipeline_core.py       # Shared engine (29545 tokens)
│       ├── qa_check.py           # Standalone QA trigger
│       ├── lint_check.py         # Standalone lint runner
│       └── backlog-log.md        # Batch tracking
├── wiki/
│   ├── sources/                  # Source summary pages
│   ├── concepts/                 # Concept articles
│   ├── entities/                 # Entity pages
│   ├── qa-pairs/                 # QA council outputs
│   ├── outputs/                  # Pipeline logs/reports
│   ├── index.md                  # Main wiki index
│   └── log.md                    # Activity log
└── CLAUDE.md                     # LLM instructions
```

---

## Pipeline Scripts

### pipeline_core.py — Shared Engine

**Location**: `raw/assets/pipeline_core.py`

The central processing engine with all logic:

| Function Group | Functions |
|----------------|-----------|
| **Config** | `load_config()`, `init_environment()`, `full_path()` |
| **X API** | `XClient` class with `lookup_posts()`, `recent_search_conversation()` |
| **Classification** | `classify_primary_type()`, `classify_content_flags()`, `load_tag_taxonomy()` |
| **Backlog** | `parse_backlog_log()`, `get_batch_ids_from_backlog()`, `find_next_batch()`, `mark_batch_done()` |
| **Extraction** | `extract_urls_from_entities()`, `index_includes()` |
| **Pipeline Phases** | `run_phase1()`, `run_phase2()`, `run_phase3()`, `run_phase4()` |
| **QA/Lint** | `run_qa_council()`, `run_wiki_lint()`, `check_and_run_qa_if_needed()` |
| **Utilities** | `retry()`, `chunk_list()`, `today_str()`, `append_to_file()` |

**Dependencies**:
```python
import requests
import yaml
from anthropic import Anthropic
from bs4 import BeautifulSoup
from dotenv import load_dotenv
```

### pipeline.py — Backlog Mode

**Location**: `raw/assets/pipeline.py`

Processes bookmarks from `backlog-log.md`:

```
1. Find next unprocessed batch (status = 'next' or first 'not_started')
2. Get bookmark IDs from batch definition
3. Query bookmarks.db for those IDs
4. Filter against existing wiki sources
5. Run full pipeline (Phases 1-4)
6. Trigger QA if 20+ new sources since last run
7. Mark batch as processed in backlog-log.md
```

**Usage**:
```bash
python raw/assets/pipeline.py
python raw/assets/pipeline.py --skip-fallback    # Skip browser-extracted items
python raw/assets/pipeline.py --config custom.yaml
```

### pipeline_live.py — Live Mode

**Location**: `raw/assets/pipeline_live.py`

Syncs and processes new bookmarks continuously:

```
1. ft sync → Pull new bookmarks into ~/.ft-bookmarks/bookmarks.db
2. Query unprocessed → Bookmarks without 'processed' tag
3. Classify untagged → Keyword cluster matching from bookmark-classification.md
4. Batch into 10s → Dynamic batching
5. Phases 1-4 per batch → Extract, analyze, compile, finalize
6. Tag as processed → Adds 'processed' to categories in DB
7. QA event check → If 20+ new sources since last QA, fires QA council
```

**Usage**:
```bash
python raw/assets/pipeline_live.py
python raw/assets/pipeline_live.py --skip-sync      # Use existing DB state
python raw/assets/pipeline_live.py --skip-fallback # Skip browser-fallback items
```

### qa_check.py — Standalone QA Trigger

**Location**: `raw/assets/qa_check.py`

Manually triggers the QA council event:

```
Reads: wiki/qa-pairs/concept-index.json, wiki/sources/*.md
Writes: wiki/qa-pairs/batch-*-qa.json, wiki/qa-pairs/_index.md
API: MiniMax M2.7 via MINIMAX_API_KEY
Trigger: sources_since_last_qa >= 20
```

**Usage**:
```bash
python raw/assets/qa_check.py
```

### lint_check.py — Standalone Wiki Lint

**Location**: `raw/assets/lint_check.py`

Runs wiki-lint skill standalone:

```
Reads: All wiki/**/*.md pages for inventory
Writes: wiki/outputs/lint-{date}.md, wiki/outputs/_index.md
API: MiniMax M2.7 via MINIMAX_API_KEY (contradiction detection only)
Schedule: Daily 8 PM EST (via cron)
```

**Usage**:
```bash
python raw/assets/lint_check.py
```

---

## Field Theory CLI Integration

### What is Field Theory?

**Field Theory** (`ft`) is an open-source CLI tool that syncs and stores X/Twitter bookmarks locally, making them available to AI agents like Claude Code.

| Command | Description |
|---------|-------------|
| `ft sync` | Download and sync all bookmarks (Chrome session, no API required) |
| `ft sync --api` | Sync via OAuth API (cross-platform) |
| `ft search <query>` | Full-text search with BM25 ranking |
| `ft classify` | LLM classification via Claude or Codex |
| `ft categories` | Show category distribution |
| `ft stats` | Top authors, languages, date range |
| `ft list --author @username` | Filter by author |
| `ft list --category <tag>` | Filter by category |
| `ft list --domain <domain>` | Filter by subject domain |

### Installation

```bash
npm install -g fieldtheory
```

### Authentication Options

| Method | Command | Notes |
|--------|---------|-------|
| **Chrome Session** | `ft sync` | Default. Requires Chrome logged into X |
| **OAuth API** | `ft sync --api` | Cross-platform, requires OAuth setup |
| **Direct Cookies** | `ft sync --csrf-token CT0 --cookie-header "ct0=CT0; auth_token=TOKEN"` | Bypass Chrome |

### Data Storage

```
~/.ft-bookmarks/
├── bookmarks.jsonl     # Raw bookmark cache (one per line)
├── bookmarks.db        # SQLite FTS5 search index
├── bookmarks-meta.json # Sync metadata
└── oauth-token.json    # OAuth token (if using API mode)
```

---

## Claude Skills Integration

The pipeline invokes these skills for specialized processing:

| Skill | Path | Purpose |
|-------|------|---------|
| **wiki-ingest** | `~/.claude/skills/wiki-ingest/SKILL.md` | Create source summaries, concept pages |
| **qa-council** | `~/.claude/skills/qa-council/SKILL.md` | Generate QA pairs for verification |
| **wiki-lint** | `~/.claude/skills/wiki-lint/SKILL.md` | Find contradictions, orphan pages, broken links |
| **image-analysis** | `~/.claude/skills/image-analysis/SKILL.md` | Analyze images, generate descriptions |
| **video-analysis** | `~/.claude/skills/video-analysis/SKILL.md` | Analyze videos, extract transcripts |

### Skill Prompts

| Skill | Prompt Files |
|-------|--------------|
| **image-analysis** | `~/.claude/skills/image-analysis/prompts/analysis.md`, `classify-image.md`, `text-analysis.md` |
| **video-analysis** | `~/.claude/skills/video-analysis/prompts/analysis.md` |
| **wiki-ingest** | `~/.claude/skills/wiki-ingest/prompts/api-ingest.md` |
| **wiki-lint** | `~/.claude/skills/wiki-lint/prompts/api-lint.md` |

---

## API Configuration

### MiniMax API (Primary)

| Setting | Value |
|---------|-------|
| Base URL | `https://api.minimax.io/anthropic` |
| Default Model | `MiniMax-M2.7` |
| Max Retries | 3 |
| Retry Backoff | 2 seconds |

### Anthropic API (Fallback)

| Setting | Value |
|---------|-------|
| SDK | `anthropic` Python package |
| Use Case | Complex reasoning, specific Claude features |

### Google Gemini API

| Setting | Value |
|---------|-------|
| Base URL | `https://generativelanguage.googleapis.com/v1/models` |
| Flash Model | `gemini-2.5-flash` |
| Pro Model | `gemini-2.5-pro` |
| Use Case | Specific multimodal tasks |

### X API v2

| Setting | Value |
|---------|-------|
| Base URL | `https://api.x.com/2` |
| Auth | Bearer token (OAuth 2.0) |
| Rate Limit | 180 requests/15 min (GET), 50 requests/15 min (POST) |

---

## Configuration File (config.yaml)

While defaults are built-in, create `config.yaml` in `raw/assets/` for customization:

```yaml
wiki_root: /Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base
bookmarks_db: ~/.ft-bookmarks/bookmarks.db
env_file: /Users/adamdrapkin/Obsidian/synteo-intelligence/.env

api:
  gemini_flash_model: gemini-2.5-flash
  gemini_pro_model: gemini-2.5-pro
  minimax_model: MiniMax-M2.7
  max_retries: 3
  retry_backoff: 2

skills:
  wiki_ingest: ~/.claude/skills/wiki-ingest/SKILL.md
  qa_council: ~/.claude/skills/qa-council/SKILL.md
  wiki_lint: ~/.claude/skills/wiki-lint/SKILL.md
  image_analysis: ~/.claude/skills/image-analysis/SKILL.md
  video_analysis: ~/.claude/skills/video-analysis/SKILL.md
```

---

## Data Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   X Bookmarks   │────▶│  Field Theory   │────▶│  bookmarks.db   │
│   (X.com)       │     │     CLI         │     │  (SQLite FTS5)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    wiki/        │◀────│  pipeline.py    │◀────│  query_bookmarks│
│  sources/       │     │  (or live)     │     │     _db()       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  wiki/          │     │   Phase 4       │
│  concepts/      │     │  - wiki-lint   │
│  entities/      │     │  - qa-council  │
└─────────────────┘     └─────────────────┘
```

---

## Processing Pipeline Details

### Phase 1 — Extract

- **API Lookup**: Fetch full tweet data via X API v2
- **Media Download**: Images → `raw/x-article-images/`, Videos → `raw/x-video-transcripts/`
- **External Links**: Save as `.txt` to `raw/x-external-links/`
- **Fallback**: Browser extraction for items not in API

### Phase 2 — Analyze

- **Image Analysis**: Invoke `image-analysis` skill for each image
- **Video Analysis**: Invoke `video-analysis` skill for each video
- **Output**: Analysis saved to `wiki/x-image-analyses/` and `wiki/x-video-analyses/`

### Phase 3 — Compile

- **Source Summaries**: Create `{author}-{year}-{short-title}.md` in `wiki/sources/`
- **Concept Extraction**: Identify concepts, create/update pages in `wiki/concepts/`
- **Entity Extraction**: Identify entities, create/update pages in `wiki/entities/`
- **Linking**: Add `[[wikilinks]]` to connect content

### Phase 4 — Finalize

- **Wiki Lint**: Run `wiki-lint` skill to find issues
- **QA Council**: Run `qa-council` if 20+ new sources
- **Index Updates**: Update `wiki/index.md`, `wiki/sources/`, `wiki/concepts/`, `wiki/entities/`
- **Backlog Update**: Mark batch as processed in `backlog-log.md`
- **Cleanup**: Remove temp files

---

## Environment Variables (.env)

Create `.env` in project root:

```bash
# Required
MINIMAX_API_KEY=your_minimax_key_here

# Optional (for fallback/specific features)
ANTHROPIC_API_KEY=your_anthropic_key_here
GEMINI_API_KEY=your_gemini_key_here
X_API_BEARER_TOKEN=your_x_bearer_token_here

# Field Theory direct auth (optional)
FT_CT0=your_ct0_cookie
FT_AUTH_TOKEN=your_auth_token
```

> **WARNING**: Never commit `.env` to version control. Add to `.gitignore`.

---

## Wiki Structure

### Source Pages

**Location**: `wiki/sources/`

**Naming**: `{author}-{year}-{short-title}.md`

**Frontmatter**:
```yaml
---
title: "Page Title"
date_created: YYYY-MM-DD
date_modified: YYYY-MM-DD
summary: "One to two sentences describing this page"
tags: [topic-tag, domain-tag]
type: source
status: draft | review | final
---
```

### Concept Pages

**Location**: `wiki/concepts/`

**Naming**: `kebab-case-concept-name.md`

**Threshold**:
- Full page: Subject appears in 2+ sources
- Stub page: Single mention (frontmatter + one-line + link back)

### Entity Pages

**Location**: `wiki/entities/`

**Naming**: Entity-specific (person, company, product, etc.)

### QA Pairs

**Location**: `wiki/qa-pairs/`

**Naming**: `batch-{date}-qa.json`

### Outputs

**Location**: `wiki/outputs/`

**Contents**: Pipeline logs, lint reports, generated answers

---

## Scheduling

### Live Pipeline

Run manually or via cron:

```bash
# Daily at 7 AM
0 7 * * * cd /path/to/synteo-intelligence && python raw/assets/pipeline_live.py >> wiki/outputs/pipeline-live.log 2>&1
```

### Wiki Lint

```bash
# Daily at 8 PM EST
0 0 * * * cd /path/to/synteo-intelligence && python raw/assets/lint_check.py >> wiki/outputs/lint.log 2>&1
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `ft: command not found` | Run `npm install -g fieldtheory` |
| No bookmarks found | Ensure Chrome is logged into X, run `ft sync` |
| Rate limiting | Pipeline auto-retries with backoff |
| API errors | Check `.env` has valid API keys |
| Missing media | Ensure `ffmpeg` is installed |

### Debug Mode

Add `--verbose` or check pipeline logs in `wiki/outputs/pipeline-live.log`.

---

## Contributing

This is a personal knowledge base system. For modifications:

1. Read `CLAUDE.md` for LLM instructions
2. Check `backlog-log.md` for batch status
3. Review `wiki/log.md` for activity history

---

## Related Documentation

- [Field Theory CLI](https://www.fieldtheory.dev/cli/)
- [X API v2 Documentation](https://developer.x.com/en/docs/x-api)
- [Claude Code](https://claude.com/code)
- [MiniMax API](https://platform.minimax.io/)

---

## License

Personal use only. API keys and data are private.