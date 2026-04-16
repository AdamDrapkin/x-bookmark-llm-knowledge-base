#!/usr/bin/env python3
"""
Comprehensive Wiki Sync - With LLM Content Generation (PARALLEL)

This script ensures:
1. All concepts/entities have updated source references from ALL sources
2. Uses MiniMax API to generate actual content for placeholder pages
3. SCHEMA.md reflects current wiki structure
4. All index files are synchronized
5. images.md reflects all X image analyses
6. videos.md reflects all X video analyses
7. PARALLEL execution for faster LLM regeneration

Run after each batch: python3 raw/assets/wiki-sync.py
"""

import re
import os
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# MiniMax imports
try:
    from anthropic import Anthropic
    MINIMAX_AVAILABLE = True
except ImportError:
    MINIMAX_AVAILABLE = False

WIKI_ROOT = Path("/Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base/wiki")
RAW_ASSETS = WIKI_ROOT.parent / "raw/assets"
TODAY = datetime.now().strftime("%Y-%m-%d")

WIKILINK_RE = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')

# Get MiniMax API key
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")


def get_minimax_client():
    """Create MiniMax client with M2.7 model settings"""
    if not MINIMAX_AVAILABLE:
        return None
    if not MINIMAX_API_KEY:
        return None
    return Anthropic(
        api_key=MINIMAX_API_KEY,
        base_url="https://api.minimax.io/anthropic"
    )


def get_all_sources():
    """Get all source files with their content for context"""
    sources = {}
    for f in (WIKI_ROOT / 'sources').glob('*.md'):
        if f.name.startswith('_'):
            continue
        content = f.read_text()
        title = f.stem
        # Extract summary from frontmatter
        summary = ""
        if content.startswith('---'):
            try:
                fm_end = content.index('---', 3)
                fm = content[3:fm_end]
                for line in fm.split('\n'):
                    if line.startswith('title:'):
                        title = line.replace('title:', '').strip().strip('"')
                    if line.startswith('summary:'):
                        summary = line.replace('summary:', '').strip().strip('"')
            except:
                pass
        # Get first 500 chars of content for context
        body = content.split('---', 2)[-1] if '---' in content else content
        body = body.strip()[:500]
        sources[f.stem] = {'title': title, 'content': content, 'summary': summary, 'body': body}
    return sources


def get_all_concepts():
    """Get all concept files"""
    concepts = {}
    for f in (WIKI_ROOT / 'concepts').glob('*.md'):
        if f.name.startswith('_'):
            continue
        concepts[f.stem] = f
    return concepts


def get_all_entities():
    """Get all entity files"""
    entities = {}
    for f in (WIKI_ROOT / 'entities').glob('*.md'):
        if not f.name.startswith('_'):
            entities[f.stem] = f
    return entities


def get_pending_terms():
    """Get pending terms from pending-terms.md"""
    pending = set()
    pf = RAW_ASSETS / "pending-terms.md"
    if pf.exists():
        content = pf.read_text()
        for line in content.split('\n'):
            if ':' in line and not line.startswith('#'):
                term = line.split(':')[0].strip()
                if term:
                    pending.add(term.lower())
    return pending


def get_existing_pages():
    """Get all existing page slugs"""
    existing = set()
    for d in ['sources', 'concepts', 'entities', 'x-video-analyses', 'x-image-analyses', 'x-github-repos']:
        dpath = WIKI_ROOT / d
        if dpath.exists():
            for f in dpath.glob('*.md'):
                if not f.name.startswith('_'):
                    existing.add(f.stem.lower())
    return existing


def build_source_entity_map(sources):
    """Map each entity to all sources that reference it"""
    entity_sources = defaultdict(set)

    entities = set()
    for f in (WIKI_ROOT / 'entities').glob('*.md'):
        if not f.name.startswith('_'):
            entities.add(f.stem.lower())

    for slug, info in sources.items():
        links = WIKILINK_RE.findall(info['content'])
        for link in links:
            link_lower = link.strip().lower()
            if link_lower in entities:
                entity_sources[link_lower].add(slug)

    return entity_sources


def build_source_concept_map(sources):
    """Map each concept to all sources that reference it"""
    concept_sources = defaultdict(set)

    concepts = set()
    for f in (WIKI_ROOT / 'concepts').glob('*.md'):
        if not f.name.startswith('_'):
            concepts.add(f.stem.lower())

    for slug, info in sources.items():
        links = WIKILINK_RE.findall(info['content'])
        for link in links:
            link_lower = link.strip().lower()
            if link_lower in concepts:
                concept_sources[link_lower].add(slug)

    return concept_sources


def is_placeholder_page(content):
    """Check if a page has placeholder/stub content"""
    placeholder_patterns = [
        'stub page',
        'placeholder',
        'tbd',
        'todo:',
        'add summary',
        'add description',
        'brief description',
        'auto created',
        'auto-generated',
        'auto-generated stub',
        'status: stub',
        'was auto-created',
    ]
    content_lower = content.lower()
    return any(p in content_lower for p in placeholder_patterns)


def generate_entity_content(client, entity_name, source_summaries):
    """Generate actual content for an entity using MiniMax"""
    if not client or not source_summaries:
        return None, None

    # Build context from sources
    context = "\n\n".join([f"Source: {s[:400]}" for s in source_summaries[:3]])

    prompt = f"""Write ONLY the wiki article - no preamble, no explanation.

ENTITY: {entity_name}

CONTEXT FROM SOURCES:
{context}

OUTPUT FORMAT (strict):
# {entity_name}

**Type:** [Product/Tool/Company/Person]
**Known For:** [brief description]

## Overview
[2-3 sentence description]

## Use Cases
- [use case 1]
- [use case 2]

## Summary
[one sentence]"""

    try:
        response = client.messages.create(
            model="MiniMax-M2.7",
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}]
        )
        text_content = ""
        for block in response.content:
            if hasattr(block, 'type') and block.type == 'text':
                text_content += block.text

        # Check for bad outputs
        if not text_content.strip() or "The user wants" in text_content or "Let me" in text_content:
            return None, None

        # Parse the structured output
        result = {'title': entity_name, 'type': '', 'known_for': '', 'overview': '', 'use_cases': [], 'summary': ''}
        lines = text_content.split('\n')
        section = None
        buffer = []

        for line in lines:
            line = line.strip()
            if line.startswith('**Type:**'):
                result['type'] = line.replace('**Type:**', '').strip()
            elif line.startswith('**Known For:**'):
                result['known_for'] = line.replace('**Known For:**', '').strip()
            elif line == '## Overview':
                section = 'overview'
                buffer = []
            elif line == '## Use Cases':
                result['overview'] = ' '.join(buffer)
                section = 'use_cases'
                buffer = []
            elif line == '## Summary':
                result['use_cases'] = [l.lstrip('- ') for l in buffer if l.startswith('-')]
                section = 'summary'
                buffer = []
            elif line and not line.startswith('#'):
                buffer.append(line)

        if buffer:
            result['summary'] = ' '.join(buffer)

        return result, text_content

    except Exception as e:
        print(f"   ⚠️  LLM error: {str(e)[:50]}")
        return None, None


def generate_concept_content(client, concept_name, source_summaries):
    """Generate actual content for a concept using MiniMax"""
    if not client or not source_summaries:
        return None, None

    context = "\n\n".join([f"Source: {s[:400]}" for s in source_summaries[:3]])

    prompt = f"""Write ONLY the wiki article - no preamble, no explanation.

CONCEPT: {concept_name}

CONTEXT FROM SOURCES:
{context}

OUTPUT FORMAT (strict):
# {concept_name}

**Category:** [General/Technique/Tool/Method]
**Definition:** [brief definition]

## Overview
[2-3 sentence description]

## Techniques
- [technique 1]
- [technique 2]

## Summary
[one sentence]"""

    try:
        response = client.messages.create(
            model="MiniMax-M2.7",
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}]
        )
        text_content = ""
        for block in response.content:
            if hasattr(block, 'type') and block.type == 'text':
                text_content += block.text

        if not text_content.strip() or "The user wants" in text_content or "Let me" in text_content:
            return None, None

        result = {'title': concept_name, 'category': '', 'definition': '', 'overview': '', 'techniques': [], 'summary': ''}
        lines = text_content.split('\n')
        section = None
        buffer = []

        for line in lines:
            line = line.strip()
            if line.startswith('**Category:**'):
                result['category'] = line.replace('**Category:**', '').strip()
            elif line.startswith('**Definition:**'):
                result['definition'] = line.replace('**Definition:**', '').strip()
            elif line == '## Overview':
                section = 'overview'
                buffer = []
            elif line == '## Techniques':
                result['overview'] = ' '.join(buffer)
                section = 'techniques'
                buffer = []
            elif line == '## Summary':
                result['techniques'] = [l.lstrip('- ') for l in buffer if l.startswith('-')]
                section = 'summary'
                buffer = []
            elif line and not line.startswith('#'):
                buffer.append(line)

        if buffer:
            result['summary'] = ' '.join(buffer)

        return result, text_content

    except Exception as e:
        print(f"   ⚠️  LLM error: {str(e)[:50]}")
        return None, None


def update_entity_with_content(entity, source_list, sources, client):
    """Update an entity page with generated content"""
    entity_file = WIKI_ROOT / 'entities' / f"{entity}.md"
    if not entity_file.exists():
        return False

    content = entity_file.read_text()

    # Check if it's a placeholder OR has LLM raw output
    has_bad_content = is_placeholder_page(content) or ("The user wants me to" in content) or ("Let me analyze" in content)

    if not has_bad_content:
        # Already has good content, just update sources
        return update_entity_sources_only(entity, source_list)

    # Generate new content
    source_summaries = [sources[s]['body'] for s in source_list if s in sources]
    if not source_summaries:
        return False

    result, generated = generate_entity_content(client, entity.replace('-', ' ').title(), source_summaries)
    if not result or not generated:
        return False

    # Build the wiki page from parsed result
    title = result.get('title', entity.replace('-', ' ').title())
    entity_type = result.get('type', 'Tool')
    known_for = result.get('known_for', '')
    overview = result.get('overview', '')
    summary = result.get('summary', '')

    new_content = f"""---
title: "{title}"
date_created: {TODAY}
date_modified: {TODAY}
summary: "{summary or known_for or 'Entity in AI/tech knowledge base'}"
tags: [entity]
type: entity
status: final
---

# {title}

**Type:** {entity_type}
**Known For:** {known_for}

## Overview

{overview}

## Related Sources

"""
    for s in sorted(source_list):
        new_content += f"- [[{s}]]\n"

    new_content += """
## Related Concepts

- [[concept]] — Related concept
"""

    entity_file.write_text(new_content)
    return True


def update_concept_with_content(concept, source_list, sources, client):
    """Update a concept page with generated content"""
    concept_file = WIKI_ROOT / 'concepts' / f"{concept}.md"
    if not concept_file.exists():
        return False

    content = concept_file.read_text()

    # Check for bad content
    has_bad_content = is_placeholder_page(content) or ("The user wants me to" in content) or ("Let me analyze" in content)

    if not has_bad_content:
        return update_concept_sources_only(concept, source_list)

    source_summaries = [sources[s]['body'] for s in source_list if s in sources]
    if not source_summaries:
        return False

    result, generated = generate_concept_content(client, concept.replace('-', ' ').title(), source_summaries)
    if not result or not generated:
        return False

    # Build from parsed result
    title = result.get('title', concept.replace('-', ' ').title())
    category = result.get('category', 'General')
    definition = result.get('definition', '')
    overview = result.get('overview', '')
    summary = result.get('summary', '')

    new_content = f"""---
title: "{title}"
date_created: {TODAY}
date_modified: {TODAY}
summary: "{summary or definition or 'Concept in AI/tech knowledge base'}"
tags: [concept]
type: concept
status: final
---

# {title}

**Category:** {category}
**Definition:** {definition}

## Overview

{overview}

## Related Sources

"""
    for s in sorted(source_list):
        new_content += f"- [[{s}]]\n"

    new_content += """
## Related Entities

- [[entity]] — Related entity
"""

    concept_file.write_text(new_content)
    return True


def update_entity_sources_only(entity, source_list):
    """Update entity page sources without regenerating content"""
    entity_file = WIKI_ROOT / 'entities' / f"{entity}.md"
    if not entity_file.exists():
        return False

    content = entity_file.read_text()
    sources_md = "\n".join([f"- [[{s}]]" for s in sorted(source_list)])

    lines = content.split('\n')
    new_lines = []
    in_section = False
    section_found = False

    for line in lines:
        if "## Related Sources" in line:
            in_section = True
            section_found = True
            new_lines.append(line)
            new_lines.append("")
            new_lines.append(sources_md)
        elif in_section and line.startswith('## '):
            in_section = False
            new_lines.append(line)
        elif not in_section:
            new_lines.append(line)

    if section_found:
        new_content = '\n'.join(new_lines)
        if new_content != content:
            entity_file.write_text(new_content)
            return True
    return False


def update_concept_sources_only(concept, source_list):
    """Update concept page sources without regenerating content"""
    concept_file = WIKI_ROOT / 'concepts' / f"{concept}.md"
    if not concept_file.exists():
        return False

    content = concept_file.read_text()
    sources_md = "\n".join([f"- [[{s}]]" for s in sorted(source_list)])

    lines = content.split('\n')
    new_lines = []
    in_section = False
    section_found = False

    for line in lines:
        if "## Related Sources" in line:
            in_section = True
            section_found = True
            new_lines.append(line)
            new_lines.append("")
            new_lines.append(sources_md)
        elif in_section and line.startswith('## '):
            in_section = False
            new_lines.append(line)
        elif not in_section:
            new_lines.append(line)

    if section_found:
        new_content = '\n'.join(new_lines)
        if new_content != content:
            concept_file.write_text(new_content)
            return True
    return False


def update_single_entity(args):
    """Worker function for parallel entity updates"""
    entity, source_list, sources, client = args
    try:
        success = update_entity_with_content(entity, source_list, sources, client)
        return (entity, success)
    except Exception as e:
        print(f"   ⚠️  Error updating {entity}: {str(e)[:50]}")
        return (entity, False)


def update_single_concept(args):
    """Worker function for parallel concept updates"""
    concept, source_list, sources, client = args
    try:
        success = update_concept_with_content(concept, source_list, sources, client)
        return (concept, success)
    except Exception as e:
        print(f"   ⚠️  Error updating {concept}: {str(e)[:50]}")
        return (concept, False)


# Parallelism level - adjust based on API rate limits
MAX_PARALLEL_LLM_CALLS = 5  # Run up to 5 LLM calls concurrently


def update_all_entities(entity_sources, sources, client):
    """Update all entity pages (PARALLEL)"""
    if not client or not entity_sources:
        return []

    # Filter entities that need regeneration (have placeholder content)
    entities_needing_regen = []
    for entity, source_list in entity_sources.items():
        entity_file = WIKI_ROOT / 'entities' / f"{entity}.md"
        if entity_file.exists():
            content = entity_file.read_text()
            if is_placeholder_page(content) or ("The user wants me to" in content):
                entities_needing_regen.append((entity, source_list))
        else:
            # New entity - needs content too
            entities_needing_regen.append((entity, source_list))

    if not entities_needing_regen:
        print("   ✅ No entities need regeneration")
        return []

    print(f"   🔄 Regenerating {len(entities_needing_regen)} entities in parallel...")

    # Prepare args
    args_list = [(e, sl, sources, client) for e, sl in entities_needing_regen]

    # Run in parallel
    updated = []
    failed = 0
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_LLM_CALLS) as executor:
        futures = {executor.submit(update_single_entity, args): args[0] for args in args_list}

        for future in as_completed(futures):
            entity, success = future.result()
            if success:
                updated.append(entity)
            else:
                failed += 1
            # Progress indicator
            total = len(entities_needing_regen)
            done = len(updated) + failed
            if done % 10 == 0 or done == total:
                print(f"      Progress: {done}/{total}")

    print(f"   ✅ Regenerated {len(updated)} entities ({failed} failed)")
    return updated


def update_all_concepts(concept_sources, sources, client):
    """Update all concept pages (PARALLEL)"""
    if not client or not concept_sources:
        return []

    # Filter concepts that need regeneration
    concepts_needing_regen = []
    for concept, source_list in concept_sources.items():
        concept_file = WIKI_ROOT / 'concepts' / f"{concept}.md"
        if concept_file.exists():
            content = concept_file.read_text()
            if is_placeholder_page(content) or ("The user wants me to" in content):
                concepts_needing_regen.append((concept, source_list))
        else:
            concepts_needing_regen.append((concept, source_list))

    if not concepts_needing_regen:
        print("   ✅ No concepts need regeneration")
        return []

    print(f"   🔄 Regenerating {len(concepts_needing_regen)} concepts in parallel...")

    # Prepare args
    args_list = [(c, sl, sources, client) for c, sl in concepts_needing_regen]

    # Run in parallel
    updated = []
    failed = 0
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_LLM_CALLS) as executor:
        futures = {executor.submit(update_single_concept, args): args[0] for args in args_list}

        for future in as_completed(futures):
            concept, success = future.result()
            if success:
                updated.append(concept)
            else:
                failed += 1
            total = len(concepts_needing_regen)
            done = len(updated) + failed
            if done % 10 == 0 or done == total:
                print(f"      Progress: {done}/{total}")

    print(f"   ✅ Regenerated {len(updated)} concepts ({failed} failed)")
    return updated


def update_entities_index():
    """Update entities/_index.md"""
    index_file = WIKI_ROOT / 'entities' / '_index.md'
    if not index_file.exists():
        return 0

    entities = sorted([f.stem for f in (WIKI_ROOT / 'entities').glob('*.md') if not f.name.startswith('_')])
    count = len(entities)

    content = index_file.read_text()
    new_content = re.sub(r'## All Entities \(\d+\)', f'## All Entities ({count})', content)

    if new_content != content:
        index_file.write_text(new_content)
    return count


def update_concepts_index():
    """Update concepts/_index.md"""
    index_file = WIKI_ROOT / 'concepts' / '_index.md'
    if not index_file.exists():
        return 0

    concepts = sorted([f.stem for f in (WIKI_ROOT / 'concepts').glob('*.md') if not f.name.startswith('_')])
    count = len(concepts)

    content = index_file.read_text()
    new_content = re.sub(r'## All Concepts \(\d+\)', f'## All Concepts ({count})', content)

    if new_content != content:
        index_file.write_text(new_content)
    return count


def update_schema():
    """Update SCHEMA.md"""
    schema_file = WIKI_ROOT.parent / "SCHEMA.md"
    if not schema_file.exists():
        return None

    extra_dirs = []
    for d in ['x-video-analyses', 'x-image-analyses', 'x-github-repos', 'syntheses', 'decisions', 'attachments']:
        if (WIKI_ROOT / d).exists():
            extra_dirs.append(d)

    content = schema_file.read_text()
    updated = False
    for d in extra_dirs:
        if d not in content:
            updated = True
            break

    if updated:
        if '## Additional Directories' not in content:
            content += "\n## Additional Directories\n"
            for d in extra_dirs:
                content += f"- `wiki/{d}/`\n"
        schema_file.write_text(content)
        return extra_dirs
    return None


def update_images_md():
    """Update wiki/attachments/images.md"""
    images_file = WIKI_ROOT / 'attachments' / 'images.md'
    analyses = []
    dpath = WIKI_ROOT / 'x-image-analyses'
    if dpath.exists():
        for f in sorted(dpath.glob('*.md')):
            if not f.name.startswith('_'):
                analyses.append(f.stem)

    content = f"""---
title: "Images"
date_created: 2026-04-08
date_modified: {TODAY}
summary: "Image analyses from X posts"
tags: [attachments, images]
type: attachment
status: draft
---

# Image Analyses

Total: {len(analyses)} images analyzed

## All Image Analyses

"""
    for a in analyses:
        content += f"- [[{a}]]\n"

    images_file.write_text(content)
    return len(analyses)


def update_videos_md():
    """Update wiki/attachments/videos.md"""
    videos_file = WIKI_ROOT / 'attachments' / 'videos.md'
    analyses = []
    dpath = WIKI_ROOT / 'x-video-analyses'
    if dpath.exists():
        for f in sorted(dpath.glob('*.md')):
            if not f.name.startswith('_'):
                analyses.append(f.stem)

    repos = []
    dpath = WIKI_ROOT / 'x-github-repos'
    if dpath.exists():
        for f in sorted(dpath.glob('*.md')):
            if not f.name.startswith('_'):
                repos.append(f.stem)

    content = f"""---
title: "Videos"
date_created: 2026-04-08
date_modified: {TODAY}
summary: "Video and GitHub repo analyses from X posts"
tags: [attachments, videos]
type: attachment
status: draft
---

# Video & Repo Analyses

## Video Analyses

Total: {len(analyses)} videos analyzed

"""
    for a in analyses:
        content += f"- [[{a}]]\n"

    content += f"\n## GitHub Repos\n\nTotal: {len(repos)} repos analyzed\n\n"
    for r in repos:
        content += f"- [[{r}]]\n"

    videos_file.write_text(content)
    return len(analyses), len(repos)


def update_qa_pairs_index():
    """Update wiki/qa-pairs/_index.md"""
    index_file = WIKI_ROOT / 'qa-pairs' / '_index.md'
    if not index_file.exists():
        return None

    qa_files = [f.stem for f in (WIKI_ROOT / 'qa-pairs').glob('*.md')
                 if not f.name.startswith('_') and 'qa.json' not in f.name]
    count = len(qa_files)

    content = index_file.read_text()
    if f'## Total QA Pairs ({count})' not in content:
        new_content = re.sub(r'## Total QA Pairs \(\d+\)', f'## Total QA Pairs ({count})', content)
        if new_content != content:
            index_file.write_text(new_content)
            return count
    return count


def check_broken_links():
    """Check for broken wikilinks"""
    existing = get_existing_pages()
    pending = get_pending_terms()

    broken = []
    for subdir in ['sources', 'concepts', 'entities', 'x-video-analyses', 'x-image-analyses', 'x-github-repos']:
        dpath = WIKI_ROOT / subdir
        if not dpath.exists():
            continue
        for fpath in dpath.glob('*.md'):
            if fpath.name.startswith('_'):
                continue
            content = fpath.read_text()
            links = WIKILINK_RE.findall(content)
            for link in links:
                link_clean = link.strip().lower()
                if link_clean and link_clean not in existing and link_clean not in pending:
                    if not link_clean.endswith(('.png', '.jpg', '.svg', '.md')):
                        broken.append(f"[[{link}]] in {fpath.name}")

    return list(set(broken))


def main():
    print("=" * 60)
    print("WIKI SYNC - Comprehensive Update with LLM")
    print("=" * 60)
    print()

    # Get MiniMax client
    client = get_minimax_client()
    if client:
        print("✅ MiniMax API connected")
    else:
        print("⚠️  MiniMax API not available - will update sources only")

    # 1. Get current state
    print("\n📊 Gathering wiki state...")
    sources = get_all_sources()
    entities = get_all_entities()
    concepts = get_all_concepts()
    print(f"   Sources: {len(sources)}")
    print(f"   Entities: {len(entities)}")
    print(f"   Concepts: {len(concepts)}")

    # 2. Build source maps
    print("\n🔗 Building source-reference maps...")
    entity_sources = build_source_entity_map(sources)
    concept_sources = build_source_concept_map(sources)
    print(f"   Entities with sources: {len(entity_sources)}")
    print(f"   Concepts with sources: {len(concept_sources)}")

    # 3. Update entities with LLM content
    print("\n✏️ Updating entities (with LLM content generation)...")
    updated_entities = update_all_entities(entity_sources, sources, client)
    print(f"   Updated: {len(updated_entities)} entity pages")

    # 4. Update concepts with LLM content
    print("\n✏️ Updating concepts (with LLM content generation)...")
    updated_concepts = update_all_concepts(concept_sources, sources, client)
    print(f"   Updated: {len(updated_concepts)} concept pages")

    # 5. Update indexes
    print("\n📑 Updating index files...")
    ent_count = update_entities_index()
    conc_count = update_concepts_index()
    print(f"   Entities index: {ent_count} entities")
    print(f"   Concepts index: {conc_count} concepts")

    # 6. Update SCHEMA.md
    print("\n📝 Checking SCHEMA.md...")
    new_dirs = update_schema()
    if new_dirs:
        print(f"   Added directories: {new_dirs}")
    else:
        print("   SCHEMA.md up to date")

    # 7. Update images.md
    print("\n🖼️ Updating images.md...")
    img_count = update_images_md()
    print(f"   Image analyses: {img_count}")

    # 8. Update videos.md
    print("\n🎬 Updating videos.md...")
    vid_count, repo_count = update_videos_md()
    print(f"   Video analyses: {vid_count}")
    print(f"   GitHub repos: {repo_count}")

    # 9. Update QA index
    print("\n❓ Updating QA pairs index...")
    qa_count = update_qa_pairs_index()
    if qa_count:
        print(f"   QA pairs: {qa_count}")

    # 10. Check for broken links
    print("\n🔍 Checking for broken links...")
    broken = check_broken_links()
    if broken:
        print(f"   ⚠️  Found {len(broken)} broken links")
    else:
        print("   ✅ No broken links")

    print("\n" + "=" * 60)
    print("✅ WIKI SYNC COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()