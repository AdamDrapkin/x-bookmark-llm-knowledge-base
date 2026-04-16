#!/usr/bin/env python3
"""Generate pending_terms.md from broken links with 1-2 mentions."""
import re
from collections import Counter
from pathlib import Path

WIKI_ROOT = Path("/Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base")
PENDING_FILE = WIKI_ROOT / "raw/assets/pending-terms.md"

WIKILINK_RE = re.compile(r'\[\[([^\]]+)\]\]')

# Build inventory
inventory = {}
for d in ['sources', 'concepts', 'entities', 'x-video-analyses', 'x-image-analyses', 'qa-pairs', 'outputs']:
    dpath = WIKI_ROOT / "wiki" / d
    if dpath.exists():
        for fname in dpath.glob('*.md'):
            if not fname.name.startswith('_'):
                inventory[fname.stem] = True

# Get broken links from all wiki dirs
broken = []
for d in ['sources', 'concepts', 'entities', 'x-video-analyses', 'x-image-analyses', 'qa-pairs']:
    dpath = WIKI_ROOT / "wiki" / d
    if not dpath.exists():
        continue
    for fname in dpath.glob('*.md'):
        if fname.name.startswith('_'):
            continue
        content = fname.read_text()
        links = WIKILINK_RE.findall(content)
        for link in links:
            if link not in inventory:
                broken.append(link)

counts = Counter(broken)

# Get 1-2 mention terms
one_or_two = []
for link, count in counts.items():
    if count <= 2:
        one_or_two.append((link, count))

# Sort by count descending
one_or_two.sort(key=lambda x: -x[1])

# Generate output
terms_list = "\n".join([f"{term}: {count}" for term, count in one_or_two])

output = f"""---
title: Pending Terms
date_created: 2026-04-16
date_modified: 2026-04-16
summary: Terms with 1-2 mentions that need more references before creating stub pages
tags: [pending, tracking]
type: output
status: draft
---

# Pending Terms (1-2 mentions)

Terms linked from sources but not yet having enough mentions (3+) to warrant stub pages.

## Format

Each entry: term: count (count = number of source mentions)

## Terms

```
{terms_list}
```

## Process

1. New terms with 1-2 mentions get added here
2. When a term reaches 3+ mentions -> create stub page in wiki/concepts/ or wiki/entities/
3. Remove from this list when stub created
"""

PENDING_FILE.write_text(output)
print(f"Added {len(one_or_two)} terms to pending-terms.md")
