```markdown
# LLM Knowledge Base — Schema

## Overview
Personal knowledge base on my X (previously Twitter) bookmarks across various topics of conversation. Raw sources
live in raw/. bookmarks live in "`~/.ft-bookmarks/bookmarks.db` (SQLite)". Query using "`sqlite3 ~/.ft-bookmarks/bookmarks.db "<SQL>". The compiled wiki lives in wiki/. You (the AI) maintain
all wiki content. I direct strategy; you execute compilation,
maintenance, and queries.

## Directory Structure
- raw/ — Source material 
- wiki/index.md — Master index linking every page with a one-line
  summary
- wiki/log.md — Append-only changelog of all operations
- wiki/concepts/ — One article per concept
- wiki/entities/ — People, organisations, tools (one per file)
- wiki/sources/ — One summary per raw source document
- wiki/syntheses/ — Cross-cutting analysis articles
- wiki/outputs/ — Filed answers to my queries
- wiki/qa-pairs/ — Generated QA pairs from wiki articles for fine-tuning
- wiki/backlog-log.md — Tracking processed bookmarks from the backlog

## File Conventions
- All filenames: kebab-case, lowercase (e.g., active-inference.md)
- Source summaries: {author}-{year}-{short-title}.md
- Every page MUST have YAML frontmatter at the top:
  ---
  title: "Page Title"
  date_created: YYYY-MM-DD
  date_modified: YYYY-MM-DD
  summary: "One to two sentences describing this page"
  tags: [topic-tag, domain-tag]
  type: concept | entity | source | synthesis | output
  status: draft | review | final
  ---
- Use [[wikilinks]] for all internal cross-references
- Link only the first occurrence of a concept per section
- Bold key terms on first use in each article

## Operations

### INGEST (when I add new raw sources; bookmarks)
1. Read the new source document
1.1 If bookmark instead of raw & is unclassified, read and act on @bookmark-classification before continuing
1.2 If bookmark classified, continue to next step
1.3 Read and act on @browser.md 
2. Create a source summary in wiki/sources/
3. Identify concepts and entities mentioned
4. Create new concept/entity pages if they don't exist yet
5. Update existing pages with new information (append, don't
   rewrite from scratch)
6. Add [[wikilinks]] to connect new content to existing pages
7. Update wiki/index.md with new entries
8. Append to wiki/log.md

### QUERY (when I ask a question)
1. Read wiki/index.md to understand available content
2. Read the relevant wiki pages
3. Synthesise an answer with citations to wiki pages
4. Save the answer as wiki/outputs/{question-slug}.md
5. Update wiki/index.md and wiki/log.md

### LINT (periodic health check)
1. Find contradictions between pages
2. Find orphan pages (no inbound links)
3. Find broken [[wikilinks]]
4. Identify missing frontmatter fields
5. Flag stale content (source date >6 months, no updates)
6. Suggest new articles for frequently mentioned but unlinked
   concepts
7. Output a report and fix what you can automatically

## Page Creation Threshold
- Create a full concept/entity page when a subject appears in 2+
  sources
- For single-mention subjects, create a stub page (frontmatter +
  one-line definition + link back to the source that mentioned it)
- Never leave a [[wikilink]] pointing to nothing — always create
  at least a stub

## Quality Standards
- Summaries: 200-500 words, synthesise — don't copy
- Concept articles: 500-1500 words with a clear lead section
- Always trace claims to specific source pages
- Flag contradictions with ⚠️, noting both positions
- Prefer recency when sources conflict
```