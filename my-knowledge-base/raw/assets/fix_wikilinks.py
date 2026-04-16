#!/usr/bin/env python3
"""Fix wikilinks in wiki/sources/ to use correct slugs.
The issue: links say [[Claude Code]] but page is claude-code.md
We need to convert the link text to kebab-case slug format.
"""

import os
import re
from pathlib import Path

WIKI_ROOT = Path("/Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base/wiki")
SOURCES_DIR = WIKI_ROOT / "sources"

def slugify(text):
    """Convert display text to kebab-case slug."""
    # Handle special cases
    if "|" in text:
        # Has display text: [[slug|display]] -> keep slug, change display
        parts = text.split("|")
        return parts[0].strip(), parts[1].strip()

    # Handle special characters
    text = text.strip()

    # Special cases first
    special_mappings = {
        "Claude Code": "claude-code",
        "Anthropic": "anthropic",
        "LangChain": "langchain",
        "Andrej Karpathy": "andrej-karpathy",
        "OpenClaw": "openclaw",
        "AI Agents": "ai-agents",
        "AI agent": "ai-agent",
        "Prompt Engineering": "prompt-engineering",
        "prompt engineering": "prompt-engineering",
        "Prompt engineering": "prompt-engineering",
        "Y Combinator": "y-combinator",
        "Claude Opus": "claude-opus",
        "Claude API": "claude-api",
        "Claude Skills": "claude-skills",
        "Claude Cowork": "claude-cowork",
        "Letta Code": "letta-code",
        "Chrome MCP": "chrome-mcp",
        "Flash Attention 2": "flash-attention-2",
        "Gemini 3": "gemini-3",
        "Gemini Pro 3.1": "gemini-pro-3.1",
        "Sonnet 4.6": "sonnet-4.6",
        "AI research": "ai-research",
        "large language models": "large-language-models",
        "Personal Knowledge Management": "personal-knowledge-management",
        "Knowledge Management": "knowledge-management",
        "multi-agent systems": "multi-agent-systems",
        "social media automation": "social-media-automation",
        "Content Creation": "content-creation",
        "video generation": "video-generation",
        "AI video generation": "ai-video-generation",
        "context window": "context-window",
        "creator economy": "creator-economy",
        "indie hacker": "indie-hacker",
        "public speaking": "public-speaking",
        "vibe-coding": "vibecoding",
        "vibecoding": "vibecoding",
        "machine learning": "machine-learning",
        "higher education costs": "higher-education-costs",
        "Document Object Model|DOM": "document-object-model|dom",
        "Open Source": "open-source",
        "Self-Hosted Software": "self-hosted-software",
        "Salesforce": "salesforce",
        "Twenty CRM": "twenty-crm",
        "Sales Operations": "sales-operations",
        "Open-Source Alternatives to SaaS": "open-source-alternatives-to-saas",
        "AI-powered content automation": "ai-powered-content-automation",
        "AI image generation": "ai-image-generation",
        "AI productivity": "ai-productivity",
        "AI filmmaking": "ai-filmmaking",
        "AI assistant interface": "ai-assistant-interface",
        "AI tool integration": "ai-tool-integration",
        "AI design agents": "ai-design-agents",
        "AI design tools": "ai-design-tools",
        "Custom Instructions": "custom-instructions",
        "Content Rewards": "content-rewards",
        "Building a Second Brain": "building-a-second-brain",
        "Tool Use": "tool-use",
    }

    if text in special_mappings:
        return special_mappings[text]

    # Default: lowercase and kebab-case
    return text.lower().replace(" ", "-").replace(".", "-")


def fix_wikilinks(content):
    """Fix wikilinks in content to use correct slugs."""
    # Pattern: [[link text]] or [[link text|display]]
    pattern = re.compile(r'\[\[([^\]]+)\]\]')

    def replace_link(match):
        link_text = match.group(1).strip()

        # Handle display text case: [[slug|display]]
        if "|" in link_text:
            parts = link_text.split("|")
            slug_part = parts[0].strip()
            display_part = parts[1].strip()

            correct_slug = slugify(slug_part)
            return f"[[{correct_slug}|{display_part}]]"

        # Simple case: [[link text]]
        correct_slug = slugify(link_text)
        return f"[[{correct_slug}]]"

    return pattern.sub(replace_link, content)


def main():
    """Process all source files and fix wikilinks."""
    total_files = 0
    total_fixes = 0

    for fpath in SOURCES_DIR.glob("*.md"):
        if fpath.name.startswith("_"):
            continue

        content = fpath.read_text()
        original_content = content

        fixed_content = fix_wikilinks(content)

        if fixed_content != original_content:
            fpath.write_text(fixed_content)
            total_files += 1
            total_fixes += 1
            print(f"  Fixed {fpath.name}")

    print(f"\n✅ Fixed {total_fixes} links across {total_files} files")


if __name__ == "__main__":
    main()
