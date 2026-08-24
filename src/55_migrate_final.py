#!/usr/bin/env python3
"""
Migrate Japanese WIP to Japanese Enhanced in-place. 13-field setup:
  Expression, Meaning, Reading, Nuance(empty), Example1-3, Ex_EN, Nuance_EN, Nuance_JP, Furigana

Preserves cards, revlog, scheduling. Does NOT modify the model.
"""
import sys, json, re, shutil, time
from pathlib import Path

COLLECTION = Path.home() / "snap" / "anki-desktop" / "common" / "User 1" / "collection.anki2"
ROOT = Path.home() / "dev" / "sino-korean"
BACKUP = COLLECTION.with_suffix(".anki2.v5_backup")

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
    shutil.copy2(COLLECTION, BACKUP)
    print(f"Backup: {BACKUP}")

    words = json.loads((ROOT / "data" / "japanese_wip_words.json").read_text(encoding="utf-8"))
    wip_file = ROOT / "data" / "sentences_raw" / "jp_batches" / "out_wip.txt"
    llm = parse_sentences(wip_file.read_text(encoding="utf-8")) if wip_file.exists() else {}
    sep = chr(31)
    now = int(time.time())

    sys.path.insert(0, "/snap/anki-desktop/85/lib/python3.12/site-packages")
    import anki.storage as storage
    col = storage.Collection(str(COLLECTION))

    old_mid = col.models.by_name("Japanese")["id"]
    new_mid = col.models.by_name("Japanese Enhanced")["id"]
    wip_did = col.decks.id_for_name("Japanese WIP")

    nids = col.db.list("SELECT n.id FROM notes n JOIN cards c ON c.nid=n.id WHERE c.did=? AND n.mid=?", wip_did, old_mid)
    print(f"Found {len(nids)} notes to migrate")

    for nid in nids:
        old_flds = col.db.scalar("SELECT flds FROM notes WHERE id=?", nid)
        expr = old_flds.split(sep)[0]

        wd = llm.get(expr, {})
        w = next((x for x in words if x['word'] == expr), {})
        meaning = re.sub(r'<[^>]+>', '', w.get('meaning', '')).strip()

        # 13 fields: Expression, Meaning, Reading, Nance(empty), Example1, Example1_EN,
        #            Example2, Example2_EN, Example3, Example3_EN, Nuance_EN, Nuance_JP, Furigana
        new_parts = [
            expr,                            # 0: Expression
            meaning,                       # 1: Meaning
            b50.make_furigana(expr),          # 2: Reading
            '',                               # 3: Nuance (keep empty, unused)
            wd.get('ex1', ''),                # 4: Example1
            wd.get('ex1_en', ''),             # 5: Example1_EN
            wd.get('ex2', ''),                # 6: Example2
            wd.get('ex2_en', ''),             # 7: Example2_EN
            wd.get('ex3', ''),                # 8: Example3
            wd.get('ex3_en', ''),             # 9: Example3_EN
            wd.get('nuance_en', ''),          # 10: Nuance_EN
            wd.get('nuance_jp', ''),          # 11: Nuance_JP
            b50.make_furigana(expr),          # 12: Furigana
        ]

        new_flds = sep.join(new_parts)
        assert len(new_parts) == 13, f"got {len(new_parts)}"

        col.db.execute("UPDATE notes SET mid=?, mod=?, usn=-1, flds=?, sfld=? WHERE id=?",
            new_mid, now, new_flds, expr, nid)

        # Delete Production template cards (ord=1) — only want Recognition
        col.db.execute("DELETE FROM cards WHERE nid=? AND ord=1", nid)

        print(f"  * {expr:15s} -> nid={nid} (13 fields, Nuance empty)")

    # Verify
    for nid in nids:
        note = col.get_note(nid)
        revlog = sum(col.db.scalar("SELECT COUNT(*) FROM revlog WHERE cid=?", cid) for cid in col.db.list("SELECT id FROM cards WHERE nid=?", nid))
        print(f"  ✓ {note.fields[0]:15s} fields={len(note.fields)} nuance_en={'y' if note.fields[10] else 'n'} nuance_jp={'y' if note.fields[11] else 'n'} furigana={'y' if note.fields[12] else 'n'} revlog={revlog} field3={'EMPTY' if not note.fields[3] else 'WARN:CONTENT'}")

    col.close()
    print(f"\nDone. Open Anki.")

if __name__ == "__main__":
    main()