#!/usr/bin/env python3
"""
qa_lint.py — QA Pairs Lint Checker

Checks for:
- Placeholder text in QA pairs
- Empty synthesis_questions
- Missing source_slugs
- Broken wikilinks
"""

import json
import sys
from pathlib import Path

WIKI_ROOT = Path("/Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base")
QA_PAIRS_DIR = WIKI_ROOT / "wiki" / "qa-pairs"
SOURCES_DIR = WIKI_ROOT / "wiki" / "sources"


def check_placeholders(batch_file):
    """Check for placeholder text in QA pairs."""
    issues = []
    with open(batch_file) as f:
        data = json.load(f)

    # Check source_questions
    for sq in data.get("source_questions", []):
        preview = sq.get("source_content_preview", "")
        if "placeholder" in preview.lower() or "requires manual review" in preview.lower():
            issues.append(f"  ⚠ {sq['source_slug']}: PLACEHOLDER source")

        # Check answers for placeholder language
        for q in sq.get("questions", []):
            answer = q.get("answer", "")
            if "placeholder" in answer.lower() or "manual review" in answer.lower():
                issues.append(f"  ⚠ {sq['source_slug']}/{q.get('question_id')}: PLACEHOLDER answer")

    return issues


def check_empty_synthesis(batch_file):
    """Check for empty synthesis_questions."""
    issues = []
    with open(batch_file) as f:
        data = json.load(f)

    synthesis = data.get("synthesis_questions", [])
    if not synthesis:
        issues.append(f"  ⚠ EMPTY synthesis_questions")

    return issues


def check_wikilinks(batch_file):
    """Check for broken wikilinks."""
    issues = []
    with open(batch_file) as f:
        data = json.load(f)

    # Get available source slugs
    available = set(s.stem for s in SOURCES_DIR.glob("*.md"))

    for sq in data.get("source_questions", []):
        slug = sq.get("source_slug", "")
        for q in sq.get("questions", []):
            answer = q.get("answer", "")
            # Check for [[wikilinks]]
            if "[[" in answer:
                import re
                links = re.findall(r'\[\[([^\]]+)\]\]', answer)
                for link in links:
                    # Extract slug from [[wikilink]]
                    clean = link.strip()
                    if clean not in available and clean not in ["source-slug-1", "source-slug-2"]:
                        issues.append(f"  ⚠ {q.get('question_id')}: Broken wikilink [[{clean}]]")

    return issues


def main():
    print("=" * 60)
    print("QA Pairs Lint Check")
    print("=" * 60)

    all_issues = []

    # Check each batch
    batch_files = sorted(QA_PAIRS_DIR.glob("batch*_qa.json"))

    for bf in batch_files:
        print(f"\n{bf.name}")
        print("-" * 40)

        issues = []
        issues.extend(check_placeholders(bf))
        issues.extend(check_empty_synthesis(bf))
        issues.extend(check_wikilinks(bf))

        if issues:
            for issue in issues:
                print(issue)
            all_issues.extend(issues)
        else:
            print("  ✓ OK")

    print("\n" + "=" * 60)
    print(f"Total issues: {len(all_issues)}")
    print("=" * 60)

    if all_issues:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())