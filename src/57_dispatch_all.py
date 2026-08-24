#!/usr/bin/env python3
"""
Dispatch remaining Japanese main deck LLM generation batches.
Reads generation_status.json, dispatches in waves of 3.
"""
import json, time, sys
from pathlib import Path

ROOT = Path.home() / "dev" / "sino-korean"
status_file = ROOT / "data" / "jp_main" / "generation_status.json"
llm_dir = ROOT / "data" / "sentences_raw" / "jp_main"

status = json.loads(status_file.read_text())
n_batches = status["total_batches"]
BATCH_SIZE = 500

# Find completed and pending batches
completed = set()
pending = []

for i in range(1, n_batches + 1):
    out = llm_dir / f"out_{i:03d}.txt"
    if out.exists() and out.stat().st_size > 100:
        completed.add(i)
    else:
        pending.append(i)

print(f"Total batches: {n_batches}")
print(f"Completed: {len(completed)}")
print(f"Pending: {len(pending)}")
print(f"Next batch: {pending[0] if pending else 'DONE'}")

# Save updated status
status["completed_batches"] = len(completed)
status_file.write_text(json.dumps(status, indent=2))
print(f"Status saved to {status_file}")