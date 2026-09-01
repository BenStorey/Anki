#!/usr/bin/env python3
"""Fix the Reading field for all Japanese Enhanced notes.

Current state:
  Field 2 (Reading): かっかざん (plain kana — wrong format)
  Field 12 (Furigana): かっかざん (same — wrong)

Target state:
  Field 2 (Reading): 活[かつ] 火山[かざん] (per-character ruby format)
  Field 12 (Furigana): 活[かつ] 火山[かざん]

The template uses {{furigana:Reading}} which requires [kanji] format.
"""

import sqlite3, re, time, sys
from pathlib import Path
import importlib.util as iu

COLLECTION = Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
ROOT = Path.home() / "dev/sino-korean"

# Load make_furigana
spec = iu.spec_from_file_location("b50", str(ROOT / "src/50_build_japanese_enhanced.py"))
b50 = iu.module_from_spec(spec)
spec.loader.exec_module(b50)
make_furigana = b50.make_furigana

# Also need the EXPR_OVERRIDES dict
print("Loading EXPR_OVERRIDES from 50_build_japanese_enhanced.py...")
# The overrides are already loaded via the module above

print(f"Connecting to {COLLECTION}...")
def unicase(a, b):
    return (a.lower() > b.lower()) - (a.lower() < b.lower())

conn = sqlite3.connect(str(COLLECTION))
conn.create_collation("unicase", unicase)

# Read all notes
cursor = conn.execute('SELECT id, flds FROM notes WHERE mid = 1738229000')
notes = []
for row in cursor.fetchall():
    nid = row[0]
    flds = row[1].split(chr(31))
    if len(flds) >= 13:
        notes.append((nid, flds))

print(f"Found {len(notes)} notes on Japanese Enhanced model")

# Process each note
updates = []
for nid, flds in notes:
    word = flds[0].strip()
    current_reading = flds[2]
    current_furigana = flds[12]
    
    try:
        new_reading = make_furigana(word)
    except Exception as e:
        print(f"  Error processing '{word}': {e}")
        new_reading = current_reading  # keep old value
    
    new_furigana = new_reading  # same format
    
    if new_reading != current_reading or new_furigana != current_furigana:
        new_flds = chr(31).join([
            flds[0],             # 0: Expression
            flds[1],             # 1: Meaning
            new_reading,         # 2: Reading (fixed)
            flds[3],             # 3: Nuance (empty)
            flds[4],             # 4: Example1
            flds[5],             # 5: Example1_EN
            flds[6],             # 6: Example2
            flds[7],             # 7: Example2_EN
            flds[8],             # 8: Example3
            flds[9],             # 9: Example3_EN
            flds[10],            # 10: Nuance_EN
            flds[11],            # 11: Nuance_JP
            new_furigana,        # 12: Furigana (fixed)
        ])
        updates.append((new_flds, nid))

print(f"Notes needing Reading+Furigana update: {len(updates)}")

if updates:
    print(f"Updating {len(updates)} notes...")
    now = int(time.time())
    conn.execute('BEGIN TRANSACTION')
    for flds, nid in updates:
        conn.execute('UPDATE notes SET flds = ?, mod = ?, usn = -1 WHERE id = ?', (flds, now, nid))
    conn.execute('UPDATE col SET mod = ?', (now,))
    conn.commit()
    print("Done!")

# Verify
print(f"\n=== Verification ===")
cursor = conn.execute('SELECT flds FROM notes WHERE mid = 1738229000 LIMIT 10')
for row in cursor.fetchall():
    flds = row[0].split(chr(31))
    word = flds[0][:20]
    reading = flds[2][:40]
    furigana = flds[12][:40]
    has_ruby = '[' in reading
    has_furi_ruby = '[' in furigana
    print(f"  {word:20s} | Reading: {reading:35s} | Furigana: {furigana:30s} | Ruby: {'✓' if has_ruby else '✗'}")

conn.close()
print("\nDone!")