#!/usr/bin/env python3
"""
qa_orchestrator.py — QA Batch Orchestrator (Sequential Mode)

Master cron fires every 30 min. This script runs ALL batches sequentially:
1. Process all batches for Layer 1 (source_questions)
2. After all Layer 1 complete, add synthesis questions to all batches
3. Update state throughout

Cron setup (every 30 min, hours 10-19):
    */30 10-19 * * * cd /path/to/my-knowledge-base && python3 raw/assets/qa_orchestrator.py
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
STATE_FILE = SCRIPT_DIR / "qa-batch-state.json"
WIKI_ROOT = Path("/Users/adamdrapkin/Obsidian/synteo-intelligence/github-base/my-knowledge-base")
QA_PAIRS_DIR = WIKI_ROOT / "wiki" / "qa-pairs"
SOURCES_DIR = WIKI_ROOT / "wiki" / "sources"
LAUNCHER_PATH = SCRIPT_DIR / "qa_launcher.sh"

BATCH_SIZE = 15
STALE_LOCK_MINUTES = 20


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


def get_next_batch(state, all_sources):
    """Get next batch of sources to process."""
    completed = set(state.get("completed_sources", []))
    locked = set(state.get("locked_sources", []))

    # Also exclude sources already in existing batches
    batched_sources = set()
    for batch_info in state.get("batches", {}).values():
        if isinstance(batch_info, dict) and "sources" in batch_info:
            batched_sources.update(batch_info["sources"])

    # Uncovered = not completed, not locked, not in existing batches
    uncovered = [s for s in all_sources if s not in completed and s not in locked and s not in batched_sources]

    if not uncovered:
        return None, None

    next_batch = uncovered[:BATCH_SIZE]
    batch_num = len(state.get("batches", {})) + 1
    batch_name = f"batch_{batch_num:03d}"

    return batch_name, next_batch


def run_batch(batch_name, sources):
    """Run a single batch via launcher."""
    print(f"\n{'='*50}")
    print(f"Running {batch_name} with {len(sources)} sources")
    print(f"{'='*50}")

    # Write current batch info
    batch_info = {
        "batch_name": batch_name,
        "sources": sources,
        "phase": "layer1"
    }
    with open(SCRIPT_DIR / "current-batch.json", 'w') as f:
        json.dump(batch_info, f, indent=2)

    # Run Claude Code via subprocess
    sources_str = ' '.join(sources)

    cmd = [
        "/Users/adamdrapkin/.local/bin/claude", "-p",
        f"""You are in the knowledge base wiki. Read the qa-council skill at ~/.claude/skills/qa-council/SKILL.md.

Process these {len(sources)} sources as {batch_name}:
{sources_str}

IMPORTANT:
1. Generate ONLY Layer 1 (source_questions) - skip synthesis_questions for now
2. Save to wiki/qa-pairs/{batch_name}_qa.json
3. Report what you did.""",
        "--dangerously-skip-permissions"
    ]

    # Create clean environment (unset CLAUDECODE to allow nested sessions)
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(WIKI_ROOT),
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min timeout
            env=env
        )

        if result.returncode == 0:
            print(f"  ✓ {batch_name} complete")
            return True
        else:
            print(f"  ✗ {batch_name} failed: {result.stderr[:200]}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  ✗ {batch_name} timed out")
        return False
    except Exception as e:
        print(f"  ✗ {batch_name} error: {e}")
        return False


def update_state_after_batch(state, batch_name, sources):
    """Update state after batch completes."""
    if "batches" not in state:
        state["batches"] = {}

    state["batches"][batch_name] = {
        "sources": sources,
        "status": "complete"
    }

    # Move from locked to completed
    completed = set(state.get("completed_sources", []))
    completed.update(sources)
    state["completed_sources"] = sorted(list(completed))
    state["locked_sources"] = []

    # Check if layer1 complete
    all_sources = get_all_sources()
    if len(completed) >= len(all_sources):
        state["layer1_complete"] = True
        state["phase"] = "synthesis"

    save_state(state)


def run_synthesis(state):
    """Run synthesis after all Layer 1 complete."""
    print(f"\n{'='*50}")
    print("All Layer 1 complete! Running synthesis...")
    print(f"{'='*50}")

    # Collect all completed batch files
    batch_files = sorted(QA_PAIRS_DIR.glob("batch-*-qa.json"))

    if not batch_files:
        print("No batch files found for synthesis!")
        return False

    # Read all sources and concepts
    all_concepts = []
    all_source_slugs = []

    for bf in batch_files:
        try:
            with open(bf) as f:
                data = json.load(f)
                all_source_slugs.extend([sq["source_slug"] for sq in data.get("source_questions", [])])
                if "concept_index_update" in data:
                    all_concepts.extend(data["concept_index_update"].get("new_concepts", []))
        except Exception as e:
            print(f"  Warning: Could not read {bf}: {e}")

    # Generate synthesis questions
    synthesis_prompt = f"""You are generating synthesis questions for the knowledge base.

After processing {len(batch_files)} batches with {len(all_source_slugs)} sources, generate 4 synthesis questions that connect concepts across batches.

## EXISTING CONCEPTS ({len(all_concepts)} total)
{json.dumps(all_concepts[:20], indent=2)}

## BATCH FILES PROCESSED
{', '.join([bf.name for bf in batch_files])}

Generate 4 synthesis questions and update ALL batch JSON files with synthesis_questions.

Output a JSON patch for synthesis_questions to add to each batch file:

{{
  "synthesis_questions": [
    {{
      "question_id": "q_synth_01",
      "question_type": "intra_batch_pattern",
      "question": "What patterns emerge across sources?",
      "answer": "Use [[wikilinks]] to connect sources...",
      "referenced_source_slugs": ["source-slug-1"],
      "cross_batch_refs": []
    }}
    // ... 4 total
  ]
}}

IMPORTANT: Output ONLY valid JSON - no markdown, no explanations."""

    cmd = [
        "/Users/adamdrapkin/.local/bin/claude", "-p",
        synthesis_prompt,
        "--dangerously-skip-permissions"
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(WIKI_ROOT),
            capture_output=True,
            text=True,
            timeout=600  # 10 min timeout
        )

        if result.returncode == 0:
            print("  ✓ Synthesis complete")
            state["synthesis_complete"] = True
            state["phase"] = "done"
            save_state(state)
            return True
        else:
            print(f"  ✗ Synthesis failed")
            return False

    except Exception as e:
        print(f"  ✗ Synthesis error: {e}")
        return False


def main():
    print(f"\n{'='*60}")
    print(f"QA Orchestrator - Sequential Mode")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # Load state
    state = load_state()
    all_sources = get_all_sources()
    state["total_sources"] = len(all_sources)

    completed = set(state.get("completed_sources", []))
    locked = set(state.get("locked_sources", []))

    print(f"Total sources: {len(all_sources)}")
    print(f"Completed: {len(completed)}")
    print(f"Locked: {len(locked)}")
    print(f"Phase: {state.get('phase', 'layer1')}")
    print(f"Layer1 complete: {state.get('layer1_complete', False)}")
    print(f"Synthesis complete: {state.get('synthesis_complete', False)}")

    # Clear stale locks
    state = clear_stale_locks(state)
    save_state(state)

    # Check if synthesis needed
    if state.get("layer1_complete") and not state.get("synthesis_complete"):
        print("\nLayer1 complete! Running synthesis...")
        run_synthesis(state)
        print(f"\n{'='*60}")
        print("ALL DONE!")
        print(f"{'='*60}")
        return

    # Check if all done
    if len(completed) >= len(all_sources):
        if not state.get("synthesis_complete"):
            print("\nAll sources processed! Running synthesis...")
            run_synthesis(state)
        print("All done!")
        return

    # Process all remaining batches sequentially
    remaining = len(all_sources) - len(completed)
    batches_needed = (remaining + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"\nRemaining: {remaining} sources → {batches_needed} batches")
    print("Processing sequentially...\n")

    batch_count = 0
    while True:
        # Get next batch
        batch_name, sources = get_next_batch(state, all_sources)

        if not sources:
            print("\nNo more sources to process!")
            break

        # Mark as processing
        state["locked_sources"] = sources
        if "batches" not in state:
            state["batches"] = {}
        state["batches"][batch_name] = {"sources": sources, "status": "processing"}
        save_state(state)

        # Run the batch
        success = run_batch(batch_name, sources)

        if success:
            # Update state
            update_state_after_batch(state, batch_name, sources)
            batch_count += 1
            completed = set(state.get("completed_sources", []))
            print(f"Progress: {len(completed)}/{len(all_sources)} complete")
        else:
            print(f"  ⚠ Batch failed, continuing to next...")
            state["locked_sources"] = []
            save_state(state)

        # Small delay between batches
        time.sleep(2)

    print(f"\nProcessed {batch_count} batches")

    # Check if all done and run synthesis
    state = load_state()
    if state.get("layer1_complete") and not state.get("synthesis_complete"):
        run_synthesis(state)

    print(f"\n{'='*60}")
    print(f"Orchestrator complete!")
    print(f"Completed: {len(state.get('completed_sources', []))}/{len(all_sources)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
