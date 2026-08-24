#!/usr/bin/env python3
"""
Migrate Japanese WIP to Japanese Enhanced using Anki's Python API.
Preserves card IDs, revlog, all review history.

Usage: Close Anki, then: python3 src/53_migrate_anki_api.py
"""
import sys, json, re
from pathlib import Path

sys.path.insert(0, "/snap/anki-desktop/85/lib/python3.12/site-packages")
import anki.storage as storage

COLLECTION_PATH = "/home/ben/snap/anki-desktop/common/User 1/collection.anki2"
ROOT = Path.home() / "dev" / "sino-korean"

import importlib.util as iu
spec = iu.spec_from_file_location("b50", str(ROOT / "src" / "50_build_japanese_enhanced.py"))
b50 = iu.module_from_spec(spec)
spec.loader.exec_module(b50)

def parse_sentences(text):
    r,cur,data = {},None,{}
    for line in text.strip().split('\n'):
        s = line.strip()
        if not s: continue
        if s.startswith('===word:') or s.startswith('===Word:'):
            if cur is not None: r[cur] = data
            m = re.match(r'===word:\s*(.+?)(?:\|.*?)?(?:===|$)', s, re.I)
            cur = m.group(1).strip() if m else s.replace('===','').strip().split('|')[0].strip()
            data = {}; continue
        for p,k in [('Nuance_EN:','nuance_en'),('Nuance_JP:','nuance_jp'),('Nuance:','nuance_jp'),
                    ('Example1:','ex1'),('Example1_EN:','ex1_en'),
                    ('Example2:','ex2'),('Example2_EN:','ex2_en'),
                    ('Example3:','ex3'),('Example3_EN:','ex3_en')]:
            if s.startswith(p): data[k] = s[len(p):].strip(); break
    if cur is not None: r[cur] = data
    return r

def main():
    words = json.loads((ROOT / "data" / "japanese_wip_words.json").read_text(encoding="utf-8"))
    wip_file = ROOT / "data" / "sentences_raw" / "jp_batches" / "out_wip.txt"
    llm = parse_sentences(wip_file.read_text(encoding="utf-8")) if wip_file.exists() else {}

    col = storage.Collection(COLLECTION_PATH)
    print("Collection opened")

    old_m = col.models.by_name("Japanese")
    new_m = col.models.by_name("Japanese Enhanced")
    if not old_m or not new_m:
        print("ERROR: models not found"); return 1

    # Show the field names in the actual model (for verification)
    fn = [f['name'] for f in new_m['flds']]
    print(f"Japanese Enhanced fields ({len(fn)}): {fn}")

    wip_did = col.decks.id_for_name("Japanese WIP")
    print(f"Japanese WIP deck id={wip_did}")

    # Find old notes
    note_map = {}
    for nid in col.db.list("SELECT n.id FROM notes n JOIN cards c ON c.nid=n.id WHERE c.did=? AND n.mid=?", wip_did, old_m['id']):
        note = col.get_note(nid)
        if note.fields:
            note_map[note.fields[0].strip()] = (nid, note)
    print(f"Found {len(note_map)} old WIP notes")

    updated = 0
    for w in words:
        expr = w['word']
        if expr not in note_map: print(f"  SKIP {expr}"); continue

        nid, old_note = note_map[expr]
        meaning = re.sub(r'<[^>]+>', '', w['meaning']).strip()
        wd = llm.get(expr, {})

        new_note = col.new_note(new_m)
        new_note['Expression'] = expr
        new_note['Reading'] = b50.make_furigana(expr)
        new_note['Meaning'] = meaning
        new_note['Furigana'] = b50.make_furigana(expr)

        # Also set Nuance (plain), Nuance_EN, Nuance_JP as needed
        nuance_jp = wd.get('nuance_jp', '')
        nuance_en = wd.get('nuance_en', '')
        try: new_note['Nuance'] = nuance_jp
        except KeyError: pass
        try: new_note['Nuance_EN'] = nuance_en
        except KeyError: pass  
        try: new_note['Nuance_JP'] = nuance_jp
        except KeyError: pass

        for i in 1, 2, 3:
            ex = wd.get(f'ex{i}', '')
            ex_en = wd.get(f'ex{i}_en', '')
            try: new_note[f'Example{i}'] = ex
            except KeyError: pass
            try: new_note[f'Example{i}_EN'] = ex_en
            except KeyError: pass

        col.add_note(new_note, wip_did)
        new_nid = new_note.id

        # Transfer old cards to new note (preserves revlog)
        old_card_ids = col.db.list("SELECT id FROM cards WHERE nid=?", nid)
        for cid in old_card_ids:
            col.db.execute("UPDATE cards SET nid=? WHERE id=?", new_nid, cid)

        col.remNotes([nid])

        updated += 1
        print(f"  * {expr:15s} -> nid={new_nid} ({len(old_card_ids)} cards transferred)")

    col.save()
    col.close()
    print(f"\nMigrated {updated}/{len(words)} notes. All history preserved.")
    print("Re-open Anki to see changes.")
    return 0

if __name__ == "__main__":
    sys.exit(main())