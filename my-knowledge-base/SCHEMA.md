# Wiki Schema

## Identity
- **Path:** /Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base/
- **Domain:** Personal knowledge base from X/Twitter bookmarks
- **Source types:** Bookmarks, URLs, articles, transcripts
- **Created:** 2026-04-09

## Directory Structure
- raw/ — Source material (immutable - skills never modify)
- wiki/index.md — Master index with one-line summaries
- wiki/log.md — Append-only changelog
- wiki/backlog-log.md — Tracking processed bookmarks
- wiki/decisions/ — Decision log for process changes
- wiki/sources/ — Source summaries (one per file)
- wiki/concepts/ — Concept articles
- wiki/entities/ — People, organisations, tools
- wiki/syntheses/ — Cross-cutting analysis
- wiki/outputs/ — Filed query answers
- wiki/qa-pairs/ — QA pairs for fine-tuning

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
- Raw assets: `raw/assets/bookmark-classification.md`, `raw/assets/browser.md`
