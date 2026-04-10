---
title: Phase Startup Prompts
date_created: 2026-04-10
date_modified: 2026-04-10
summary: Startup prompts for the 4-phase wiki backlog pipeline
tags: [wiki-backlog, phases, prompts]
type: output
status: ready
---

# Phase Startup Prompts

Copy the appropriate prompt when starting a new conversation for a specific phase.

---

## Phase 1 Prompt (Steps 1-4)

**Use for:** Starting content extraction (new conversation)

```
For batch #BATCH_NUM, you are processing a wiki backlog batch.

## TARGET: Phase 1 - Execute wiki-backlog skill

Execute the wiki-backlog skill following Steps 1, 2, 3, and 4 in order:

1. **Step 1** - Read backlog-log.md: /Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base/raw/assets/backlog-log.md
   - Identify the next unprocessed batch
   - Extract the batch IDs

2. **Step 2** - Identify the specific bookmark IDs for this batch from backlog-log.md

3. **Step 3** - Query the database:
   sqlite3 ~/.ft-bookmarks/bookmarks.db "SELECT id, text, author_handle, primary_category, categories, synced_at FROM bookmarks WHERE id IN ('{batch_ids}');"

4. **Step 4** - Read browser.md: /Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base/raw/assets/browser.md

5. **Step 4** - **CRITICAL: Inject cookies into browser BEFORE any navigation**
   - Per browser.md "AUTHENTICATION" section:
     1. Navigate to x.com FIRST (any page)
     2. Then inject cookies via browser JavaScript (use `.x.com` domain prefix)
     3. Verify logged in before proceeding to extraction

6. **Step 5** - Extract each bookmark in the batch:
   - For EACH bookmark: navigate, snapshot, extract media (images→raw/x-article-images, videos→raw/x-video-transcripts, links→raw/x-external-links as .txt)
   - After ALL extracted: count images (N) and videos (M), generate per-item TODOs

Temp dir: /tmp/wiki-backlog-batch-{BATCH_NUM}/{snapshots,scrapes,videos}

## PHASE COMPLETION
After Phase 1 finishes:
1. Update backlog-log.md: Mark Phase 1 = complete for this batch
2. Note temp directory location for next phase: /tmp/wiki-backlog-batch-{BATCH_NUM}/
```

---

## Phase 2 Prompt (Step 5)

**Use for:** Continuing to media analysis (same conversation as Phase 1)

```
For batch #BATCH_NUM, you are continuing wiki backlog processing.

## TARGET: Phase 2 - Execute wiki-backlog skill Step 5

Execute Step 5 from the wiki-backlog skill:

1. Check temp directory for this batch: /tmp/wiki-backlog-batch-{BATCH_NUM}/
   - Review snapshots from Phase 1 to identify all images and videos extracted

2. Load API keys: source /Users/adamdrapkin/Obsidian/synteo-intelligence/.env

3. **Step 5** - Process all extracted images:
   - The images are in raw/x-article-images/ (count N from Phase 1)
   - For EACH image: run image-analysis skill, verify output at wiki/x-image-analyses/
   - DO NOT batch - process ONE at a time

4. **Step 5** - Process all extracted videos:
   - The videos are in raw/x-video-transcripts/ (count M from Phase 1)
   - For EACH video: run video-analysis skill, verify output at wiki/x-video-analyses/
   - DO NOT batch - process ONE at a time

## PHASE COMPLETION
After Phase 2 finishes:
1. Update backlog-log.md: Mark Phase 2 = complete for this batch
2. Keep temp directory for next phase reference
```

---

## Phase 3 Prompt (Steps 6 + wiki-ingest)

**Use for:** Create source summaries THEN run qa-council (same conversation as Phase 2)

**CRITICAL FIX:** Sources must be created BEFORE qa-council can run. wiki-ingest creates sources.

```
For batch #BATCH_NUM, you are continuing wiki backlog processing.

## TARGET: Phase 3 - Create sources + Execute wiki-backlog skill Step 6

**CRITICAL:** Sources must exist in wiki/sources/ BEFORE qa-council can run.

1. Check temp directory for this batch: /tmp/wiki-backlog-batch-{BATCH_NUM}/
   - Review Phase 1/2 progress to confirm media analysis completed

2. **Phase 3a** - Create source summaries (wiki-ingest):
   - Execute wiki-ingest for EACH of the 10 bookmark IDs in this batch
   - Create source summary in wiki/sources/{author}-{tweet-id}.md
   - MUST create sources BEFORE qa-council can run
   - DO NOT batch - process ONE source at a time

3. **Phase 3b** - Run qa-council on each source:
   - Sources now exist in wiki/sources/ (10 sources from this batch)
   - For EACH source: run qa-council skill, verify QA pair in wiki/qa-pairs/
   - DO NOT batch - process ONE source at a time

## PHASE COMPLETION
After Phase 3 finishes:
1. Update backlog-log.md: Mark Phase 3 = complete for this batch
```

---

## Phase 4 Prompt (Steps 7-9)

**Use for:** Finalization - lint, indexes, backlog update (same conversation as Phase 3)

```
For batch #BATCH_NUM, you are continuing wiki backlog processing.

## TARGET: Phase 4 - Execute wiki-backlog skill Steps 7, 8, and 9

Execute Steps 7, 8, and 9 from the wiki-backlog skill:

1. Check temp directory for this batch: /tmp/wiki-backlog-batch-{BATCH_NUM}/
   - Confirm Phase 3 QA generation completed

2. **Step 7** - Run wiki-lint:
   - Run /wiki-lint skill
   - Execute EACH category check individually (contradictions, orphan pages, broken links, frontmatter, stale content, suggestions)
   - Fix each category before moving to next

3. **Step 8** - Update all wiki indexes:
   - wiki/index.md
   - wiki/sources/_index.md
   - wiki/concepts/_index.md
   - wiki/entities/_index.md
   - wiki/x-image-analyses/_index.md (if images analyzed)
   - wiki/x-video-analyses/_index.md (if videos analyzed)
   - wiki/qa-pairs/_index.md
   - wiki/outputs/_index.md (lint report)
   - wiki/log.md (add batch entry)

4. **Step 9** - Update backlog-log.md:
   - In: /Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base/raw/assets/backlog-log.md
   - Mark batch IDs as "done"
   - Mark Phase 4 = complete for this batch

5. **Cleanup** - Delete temp files: rm -rf /tmp/wiki-backlog-batch-{BATCH_NUM}/

## PHASE COMPLETION
After Phase 4 finishes:
- Batch fully processed
- All phases marked complete in backlog-log.md
- Temp files cleaned up
```

---

## How to Use

1. **Start new batch:** Open phase-startup-prompts.md, copy Phase 1 prompt, replace `#BATCH_NUM` with batch number (e.g., "3")
2. **Continue same batch:** Copy next phase prompt, keep same batch number
3. **Track progress:** Each phase updates backlog-log.md with phase completion status

## Batch Number Reference

| Batch | IDs | Status |
|-------|-----|--------|
| Batch 1 | 1-10 | done |
| Batch 2 | 11-20 | done |
| Batch 3 | 21-30 | next |
| Batch 4 | 31-40 | done |
| Batch 5 | 41-50 | - |