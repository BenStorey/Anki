#!/usr/bin/env python3
"""Merge backfill CSV with live CSV — live wins on overlap.

Usage: python3 merge_csv.py backfill.csv live.csv output.csv
"""

from __future__ import annotations

import csv
import sys

CSV_SCHEMA = ["date", "deck", "pending_review", "pending_learning",
              "pending_new", "source"]


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    backfill_csv, live_csv, out_csv = sys.argv[1:4]

    merged: dict[tuple[str, str], dict] = {}

    with open(backfill_csv, newline="") as f:
        for r in csv.DictReader(f):
            merged[(r["date"], r["deck"])] = r

    with open(live_csv, newline="") as f:
        for r in csv.DictReader(f):
            merged[(r["date"], r["deck"])] = r  # live wins

    rows = sorted(merged.values(), key=lambda r: (r["date"], r["deck"]))
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_SCHEMA)
        w.writeheader()
        w.writerows(rows)
    print(f"merged: {len(rows)} rows -> {out_csv}")


if __name__ == "__main__":
    main()
