#!/usr/bin/env python3
"""
Phase 1: Migrate Chinese WIP (1,183 cards) to Chinese Enhanced (11 fields).

Run this AFTER all 6 out_cw_*.txt files are generated.
Created notetype ID: 1787807921282
Old Chinese model ID: 1351220176888
"""

import sqlite3, re, time, sys
from pathlib import Path

COLLECTION = Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
LLM_DIR = Path.home() / "dev/sino-korean/data/sentences_raw/chinese_wip"
NEW_MODEL_ID = 1787807921282
OLD_MODEL_ID = 1351220176888
WIP_DECK_ID = 1754445298156
CHINESE_DECK_ID = 1351219999178

# ── Helper: count entries in output file ──
def count_entries(path):
    if not path.exists():
        return 0
    content = path.read_text(errors="replace")
    return content.count("===word:")

# ── Step 0: Verify all batches complete ──
print("Verifying batch completeness...")
incomplete = []
for i in range(1, 7):
    pf = LLM_DIR / f"prompt_cw_{i:03d}_of_006.txt"
    of = LLM_DIR / f"out_cw_{i:03d}_of_006.txt"
    if not pf.exists():
        continue
    p_lines = len([l for l in pf.read_text(errors="replace").split('\n') if '|' in l])
    o_entries = count_entries(of)
    if o_entries < p_lines * 0.8:
        incomplete.append(f"Batch {i}: {o_entries}/{p_lines}")

if incomplete:
    print("INCOMPLETE — needs refill:")
    for msg in incomplete:
        print(f"  {msg}")
    sys.exit(1)

print("  All 6 batches complete!")

# ── Step 1: Load LLM output ──
print("Loading LLM output...")
llm_map = {}
for f in sorted(LLM_DIR.glob("out_cw_*.txt")):
    content = f.read_text(encoding="utf-8", errors="replace")
    for block in content.split("===word: ")[1:]:
        word = block.split("===")[0].strip()
        rest = block.split("===")[1] if "===" in block else block
        fields = {}
        for line in rest.split('\n'):
            s = line.strip()
            for prefix, key in [("Meaning:", "meaning"), ("Nuance_EN:", "nuance_en"), 
                                ("Nuance_CN:", "nuance_cn"), ("Example1:", "ex1"),
                                ("Example1_EN:", "ex1_en"), ("Example2:", "ex2"),
                                ("Example2_EN:", "ex2_en"), ("Example3:", "ex3"),
                                ("Example3_EN:", "ex3_en")]:
                if s.startswith(prefix):
                    fields[key] = s[len(prefix):].strip()
        if word:
            llm_map[word] = fields

print(f"  Loaded {len(llm_map)} words")

# ── Step 2: Connect to DB ──
print(f"Connecting to {COLLECTION}...")
def unicase(a, b):
    return (a.lower() > b.lower()) - (a.lower() < b.lower())
conn = sqlite3.connect(str(COLLECTION))
conn.create_collation("unicase", unicase)

# Get WIP notes
cursor = conn.execute('''
    SELECT n.id, n.flds 
    FROM notes n 
    JOIN cards c ON c.nid = n.id 
    WHERE n.mid = ? AND c.did = ?
    GROUP BY n.id
''', (OLD_MODEL_ID, WIP_DECK_ID))
notes = [(row[0], row[1].split(chr(31))) for row in cursor.fetchall()]
print(f"  {len(notes)} WIP notes found")

# ── Step 3: Build updates ──
matched = 0
not_matched = 0
updates = []

for nid, flds in notes:
    word = flds[0].strip()
    entry = llm_map.get(word)
    if not entry:
        not_matched += 1
        continue
    
    matched += 1
    new_flds = chr(31).join([
        word,                          # 0: Expression
        entry.get('meaning', ''),      # 1: Meaning
        flds[2] if len(flds) > 2 else '',  # 2: Pinyin (keep original)
        '',                            # 3: Nuance (empty)
        entry.get('ex1', ''),          # 4: Example1
        entry.get('ex1_en', ''),       # 5: Example1_EN
        entry.get('ex2', ''),          # 6: Example2
        entry.get('ex2_en', ''),       # 7: Example2_EN
        entry.get('ex3', ''),          # 8: Example3
        entry.get('ex3_en', ''),       # 9: Example3_EN
        entry.get('nuance_en', ''),    # 10: Nuance_EN
        entry.get('nuance_cn', ''),    # 11: Nuance_CN
    ])
    updates.append((new_flds, nid))

print(f"  Matched: {matched}, Not matched: {not_matched}")

# ── Step 4: Execute ──
if updates:
    print(f"Updating {len(updates)} notes...")
    now = int(time.time() * 1000)
    conn.execute('BEGIN TRANSACTION')
    for flds, nid in updates:
        conn.execute('UPDATE notes SET mid = ?, flds = ?, mod = ?, usn = -1 WHERE id = ?',
                    (NEW_MODEL_ID, flds, now, nid))
    # Keep cards IN PLACE in the Chinese WIP deck (no move to Chinese deck)
    conn.execute('UPDATE cards SET mod = ?, usn = -1 WHERE did = ? AND nid IN (SELECT id FROM notes WHERE mid = ?)',
                 (now, WIP_DECK_ID, NEW_MODEL_ID))
    conn.execute('UPDATE col SET mod = ?', (now,))
    conn.commit()
    print(f"  Updated notes in place (Chinese WIP deck: id={WIP_DECK_ID})")
else:
    print("  No updates needed.")

# ── Step 5: Verify ──
print(f"\n{'='*60}")
print("VERIFICATION")
print(f"{'='*60}")

cursor = conn.execute('SELECT flds FROM notes WHERE mid = ? LIMIT 5', (NEW_MODEL_ID,))
for row in cursor.fetchall():
    flds = row[0].split(chr(31))
    if len(flds) >= 12:
        print(f"  {flds[0][:25]:25s} | Meaning: {flds[1][:30]:30s} | EN: {flds[10][:30]:30s} | CN: {flds[11][:30]}")

# Stats
cursor = conn.execute('SELECT flds FROM notes WHERE mid = ?', (NEW_MODEL_ID,))
total = 0
m_ok = en_ok = cn_ok = ex_ok = 0
for row in cursor.fetchall():
    flds = row[0].split(chr(31))
    if len(flds) >= 12:
        total += 1
        if flds[1].strip(): m_ok += 1
        if flds[10].strip(): en_ok += 1
        if flds[11].strip(): cn_ok += 1
        if flds[4].strip(): ex_ok += 1

print(f"\nField stats ({total} notes):")
print(f"  Meaning:   {m_ok}/{total} ({m_ok/total*100:.0f}%)")
print(f"  Nuance_EN: {en_ok}/{total} ({en_ok/total*100:.0f}%)")
print(f"  Nuance_CN: {cn_ok}/{total} ({cn_ok/total*100:.0f}%)")
print(f"  Examples:  {ex_ok}/{total} ({ex_ok/total*100:.0f}%)")

conn.close()
print("\nDone!")