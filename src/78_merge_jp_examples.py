#!/usr/bin/env python3
"""
Re-merge Phase-3 JP content (Nuance_JP + Example1-3 + EN) into Japanese Enhanced notes.

Background: script 61 loaded out_*.txt in sorted order; out_mn_* (Meaning+Nuance_EN
only) overwrote word entries and wiped Example1-3 + Nuance_JP for notes (they ended
up ~blank in fields 4-9 and 11). Meaning(1), Nuance_EN(10), Reading(2), Furigana(12)
are already filled and must be preserved.

This pass loads ONLY the Phase-3 files (out_*.txt minus out_mn_*), parses Nuance +
Example1..3 + their EN, and UPDATEs fields 4-9 and 11. Leaves 0,1,2,3,10,12 untouched.

SAFETY: Anki must be closed. Backs up first.
"""
import sqlite3, re, time, sys, subprocess
from pathlib import Path

COLLECTION = Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
LLM_DIR = Path.home() / "dev/sino-korean/data/sentences_raw/jp_main"
BACKUP_DIR = Path.home() / "dev/sino-korean/backups"
MODEL_ID = 1738229000  # Japanese Enhanced

def unicase(a, b):
    return (a.lower() > b.lower()) - (a.lower() < b.lower())

def check_anki_closed():
    for proc in ["anki", "anki-qt", "anki-desktop"]:
        r = subprocess.run(["pgrep", "-x", proc], capture_output=True, text=True)
        if r.stdout.strip():
            sys.exit(f"ABORT: Anki ({proc}) running.")

def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"collection_pre_jp_phase3_merge_{stamp}.anki2"
    src = sqlite3.connect(f"file:{COLLECTION}?mode=ro", uri=True)
    src.create_collation("unicase", unicase)
    dst = sqlite3.connect(str(backup)); src.backup(dst)
    dst.close(); src.close()
    print(f"  Backup: {backup}")

def load_phase3():
    """Return {word: {nuance_jp, ex1..ex3, ex1_en..ex3_en}} from non-mn out files."""
    out = {}
    files = [f for f in sorted(LLM_DIR.glob("out_*.txt")) if "out_mn_" not in f.name]
    for f in files:
        content = f.read_text(encoding="utf-8", errors="replace")
        for block in content.split("===word: ")[1:]:
            word = block.split("===")[0].strip()
            rest = block.split("===")[1] if "===" in block else block
            e = {"nuance_jp": "", "ex1": "", "ex1_en": "", "ex2": "", "ex2_en": "",
                 "ex3": "", "ex3_en": ""}
            for line in rest.split("\n"):
                s = line.strip()
                if s.startswith("Nuance:"):
                    e["nuance_jp"] = s[len("Nuance:"):].strip()
                elif s.startswith("Example1_EN:"):
                    e["ex1_en"] = s[len("Example1_EN:"):].strip()
                elif s.startswith("Example1:"):
                    e["ex1"] = s[len("Example1:"):].strip()
                elif s.startswith("Example2_EN:"):
                    e["ex2_en"] = s[len("Example2_EN:"):].strip()
                elif s.startswith("Example2:"):
                    e["ex2"] = s[len("Example2:"):].strip()
                elif s.startswith("Example3_EN:"):
                    e["ex3_en"] = s[len("Example3_EN:"):].strip()
                elif s.startswith("Example3:"):
                    e["ex3"] = s[len("Example3:"):].strip()
            if word:
                # merge: keep multl-line nuance
                if word in out:
                    prev = out[word]
                    e["nuance_jp"] = prev.get("nuance_jp","")
                    for k in ["ex1","ex1_en","ex2","ex2_en","ex3","ex3_en"]:
                        if not e.get(k) and prev.get(k): e[k]=prev[k]
                out[word] = e
    return out

def main():
    check_anki_closed()
    print("Loading Phase-3 content...")
    p3 = load_phase3()
    print(f"  Loaded {len(p3)} words")
    make_backup()

    conn = sqlite3.connect(str(COLLECTION))
    conn.create_collation("unicase", unicase)
    cursor = conn.execute("SELECT id, flds FROM notes WHERE mid=?", (MODEL_ID,))
    full = [(row[0], row[1].split(chr(31))) for row in cursor.fetchall()]
    print(f"  {len(full)} Enhanced notes")

    updates = []
    matched = 0
    for nid, flds in full:
        if len(flds) < 13:
            continue
        w = flds[0].strip()
        e = none if False else (p3.get(w) or None)
        if not e:
            # try normalized match
            for lw in p3:
                if lw in w or w in lw:
                    e = p3[lw]; break
        if not e:
            continue
        ex1 = e.get("ex1") or flds[4]
        ex1_en = e.get("ex1_en") or flds[5]
        ex2 = e.get("ex2") or flds[6]
        ex2_en = e.get("ex2_en") or flds[7]
        ex3 = e.get("ex3") or flds[8]
        ex3_en = e.get("ex3_en") or flds[9]
        nu_jp = e.get("nuance_jp") or flds[11]
        # only update if something changes
        if (ex1, ex1_en, ex2, ex2_en, ex3, ex3_en, nu_jp) != (flds[4], flds[5], flds[6], flds[7], flds[8], flds[9], flds[11]):
            matched += 1
            new_flds = chr(31).join([
                flds[0], flds[1], flds[2], flds[3],
                ex1, ex1_en, ex2, ex2_en, ex3, ex3_en,
                flds[10], nu_jp, flds[12],
            ])
            updates.append((new_flds, nid))

    print(f"  Matched: {matched}")

    if updates:
        now = int(time.time())
        conn.execute("BEGIN")
        for flds, nid in updates:
            conn.execute("UPDATE notes SET flds=?, mod=?, usn=-1 WHERE id=?", (flds, now, nid))
        conn.execute("UPDATE col SET mod=?", (now,))
        conn.commit()
        print(f"  Updated {len(updates)} notes")

    # Verify
    cursor = conn.execute("SELECT flds FROM notes WHERE mid=?", (MODEL_ID,))
    total = m = en = jp = ex = fu = 0
    for (flds,) in cursor.fetchall():
        f = flds.split(chr(31))
        if len(f) >= 13:
            total += 1
            if f[4].strip(): ex += 1
            if f[11].strip(): jp += 1
            if f[1].strip(): m += 1
            if f[10].strip(): en += 1
            if f[12].strip(): fu += 1
    print(f"\nFinal ({total} notes):")
    print(f"  Example1: {ex}/{total} ({ex/total*100:.0f}%)")
    print(f"  Nuance_JP: {jp}/{total} ({jp/total*100:.0f}%)")
    print(f"  Meaning:   {m}/{total}")
    print(f"  Nuance_EN: {en}/{total}")
    print(f"  Furigana:  {fu}/{total}")
    conn.close()
    print("\nDone!")

if __name__ == "__main__":
    main()