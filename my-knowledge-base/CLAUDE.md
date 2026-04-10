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

## Backlog Processing Workflow

Reference the wiki-backlog skill for full process: ~/.claude/skills/wiki-backlog/SKILL.md
When wiki-backlog skill is activated, the following workflow applies:

Step 1 - Read backlog-log.md: Identify batches, what's processed, target batch
Step 2 - Get batch IDs: Extract specific bookmark IDs from backlog-log.md
Step 3 - Query database: Fetch ONLY those IDs from ~/.ft-bookmarks/bookmarks.db
Step 4 - Read browser.md: Load extraction process before any processing
Step 5 - Extract each bookmark individually:
  5a. Navigate to tweet URL in browser
  5b. Take browser SNAPSHOT (NOT from FT bookmarks)
  5c. Evaluate the SNAPSHOT for: isRepost, isReply, hasImage, hasVideo, hasExternalLinks
  5d. If image → download to raw/x-article-images/
  5e. If video → download to raw/x-video-transcripts/ + transcript
  5f. If external link → save as .txt to raw/x-external-links/
  5g. Verify file saved (ls confirmation)
  5h. Mark TODO complete → THEN next bookmark
  5i. TODO: AFTER ALL bookmarks extracted → Review all snapshots for missing media:
       - Check temp snapshots for any missed images, videos, links
       - Create TODO for each missing item found
       - Mark TODO complete
       - Only then move to Step 6
Step 6 - Process media BEFORE wiki-ingest:
  6a. For each image → run image-analysis skill
  6b. For each video → run video-analysis skill
  6c. Verify analysis saved to wiki/x-image-analyses/ or wiki/x-video-analyses/
Step 7 - Run qa-council: One run per source, verify QA pair created
Step 8 - Run wiki-lint: One run per category, fix issues found
Step 9 - Update all wiki indexes: wiki/index.md, wiki/sources/, wiki/concepts/, wiki/entities/, wiki/log.md
Step 10 - Update backlog-log.md: Mark batch IDs as processed

VERIFICATION AFTER EACH SUB-STEP:
- File exists in correct location (ls to confirm)
- Only then mark TODO complete
- Only then move to next item

CRITICAL MEDIA RULE:
- NEVER trust the database for media detection (isRepost, hasImage, hasVideo, hasExternalLinks)
- The browser SNAPSHOT is the ONLY source of truth for media identification
- Ignore database media fields - evaluate the snapshot only

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
1. Read new source document
2. If bookmark unclassified → read @bookmark-classification.md first
3. Read @browser.md for extraction details
4. Create source summary in wiki/sources/
5. Identify concepts/entities → create/update pages
6. Add [[wikilinks]] to connect content
7. Update wiki/index.md
8. Append to wiki/log.md

### QUERY
1. Read wiki/index.md
2. Read relevant wiki pages
3. Synthesise answer with citations
4. Save as wiki/outputs/{question-slug}.md
5. Update wiki/index.md and wiki/log.md

### LINT
1. Find contradictions between pages
2. Find orphan pages (no inbound links)
3. Find broken [[wikilinks]]
4. Identify missing frontmatter fields
5. Flag stale content (source date >6 months)
6. Suggest new articles for unlinked concepts
7. Output report

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
