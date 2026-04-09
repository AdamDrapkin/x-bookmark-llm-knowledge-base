---
title: Decision - Process by Category
date_created: 2026-04-09
date_modified: 2026-04-09
summary: Decision to process bookmarks category-by-category instead of mixed
tags: [decision, process]
type: output
status: final
---

# Decision: Process Backlog by Category

## Context
We have 874 bookmarks total, 5 already processed, 869 remaining. The wiki-backlog skill needs a systematic approach.

## Decision
Process bookmarks **category-by-category** from largest to smallest:
1. Start with prompt-engineering (132 total, 130 remaining)
2. Work through each category completely before moving to next

## Rationale
- **Cohesion**: Same category bookmarks relate to each other → better wiki structure
- **Tracking**: Easier to see progress per category
- **Batching**: 10 per batch, pre-defined batches per category

## Implementation
- Update backlog-log.md with full category breakdown
- Create batch lists before starting each category
- Add decisions folder for process changes
- Update CLAUDE.md to reference wiki/decisions/
