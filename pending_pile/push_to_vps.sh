#!/usr/bin/env bash
# Push the merged pending-pile CSV to the VPS status page.
# Run after merge_csv.py (or by the add-on's cron, if any).
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$DIR/merged.csv"
[ -f "$SRC" ] || { echo "no merged.csv in $DIR — run merge_csv.py first" >&2; exit 1; }
scp "$SRC" ben@187.52.119.20:~/life/anki-pending.csv
ssh ben@187.52.119.20 'python3 ~/bin/life-page.py'
echo "pushed + status page regenerated"
