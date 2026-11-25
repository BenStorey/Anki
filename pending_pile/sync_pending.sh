#!/usr/bin/env bash
# Pending-pile sync: reconstruct the full series straight from the
# collection DB (Anki does NOT need to be open), merge with the add-on's
# live anchor snapshots, then push to the status page.
#
# Designed for a systemd user timer; safe to run manually any time.
# Read-only wrt collection.anki2 (immutable URI) — Anki-open safe.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
VPS="ben@187.52.119.20"
COLL="$HOME/snap/anki-desktop/common/User 1/collection.anki2"
LIVE_CSV="$HOME/snap/anki-desktop/common/User 1/pending-pile.csv"

cd "$DIR"

# 1. Full reconstruction from the DB (covers PC-off days exactly: the
#    recon engine replays due-date flips with zero reviews).
python3 backfill_from_revlog.py "$COLL" backfill.csv

# 2. Merge with the add-on's live anchors (live wins on overlap).
if [ -f "$LIVE_CSV" ]; then
    python3 merge_csv.py backfill.csv "$LIVE_CSV" merged.csv
else
    cp backfill.csv merged.csv
fi

# 3. Push + regenerate the status page (life-page.py owns index.html).
scp -q merged.csv "$VPS:~/life/anki-pending.csv"
ssh "$VPS" 'python3 ~/bin/life-page.py' >/dev/null

echo "synced: $(tail -1 merged.csv | cut -d, -f1) -> status page"
