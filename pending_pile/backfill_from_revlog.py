#!/usr/bin/env python3
"""Offline backfill: revlog -> CSV pending-pile history.

Read-only (mode=ro). Produces per-day, per-top-level-deck pending
review counts from the validated reconstruction rules in addon/recon.py,
from the day after the last FSRS-reschedule event to today.

Usage:
    python3 backfill_from_revlog.py [collection.anki2] [output.csv]

Validation: prints the backfill's last-day total next to a live probe;
they should match within a few percent.
"""

from __future__ import annotations

import csv
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "addon"))
import recon  # noqa: E402

DEFAULT_COLLECTION = os.path.expanduser(
    "~/snap/anki-desktop/common/User 1/collection.anki2"
)
DEFAULT_OUTPUT = os.path.join(HERE, "backfill.csv")
CSV_SCHEMA = ["date", "deck", "pending_review", "pending_learning",
              "pending_new", "source"]


def main() -> None:
    coll = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_COLLECTION
    out = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT

    db = sqlite3.connect(f"file:{coll}?mode=ro&immutable=1", uri=True)
    try:
        ws = recon.last_blind_day(db) + 1
        we = recon.current_day(db)
        print(f"backfill window: Anki-day {ws}..{we} "
              f"({recon.day_date(db, ws)} .. {recon.day_date(db, we)}, "
              f"{we - ws + 1} days)")

        cards, rev = recon.load_events(db, we)
        series = recon.reconstruct_series(db, ws, we)

        rows = []
        for N, counts in sorted(series.items()):
            date = recon.day_date(db, N)
            for deck in sorted(counts):
                rows.append({
                    "date": date,
                    "deck": deck,
                    "pending_review": counts[deck],
                    "pending_learning": "",
                    "pending_new": "",
                    "source": "backfill",
                })
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_SCHEMA)
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {len(rows)} rows -> {out}")

        # ---- validation: last backfill day vs live probe
        live = recon.live_pending(db)
        last_all = series[we]["ALL"]
        live_all = live["ALL"]
        drift = abs(last_all - live_all) / max(live_all, 1)
        print(f"validation: backfill day {we} = {last_all:,}  |  "
              f"live probe now = {live_all:,}  |  drift = {drift:.2%}")
        print("per-deck (backfill vs live):")
        for deck in sorted(live):
            if deck == "ALL":
                continue
            b = series[we].get(deck, 0)
            l = live[deck]
            mark = "" if b == l else f"  (diff {b - l:+d})"
            print(f"  {deck:<24} {b:>6,} vs {l:>6,}{mark}")
        if drift > 0.05:
            print("WARNING: drift above 5% — investigate before merging")
        else:
            print("OK: within validation gate")
    finally:
        db.close()


if __name__ == "__main__":
    main()
