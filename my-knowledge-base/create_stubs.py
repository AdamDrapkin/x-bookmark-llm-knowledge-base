#!/usr/bin/env python3
"""Create stub pages for missing wikilinks with 3+ mentions."""

import os, re
from pathlib import Path

# Get all wikilinks from sources
wikilinks = set()
for f in Path('wiki/sources').glob('*.md'):
    if f.name.startswith('_'):
        continue
    content = f.read_text()
    links = re.findall(r'\[\[([^\]]+)\]\]', content)
    for l in links:
        slug = l.lower().replace(' ', '-')
        wikilinks.add(slug)

# Get existing concepts + entities
existing = set()
for f in Path('wiki/concepts').glob('*.md'):
    if not f.name.startswith('_'):
        existing.add(f.stem.lower())
for f in Path('wiki/entities').glob('*.md'):
    if not f.name.startswith('_'):
        existing.add(f.stem.lower())

missing = wikilinks - existing
print(f"Total wikilinks: {len(wikilinks)}, Existing: {len(existing)}, Missing: {len(missing)}")

# Count occurrences
from collections import Counter
link_counts = Counter()
for f in Path('wiki/sources').glob('*.md'):
    if f.name.startswith('_'):
        continue
    content = f.read_text()
    links = re.findall(r'\[\[([^\]]+)\]\]', content)
    for l in links:
        slug = l.lower().replace(' ', '-')
        if slug in missing:
            link_counts[slug] += 1

# Create stub pages for 3+ mentions
created = 0
for link, count in sorted(link_counts.items(), key=lambda x: -x[1]):
    if count < 3:
        break

    # Heuristic: title case = entity, lowercase = concept
    is_entity = any(c.isupper() for c in link) or link.startswith('@')

    if is_entity:
        subdir = "wiki/entities"
    else:
        subdir = "wiki/concepts"

    # Title case for display
    title = link.replace('-', ' ').title()

    frontmatter = f"""---
title: "{title}"
date_created: 2026-04-15
date_modified: 2026-04-15
summary: "Auto-generated stub for '{title}' - referenced in {count} sources"
tags: [auto-generated]
type: {"entity" if is_entity else "concept"}
status: stub
---

# {title}

*This page was auto-created because it was linked from {count} sources but had no existing page.*

## References

- Referenced in {count} source pages
"""

    path = Path(f"{subdir}/{link}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter)
    created += 1
    print(f"  Created: {subdir}/{link}.md ({count} mentions)")

print(f"\nCreated {created} stub pages")