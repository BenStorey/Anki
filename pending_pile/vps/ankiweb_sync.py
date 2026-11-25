#!/usr/bin/env python3
"""Pull the collection from AnkiWeb headless and rebuild the status CSV.

Runs on the VPS. Anki and the laptop are NOT needed:

1. Mirror collection at ~/life/anki-sync/collection.anki2:
   - missing -> create empty, full download from AnkiWeb
   - present -> sync_status: 0 = nothing, 1 = incremental, 2 = full download
   The mirror is only ever read by the recon engine; sync writes to it are
   the mirror catching up with the server. We never upload.
2. Run the validated recon engine (addon/recon.py) over the mirror ->
   write ~/life/anki-pending.csv (the exact file life-page.py reads).

Credentials: hkey in ~/life/anki-sync/hkey (chmod 600), copied from the
laptop's prefs21.db profile blob. The mirror is a *follower*; AnkiWeb is
the master. Losing the laptop costs nothing but this file's freshness.
"""
from __future__ import annotations

import csv
import os
import sqlite3
import sys
import time

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, "life", "anki-sync")
MIRROR = os.path.join(BASE, "collection.anki2")
HKEY_PATH = os.path.join(BASE, "hkey")
OUT_CSV = os.path.join(HOME, "life", "anki-pending.csv")
LOG = os.path.join(BASE, "sync.log")
HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, HERE)
import recon  # noqa: E402  (addon/recon.py — read-only engine)

CSV_SCHEMA = ["date", "deck", "pending_review", "pending_learning",
              "pending_new", "source"]


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def sync_mirror() -> None:
    from anki.collection import Collection
    from anki.sync import SyncAuth

    hkey = open(HKEY_PATH).read().strip()
    auth = SyncAuth(hkey=hkey, endpoint="https://sync29.ankiweb.net/",
                    io_timeout_secs=120)

    fresh = not os.path.exists(MIRROR)
    col = Collection(MIRROR)
    try:
        st = col.sync_status(auth)
        log(f"sync_status required={st.required} (0=none,1=incremental,"
            f"2=full) fresh={fresh}")
        if st.new_endpoint:
            auth = SyncAuth(hkey=hkey, endpoint=st.new_endpoint,
                            io_timeout_secs=120)
        if st.required == 1:
            out = col.sync_collection(auth, sync_media=False)
            log(f"incremental sync done (server_usn={out.server_usn})")
        elif st.required == 2 or fresh:
            col.close_for_full_sync()
            col.full_upload_or_download(auth=auth, server_usn=None,
                                        upload=False)
            log("full download done")
        else:
            log("mirror already in sync")
    finally:
        col.close()


def build_csv() -> None:
    db = sqlite3.connect(f"file:{MIRROR}?mode=ro&immutable=1", uri=True)
    try:
        ws = recon.last_blind_day(db) + 1
        we = recon.current_day(db)
        series = recon.reconstruct_series(db, ws, we)
        live = recon.live_pending(db)
        rows = []
        for N, counts in sorted(series.items()):
            date = recon.day_date(db, N)
            for deck in sorted(counts):
                rows.append({
                    "date": date, "deck": deck,
                    "pending_review": counts[deck],
                    "pending_learning": "", "pending_new": "",
                    "source": "ankiweb-recon",
                })
        with open(OUT_CSV, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_SCHEMA)
            w.writeheader()
            w.writerows(rows)
        last_all = series[we]["ALL"]
        drift = abs(last_all - live["ALL"]) / max(live["ALL"], 1)
        log(f"csv written: {len(rows)} rows, window day {ws}..{we} "
            f"({we - ws + 1} days)")
        log(f"validation: recon day {we} = {last_all:,} | "
            f"mirror live now = {live['ALL']:,} | drift = {drift:.2%}")
        if drift > 0.05:
            log("WARNING: drift above 5% — investigate")
    finally:
        db.close()


def regen_page() -> None:
    """Regenerate the status page (life-page.py owns index.html)."""
    import subprocess
    r = subprocess.run(
        ["python3", os.path.join(HOME, "bin", "life-page.py")],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        log(f"life-page.py failed: {r.stderr.strip()[:300]}")
    else:
        log("status page regenerated")


def main() -> None:
    os.makedirs(BASE, exist_ok=True)
    if not os.path.exists(HKEY_PATH):
        print("no hkey file — see README", file=sys.stderr)
        sys.exit(1)
    sync_mirror()
    build_csv()
    regen_page()


if __name__ == "__main__":
    main()
