#!/usr/bin/env python3
"""Fix remaining wikilinks - handle special cases with periods in slug."""

import os
import re
from pathlib import Path

WIKI_ROOT = Path("/Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base/wiki")

# Subdirs to process
WIKI_SUBDIRS = ["sources", "concepts", "entities", "x-video-analyses", "x-image-analyses", "qa-pairs", "outputs"]

def slugify(text):
    """Convert display text to slug - with special handling for periods."""
    # Handle display text case: [[slug|display]]
    if "|" in text:
        parts = text.split("|")
        slug_part = parts[0].strip()
        display_part = parts[1].strip()
        return slugify(slug_part), display_part

    # Special case mappings (things that have periods in filename)
    special_mappings = {
        # Entities with periods
        "seedance-2-0": "seedance-2.0",
        "gemini-pro-3-1": "gemini-pro-3.1",
        "sonnet-4-6": "sonnet-4.6",
        "document-object-model|dom": "document-object-model|dom",
        "claude-md": "claude.md",

        # Other common ones that might have been converted wrongly
        "ai-research": "ai-research",

        # Title Case -> lowercase (common entity references)
        "Cursor": "cursor",
        "Figma": "figma",
        "Lovable": "lovable",
        "Mobbin": "mobbin",
        "Dribbble": "dribbble",
        "MyMind": "mymind",
        "Aura": "aura",
        "Unicorn Studio": "unicorn-studio",
        "AI Studio": "ai-studio",
        "Gemini 3": "gemini-3",
        "Screen Studio": "screen-studio",
        "AI design tools": "ai-design-tools",
        "Prompt engineering": "prompt-engineering",
        # Other broken links
        "AI models": "ai-models",
    }

    # Check if we have a special mapping
    if text in special_mappings:
        return special_mappings[text]

    # Default conversion
    result = text.lower().replace(" ", "-")
    return result


def fix_wikilinks(content):
    """Fix wikilinks in content - handle special period cases."""
    # Pattern: [[link text]] or [[link text|display]]
    pattern = re.compile(r'\[\[([^\]]+)\]\]')

    def replace_link(match):
        link_text = match.group(1).strip()

        # Handle display text case
        if "|" in link_text:
            parts = link_text.split("|")
            slug_part = parts[0].strip()
            display_part = parts[1].strip()
            correct_slug = slugify(slug_part)
            return f"[[{correct_slug}|{display_part}]]"

        # Simple case
        correct_slug = slugify(link_text)
        return f"[[{correct_slug}]]"

    return pattern.sub(replace_link, content)


def main():
    total_files = 0

    for subdir in WIKI_SUBDIRS:
        dir_path = WIKI_ROOT / subdir
        if not dir_path.exists():
            continue
        for fpath in dir_path.glob("*.md"):
            if fpath.name.startswith("_"):
                continue
            content = fpath.read_text()
            original = content
            fixed = fix_wikilinks(content)
            if fixed != original:
                fpath.write_text(fixed)
                total_files += 1
                print(f"  Fixed {fpath.relative_to(WIKI_ROOT)}")

    print(f"\n✅ Fixed {total_files} files")


if __name__ == "__main__":
    main()
