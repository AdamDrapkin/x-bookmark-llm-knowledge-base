#!/usr/bin/env python3
"""
pipeline.py — Backlog mode. Processes the next unprocessed batch from backlog-log.md.

Location: raw/assets/pipeline.py

Usage:
    python raw/assets/pipeline.py
    python raw/assets/pipeline.py --skip-fallback
"""

import argparse
import multiprocessing
import os
import sys

# macOS fix: Use spawn instead of fork to avoid crashes with multi-threaded processes
# This prevents "fork() in multi-threaded context crashes on macOS ARM"
if sys.platform == "darwin":
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass  # Already set

from pipeline_core import (
    init_environment,
    find_next_batch,
    get_batch_ids_from_backlog,
    query_bookmarks_db,
    query_bookmarks_by_offset,
    get_existing_source_ids,
    run_full_pipeline,
    check_and_run_qa_if_needed,
    increment_qa_source_counter,
)


def main():
    parser = argparse.ArgumentParser(description="X Bookmark Pipeline — Backlog Mode")
    parser.add_argument("--skip-fallback", action="store_true", help="Skip browser-fallback items")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config = init_environment(args.config)
    wiki_root = config["wiki_root"]

    # Find next unprocessed batch
    batch_num = find_next_batch(wiki_root, config["backlog_log"])
    print(f"Next unprocessed batch: {batch_num}")

    # Get batch IDs and query DB
    batch_ids = get_batch_ids_from_backlog(wiki_root, config["backlog_log"], batch_num)
    bookmarks = query_bookmarks_db(config["bookmarks_db"], batch_ids)
    if not bookmarks:
        bookmarks = query_bookmarks_by_offset(
            config["bookmarks_db"], int(batch_ids[0]) if batch_ids else 1, len(batch_ids)
        )

    if not bookmarks:
        print("No bookmarks found for this batch.")
        sys.exit(0)

    # Filter already-processed
    existing = get_existing_source_ids(wiki_root)
    bookmarks = [b for b in bookmarks if b["id"] not in existing]
    if not bookmarks:
        print("All bookmarks in this batch already processed.")
        sys.exit(0)

    print(f"Processing {len(bookmarks)} bookmarks in batch {batch_num}")

    # Run full pipeline
    batch_id = f"batch_{batch_num:03d}"
    manifest = run_full_pipeline(
        bookmarks, config, batch_id,
        skip_fallback=args.skip_fallback,
        skip_qa=False,
        update_backlog=True,
        batch_num=batch_num,
    )

    # Increment QA counter and check trigger
    source_count = sum(
        1 for b in manifest["bookmarks"] if b.get("phase3", {}).get("source_summary")
    )
    increment_qa_source_counter(config, source_count)
    check_and_run_qa_if_needed(config)


if __name__ == "__main__":
    main()
