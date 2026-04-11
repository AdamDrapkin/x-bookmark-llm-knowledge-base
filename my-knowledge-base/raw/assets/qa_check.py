#!/usr/bin/env python3
"""Standalone QA council event trigger."""
# SKILL: qa-council (wiki/qa-pairs/)
# Reads: ~/.claude/skills/qa-council/SKILL.md
# Reads: wiki/qa-pairs/concept-index.json
# Reads: wiki/sources/*.md (uncovered sources)
# Writes: wiki/qa-pairs/batch-*-qa.json
# Writes: wiki/qa-pairs/concept-index.json (merged)
# Writes: wiki/qa-pairs/_index.md (updated)
# Writes: wiki/outputs/pipeline-live.log (appended)
# API: MiniMax M2.7 via MINIMAX_API_KEY
# Trigger: sources_since_last_qa >= 20

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_core import init_environment, check_and_run_qa_if_needed

def main():
    config = init_environment()
    check_and_run_qa_if_needed(config)

if __name__ == "__main__":
    main()