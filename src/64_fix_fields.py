#!/usr/bin/env python3
"""
Phase 5: Fix Meaning, Nuance_EN, and Furigana on Japanese Enhanced notes.

Steps:
1. Read all out_mn_*.txt files → {word: {meaning, nuance_en}}
2. For each Japanese Enhanced note, rebuild field 1 (Meaning), field 10 (Nuance_EN),
   and field 12 (Furigana) using make_furigana()
3. Update in-place via SQL

Before running: ensure Anki is closed and the LLM generation is complete.
"""

import sqlite3, re, time, sys
from pathlib import Path

COLLECTION = Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
ROOT = Path.home() / "dev/sino-korean"
LLM_DIR = ROOT / "data/sentences_raw/jp_main"

# Load make_furigana from proven script
import importlib.util as iu
spec = iu.spec_from_file_location("b50", str(ROOT / "src/50_build_japanese_enhanced.py"))
b50 = iu.module_from_spec(spec)
spec.loader.exec_module(b50)
make_furigana = b50.make_furigana

# ── Step 1: Load LLM output ──
print("Loading LLM meaning+nuance output...")
llm_map = {}  # word → {meaning, nuance_en}

for f in sorted(LLM_DIR.glob("out_mn_*.txt")):
    if f.stat().st_size < 100:
        continue
    content = f.read_text(encoding="utf-8", errors="replace")
    for block in content.split("===word: ")[1:]:
        word = block.split("===")[0].strip()
        rest = block.split("===")[1] if "===" in block else block
        meaning = ""
        nuance_en = ""
        for line in rest.split('\n'):
            s = line.strip()
            if s.startswith("Meaning:"):
                meaning = s[8:].strip()
            elif s.startswith("Nuance_EN:"):
                nuance_en = s[10:].strip()
        if word:
            llm_map[word] = {'meaning': meaning, 'nuance_en': nuance_en}

print(f"  Loaded {len(llm_map)} words from LLM output")

# ── Step 2: Connect to DB ──
print(f"\nConnecting to {COLLECTION}...")
def unicase(a, b):
    return (a.lower() > b.lower()) - (a.lower() < b.lower())

conn = sqlite3.connect(str(COLLECTION))
conn.create_collation("unicase", unicase)

# ── Step 3: Read current notes ──
cursor = conn.execute('SELECT id, flds FROM notes WHERE mid = 1738229000')
notes = []
for row in cursor.fetchall():
    nid = row[0]
    flds = row[1].split(chr(31))
    if len(flds) >= 13:
        notes.append((nid, flds))

print(f"  {len(notes)} notes on Japanese Enhanced model")

# ── Step 4: Look up matches and build updates ──
# Strategy: match LLM word → DB word
# The LLM output uses clean words, but DB may have messy versions
# We'll try exact match, then normalized match

def norm_word(w):
    """Normalize a word for matching."""
    w = re.sub(r'^&nbsp;', '', w)
    w = re.sub(r'^"(.*?)"\s*は、.*$', r'\1', w)
    w = re.sub(r'^[（(].*?[)）]', '', w)
    w = re.sub(r'\s*again$', '', w, flags=re.IGNORECASE)
    w = re.sub(r'\s*（again|AGAIN|2nd meaning）.*$', '', w, flags=re.IGNORECASE)
    w = re.sub(r'\s*\(again|AGAIN|2nd meaning\).*$', '', w, flags=re.IGNORECASE)
    w = re.sub(r'\s*（2nd meaning）.*$', '', w)
    w = w.strip()
    # Extract first Japanese text segment
    m = re.search(r'[\u3040-\u9fff\u3000-\u303f]', w)
    return w

# Build reverse index: clean word → DB word
llm_keys = list(llm_map.keys())

matched = 0
not_matched = 0
updates = []

for nid, flds in notes:
    db_word = flds[0].strip()
    current_meaning = flds[1]
    current_reading = flds[2].strip()
    
    # Try to find match
    entry = llm_map.get(db_word)
    
    # Try normalized match
    if not entry:
        db_norm = norm_word(db_word)
        for lw in llm_keys:
            if lw in db_word or db_word in lw or norm_word(lw) == db_norm:
                entry = llm_map[lw]
                break
    
    if entry:
        new_meaning = entry['meaning'] or current_meaning
        new_nuance_en = entry['nuance_en'] or flds[10]
    else:
        new_meaning = current_meaning
        new_nuance_en = flds[10]
        not_matched += 1
    
    # Regenerate furigana from the expression
    try:
        new_furigana = make_furigana(db_word)
    except Exception:
        new_furigana = flds[12]  # keep existing
    
    if entry:
        matched += 1
    else:
        # Even if no LLM match, still update furigana
        pass
    
    # Only update if something changed
    if new_meaning != flds[1] or new_nuance_en != flds[10] or new_furigana != flds[12]:
        new_flds = chr(31).join([
            flds[0],             # 0: Expression
            new_meaning,         # 1: Meaning (new)
            flds[2],             # 2: Reading
            flds[3],             # 3: Nuance (empty)
            flds[4],             # 4: Example1
            flds[5],             # 5: Example1_EN
            flds[6],             # 6: Example2
            flds[7],             # 7: Example2_EN
            flds[8],             # 8: Example3
            flds[9],             # 9: Example3_EN
            new_nuance_en,       # 10: Nuance_EN (new)
            flds[11],            # 11: Nuance_JP
            new_furigana,        # 12: Furigana (new)
        ])
        updates.append((new_flds, nid))

print(f"  Matched with LLM: {matched}")
print(f"  No LLM match: {not_matched}")
print(f"  Notes needing update: {len(updates)}")

# ── Step 5: Execute updates ──
if updates:
    print(f"\nUpdating {len(updates)} notes...")
    now = int(time.time() * 1000)
    conn.execute('BEGIN TRANSACTION')
    for flds, nid in updates:
        conn.execute('UPDATE notes SET flds = ?, mod = ?, usn = -1 WHERE id = ?', (flds, now, nid))
    # Update col mod so Anki syncs
    conn.execute('UPDATE col SET mod = ?', (now,))
    conn.commit()
    print("  Done!")
else:
    print("\nNo updates needed.")

# ── Step 6: Verify ──
print(f"\n{'='*60}")
print("VERIFICATION")
print(f"{'='*60}")

cursor = conn.execute('SELECT flds FROM notes WHERE mid = 1738229000 LIMIT 5')
for row in cursor.fetchall():
    flds = row[0].split(chr(31))
    word = flds[0][:20]
    meaning = flds[1][:40]
    nuance_en = flds[10][:60]
    furigana = flds[12][:40]
    has_nuance = "✓" if nuance_en else "✗"
    has_furi = "✓" if furigana else "✗"
    print(f"  {word:20s} | Meaning: {meaning:30s} | Nuance_EN: {has_nuance} | Furigana: {has_furi}")

# Count non-empty fields
cursor = conn.execute('SELECT flds FROM notes WHERE mid = 1738229000')
has_meaning = 0
has_nuance_en = 0
has_furigana = 0
total = 0
for row in cursor.fetchall():
    flds = row[0].split(chr(31))
    if len(flds) >= 13:
        total += 1
        if flds[1].strip(): has_meaning += 1
        if flds[10].strip(): has_nuance_en += 1
        if flds[12].strip(): has_furigana += 1

print(f"\nField stats ({total} notes):")
print(f"  Meaning filled:   {has_meaning}/{total} ({has_meaning/total*100:.0f}%)")
print(f"  Nuance_EN filled: {has_nuance_en}/{total} ({has_nuance_en/total*100:.0f}%)")
print(f"  Furigana filled:  {has_furigana}/{total} ({has_furigana/total*100:.0f}%)")

conn.close()
print("\nDone!")