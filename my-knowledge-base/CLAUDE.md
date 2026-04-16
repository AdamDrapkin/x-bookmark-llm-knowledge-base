# LLM Knowledge Base — Schema

## Core Instruction
- **Execute exactly what is asked** — Do not seek simpler approaches or shortcuts. The given command is the task. Follow it as specified.

## Quick Reference
- **Memory:** See [`.claude/memory.md`](.claude/memory.md) for operational rules and learnings. Update it when:
  - Discovering new patterns or errors in the workflow
  - Making process changes that affect future work
  - Learning what NOT to do from failed attempts

## Overview
Personal knowledge base on my X (previously Twitter) bookmarks across various topics. Raw sources live in `raw/`. Bookmarks live in `~/.ft-bookmarks/bookmarks.db` (SQLite). The compiled wiki lives in `wiki/`. You (the AI) maintain all wiki content.

**Full directory structure:** See [SCHEMA.md](SCHEMA.md)

## Pipeline System

### Automatic — New Content (pipeline_live.py)
Runs automatically via cron at 10 AM / 8 PM daily:
1. pipeline_monitor.py checks X list (47 accounts) + watchlist (8 accounts)
2. Inserts new posts into bookmarks.db (tagged as unprocessed)
3. pipeline_live.py picks up unprocessed bookmarks
4. Processes through Phases 1-4: extract → analyze → compile → finalize

### Manual — Backlog (pipeline.py)
Run manually when you want to process historical bookmarks:
1. Read backlog-log.md to see remaining batches
2. Run: python3 raw/assets/pipeline.py
3. Pipeline processes batches automatically

## File Conventions
- All filenames: kebab-case, lowercase (e.g., active-inference.md)
- Source summaries: `{author}-{year}-{short-title}.md`
- Every page MUST have YAML frontmatter:
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
- Use [[wikilinks]] for all internal cross-references
- Bold key terms on first use in each article

## Operations

### INGEST

#### Automatic (new bookmarks via pipeline_live.py)
1. pipeline_live.py creates source summary in wiki/sources/
2. Identifies concepts/entities → creates/updates pages
3. Adds [[wikilinks]] to connect content
4. Updates wiki/index.md
5. Appends to wiki/log.md
6. QA automatically generated via qa_orchestrator.py

#### Manual (backlog via pipeline.py)
- pipeline.py handles this automatically
- Run: python3 raw/assets/pipeline.py

### QUERY
1. Read wiki/index.md
2. Read relevant wiki pages
3. Synthesise answer with citations
4. Save as wiki/outputs/{question-slug}.md
5. Update wiki/index.md and wiki/log.md

### LINT
1. Run qa_lint.py — QA validation
2. Run fix_wikilinks.py — Fix broken wikilinks
3. Run gen_pending_terms.py — Generate pending terms
4. Run wiki-sync.py — Comprehensive sync with LLM regeneration
5. Fix remaining issues
6. Output lint report

## Key Python Scripts (raw/assets/)

| Script | Purpose |
|-------|--------|
| `fix_wikilinks.py` | Fix broken wikilinks (periods, piped links) |
| `gen_pending_terms.py` | Generate pending terms from low-mention links |
| `wiki-sync.py` | Comprehensive sync with MiniMax LLM (PARALLEL, 5 concurrent) |
| `qa_lint.py` | QA pairs validation |

## Monitoring

### Pipeline Monitor
1. Check pipeline_monitor.py cron: crontab -l | grep pipeline
2. Check latest insertions: sqlite3 ~/.ft-bookmarks/bookmarks.db "SELECT COUNT(*) FROM bookmarks WHERE date(created_at) > date('now','-1 day')"
3. Run manually: python3 raw/assets/pipeline_monitor.py
4. Check raw/assets/backlog-log.md for new entries

## QA Validation

### QALint
1. Run: python3 raw/assets/qa_lint.py
2. Check raw/assets/qa-batch-state.json for progress
3. Review raw/assets/qa-cron.log for errors
4. Regenerate QA if placeholder issues found

## Page Creation Threshold
- Full page: subject appears in 2+ sources
- Stub page: single mention (frontmatter + one-line + link back)
- Never leave [[wikilink]] pointing to nothing

## Quality Standards
- Summaries: 200-500 words, synthesise — don't copy
- Concept articles: 500-1500 words with clear lead
- Always trace claims to source pages
- Flag contradictions with ⚠️
- Prefer recency when sources conflict
