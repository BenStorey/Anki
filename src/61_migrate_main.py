#!/usr/bin/env python3
"""
Phase 4: Main deck migration to Japanese Enhanced (13 fields).

Migrates ~27,947 notes from old "Japanese" model (3 fields) to
"Japanese Enhanced" model (13 fields) using LLM-generated content.

Strategy:
1. For each note on old model, look up the word in LLM output files
2. If found: UPDATE mid + build 13-segment flds
3. If not found: leave on old model, will be moved to "Japanese (Old)" deck
4. Also move existing Japanese Enhanced notes from Takoboto/WIP decks to Japanese deck

Before running: ensure Anki is closed. A backup is assumed to exist.
"""

import sqlite3, re, json
from pathlib import Path

# --- CONFIG ---
COLLECTION = Path("/home/ben/snap/anki-desktop/common/User 1/collection.anki2")
OLD_MODEL_ID = 1351215240429  # "Japanese" (3 fields)
NEW_MODEL_ID = 1738229000     # "Japanese Enhanced" (13 fields)
JAPANESE_DECK_ID = 1355152451702  # "Japanese" deck
TARGET_DECK_ID = 1355152451702     # same
LLM_DIR = Path("/home/ben/dev/sino-korean/data/sentences_raw/jp_main")

# --- STEP 1: Load all LLM output into a lookup dict ---
# Maps word → {nuance: str, ex1: str, ex1_en: str, ex2: str, ex2_en: str, ex3: str, ex3_en: str}
print("Loading LLM output files...")
llm_data = {}

for f in sorted(LLM_DIR.glob("out_*.txt")):
    content = f.read_text(encoding="utf-8", errors="replace")
    # Split by ===word: markers
    blocks = content.split("===word: ")
    for block in blocks[1:]:  # skip split prefix
        header_end = block.find("===")
        if header_end == -1:
            continue
        word = block[:header_end].strip()
        rest = block[header_end + 3:]  # skip ===
        
        # Extract fields
        nuance = ""
        ex1 = ex1_en = ex2 = ex2_en = ex3 = ex3_en = ""
        
        # Nuance: can span multiple lines until next label
        m = re.search(r'^Nuance:\s*(.+?)(?=^Example1:|^Example[12]_EN:)', rest, re.MULTILINE | re.DOTALL)
        if m:
            nuance = m.group(1).strip().replace('\n', ' ')
        # Fallback: simpler single-line
        if not nuance:
            m = re.search(r'^Nuance:\s*(.+?)$', rest, re.MULTILINE)
            if m:
                nuance = m.group(1).strip()
        
        # Example1
        m = re.search(r'^Example1:\s*(.+?)$', rest, re.MULTILINE)
        if m: ex1 = m.group(1).strip()
        m = re.search(r'^Example1_EN:\s*(.+?)$', rest, re.MULTILINE)
        if m: ex1_en = m.group(1).strip()
        
        # Example2
        m = re.search(r'^Example2:\s*(.+?)$', rest, re.MULTILINE)
        if m: ex2 = m.group(1).strip()
        m = re.search(r'^Example2_EN:\s*(.+?)$', rest, re.MULTILINE)
        if m: ex2_en = m.group(1).strip()
        
        # Example3
        m = re.search(r'^Example3:\s*(.+?)$', rest, re.MULTILINE)
        if m: ex3 = m.group(1).strip()
        m = re.search(r'^Example3_EN:\s*(.+?)$', rest, re.MULTILINE)
        if m: ex3_en = m.group(1).strip()
        
        # Nuance_EN and Nuance_JP — both come from the Nuance field
        # Nuance_JP gets the full Japanese nuance
        # Nuance_EN gets a compressed version
        nuance_jp = nuance
        nuance_en = ""
        # Try to extract English from Nuance if it's mixed
        # Some early batches have English in the nuance
        # For now, Nuance_EN gets the nuance, Nuance_JP gets the nuance too
        
        if word:
            llm_data[word] = {
                'nuance': nuance,
                'ex1': ex1, 'ex1_en': ex1_en,
                'ex2': ex2, 'ex2_en': ex2_en,
                'ex3': ex3, 'ex3_en': ex3_en,
                'nuance_jp': nuance_jp,
                'nuance_en': nuance_en,
            }

print(f"  Loaded {len(llm_data)} words from output files")

# --- STEP 2: Connect to collection ---
print(f"\nConnecting to {COLLECTION}...")
conn = sqlite3.connect(str(COLLECTION))
conn.row_factory = sqlite3.Row

# --- STEP 3: Count notes on old model ---
old_count = conn.execute('SELECT COUNT(*) FROM notes WHERE mid = ?', (OLD_MODEL_ID,)).fetchone()[0]
print(f"  Notes on old Japanese model: {old_count}")

# --- STEP 4: Process each note ---
# We'll do this in batches with explicit SQL
print("\nMigrating notes...")

# Get all notes from old model
notes = conn.execute('SELECT id, flds, sfld FROM notes WHERE mid = ?', (OLD_MODEL_ID,)).fetchall()

matched = 0
not_matched = 0
updated_notes = []

for note in notes:
    nid = note['id']
    flds = note['flds']
    fields = flds.split(chr(31))
    
    if len(fields) < 2:
        continue
    
    word = fields[0].strip()
    meaning = fields[1].strip() if len(fields) > 1 else ""
    reading = fields[2].strip() if len(fields) > 2 else ""
    
    # Clean reading: remove the WORD[READING] format if present
    # Some readings look like "WORD[READING]" — strip the word part
    if '[' in reading and ']' in reading:
        reading = reading.split('[')[-1].split(']')[0].strip()
    
    # Try to find in LLM data
    # Try exact match first, then with various normalizations
    match = llm_data.get(word)
    if not match:
        # Try with common variations
        for k, v in llm_data.items():
            if k in word or word in k:
                match = v
                break
    
    # Also try stripping parens/readings from the word
    if not match:
        clean_word = re.sub(r'\s*[（(][^)）]*[)）]$', '', word).strip()
        match = llm_data.get(clean_word)
    
    if match:
        # Build 13-segment flds
        new_flds = chr(31).join([
            word,                     # 0: Expression
            meaning,                  # 1: Meaning
            reading,                  # 2: Reading
            "",                       # 3: Nuance (empty)
            match['ex1'],             # 4: Example1
            match['ex1_en'],          # 5: Example1_EN
            match['ex2'],             # 6: Example2
            match['ex2_en'],          # 7: Example2_EN
            match['ex3'],             # 8: Example3
            match['ex3_en'],          # 9: Example3_EN
            match['nuance_en'],       # 10: Nuance_EN
            match['nuance_jp'],       # 11: Nuance_JP
            reading,                  # 12: Furigana (just the reading)
        ])
        updated_notes.append((NEW_MODEL_ID, new_flds, nid))
        matched += 1
    else:
        not_matched += 1

print(f"  Matched with LLM data: {matched}")
print(f"  No LLM match: {not_matched}")

# --- STEP 5: Execute the updates ---
if matched > 0:
    print(f"\nUpdating {matched} notes in database...")
    conn.execute('BEGIN TRANSACTION')
    for mid, flds, nid in updated_notes:
        conn.execute('UPDATE notes SET mid = ?, flds = ?, mod = ? WHERE id = ?',
                    (mid, flds, int(conn.execute('SELECT mod FROM col').fetchone()[0]), nid))
    conn.commit()
    print("  Done!")

# --- STEP 6: Move existing Japanese Enhanced notes to Japanese deck ---
# Notes already on Japanese Enhanced model but in Takoboto or WIP decks
print(f"\nMoving existing Japanese Enhanced notes to Japanese deck...")
# Get the IDs of notes on Japanese Enhanced model
cursor = conn.execute('''
    SELECT c.id FROM cards c
    JOIN notes n ON c.nid = n.id
    WHERE n.mid = ? AND c.did != ?
''', (NEW_MODEL_ID, JAPANESE_DECK_ID))
cards_to_move = [r['id'] if isinstance(r, sqlite3.Row) else r[0] for r in cursor.fetchall()]
print(f"  Cards to move: {len(cards_to_move)}")

if cards_to_move:
    conn.execute('BEGIN TRANSACTION')
    for cid in cards_to_move:
        conn.execute('UPDATE cards SET did = ?, mod = ?, usn = -1 WHERE id = ?', 
                    (JAPANESE_DECK_ID, conn.execute('SELECT mod FROM col').fetchone()[0], cid))
    conn.commit()
    print("  Done!")

# --- STEP 7: Move unmatched old-model notes to Japanese (Old) deck ---
# Create the "Japanese (Old)" deck if it doesn't exist
print(f"\nPreparing unmatched notes for Japanese (Old) deck...")
# The deck ID needs to be created properly
# For now, just report how many would be moved
unmatched_count = conn.execute('SELECT COUNT(*) FROM notes WHERE mid = ?', (OLD_MODEL_ID,)).fetchone()[0]
print(f"  Notes still on old model: {unmatched_count}")

# --- FINAL REPORT ---
print(f"\n{'='*60}")
print("MIGRATION SUMMARY")
print(f"{'='*60}")
print(f"  Notes migrated to Japanese Enhanced: {matched}")
print(f"  Notes without LLM content: {not_matched}")
print(f"  Cards moved to Japanese deck: {len(cards_to_move)}")
print(f"  Notes still on old model: {unmatched_count}")
print(f"\nNext steps:")
print(f"  1. Open Anki and verify")
print(f"  2. For the {not_matched} unmatched notes, consider:")
print(f"     - Creating a 'Japanese (Old)' deck")
print(f"     - Moving them there for safekeeping")

conn.close()
print("\nDone!")