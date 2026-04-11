#!/usr/bin/env python3
"""Standalone wiki lint runner."""
# SKILL: wiki-lint (wiki/outputs/)
# Reads: ~/.claude/skills/wiki-lint/SKILL.md
# Reads: All wiki/**/*.md pages for inventory
# Writes: wiki/outputs/lint-{date}.md
# Writes: wiki/outputs/_index.md (updated)
# Writes: wiki/index.md (maintenance section)
# Writes: wiki/log.md (appended)
# Writes: wiki/entities/*.md or wiki/concepts/*.md (stub pages for broken links)
# API: MiniMax M2.7 via MINIMAX_API_KEY (contradiction detection only)
# Schedule: Daily 8 PM EST

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_core import init_environment, run_phase4, create_manifest, full_path, today_str, append_to_file

def main():
    config = init_environment()
    wiki_root = config["wiki_root"]
    print("═══ STANDALONE WIKI LINT ═══")
    manifest = {
        "batch_number": 0, "batch_id": f"lint_{today_str()}",
        "temp_dir": "/tmp/lint-standalone", "wiki_root": wiki_root,
        "status": "lint_only",
        "phase_status": {"phase4_finalize": "pending"},
        "bookmarks": [], "repost_originals": [],
        "qa_council": {"status": "skipped", "batch_qa_path": None},
        "lint": {"status": "pending", "report_path": None},
        "indexes_updated": False, "backlog_updated": False, "cleanup_complete": False,
    }
    run_phase4(manifest, config)
    log_msg = f"[{today_str()}] Standalone lint completed. Report: {manifest['lint'].get('report_path', 'N/A')}\n"
    append_to_file(full_path(wiki_root, "wiki/outputs/pipeline-live.log"), log_msg)
    print(f"\n✅ Lint complete. Report: {manifest['lint'].get('report_path')}")

if __name__ == "__main__":
    main()