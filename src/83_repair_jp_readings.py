#!/usr/bin/env python3
"""
83_repair_jp_readings.py — fix JP Enhanced Reading/Furigana fields in place.

Problem:
  - The furigana generator (fugashi/MeCab) misread homographs: 白鳥→はくちょう,
    小刀→しょうとう, 門扉→もんとびら (correct = しらとり/こがたな/もんぴ).
  - It also left ugly spacing: 宜[むべ] なる か な, 割[わ]っ て 入[はい]る.

Solution (authoritative source = user's pre-migration backup readings):
  For each note, read the OLD reading (backup, note IDs preserved in-place),
  take its kana as ground truth, and RE-RENDER ruby ONLY over kanji runs.
  Validate that aligned_kana == old_kana (nothing lost/corrupted) and skip if not
  (covers e.g. sentence-contaminated reading fields, ~3.9K, which can't be
  safely aligned — those are left untouched).

Usage (venv, Anki closed):
  python3 src/83_repair_jp_readings.py
"""
import re, sqlite3, sys, time
from pathlib import Path

HOME = Path.home()
COLLECTION = Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
BACKUP = Path.home() / "dev/sino-korean/backups/collection_pre_jp_migrate_20260828_115923.anki2"
JP_ENH = 1738229000
JP_OLD = 1351215240429
BACKUP_DIR = Path.home() / "dev/sino-korean/backups"

def is_kana(c): return '\u3040' <= c <= '\u30ff' or c == 'ー'
def is_kanji(c): return '\u4e00' <= c <= '\u9fff'

def old_total_kana(blob):
    """Extract all kana the old reading represents (bracket contents + bare kana)."""
    s = re.sub(r'\[([^\]]+)\]', lambda m: m.group(1), blob)
    return ''.join(c for c in s if is_kana(c))

def has_sentence_junk(blob):
    """A reading field that contains a full sentence / is abnormally long."""
    return ('<' in blob or '。' in blob or 'Meaning:' in blob
            or len(blob) > 60 or 'と' in blob and '。' in blob)

def split_kanji_runs(surface):
    runs = []; i = 0
    while i < len(surface):
        ch = surface[i]
        if is_kanji(ch):
            j = i
            while j < len(surface) and is_kanji(surface[j]): j += 1
            runs.append(('kanji', surface[i:j])); i = j
        elif is_kana(ch):
            j = i
            while j < len(surface) and is_kana(surface[j]): j += 1
            runs.append(('kana', surface[i:j])); i = j
        else:
            runs.append(('other', ch)); i += 1
    return runs

def align(surface, full_kana):
    """Rewalk surface + kana; attach kana to each kanji run. Kana/other stay bare."""
    if not full_kana: return surface
    runs = split_kanji_runs(surface)
    ri = 0; out = []
    for idx, (typ, text) in enumerate(runs):
        if typ == 'other':
            out.append(text); continue
        if typ == 'kana':
            out.append(text)
            for ch in text:
                if ri < len(full_kana) and full_kana[ri] == ch: ri += 1
            continue
        rest = ''.join(t for _, t in runs[idx+1:])
        next_kana = next((c for c in rest if is_kana(c)), None)
        buf = []
        while ri < len(full_kana):
            if next_kana and full_kana[ri] == next_kana: break
            buf.append(full_kana[ri]); ri += 1
        out.append(f"{text}[{''.join(buf)}]" if buf else text)
    return ''.join(out)

def check_anki_closed():
    for proc in ["anki", "anki-qt", "anki-desktop", "ankiw"]:
        r = __import__("subprocess").run(["pgrep", "-x", proc], capture_output=True, text=True)
        if r.stdout.strip():
            sys.exit(f"ABORT: Anki ({proc}) is running. Close Anki and re-run.")

def main():
    check_anki_closed()
    # backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"collection_pre_jp_readings_{stamp}.anki2"
    src = sqlite3.connect(f"file:{COLLECTION}?mode=ro", uri=True)
    src.create_collation("unicase", lambda a,b:(a.lower()>b.lower())-(a.lower()<b.lower()))
    dst = sqlite3.connect(str(backup)); src.backup(dst); dst.close(); src.close()
    print(f"  Backup: {backup}")

    # old readings
    oldc = sqlite3.connect(f"file:{BACKUP}?mode=ro&immutable=1", uri=True)
    oldc.create_collation("unicase", lambda a,b:(a.lower()>b.lower())-(a.lower()<b.lower()))
    old_map = {nid: flds.split(chr(31))[2] for nid, flds in oldc.execute("SELECT id,flds FROM notes WHERE mid=?", (JP_OLD,))}
    oldc.close()

    conn = sqlite3.connect(str(COLLECTION)); conn.create_collation("unicase", lambda a,b:(a.lower()>b.lower())-(a.lower()<b.lower()))
    rows = conn.execute("SELECT id, flds FROM notes WHERE mid=?", (JP_ENH,)).fetchall()

    now = int(time.time())
    conn.execute("BEGIN")
    updated = 0; skipped_junk = 0; skipped_validate = 0; skipped_same = 0; skipped_noold = 0
    for nid, flds in rows:
        f = flds.split(chr(31))
        ex = f[0]; cur = f[2]
        old = old_map.get(nid, '')
        if not old:
            skipped_noold += 1; continue
        if has_sentence_junk(old):
            skipped_junk += 1; continue   # can't safely align; leave untouched
        okana = old_total_kana(old)
        if not okana:
            skipped_validate += 1; continue
        new = align(ex, okana)
        # VALIDATE: aligned kana must exactly equal the authoritative old kana
        if old_total_kana(new) != okana:
            skipped_validate += 1; continue
        if new == cur:
            skipped_same += 1; continue
        f[2] = new
        f[12] = new            # Furigana field
        conn.execute("UPDATE notes SET flds=?, mod=?, usn=-1 WHERE id=?", (chr(31).join(f), now, nid))
        conn.execute("UPDATE cards SET mod=?, usn=-1 WHERE nid=?", (now, nid))
        updated += 1
    conn.execute("UPDATE col SET mod=?", (now,))
    conn.commit(); conn.close()

    print(f"JP Enhanced notes: {len(rows)}")
    print(f"  UPDATED reading+furigana: {updated}")
    print(f"  skipped (sentence-junk old reading, left as-is): {skipped_junk}")
    print(f"  skipped (validation failed, left as-is): {skipped_validate}")
    print(f"  skipped (old==current): {skipped_same}")
    print(f"  skipped (no old reading): {skipped_noold}")
    print("Done. Verify, then Open Anki -> Check Database -> sync.")

if __name__ == "__main__":
    main()