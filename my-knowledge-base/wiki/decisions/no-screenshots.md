---
title: "No Screenshots in Browser Automation"
date_created: 2026-04-09
date_modified: 2026-04-09
summary: "Decision to never use screenshots in browser automation - use snapshots instead"
tags: [process-change, browser-automation]
type: decision
status: final
---

# No Screenshots in Browser Automation

## Decision
Never use `mcp__glance__browser_screenshot` for X/Twitter content extraction. Always use `mcp__glance__browser_snapshot` instead.

## Rationale
- Screenshots produce image files that Claude cannot read or process
- Snapshots produce structured HTML/JSON that Claude can analyze
- Snapshots reveal visual content indicators (repost badges, quote labels, etc.) that JavaScript evaluation may miss

## Implementation
- Updated browser.md to require snapshot BEFORE evaluation script
- Created `.claude/memory.md` to track this and future learnings
- All browser automation must follow: navigate → inject cookies → snapshot → evaluate