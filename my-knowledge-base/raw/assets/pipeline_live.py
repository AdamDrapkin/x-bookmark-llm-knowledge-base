#!/usr/bin/env python3
"""
pipeline_live.py — Live mode. Syncs new bookmarks via Field Theory CLI,
classifies them, and processes in batches of 10.

Location: raw/assets/pipeline_live.py

Prerequisites:
    - Field Theory CLI installed: npm install -g fieldtheory
    - Chrome logged into X (for ft sync session extraction)
    - ft auth completed (if using --api mode)

Usage:
    python raw/assets/pipeline_live.py

Flow:
    1. ft sync              → pulls new bookmarks into ~/.ft-bookmarks/bookmarks.db
    2. Query unprocessed    → bookmarks without 'processed' tag
    3. Classify untagged    → keyword cluster matching from bookmark-classification.md
    4. Batch into 10s       → dynamic batching
    5. Phases 1-4 per batch → extract, analyze, compile, finalize (QA skipped per-batch)
    6. Tag as processed     → adds 'processed' to categories in DB
    7. QA event check       → if 20+ new sources since last QA, fires QA council
"""

import argparse
import subprocess
import sys
from datetime import datetime

from pipeline_core import (
    init_environment,
    query_unprocessed_bookmarks,
    classify_untagged_bookmarks,
    get_existing_source_ids,
    run_full_pipeline,
    tag_as_processed,
    check_and_run_qa_if_needed,
    increment_qa_source_counter,
    chunk_list,
    full_path,
    append_to_file,
    today_str,
)


def main():
    parser = argparse.ArgumentParser(description="X Bookmark Pipeline — Live Mode")
    parser.add_argument("--skip-sync", action="store_true", help="Skip ft sync (use existing DB state)")
    parser.add_argument("--skip-fallback", action="store_true", help="Skip browser-fallback items")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config = init_environment(args.config)
    wiki_root = config["wiki_root"]
    db_path = config["bookmarks_db"]

    # ── STEP 1: SYNC ──
    if not args.skip_sync:
        print("═══ SYNCING BOOKMARKS ═══")
        try:
            result = subprocess.run(
                ["ft", "sync"],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                print(f"  ✓ Sync complete")
                if result.stdout.strip():
                    print(f"    {result.stdout.strip()[:200]}")
            else:
                print(f"  ⚠ Sync returned code {result.returncode}")
                if result.stderr.strip():
                    print(f"    {result.stderr.strip()[:200]}")
                # Continue anyway — DB may still have new items from partial sync
        except FileNotFoundError:
            print("  ✗ 'ft' command not found. Install: npm install -g fieldtheory")
            print("  Continuing with existing DB state...")
        except subprocess.TimeoutExpired:
            print("  ⚠ Sync timed out after 120s. Continuing with existing DB state...")

    # ── STEP 2: GET UNPROCESSED ──
    print("\n═══ CHECKING FOR NEW BOOKMARKS ═══")
    unprocessed = query_unprocessed_bookmarks(db_path)

    if not unprocessed:
        print("  Nothing new. All bookmarks are tagged 'processed'.")
        _log(wiki_root, "No new bookmarks found.")
        return

    # Filter against existing sources (belt + suspenders)
    existing_ids = get_existing_source_ids(wiki_root)
    truly_new = [b for b in unprocessed if b["id"] not in existing_ids]

    if not truly_new:
        print(f"  {len(unprocessed)} untagged bookmarks, but all have existing sources. Tagging as processed.")
        tag_as_processed([b["id"] for b in unprocessed], db_path)
        return

    print(f"  Found {len(truly_new)} new bookmarks to process")

    # ── STEP 3: CLASSIFY ──
    print("\n═══ CLASSIFYING UNTAGGED ═══")
    classify_untagged_bookmarks(truly_new, config)

    # ── STEP 4: BATCH & PROCESS ──
    batches = chunk_list(truly_new, 10)
    print(f"\n═══ PROCESSING {len(truly_new)} BOOKMARKS IN {len(batches)} BATCH(ES) ═══")

    total_sources = 0
    for i, batch in enumerate(batches):
        batch_id = f"live_{today_str()}_{i + 1:03d}"
        print(f"\n── Batch {i + 1}/{len(batches)}: {batch_id} ({len(batch)} bookmarks) ──")

        manifest = run_full_pipeline(
            batch, config, batch_id,
            skip_fallback=args.skip_fallback,
            skip_qa=True,  # QA is event-triggered, not per-batch in live mode
            update_backlog=False,
            batch_num=None,
        )

        # Tag as processed
        processed_ids = [b["id"] for b in batch]
        tag_as_processed(processed_ids, db_path)
        print(f"  Tagged {len(processed_ids)} bookmarks as processed")

        # Count sources created
        batch_sources = sum(
            1 for b in manifest["bookmarks"] if b.get("phase3", {}).get("source_summary")
        )
        total_sources += batch_sources
        increment_qa_source_counter(config, batch_sources)

    # ── STEP 5: QA EVENT CHECK ──
    print(f"\n═══ QA COUNCIL CHECK ═══")
    check_and_run_qa_if_needed(config)

    # ── DONE ──
    print(f"\n{'=' * 50}")
    print(f"  ✅ Live pipeline complete!")
    print(f"  Bookmarks processed: {len(truly_new)}")
    print(f"  Sources created: {total_sources}")
    print(f"  Batches: {len(batches)}")
    print(f"{'=' * 50}")

    _log(wiki_root, f"Processed {len(truly_new)} bookmarks → {total_sources} sources in {len(batches)} batches")


def _log(wiki_root: str, message: str):
    """Append to pipeline-live.log in wiki/outputs/."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path = full_path(wiki_root, "wiki/outputs/pipeline-live.log")
    append_to_file(log_path, f"[{timestamp}] {message}\n")


if __name__ == "__main__":
    main()
