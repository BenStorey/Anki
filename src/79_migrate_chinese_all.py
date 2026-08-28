#!/usr/bin/env python3
"""
Migrate BOTH Chinese decks (Chinese + Chinese WIP) to the Chinese Enhanced model.

Only run AFTER the Chinese Enhanced notetype exists (created by importing
chinese_enhanced.apkg in Anki — the import also yields a dummy card to delete).

Reads LLM output from data/sentences_raw/chinese_main (out_cm_) and
chinese_wip (out_cw_). Maps each old-model note by Expression, builds the
12-field record, and updates in place — cards STAY in whichever deck they
currently occupy (Chinese or Chinese WIP).

Field map (Chinese Enhanced 12f):
  0 Expression | 1 Meaning | 2 Pinyin | 3 Nuance | 4 Ex1 | 5 Ex1_EN
  6 Ex2 | 7 Ex2_EN | 8 Ex3 | 9 Ex3_EN | 10 Nuance_EN | 11 Nuance_CN

Old model: Expression | Meaning(HTML) | Reading(=Pinyin)

SAFETY: Anki closed; backup first.
"""
import sqlite3, re, time, sys, subprocess
from pathlib import Path

COLLECTION = Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
ROOT = Path.home() / "dev/sino-korean"
BACKUP_DIR = ROOT / "backups"
LLM_DIRS = {
    1351219999178: ROOT / "data/sentences_raw/chinese_main",   # Chinese deck
    1754445298156: ROOT / "data/sentences_raw/chinese_wip",     # Chinese WIP
}
NEW_MODEL_ID = 1787807921282   # Chinese Enhanced
OLD_MODEL_ID = 1351220176888   # Chinese

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
    backup = BACKUP_DIR / f"collection_pre_chinese_migrate_{stamp}.anki2"
    src = sqlite3.connect(f"file:{COLLECTION}?mode=ro", uri=True)
    src.create_collation("unicase", unicase)
    dst = sqlite3.connect(str(backup)); src.backup(dst)
    dst.close(); src.close()
    print(f"  Backup: {backup}")

def load_llm(directory):
    prefixes = [("Meaning:", "meaning"), ("Nuance_EN:", "nuance_en"),
                ("Nuance_CN:", "nuance_cn"), ("Example1:", "ex1"),
                ("Example1_EN:", "ex1_en"), ("Example2:", "ex2"),
                ("Example2_EN:", "ex2_en"), ("Example3:", "ex3"),
                ("Example3_EN:", "ex3_en")]
    out = {}
    for f in sorted(directory.glob("out_*.txt")):
        content = f.read_text(encoding="utf-8", errors="replace")
        for block in content.split("===word: ")[1:]:
            word = block.split("===")[0].strip()
            rest = block.split("===")[1] if "===" in block else block
            fields = {}
            for line in rest.split("\n"):
                s = line.strip()
                for pfx, key in prefixes:
                    if s.startswith(pfx):
                        fields[key] = s[len(pfx):].strip()
            if word:
                out[word] = fields
    return out

def build_fields(word, old_flds, entry):
    pinyin = old_flds[2].strip() if len(old_flds) > 2 else ""
    return chr(31).join([
        word, entry.get("meaning", ""), pinyin, "", entry.get("ex1", ""),
        entry.get("ex1_en", ""), entry.get("ex2", ""), entry.get("ex2_en", ""),
        entry.get("ex3", ""), entry.get("ex3_en", ""),
        entry.get("nuance_en", ""), entry.get("nuance_cn", ""),
    ])

def main():
    check_anki_closed()
    # Verify notetype exists
    conn0 = sqlite3.connect(f"file:{COLLECTION}?mode=ro", uri=True)
    conn0.create_collation("unicase", unicase)
    has_nt = conn0.execute("SELECT COUNT(*) FROM notetypes WHERE id=?", (NEW_MODEL_ID,)).fetchone()[0]
    conn0.close()
    if not has_nt:
        sys.exit("ABORT: Chinese Enhanced notetype does NOT exist. Import chinese_enhanced.apkg in Anki first, then re-run.")

    llm_loaded = 0
    total = matched = unmatched = 0
    updates = []
    unmatched_words = []

    for deck_id, llm_dir in LLM_DIRS.items():
        llm = load_llm(llm_dir)
        llm_loaded += len(llm)
        print(f"Deck {deck_id}: loaded {len(llm)} words from {llm_dir.name}")

        conn = sqlite3.connect(f"file:{COLLECTION}?mode=ro", uri=True)
        conn.create_collation("unicase", unicase)
        cursor = conn.execute('''
            SELECT n.id, n.flds FROM notes n
            JOIN cards c ON c.nid = n.id
            WHERE n.mid = ? AND c.did = ?
            GROUP BY n.id
        ''', (OLD_MODEL_ID, deck_id))
        notes = [(row[0], row[1].split(chr(31))) for row in cursor.fetchall()]
        conn.close()
        print(f"  {len(notes)} notes in deck {deck_id}")

        for nid, flds in notes:
            total += 1
            word = (flds[0].strip() if flds else "")
            entry = llm.get(word)
            if not entry or not entry.get("meaning"):
                clean = re.sub(r"\s*[（(][^)）]*$", "", word).strip()
                if not entry:
                    entry = llm.get(clean)
                elif not entry.get("meaning"):
                    entry = llm.get(clean)
            if entry and entry.get("meaning"):
                updates.append((build_fields(word, flds, entry), nid, deck_id))
                matched += 1
            else:
                unmatched += 1
                if unmatched <= 80:
                    unmatched_words.append(word)

    print(f"\n  Loaded {llm_loaded} LLM entries total")
    print(f"  Matched: {matched}, unmatched: {unmatched}")

    if updates:
        conn = sqlite3.connect(str(COLLECTION))
        conn.create_collation("unicase", unicase)
        now = int(time.time() * 1000)
        conn.execute("BEGIN")
        for flds, nid, deck_id in updates:
            conn.execute("UPDATE notes SET mid=?, flds=?, mod=?, usn=-1 WHERE id=?",
                         (NEW_MODEL_ID, flds, now, nid))
            conn.execute("UPDATE cards SET mod=?, usn=-1 WHERE did=? AND nid=?", (now, deck_id, nid))
        conn.execute("UPDATE col SET mod=?", (now,))
        conn.commit()
        conn.close()
        print(f"  Updated {len(updates)} notes in place")

    if unmatched_words:
        print(f"\nUnmatched ({unmatched}), sample: {unmatched_words[:30]}")

    # Verify
    conn = sqlite3.connect(f"file:{COLLECTION}?mode=ro", uri=True)
    conn.create_collation("unicase", unicase)
    cursor = conn.execute("SELECT flds FROM notes WHERE mid=?", (NEW_MODEL_ID,))
    total_e = m = pin = cn = en = 0
    for (flds,) in cursor.fetchall():
        f = flds.split(chr(31))
        if len(f) >= 12:
            total_e += 1
            if f[1].strip(): m += 1
            if f[2].strip(): pin += 1
            if f[10].strip(): en += 1
            if f[11].strip(): cn += 1
    conn.close()
    print(f"\nChinese Enhanced notes: {total_e}")
    if total_e:
        print(f"  Meaning:   {m} ({m/total_e*100:.0f}%)")
        print(f"  Pinyin:    {pin}")
        print(f"  Nuance_EN: {en}")
        print(f"  Nuance_CN: {cn}")
    print("\nDone!")

if __name__ == "__main__":
    main()