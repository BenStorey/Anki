# Migration Plan: Japanese Enhanced Main Deck

## Goal
Move all ~27,000 cards from the old "Japanese" model to the "Japanese Enhanced" model (13 fields), with LLM-generated nuance + 3 examples on each card. Any cards that don't match (old sentences, grammar notes) get moved to "Japanese (Old)" deck.

## Pre-requisites (all done)
- ✅ Japanese Enhanced note type created (model ID: 1738229000, 13 fields)
- ✅ Phase 1 + 2: 121 Takoboto cards + 5 WIP cards migrated (in-place on collection)
- ✅ Phase 3: ~21,500 LLM batch outputs generated (data/sentences_raw/jp_main/out_*.txt)
- ✅ 89 salvageable words identified, 36 dispatched for LLM generation (out_salvaged_vocab.txt pending)
- ✅ All data committed to git (commit d970b0d, pushed to GitHub)

## Migration Strategy
Same approach as the WIP migration (src/55_migrate_final.py) — direct SQL UPDATE on collection.anki2:

### Step 1: Backup
```bash
cp /home/ben/snap/anki-desktop/common/User\ 1/collection.anki2 \
   /home/ben/snap/anki-desktop/common/User\ 1/collection.anki2.before_main_migration
```

### Step 2: Build the migration script
Write a Python script that:
1. Reads all output files (out_*.txt + out_salvaged_vocab.txt + out_html_vocab.txt)
2. For each word, finds the matching note in the old Japanese model
3. Updates `mid` to 1738229000 and `flds` to a 13-segment field string
4. Skips notes that don't match any output word (these stay on old model)

### Step 3: Field Mapping
13 fields in order (index 0-12):
```
0: Expression (the word)
1: Meaning (from original card)
2: Reading (from original card)
3: Nuance (EMPTY — kept to avoid field shift)
4: Example1 (from LLM)
5: Example1_EN (from LLM)
6: Example2 (from LLM)
7: Example2_EN (from LLM)
8: Example3 (from LLM)
9: Example3_EN (from LLM)
10: Nuance_EN (from LLM nuance field)
11: Nuance_JP (from LLM nuance field)
12: Furigana (generated at build time)
```

### Step 4: Move unmatched cards
After migration, any notes still on the old Japanese model ID get moved to a "Japanese (Old)" deck:
```sql
UPDATE notes SET mid = <old_model_id> WHERE mid = <old_model_id>;  -- already there
-- Create a new deck "Japanese (Old)" and update cards pointing to these notes
```

### Step 5: Verification
- Count notes on Japanese Enhanced model = expected count
- Spot-check a dozen cards open in Anki
- Verify review history preserved (revlog entries)

## What I need from you
- **One-time approval** to run the SQL migration on the live collection (same as the WIP migration)
- **Anki closed** during the migration (SQLite can't be accessed while Anki is open)
- After migration: open Anki → it will re-convert on sync (expected 15K deletion look, resolves)