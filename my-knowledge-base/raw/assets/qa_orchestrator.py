#!/usr/bin/env python3
"""
qa_orchestrator.py — QA Batch Orchestrator

Called by cron every minute. Reads state file, determines what to process next.

Cron setup (every minute, hours 10-19):
    * 10-19 * * * cd /path/to/my-knowledge-base && python3 raw/assets/qa_orchestrator.py

State file: raw/assets/qa-batch-state.json
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
STATE_FILE = SCRIPT_DIR / "qa-batch-state.json"
WIKI_ROOT = Path("/Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base")
QA_PAIRS_DIR = WIKI_ROOT / "wiki" / "qa-pairs"
SOURCES_DIR = WIKI_ROOT / "wiki" / "sources"

BATCH_SIZE = 15
STALE_LOCK_MINUTES = 15


def load_state():
    """Load current state from JSON file."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "phase": "layer1",
        "batches": {},
        "locked_sources": [],
        "completed_sources": [],
        "total_sources": 0,
        "batches_needed": 0,
        "batch_size": BATCH_SIZE,
        "layer1_complete": False,
        "synthesis_complete": False,
        "last_updated": None
    }


def save_state(state):
    """Save state to JSON file."""
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def get_all_sources():
    """Get list of all source slugs from wiki/sources/."""
    if not SOURCES_DIR.exists():
        return []
    return sorted([f.stem for f in SOURCES_DIR.glob("*.md")])


def get_uncovered_sources(all_sources, completed):
    """Get sources not yet processed."""
    return [s for s in all_sources if s not in completed]


def clear_stale_locks(state):
    """Clear locks older than STALE_LOCK_MINUTES."""
    if not state.get("locked_sources"):
        return state

    last_updated = state.get("last_updated")
    if not last_updated:
        state["locked_sources"] = []
        return state

    try:
        last_time = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        elapsed = (now - last_time).total_seconds() / 60

        if elapsed > STALE_LOCK_MINUTES:
            print(f"Clearing stale lock: {len(state['locked_sources'])} sources")
            state["locked_sources"] = []
    except Exception as e:
        print(f"Error parsing last_updated: {e}")
        state["locked_sources"] = []

    return state


def get_next_batch_number(state):
    """Get the next batch number to create."""
    existing = state.get("batches", {})
    batch_nums = []
    for name in existing.keys():
        if name.startswith("batch_"):
            try:
                num = int(name.split("_")[1])
                batch_nums.append(num)
            except:
                pass
    return max(batch_nums) + 1 if batch_nums else 1


def claim_next_batch(state, all_sources):
    """Claim next batch of sources to process."""
    completed = set(state.get("completed_sources", []))
    locked = set(state.get("locked_sources", []))

    uncovered = [s for s in all_sources if s not in completed and s not in locked]

    if not uncovered:
        return None, None, state

    next_batch = uncovered[:BATCH_SIZE]
    batch_num = get_next_batch_number(state)
    batch_name = f"batch_{batch_num:03d}"

    # Create batch entry
    if "batches" not in state:
        state["batches"] = {}

    state["batches"][batch_name] = {
        "sources": next_batch,
        "status": "processing"
    }

    state["locked_sources"] = next_batch
    state["phase"] = "layer1"

    return batch_name, next_batch, state


def mark_batch_complete(state, batch_name):
    """Move batch from locked to completed."""
    if batch_name and batch_name in state.get("batches", {}):
        state["batches"][batch_name]["status"] = "complete"

    completed = set(state.get("completed_sources", []))
    locked = set(state.get("locked_sources", []))
    completed.update(locked)

    state["completed_sources"] = sorted(list(completed))
    state["locked_sources"] = []

    # Check if layer1 complete
    all_sources = get_all_sources()
    if len(completed) >= len(all_sources):
        state["layer1_complete"] = True
        state["phase"] = "synthesis"

    return state


def main():
    print(f"\n{'='*50}")
    print(f"QA Orchestrator - {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*50}")

    # Load state
    state = load_state()
    all_sources = get_all_sources()
    state["total_sources"] = len(all_sources)

    print(f"Total sources: {len(all_sources)}")
    print(f"Completed: {len(state.get('completed_sources', []))}")
    print(f"Locked: {len(state.get('locked_sources', []))}")
    print(f"Phase: {state.get('phase', 'layer1')}")
    print(f"Batches: {list(state.get('batches', {}).keys())}")

    # Clear stale locks
    state = clear_stale_locks(state)

    # Check if synthesis needed
    if state.get("layer1_complete") and not state.get("synthesis_complete"):
        print("\nLayer1 complete! Ready for synthesis phase.")
        print("Run synthesis manually or set up synthesis cron.")
        save_state(state)
        return

    # If nothing locked and nothing to do
    completed = set(state.get("completed_sources", []))
    if len(completed) >= len(all_sources):
        print("All sources processed!")
        save_state(state)
        return

    # Claim next batch
    batch_name, batch, state = claim_next_batch(state, all_sources)

    if not batch:
        print("No more batches to claim")
        save_state(state)
        return

    print(f"\nClaimed {batch_name}: {len(batch)} sources")
    print(f"  First: {batch[0]}")
    print(f"  Last: {batch[-1]}")

    save_state(state)

    # Output the batch info for the session to use
    batch_info = {
        "batch_name": batch_name,
        "sources": batch,
        "phase": "layer1"
    }

    # Write batch info to temp file for session to read
    batch_file = SCRIPT_DIR / f"current-batch.json"
    with open(batch_file, 'w') as f:
        json.dump(batch_info, f, indent=2)

    print(f"\nBatch info written to {batch_file}")
    print("Run Claude Code session with these sources")


if __name__ == "__main__":
    main()
