# LLM Knowledge Base — Schema

## Overview
Personal knowledge base on my X (previously Twitter) bookmarks across various topics. Raw sources live in `raw/`. Bookmarks live in `~/.ft-bookmarks/bookmarks.db` (SQLite). The compiled wiki lives in `wiki/`. You (the AI) maintain all wiki content.

**Full directory structure:** See [SCHEMA.md](SCHEMA.md)

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
2. If bookmark unclassified → read @bookmark-classification first
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
