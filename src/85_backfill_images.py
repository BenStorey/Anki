#!/usr/bin/env python3
"""
85_backfill_images.py — put the recovered <img> into the Image field of JP/CN Enhanced notes.

Run AFTER 84_add_image_field.py (Image field present). Uses a pre-migration backup
as the source of image references (the old Meaning field held the <img> and the
in-place migration preserved note IDs).

For each note ID that owned an image in the source backup (backup -> live by same
nid), set the note's new trailing 'Image' field to the recovered <img> HTML.

Usage (snap python, Anki closed): x src/85_backfill_images.py <live.anki2> [--apply]
Without --apply it prints a dry-run (how many would be patched).
"""
import re, sqlite3, sys
from pathlib import Path

HOME = Path.home()
LIVE = Path(sys.argv[1]) if len(sys.argv) > 1 else HOME / "snap/anki-desktop/common/User 1/collection.anki2"
APPLY = "--apply" in sys.argv
# Pre-migration backups that still hold the image references:
JP_BACKUP = HOME / "dev/sino-korean/backups/collection_pre_jp_migrate_20260828_115923.anki2"
CN_BACKUP = HOME / "dev/sino-korean/backups/collection_pre_chinese_wip_20260827_172451.anki2"
JP_MID = 1351215240429            # old Japanese model
CN_MID = 1351220176888            # old Chinese model
JP_ENH = 1738229000
CN_ENH = 1787807921282
# Live Image field index = new count-1
JP_IMAGE_IDX = 13
CN_IMAGE_IDX = 12

def uc(a, b): return (a.lower() > b.lower()) - (a.lower() < b.lower())

def collect(refs, olddb, mid):
    """From olddb, gather {nid: <img...> html} for the given old model."""
    conn = sqlite3.connect(f"file:{olddb}?mode=ro&immutable=1", uri=True)
    conn.create_collation("unicase", uc)
    out = {}
    for nid, flds in conn.execute("SELECT id, flds FROM notes WHERE mid=?", (mid,)):
        for m in re.finditer(r"<img[^>]*>", flds):
            out[nid] = m.group(0)
            break  # one image per note (they had one)
    conn.close()
    return out

def main():
    print(f"Live: {LIVE}  apply={APPLY}")
    jp_img = collect(JP_BACKUP, JP_BACKUP, JP_MID)
    cn_img = collect(CN_BACKUP, CN_BACKUP, CN_MID)
    print(f"  image-notes from backups: JP={len(jp_img)} CN={len(cn_img)}")

    conn = sqlite3.connect(str(LIVE))
    conn.create_collation("unicase", uc)
    updates = []
    # JP
    for nid, img in jp_img.items():
        row = conn.execute("SELECT mid, flds FROM notes WHERE id=? AND mid=?", (nid, JP_ENH)).fetchone()
        if not row:
            continue
        flds = row[1].split(chr(31))
        if len(flds) != JP_IMAGE_IDX + 1:
            continue
        # set Image field (index JP_IMAGE_IDX); don't clobber if already set
        if not flds[JP_IMAGE_IDX].strip():
            updates.append((nid, JP_IMAGE_IDX, img))
    for nid, img in cn_img.items():
        row = conn.execute("SELECT mid, flds FROM notes WHERE id=? AND mid=?", (nid, CN_ENH)).fetchone()
        if not row:
            continue
        flds = row[1].split(chr(31))
        if len(flds) != CN_IMAGE_IDX + 1:
            continue
        if not flds[CN_IMAGE_IDX].strip():
            updates.append((nid, CN_IMAGE_IDX, img))

    print(f"  notes to backfill: {len(updates)}")
    if not APPLY:
        print("  dry-run — re-run with --apply to write")
        conn.close()
        return
    import time
    now = int(time.time())
    conn.execute("BEGIN")
    for nid, idx, img in updates:
        flds = conn.execute("SELECT flds FROM notes WHERE id=?", (nid,)).fetchone()[0].split(chr(31))
        flds[idx] = img
        conn.execute("UPDATE notes SET flds=?, mod=?, usn=-1 WHERE id=?", (chr(31).join(flds), now, nid))
        conn.execute("UPDATE cards SET mod=?, usn=-1 WHERE nid=?", (now, nid))
    conn.execute("UPDATE col SET mod=?", (now,))
    conn.commit()
    conn.close()
    print(f"  Applied {len(updates)} image backfills.")
    print("  Next: update the card templates to render {{Image}}.")

if __name__ == "__main__":
    main()