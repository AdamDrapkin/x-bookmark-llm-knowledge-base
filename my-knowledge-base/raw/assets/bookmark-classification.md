# Bookmark Classification

## Overview
Process X bookmarks from `~/.ft-bookmarks/bookmarks.db` into the LLM Knowledge Base. Bookmarks need classification BEFORE wiki indexing.

## Source
- **Raw data**: `~/.ft-bookmarks/bookmarks.db` (SQLite)
- **Query**: `sqlite3 ~/.ft-bookmarks/bookmarks.db "<SQL>"`

## Existing Tags

### Primary Categories (from `primary_category` field)
```
ai-agents
ai-business
ai-research
ai-tools-comparison
claude-code
content-creation
image-generation
learning
local-ai
n8n-automation
open-source
philosophy
pricing-costs
productivity
prompt-engineering
seo-marketing
tool-releases
unclassified
video-generation
web-development
```

### Sub-Tags (from `tags_json` field)
```
ai-business, marketing-automation, growth
productivity, self-improvement, career
prompt-engineering, ai-prompts, tutorial
n8n, workflow-automation, automation
open-source, tools, github
claude-code, ai-development, vibe-coding
ai-tools, comparison, reviews
```

## Classification Workflow — Agent Scaling

### Level 1: Single Agent (1 agent)
**When**: <10 new unclassified bookmarks
- One agent processes all bookmarks
- Quick tag discovery and SQL update

### Level 2: Two Agents (2 agents)
**When**: 10-50 new unclassified bookmarks
- Agent 1: First half of bookmarks
- Agent 2: Second half of bookmarks
- Peer review between them

### Level 3: Three Agents (3 agents)
**When**: 50-150 bookmarks
- Agent 1: Batch 1, Agent 2: Batch 2, Agent 3: Batch 3
- One agent reviews all outputs (chairman)

### Level 4: Four Agents (4 agents)
**When**: 150-300 bookmarks
- 3 agents process batches, 1 agent synthesizes

### Level 5: Five Agents (5 agents)
**When**: 300+ bookmarks OR initial full classification
- 4 agents process quarters, 1 chairman synthesizes master tag list with SQL updates

### Agent Prompt Template
```
You are a Bookmark Analyst.

Your job: Analyze your assigned batch of bookmarks and DISCOVER tags organically.
DO NOT use predefined tags — look at what the bookmarks actually contain.

For each bookmark, identify:
1. What TOPIC is this about?
2. What TOOLS are mentioned?
3. What TECHNIQUE or METHOD is shown?
4. What CONTENT TYPE: news/insight, tool release, tutorial, opinion, announcement?

Output JSON:
{
  "agent_id": X,
  "tags_discovered": [{"tag": "tag-name", "why": "because bookmarks mention X"}],
  "bookmarks": [{"id": "...", "discovered_tags": ["tag1", "tag2"]}],
  "patterns": "Any patterns you notice"
}
```

### Query Command
```bash
sqlite3 ~/.ft-bookmarks/bookmarks.db "SELECT id, text, author_handle, primary_category FROM bookmarks ORDER BY synced_at DESC LIMIT N OFFSET X"
```

## Execute Classification SQL

Run the SQL updates to populate:
- `primary_category` — main topic
- `categories` — JSON array of all applicable tags
- `tags_json` — sub-tags

## Ongoing Classification (New Bookmarks)

1. **Check for unclassified**:
   ```bash
   sqlite3 ~/.ft-bookmarks/bookmarks.db "SELECT id, text, author_handle, primary_category FROM bookmarks WHERE primary_category IS NULL OR primary_category = '' LIMIT 10;"
   ```

2. **Match to existing tags** (ALWAYS check existing tags first):
   - Scan bookmark text against PRIMARY CATEGORIES list above
   - Scan against SUB-TAGS list above
   - If existing tag fits, use it — DO NOT create duplicate tags
   - If no existing tag fits, create new tag following naming convention

3. **Assign category**:
   - Match content to existing tags from the lists above
   - If no match, create new tag following naming convention
   - Update: `UPDATE bookmarks SET primary_category = 'X', categories = '["X", "Y"]' WHERE id = '...';`

## Wiki Indexing After Classification

Handled by the LLM Knowledge Base #Operations section in CLAUDE.md.