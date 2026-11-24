# Pending Pile Tracker

Anki add-on + offline backfill that records how many **review cards are
pending** (deck limits ignored) at the start of each Anki day, so the
shrinking pile is visible day by day.

- **Headline number = review cards only** (`type=2, queue>=0, due<=today`).
  New cards are excluded (15.7k of them never change); learning/new counts
  are logged as extra CSV columns.
- **History**: ~670 days reconstructed exactly from the revlog (backfill),
  then live snapshots every day Anki is opened (first open of the day wins).
  Days Anki was never opened are gap-filled exactly by the add-on.
- **Deck-by-deck**: banner on the deck browser (global diff vs yesterday),
  chart on the stats screen (one line per top-level deck + bold total).
- **Read-only**: the add-on never writes to collection.anki2.

## Install

Copy (or symlink) `addon/` into the Anki add-ons folder as `pending-pile`:

    cp -r pending_pile/addon "/home/ben/snap/anki-desktop/common/addons21/pending-pile"

Restart Anki. On first open it appends today's snapshot to
`pending-pile.csv` next to the collection and logs to
`addons21/pending-pile/pending-pile.log`.

## Backfill (run once, Anki closed or open — read-only either way)

    python3 pending_pile/backfill_from_revlog.py

Writes `backfill.csv` (day 2025-01-23 → today, per top-level deck) and
prints a validation line: backfill endpoint vs live probe. Verified
2026-11-24: within 0.05% globally, exact for the three big decks.

## Merge + push to status page

    python3 pending_pile/merge_csv.py backfill.csv pending-pile.csv merged.csv

`merged.csv` is what the stats chart and the VPS status page read.
Laptop pushes it:

    scp merged.csv ben@187.52.119.20:~/life/anki-pending.csv

## CSV schema

    date,deck,pending_review,pending_learning,pending_new,source

`deck` is a top-level deck name or `ALL`. `source` is `backfill`,
`gapfill`, or `live`.

## Semantics (why the numbers are what they are)

- A review card is pending on day N iff its last due-setting event
  before day N set due <= N. Reviews (revlog types 1/2/3) set
  `due = day + interval`; type 4/5 (manual / FSRS reschedule) are opaque,
  handled per BRIEF.md's Type-5 Hole rules (cards.due is exact when no
  later review exists; otherwise the card is pending through the blind
  gap until its next review).
- The window starts 2025-01-23 (day after the last FSRS reschedule);
  earlier days are not reconstructible (verified — no estimator works).
- Snapshots are start-of-day: today's row reflects 03:00 HKT, before any
  reviews done today. Expect the banner to be slightly higher than the
  live deck-browser count on days you already reviewed.
