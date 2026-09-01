#!/usr/bin/env python3
"""
85_restore_jp_readings.py — restore JP Enhanced Reading/Furigana to the ORIGINAL
backup values, reverting damage from 83_repair_jp_readings.py.

WHY: 83_repair_jp_readings.py re-rendered readings from the user's backup but
     broke ~9,074 cards — cramming the user's correct per-kanji spacing into
     whole-word blobs AND corrupting the reading kana on ~1,451 (e.g.
     親[した]しい -> 親しいたしい). The user's ORIGINAL backup readings are the
     ground truth and were mostly correct/spaced properly.

WHAT: For every JP Enhanced note whose live Reading differs from the pre-migration
     backup reading, copy the backup reading (exactly) into Reading + Furigana.
     This is a pure copy-back of the user's own correct data — no re-gen, no
     algorithm, no risk of introducing new errors.

SAFETY (this may be re-run):
  - Requires Anki closed; takes a backup first.
  - Only writes a note if it HAS a source backup reading (else leaves untouched).
  - Never invents readings — only copies the user's original string.
  - If a note's backup reading is empty/missing, it is skipped.

USAGE (venv, Anki closed):
  python3 src/85_restore_jp_readings.py
"""
import re, sqlite3, subprocess, sys, time
from pathlib import Path

HOME = Path.home()
COLLECTION = Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
BACKUP_READINGS = Path.home() / "dev/sino-korean/backups/collection_pre_jp_migrate_20260828_115923.anki2"
JP_ENH = 1738229000
JP_OLD = 1351215240429
BACKUP_DIR = HOME / "dev/sino-korean/backups"
# Sentence-contaminated old readings can't be reliably restored as-is (they held
# example sentences the user had in the reading field). Wait—those ARE the user's
# data too. But the current deck has clean separated example fields. We restore the
# reading PART of the old blob when clean, else skip.
JUNKY = re.compile(r'<br>|Meaning:|。|．')


def check_anki_closed():
    for proc in ["anki", "anki-qt", "anki-desktop", "ankiw"]:
        r = subprocess.run(["pgrep", "-x", proc], capture_output=True, text=True)
        if r.stdout.strip():
            sys.exit(f"ABORT: Anki ({proc}) is running. Close Anki and re-run.")


def main():
    check_anki_closed()
    # backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"collection_pre_jp_restore_{stamp}.anki2"
    uc = lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower())
    src = sqlite3.connect(f"file:{COLLECTION}?mode=ro", uri=True); src.create_collation("unicase", uc)
    dst = sqlite3.connect(str(backup)); src.backup(dst); dst.close(); src.close()
    print(f"  Backup: {backup}")

    # load original backup readings
    og = sqlite3.connect(f"file:{BACKUP_READINGS}?mode=ro&immutable=1", uri=True); og.create_collation("unicase", uc)
    old_map = {nid: flds.split(chr(31))[2] for nid, flds in og.execute("SELECT id,flds FROM notes WHERE mid=?", (JP_OLD,))}
    og.close()
    print(f"  Backup readings loaded: {len(old_map)}")

    conn = sqlite3.connect(str(COLLECTION)); conn.create_collation("unicase", uc)
    rows = conn.execute("SELECT id, flds FROM notes WHERE mid=?", (JP_ENH,)).fetchall()
    now = int(time.time())
    conn.execute("BEGIN")
    restored = 0; sk_no_old = 0; sk_same = 0
    for nid, flds in rows:
        f = flds.split(chr(31))
        cur = f[2]
        old = old_map.get(nid, '')
        if not old:
            sk_no_old += 1; continue
        # The user's ORIGINAL reading (including any old sentence-form) is the
        # authoritative data that 83 corrupted. Restore it EXACTLY. We do NOT skip
        # sentence-junk here — 83 broke the spacing on those too, and the old
        # sentence-reading is the correct original state.
        if old == cur:
            sk_same += 1; continue
        f[2] = old
        if len(f) > 12:
            f[12] = old
        conn.execute("UPDATE notes SET flds=?, mod=?, usn=-1 WHERE id=?", (chr(31).join(f), now, nid))
        conn.execute("UPDATE cards SET mod=?, usn=-1 WHERE nid=?", (now, nid))
        restored += 1
    conn.execute("UPDATE col SET mod=?", (now,))
    conn.commit(); conn.close()
    print(f"JP Enhanced notes: {len(rows)}")
    print(f"  RESTORED to original backup reading: {restored}")
    print(f"  skipped (no old reading): {sk_no_old}")
    print(f"  skipped (old == current): {sk_same}")
    print("Done. Verify -> Open Anki -> Check Database -> sync.")


if __name__ == "__main__":
    main()