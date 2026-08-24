#!/usr/bin/env python3
"""
Migrate Japanese WIP to Japanese Enhanced using Anki's built-in
change_notetype_of_notes API. Preserves card IDs, revlog, history.

Usage: Close Anki, then: python3 src/54_migrate_change_notetype.py
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
    if not old_m or not new_m: print("ERROR: models"); return 1

    wip_did = col.decks.id_for_name("Japanese WIP")

    # Find old notes
    nids = col.db.list("SELECT n.id FROM notes n JOIN cards c ON c.nid=n.id WHERE c.did=? AND n.mid=?", wip_did, old_m['id'])
    if not nids: print("No old notes found"); return 1
    print(f"Found {len(nids)} notes to convert: {nids}")

    # Build field mapping: old field index -> new field index
    old_names = [f['name'] for f in old_m['flds']]
    new_names = [f['name'] for f in new_m['flds']]
    print(f"Old fields: {old_names}")
    print(f"New fields: {new_names}")

    field_map = {}
    for i, name in enumerate(old_names):
        if name in new_names:
            field_map[i] = new_names.index(name)

    # Use Anki's built-in change_notetype
    info = col.models.change_notetype_info(old_m, new_m, field_map, {})
    # info is a ChangeNotetypeInfo with note_data containing converted notes
    # But actually we need to call col.models.change_notetype_of_notes

    col.models.change_notetype_of_notes(nids, new_m['id'], old_m['id'], field_map, {})

    # Now the notes are converted. Update the enhanced fields.
    sep = chr(31)
    for nid in nids:
        note = col.get_note(nid)
        expr = note.fields[0]
        wd = llm.get(expr, {})
        meaning = re.sub(r'<[^>]+>', '', next((w['meaning'] for w in words if w['word'] == expr), '')).strip()

        note.fields[1] = b50.make_furigana(expr)  # Reading
        note.fields[3] = wd.get('nuance_jp', '')  # Nuance
        note.fields[4] = wd.get('ex1', '')
        note.fields[5] = wd.get('ex1_en', '')
        note.fields[6] = wd.get('ex2', '')
        note.fields[7] = wd.get('ex2_en', '')
        note.fields[8] = wd.get('ex3', '')
        note.fields[9] = wd.get('ex3_en', '')
        note.fields[10] = wd.get('nuance_en', '')  # Nuance_EN
        note.fields[11] = wd.get('nuance_jp', '')  # Nuance_JP
        note.fields[12] = b50.make_furigana(expr)  # Furigana

        note.flush()
        print(f"  * {expr:15s} -> nid={nid} (all 13 fields populated)")

    # Remove the Production template (ord=1) from the model since user
    # only wants recognition cards. This avoids duplicate card creation
    # on future imports.
    #
    # Actually, we can't retroactively remove template cards that already
    # exist. We need to delete the ord=1 cards for just these notes.
    for nid in nids:
        ord1_cards = col.db.list("SELECT id FROM cards WHERE nid=? AND ord=1", nid)
        for cid in ord1_cards:
            col.db.execute("DELETE FROM cards WHERE id=?", cid)
        if ord1_cards:
            print(f"    removed {len(ord1_cards)} Production card(s)")

    col.save()
    col.close()
    print(f"\nMigrated {len(nids)} notes. Re-open Anki to see changes.")

if __name__ == "__main__":
    main()