#!/usr/bin/env python3
"""
Extract all words from the main Chinese deck into offline prompt batches.

Reads ONLY (no writes to the collection). Writes:
  data/sentences_raw/chinese_main/prompt_cm_###_of_###.txt   (word|pinyin|meaning)
so the LLM generation can run fully offline, storing every field on disk
before any SQL migration is attempted.

The 'Chinese Enhanced' notetype already exists (from the apkg import) — this
script does NOT touch the notetype or any note fields.
"""
import sqlite3, re
from pathlib import Path

COLLECTION = Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
CHINESE_MODEL_ID = 1351220176888   # old "Chinese" model
CHINESE_DECK_ID = 1351219999178    # main Chinese deck
OUT_DIR = Path.home() / "dev/sino-korean/data/sentences_raw/chinese_main"
BATCH_SIZE = 200

def unicase(a, b):
    return (a.lower() > b.lower()) - (a.lower() < b.lower())

def clean_html(s):
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:200]

conn = sqlite3.connect(f'file:{COLLECTION}?mode=ro', uri=True)
conn.create_collation('unicase', unicase)

# Distinct words attached to the main Chinese deck on the old model.
# One row per note (a note may have cards in multiple decks; we take any
# note whose cards sit in the main Chinese deck).
cursor = conn.execute('''
    SELECT n.id, n.flds
    FROM notes n
    JOIN cards c ON c.nid = n.id
    WHERE n.mid = ? AND c.did = ?
    GROUP BY n.id
''', (CHINESE_MODEL_ID, CHINESE_DECK_ID))

rows = []
for nid, flds_raw in cursor.fetchall():
    flds = flds_raw.split(chr(31))
    if len(flds) >= 3:
        word = flds[0].strip()
        meaning = clean_html(flds[1] if len(flds) > 1 else "")
        pinyin = flds[2].strip() if len(flds) > 2 else ""
        if word:
            rows.append((word, pinyin, meaning))
conn.close()

print(f"Read {len(rows)} distinct words from main Chinese deck")
# Dedup preserveting order
seen, uniq = set(), []
for w, p, m in rows:
    key = w
    if key not in seen:
        seen.add(key)
        uniq.append((w, p, m))
rows = uniq
print(f"After dedup: {len(rows)} words")

OUT_DIR.mkdir(parents=True, exist_ok=True)
# Clear old prompt files (keep out_* LLM output)
for f in OUT_DIR.glob("prompt_cm_*.txt"):
    f.unlink()

num = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
manifest = []
for i in range(0, len(rows), BATCH_SIZE):
    batch = rows[i:i+BATCH_SIZE]
    b = i // BATCH_SIZE + 1
    lines = [f"{w}|{p}|{m}" for w, p, m in batch]
    pf = OUT_DIR / f"prompt_cm_{b:03d}_of_{num:03d}.txt"
    pf.write_text("\n".join(lines), encoding="utf-8")
    manifest.append(pf.name)
    print(f"  written {pf.name}: {len(batch)} words")

# Save a manifest so migration knows the order/source
mf = OUT_DIR / "manifest.txt"
mf.write_text("\n".join(manifest), encoding="utf-8")
print(f"\nTotal {num} batches -> {OUT_DIR}")
batch_word_counts = [sum(1 for l in pf.read_text(encoding='utf-8').splitlines() if '|' in l) for pf in OUT_DIR.glob('prompt_cm_*.txt')]
print(f"Words per batch: {batch_word_counts}")
print(f"TOTAL words: {sum(batch_word_counts)}")