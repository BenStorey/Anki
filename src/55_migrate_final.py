#!/usr/bin/env python3
"""
Migrate Japanese WIP (5 cards) to Japanese Enhanced in-place via direct SQL.

Works because:
  - flds is updated with exactly 13 segments (matching model field count)
  - mid is updated to Japanese Enhanced
  - Card IDs are unchanged → revlog preserved
  - Anki sees consistent field count → no "check database" prompts

Usage: Close Anki, then: python3 src/55_migrate_final.py
"""
import sys, json, re, time, shutil
from pathlib import Path

COLLECTION = Path.home() / "snap" / "anki-desktop" / "common" / "User 1" / "collection.anki2"
ROOT = Path.home() / "dev" / "sino-korean"
BACKUP = COLLECTION.with_suffix(".anki2.before_wip_final")

# Import furigana from Phase 1 builder
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

    # Use Anki API only for connection (better than raw sqlite3 for unicase etc)
    sys.path.insert(0, "/snap/anki-desktop/85/lib/python3.12/site-packages")
    import anki.storage as storage
    col = storage.Collection(str(COLLECTION))
    
    old_mid = col.models.by_name("Japanese")["id"]
    new_mid = col.models.by_name("Japanese Enhanced")["id"]
    wip_did = col.decks.id_for_name("Japanese WIP")
    sep = chr(31)
    now = int(time.time())

    # Find old notes
    nids = col.db.list("SELECT n.id FROM notes n JOIN cards c ON c.nid=n.id WHERE c.did=? AND n.mid=?", wip_did, old_mid)
    print(f"Found {len(nids)} notes to migrate")

    for nid in nids:
        old_flds = col.db.scalar("SELECT flds FROM notes WHERE id=?", nid)
        old_parts = old_flds.split(sep)
        expr = old_parts[0]
        
        wd = llm.get(expr, {})
        meaning = old_parts[1] if len(old_parts) > 1 else ''
        reading_old = old_parts[2] if len(old_parts) > 2 else ''
        
        # Build 13-field content matching Japanese Enhanced model
        # Order: Expression, Meaning, Reading, Nuance, Example1, Example1_EN,
        #        Example2, Example2_EN, Example3, Example3_EN,
        #        Nuance_EN, Nuance_JP, Furigana
        new_parts = [
            expr,
            meaning,
            b50.make_furigana(expr),  # Reading with furigana
            wd.get('nuance_jp', ''),  # Nuance (plain)
            wd.get('ex1', ''),
            wd.get('ex1_en', ''),
            wd.get('ex2', ''),
            wd.get('ex2_en', ''),
            wd.get('ex3', ''),
            wd.get('ex3_en', ''),
            wd.get('nuance_en', ''),  # Nuance_EN
            wd.get('nuance_jp', ''),  # Nuance_JP
            b50.make_furigana(expr),  # Furigana
        ]
        
        new_flds = sep.join(new_parts)
        assert len(new_parts) == 13, f"expected 13 parts, got {len(new_parts)}"
        
        col.db.execute(
            "UPDATE notes SET mid=?, mod=?, usn=-1, flds=?, sfld=? WHERE id=?",
            new_mid, now, new_flds, expr, nid
        )
        
        # Delete the Production template card (ord=1) — we only want Recognition
        col.db.execute("DELETE FROM cards WHERE nid=? AND ord=1", nid)
        
        print(f"  * {expr:15s} -> nid={nid} ({old_mid} -> {new_mid})")
    
    col.save()
    col.close()
    
    # Verify
    sys.path.insert(0, "/snap/anki-desktop/85/lib/python3.12/site-packages")
    import anki.storage as storage2
    col2 = storage2.Collection(str(COLLECTION))
    for nid in nids:
        note = col2.get_note(nid)
        cards = col2.db.list("SELECT id, ord FROM cards WHERE nid=?", nid)
        revlog = sum(col2.db.scalar("SELECT COUNT(*) FROM revlog WHERE cid=?", c[0]) for c in cards)
        print(f"  ✓ {note.fields[0]:15s} fields={len(note.fields)} cards={len(cards)} revlog={revlog}")
    col2.close()
    
    print(f"\nDone. Open Anki to see changes.")
    return 0

if __name__ == "__main__":
    sys.exit(main())