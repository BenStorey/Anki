#!/usr/bin/env python3
"""
Migrate Japanese WIP (5 cards) to Japanese Enhanced note type in-place,
preserving ALL history (cards, revlog, scheduling).

Usage: Close Anki, then: python3 src/52_migrate_japanese_wip.py

Strategy: UPDATE existing notes' mid + flds in-place. Card and revlog tables
are untouched — same card IDs, same review history.
"""
import json, re, sqlite3, shutil, time, sys
from pathlib import Path

# Import furigana helpers from Phase 1 builder
sys.path.insert(0, str(Path.home() / "dev" / "sino-korean" / "src"))
import importlib.util as iu
spec = iu.spec_from_file_location("b50", str(Path.home() / "dev" / "sino-korean" / "src" / "50_build_japanese_enhanced.py"))
b50 = iu.module_from_spec(spec)
spec.loader.exec_module(b50)

make_furigana = b50.make_furigana
kata_to_hira = b50.kata_to_hira

COLLECTION = Path.home() / "snap" / "anki-desktop" / "common" / "User 1" / "collection.anki2"
ROOT = Path.home() / "dev" / "sino-korean"
BACKUP = COLLECTION.with_suffix(".anki2.before_wip_migration")

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def parse_sentences(text):
    r,cur,data = {},None,{}
    for line in text.strip().split('\n'):
        s = line.strip()
        if not s: continue
        if s.startswith('===word:') or s.startswith('===Word:'):
            if cur is not None: r[cur] = data
            m = re.match(r'===word:\s*(.+?)(?:\|.*?)?(?:===|$)', s, re.I)
            cur = m.group(1).strip() if m else s.replace('===','').strip().split('|')[0].strip()
            data = {}
            continue
        for p,k in [('Nuance_EN:','nuance_en'),('Nuance_JP:','nuance_jp'),('Nuance:','nuance_jp'),
                    ('Example1:','ex1'),('Example1_EN:','ex1_en'),
                    ('Example2:','ex2'),('Example2_EN:','ex2_en'),
                    ('Example3:','ex3'),('Example3_EN:','ex3_en')]:
            if s.startswith(p): data[k] = s[len(p):].strip(); break
    if cur is not None: r[cur] = data
    return r

MODEL_ID = 1738229000

def main():
    if not COLLECTION.exists():
        print(f"ERROR: not found {COLLECTION}")
        return 1

    shutil.copy2(COLLECTION, BACKUP)
    print(f"Backup saved to {BACKUP}")

    words = json.loads((ROOT / "data" / "japanese_wip_words.json").read_text(encoding="utf-8"))
    wip_file = ROOT / "data" / "sentences_raw" / "jp_batches" / "out_wip.txt"
    llm = parse_sentences(wip_file.read_text(encoding="utf-8")) if wip_file.exists() else {}
    sep = chr(31)

    conn = sqlite3.connect(str(COLLECTION))
    # Anki uses a custom unicase collation; register a simple ASCII-case-insensitive version
    conn.create_collation("unicase", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    conn.execute("PRAGMA journal_mode=WAL")

    wip_did = conn.execute("SELECT id FROM decks WHERE name='Japanese WIP'").fetchone()
    if not wip_did:
        print("ERROR: Japanese WIP deck not found")
        conn.close()
        return 1
    wip_did = wip_did[0]

    old_mid = conn.execute("SELECT id FROM notetypes WHERE name='Japanese'").fetchone()
    if not old_mid:
        print("ERROR: Japanese note type not found")
        conn.close()
        return 1
    old_mid = old_mid[0]

    enh_mid = conn.execute("SELECT id FROM notetypes WHERE name='Japanese Enhanced'").fetchone()
    if not enh_mid:
        print("ERROR: Japanese Enhanced notetype not found")
        conn.close()
        return 1
    enh_mid = enh_mid[0]

    print(f"Deck: Japanese WIP ({wip_did})")
    print(f"Old model: Japanese ({old_mid}) -> New model: Japanese Enhanced ({enh_mid})")

    # Find old notes by expression
    note_map = {}
    for row in conn.execute("SELECT n.id, n.flds FROM notes n JOIN cards c ON c.nid=n.id WHERE c.did=? AND n.mid=?",
                          (wip_did, old_mid)).fetchall():
        parts = row[1].split(sep)
        expr = parts[0].strip() if parts else ''
        note_map[expr] = row[0]
    print(f"Found {len(note_map)} old WIP notes to migrate")

    now = int(time.time())
    updated = 0
    for w in words:
        expr = w['word']
        if expr not in note_map:
            print(f"  SKIP {expr}: not found")
            continue

        nid = note_map[expr]
        furigana = make_furigana(expr)
        meaning = w['meaning']
        meaning_clean = re.sub(r'<[^>]+>', '', meaning).strip()
        wd = llm.get(expr, {})

        fields = [
            esc(expr), esc(furigana), esc(meaning_clean),
            esc(wd.get('nuance_en','')), esc(wd.get('nuance_jp','')),
            esc(wd.get('ex1','')), esc(wd.get('ex1_en','')),
            esc(wd.get('ex2','')), esc(wd.get('ex2_en','')),
            esc(wd.get('ex3','')), esc(wd.get('ex3_en','')),
        ]
        flds_str = sep.join(fields)

        conn.execute("UPDATE notes SET mid=?, mod=?, usn=-1, flds=?, sfld=? WHERE id=?",
            (enh_mid, now, flds_str, esc(expr), nid))
        updated += 1
        print(f"  * {expr:15s} -> nid={nid} ({old_mid} -> {enh_mid})")

    conn.commit()
    conn.close()
    print(f"\nMigrated {updated}/{len(words)} notes. Full history preserved.")
    print("Re-open Anki to see changes.")
    return 0

if __name__ == "__main__":
    exit(main())
