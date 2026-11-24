#!/usr/bin/env python3
"""Pending Pile reconstruction engine — shared by the add-on and the
backfill script.

Computes, per Anki-day, how many review cards were pending (limits
ignored) at the START of each Anki day, per top-level deck.

Rules (validated against live data 2026-11-24, see BRIEF.md):

- A review card (type=2, queue>=0) is pending on day N iff the last
  due-setting event strictly before day N set its due <= N.
- Due-setting events:
  * revlog type 1/2/3 (review): due = event_day + max(ivl, 0) Anki-days
    (ivl <= 0 -> pending from the event day itself)
  * revlog type 4/5 (manual / FSRS mass reschedule): OPAQUE — the
    revlog does not record the due actually written. Two cases:
      - no review after the event, ever: the due it wrote survives in
        cards.due (EXACT)
      - a review comes later: bridge the blind gap with the pre-blind
        review's due (the card was pending from that due through the
        blind event, and its review soon after proves it was still in
        the due pile; approximation band <1% of the pile)
- Cards never touched by a review (types 1/2/3) were 'new' — excluded.
- Backfill window starts the day after the last type-4/5 event, so
  blind events never occur INSIDE the window; they only bound the
  window start.

Implementation: per-card pending-interval construction + sweep-line
diff arrays (fast: one pass over events, O(days) aggregation).

Read-only: callers pass an sqlite3 connection opened with mode=ro.
This module never writes to the collection.
"""

from __future__ import annotations

import datetime
import sqlite3
import time
from collections import defaultdict

REVIEW_TYPES = (1, 2, 3)
BLIND_TYPES = (4, 5)
DAY = 86400


# ---------------------------------------------------------------- basics

def crt_of(db: sqlite3.Connection) -> int:
    return db.execute("SELECT crt FROM col").fetchone()[0]


def day_number(db: sqlite3.Connection, epoch_secs: float) -> int:
    """Anki day number for a wall-clock epoch-seconds timestamp."""
    return int((epoch_secs - crt_of(db)) // DAY)


def current_day(db: sqlite3.Connection) -> int:
    return day_number(db, time.time())


def last_blind_day(db: sqlite3.Connection) -> int:
    """Latest Anki-day with an opaque due-writing event (type 4/5)."""
    row = db.execute("SELECT MAX(id) FROM revlog WHERE type IN (4,5)").fetchone()
    if row is None or row[0] is None:
        return 0
    return int((row[0] / 1000 - crt_of(db)) // DAY)


def day_date(db: sqlite3.Connection, N: int) -> str:
    """Calendar date (YYYY-MM-DD, HKT) on which Anki-day N starts."""
    ts = crt_of(db) + N * DAY + 8 * 3600
    return datetime.datetime.fromtimestamp(
        ts, datetime.timezone.utc
    ).strftime("%Y-%m-%d")


def date_day(db: sqlite3.Connection, date_str: str) -> int:
    """Inverse of day_date: Anki-day that starts on date_str (HKT)."""
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    ts = dt.replace(tzinfo=datetime.timezone.utc).timestamp() - 8 * 3600
    return day_number(db, ts)


def top_level_decks(db: sqlite3.Connection) -> list[str]:
    """Names of all non-filtered top-level decks (excl. Default)."""
    out = []
    for _id, name in db.execute("SELECT id, name FROM decks"):
        if "::" in name or name == "Default":
            continue
        out.append(name)
    return out


def live_pending(db: sqlite3.Connection) -> dict[str, int]:
    """Live pending review counts per top-level deck (limits ignored).

    Child-deck cards fold into the top-level name. 'ALL' holds the sum.
    """
    N = current_day(db)
    deckname = dict(db.execute("SELECT id, name FROM decks"))
    counts: dict[str, int] = defaultdict(int)
    q = db.execute(
        "SELECT c.did, COUNT(*) FROM cards c "
        "WHERE c.type=2 AND c.queue>=0 AND c.due<=? GROUP BY c.did",
        (N,),
    )
    for did, n in q:
        top = deckname.get(did, "?").split("::")[0]
        if top == "Default":
            continue
        counts[top] += n
    total = sum(counts.values())
    counts["ALL"] = total
    return dict(counts)


# ------------------------------------------------------- event loading

def load_events(db: sqlite3.Connection, max_day: int):
    """Load revlog events for all review cards, up to max_day inclusive.

    Returns (cards, rev):
      cards: [(cid, top_deck_name, current_due), ...]  (queue>=0, type=2)
      rev:   {cid: [(day, type, ivl), ...] sorted by day}
    """
    deckname = dict(db.execute("SELECT id, name FROM decks"))
    cards = []
    for cid, did, due in db.execute(
        "SELECT id, did, due FROM cards WHERE type=2 AND queue>=0"
    ):
        top = deckname.get(did, "?").split("::")[0]
        if top == "Default":
            continue
        cards.append((cid, top, due))

    card_ids = [c[0] for c in cards]
    rev: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    q = db.execute(
        "SELECT cid, id, type, ivl FROM revlog "
        "WHERE cid IN (SELECT id FROM cards WHERE type=2) ORDER BY cid, id"
    )
    for cid, rid, typ, ivl in q:
        d = int((rid / 1000 - crt_of(db)) // DAY)
        if d <= max_day:
            rev[cid].append((d, typ, ivl))
    return cards, rev


# ------------------------------------------------ intervals (per card)

def pending_intervals(
    events: list[tuple[int, int, int]],
    cur_due: int,
    window_end: int,
) -> list[tuple[int, int]]:
    """Days (as half-open-ish inclusive ranges) during which ONE card
    was pending, up to window_end. Merged and sorted."""
    evs = [e for e in events if e[0] <= window_end and e[1] in (1, 2, 3, 4, 5)]
    if not evs:
        return []
    n = len(evs)
    # review_after[i]: does any review (1/2/3) exist after index i?
    review_after = [False] * (n + 1)
    for i in range(n - 1, -1, -1):
        review_after[i] = review_after[i + 1] or evs[i][1] in REVIEW_TYPES

    ivs: list[tuple[int, int]] = []
    pending_since: int | None = None  # card pending from this day onwards
    for i, (d, typ, ivl) in enumerate(evs):
        # close any open interval: the card's status changes AT this event
        # (start-of-day semantics: it was pending up to and including d
        # iff pending_since <= d; the event's own effect starts after d)
        if pending_since is not None:
            ivs.append((pending_since, d))
            pending_since = None
        if typ in REVIEW_TYPES:
            if ivl <= 0:
                # new due = d -> pending again from d+1 (at d's start the
                # review hadn't happened yet, so unless the card was
                # already pending the closed interval above covers it)
                pending_since = d + 1
            else:
                pending_since = d + ivl
        else:  # type 4/5 — opaque
            if not review_after[i + 1]:
                # no review after, ever: cards.due is the exact output
                a = max(d + 1, cur_due)
                pending_since = a if a <= window_end else None
            else:
                # a review comes later: bridge the blind gap.
                # - card had prior reviews: it was demonstrably still in
                #   the due pile (it got reviewed soon after) -> pending
                #   from the day after the blind event until that review
                # - card was reschedule-only (no review before either):
                #   the rescheduler gave it its first review-queue due;
                #   pending from the blind event until that review
                pending_since = d + 1
    if pending_since is not None:
        ivs.append((pending_since, window_end))
    return _merge(ivs)  # type: ignore[return-value]


def _merge(ivs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ivs:
        return []
    ivs = sorted(ivs)
    out = [list(ivs[0])]
    for a, b in ivs[1:]:
        if a <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [tuple(x) for x in out]


def pending_on_day(
    events: list[tuple[int, int, int]],
    cur_due: int,
    N: int,
) -> bool:
    """Single-day pending check (reference implementation, matches
    pending_intervals semantics exactly)."""
    evs = [e for e in events if e[0] < N and e[1] in (1, 2, 3, 4, 5)]
    if not evs:
        return False
    d, typ, ivl = evs[-1]
    if typ in REVIEW_TYPES:
        return (d if ivl <= 0 else d + ivl) <= N
    # blind event is the last one before N:
    # was it followed by a review at all? If not, cards.due is truth.
    review_after = any(e[1] in REVIEW_TYPES for e in evs[len(evs):])
    if not review_after:
        return cur_due <= N
    # a review comes after N: bridge — pending from the day after the
    # blind event (the card was in the due pile: it got reviewed later)
    return d + 1 <= N


# ------------------------------------------------------------- series

def reconstruct_series(
    db: sqlite3.Connection,
    window_start: int,
    window_end: int,
) -> dict[int, dict[str, int]]:
    """Pending review counts per top-level deck at the START of each day
    in [window_start, window_end]. Returns {day: {deck: count, 'ALL': n}}.
    """
    cards, rev = load_events(db, window_end)
    W = window_end - window_start + 1
    diffs: dict[str, list[int]] = {}

    for cid, deck, cur_due in cards:
        events = rev.get(cid)
        if not events:
            continue  # never reviewed -> new, excluded
        if deck not in diffs:
            diffs[deck] = [0] * (W + 2)
        arr = diffs[deck]
        for a, b in pending_intervals(events, cur_due, window_end):
            a2 = max(a, window_start)
            b2 = min(b, window_end)
            if a2 > b2:
                continue
            arr[a2 - window_start] += 1
            arr[b2 + 1 - window_start] -= 1

    out: dict[int, dict[str, int]] = {}
    for deck, arr in diffs.items():
        running = 0
        for i in range(W):
            running += arr[i]
            if running:
                out.setdefault(window_start + i, {})[deck] = running
    for day_counts in out.values():
        day_counts["ALL"] = sum(v for k, v in day_counts.items() if k != "ALL")
    return out
