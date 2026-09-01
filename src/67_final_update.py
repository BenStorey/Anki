#!/usr/bin/env python3
"""
Final update: Merge LLM Meaning+Nuance_EN output into DB, and run furigana if not already done.

Run this AFTER all 134 out_mn_*.txt files are fully generated.
Checks prompt vs output counts for completeness before updating.
Supports both ===word: format (from main script) and pipe format (from chunked runs).
"""

import sqlite3, re, time, sys
from pathlib import Path
import importlib.util as iu

COLLECTION = Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
ROOT = Path.home() / "dev/sino-korean"
LLM_DIR = ROOT / "data/sentences_raw/jp_main"

# ── Helper: count entries in an output file regardless of format ──
def count_entries(path):
    if not path.exists():
        return 0
    content = path.read_text(errors="replace")
    ec = content.count("===word:")
    if ec > 0:
        return ec
    # Pipe format: count lines with 2 pipes
    return sum(1 for l in content.strip().split('\n') if l.count('|') == 2)

# ── Step 0: Verify all batches complete ──
print("Verifying batch completeness...")
incomplete = []
for i in range(1, 135):
    pf = LLM_DIR / f"prompt_mn_{i:03d}_of_134.txt"
    of = LLM_DIR / f"out_mn_{i:03d}_of_134.txt"
    if not pf.exists():
        incomplete.append(f"Batch {i}: prompt missing")
        continue
    p_lines = len([l for l in pf.read_text(errors="replace").split('\n') if '|' in l])
    o_entries = count_entries(of)
    if o_entries < p_lines * 0.8:
        incomplete.append(f"Batch {i}: {o_entries}/{p_lines}")

if incomplete:
    print(f"INCOMPLETE — needs refill:")
    for msg in incomplete:
        print(f"  {msg}")
    sys.exit(1)

print("  All 134 batches complete!")

# ── Step 1: Load LLM output ──
print("Loading LLM meaning+nuance output...")
llm_map = {}
for f in sorted(LLM_DIR.glob("out_mn_*.txt")):
    content = f.read_text(encoding="utf-8", errors="replace")
    # Handle ===word: format
    if "===word:" in content:
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
    # Handle pipe format (word|meaning|nuance)
    elif "|" in content:
        for line in content.strip().split('\n'):
            if line.count('|') >= 2:
                parts = line.split('|', 2)
                w = parts[0].strip()
                m = parts[1].strip()
                n = parts[2].strip() if len(parts) > 2 else ""
                if w:
                    llm_map[w] = {'meaning': m, 'nuance_en': n}

print(f"  Loaded {len(llm_map)} words from LLM output")

# ── Step 2: Load make_furigana ──
print("Loading furigana generator...")
spec = iu.spec_from_file_location("b50", str(ROOT / "src/50_build_japanese_enhanced.py"))
b50 = iu.module_from_spec(spec)
spec.loader.exec_module(b50)
make_furigana = b50.make_furigana

# ── Step 3: Connect to DB ──
print(f"Connecting to {COLLECTION}...")
def unicase(a, b):
    return (a.lower() > b.lower()) - (a.lower() < b.lower())
conn = sqlite3.connect(str(COLLECTION))
conn.create_collation("unicase", unicase)

cursor = conn.execute('SELECT id, flds FROM notes WHERE mid = 1738229000')
notes = [(row[0], row[1].split(chr(31))) for row in cursor.fetchall()]
print(f"  {len(notes)} notes on Japanese Enhanced model")

# ── Step 4: Build updates ──
def norm_word(w):
    w = re.sub(r'^&nbsp;', '', w)
    w = re.sub(r'^"(.*?)"\s*は、.*$', r'\1', w)
    w = re.sub(r'^[（(].*?[)）]', '', w)
    w = re.sub(r'\s*again$', '', w, flags=re.IGNORECASE)
    w = re.sub(r'\s*（again|AGAIN|2nd meaning）.*$', '', w, flags=re.IGNORECASE)
    w = w.strip()
    return w

llm_keys = list(llm_map.keys())
matched = 0
not_matched = 0
updates = []

for nid, flds in notes:
    db_word = flds[0].strip()
    entry = llm_map.get(db_word)
    if not entry:
        db_norm = norm_word(db_word)
        for lw in llm_keys:
            if lw in db_word or db_word in lw or norm_word(lw) == db_norm:
                entry = llm_map[lw]
                break
    if entry:
        matched += 1
        new_meaning = entry['meaning'] or flds[1]
        new_nuance_en = entry['nuance_en'] or flds[10]
    else:
        not_matched += 1
        new_meaning = flds[1]
        new_nuance_en = flds[10]

    try:
        new_furigana = make_furigana(db_word)
    except Exception:
        new_furigana = flds[12]

    if new_meaning != flds[1] or new_nuance_en != flds[10] or new_furigana != flds[12]:
        new_flds = chr(31).join([
            flds[0], new_meaning, flds[2], flds[3],
            flds[4], flds[5], flds[6], flds[7],
            flds[8], flds[9], new_nuance_en, flds[11], new_furigana,
        ])
        updates.append((new_flds, nid))

print(f"  Matched: {matched}, Not matched: {not_matched}")
print(f"  Notes needing update: {len(updates)}")

# ── Step 5: Execute ──
if updates:
    print(f"Updating {len(updates)} notes...")
    now = int(time.time())
    conn.execute('BEGIN TRANSACTION')
    for flds, nid in updates:
        conn.execute('UPDATE notes SET flds = ?, mod = ?, usn = -1 WHERE id = ?', (flds, now, nid))
    conn.execute('UPDATE col SET mod = ?', (now,))
    conn.commit()
    print("  Done!")
else:
    print("  No updates needed.")

# ── Step 6: Verify ──
print(f"\n{'='*60}")
print("VERIFICATION")
print(f"{'='*60}")
cursor = conn.execute('SELECT flds FROM notes WHERE mid = 1738229000 LIMIT 8')
for row in cursor.fetchall():
    flds = row[0].split(chr(31))
    print(f"  {flds[0][:20]:20s} | Meaning: {flds[1][:30]:30s} | Nuance_EN: {flds[10][:40]:40s} | Ruby: {'✓' if '[' in flds[2] else '✗'}")

cursor = conn.execute('SELECT flds FROM notes WHERE mid = 1738229000')
total = 0
m_ok = nu_ok = ru_ok = 0
for row in cursor.fetchall():
    flds = row[0].split(chr(31))
    if len(flds) >= 13:
        total += 1
        if flds[1].strip(): m_ok += 1
        if flds[10].strip(): nu_ok += 1
        if '[' in flds[2]: ru_ok += 1

print(f"\nField stats ({total} notes):")
print(f"  Meaning:   {m_ok}/{total} ({m_ok/total*100:.0f}%)")
print(f"  Nuance_EN: {nu_ok}/{total} ({nu_ok/total*100:.0f}%)")
print(f"  Ruby read: {ru_ok}/{total} ({ru_ok/total*100:.0f}%)")

conn.close()
print("\nDone!")