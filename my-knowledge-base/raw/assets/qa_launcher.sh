#!/bin/bash
#
# qa_launcher.sh — Launch QA session for current batch
#
# Usage: qa_launcher.sh
#
# Reads current-batch.json from raw/assets/ and runs Claude Code
# with the batch sources for Layer 1 processing.
#
# After completion, updates qa-batch-state.json to mark batch complete.
#

set -e

WIKI_ROOT="/Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base"
CLAUDE_BIN="/Users/adamdrapkin/.local/bin/claude"
cd "$WIKI_ROOT"

# Run orchestrator to claim next batch
python3 raw/assets/qa_orchestrator.py

# Read the batch info
BATCH_INFO=$(cat raw/assets/current-batch.json)
BATCH_NAME=$(echo "$BATCH_INFO" | python3 -c "import json,sys; print(json.load(sys.stdin)['batch_name'])")
SOURCES=$(echo "$BATCH_INFO" | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin)['sources']))")

echo "Launching $BATCH_NAME with $SOURCES"
echo "---"

# Unset CLAUDECODE to allow nested sessions
unset CLAUDECODE

# Run Claude Code with the sources - USE FULL PATH
$CLAUDE_BIN -p "You are in the knowledge base wiki. Read the qa-council skill at ~/.claude/skills/qa-council/SKILL.md.

Process these 15 sources as $BATCH_NAME:
$SOURCES

IMPORTANT:
1. Generate ONLY Layer 1 (source_questions) - skip synthesis_questions for now
2. Save to wiki/qa-pairs/${BATCH_NAME}_qa.json
3. Report what you did including the source slugs processed." --dangerously-skip-permissions

echo "---"
echo "Batch $BATCH_NAME complete. Updating state..."

# Update state file - move from locked to completed
python3 -c "
import json
from pathlib import Path

STATE_FILE = Path('$WIKI_ROOT/raw/assets/qa-batch-state.json')
BATCH_NAME = '$BATCH_NAME'

with open(STATE_FILE) as f:
    state = json.load(f)

# Get the locked sources for this batch
locked = state.get('locked_sources', [])
batch_info = state.get('batches', {}).get(BATCH_NAME, {})

if batch_info:
    batch_info['status'] = 'complete'
    state['batches'][BATCH_NAME] = batch_info

# Move locked to completed
completed = set(state.get('completed_sources', []))
completed.update(locked)
state['completed_sources'] = sorted(list(completed))
state['locked_sources'] = []

# Update last_updated
from datetime import datetime, timezone
state['last_updated'] = datetime.now(timezone.utc).isoformat()

with open(STATE_FILE, 'w') as f:
    json.dump(state, f, indent=2)

print(f'State updated: {BATCH_NAME} complete')
print(f'Completed sources: {len(state[\"completed_sources\"])}')
"

echo "Done!"
