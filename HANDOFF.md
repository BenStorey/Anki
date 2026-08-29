# Stabilized — How to Add New Cards (Handoff Guide)

**Read this first. It is the current, authoritative workflow.** The other `*.md`
files in this repo are historical/planning docs (some stale — see Conflicts at the bottom).

Last validated: 2026-08-28. Both languages fully migrated:

| Language | Enhanced notetype | Notes | Templates | Cards (1:1) |
|----------|-------------------|-------|-----------|--------------|
| Japanese | `Japanese Enhanced` (id `1738229000`) | 27,949 | 1 × Recognition | 27,949 |
| Chinese  | `Chinese Enhanced`  (id `1787807921282`) | 16,370 | 1 × Recognition | 16,370 |

---

## The ONLY workflow you need: add new cards covered with LLM examples

New words arrive authoritatively in **`Japanese Enhanced: Takoboto`** (jp) and
**`Pleco`** (cn; renamed from "Chinese WIP", stable deck id `1754445298156`)
decks.

### ⭐ Card placement policy (user's explicit preference)
**New arrivals are batch-updated IN PLACE in their source deck, and STAY there**
for the user to examine. The agent does NOT auto-move them into the main
`Japanese`/`Chinese` deck. The user reviews the newly-covered cards in the
source/Pleco/Takoboto deck and **manually** moves them into the main deck only
when satisfied. Migration steps in the scripts keep cards in whatever deck they
currently occupy — preserve that. Never add an auto "move to main deck" step
unless explicitly asked.

### 0. Non-negotiables (learned the hard way)
1. **Anki must be fully closed** before ANY write to `collection.anki2`.
   Verify: `pgrep -x anki` (empty = safe). Writing with Anki open corrupts the DB
   ("disk image is malformed") and forces a restore.
2. **Take a backup** before every migration:
   ```bash
   cp "/home/ben/snap/anki-desktop/common/User 1/collection.anki2" \
      ~/dev/sino-korean/backups/pre_$(date +%F_%H%M%S).anki2
   ```
   Backups are **local only** (gitignored — GitHub rejects >100 MB).
3. **Both Enhanced models are Recognition-only (1 template).** If a model ever has
   2+ templates, migrations silently spawn duplicate "New" cards. If you must change
   templates, use Anki's API (snap python), never raw SQL on the template blob.
4. Keep experimental/imported cards in their own deck until verified — don't move
   them into the main deck prematurely.

### 1. Extract the new words (offline, read-only)
```bash
cd ~/dev/sino-korean && source .venv/bin/activate
python3 src/74_extract_chinese_main.py   # (or equivalent per deck — see below)
```
Read-only SQL flattens each deck's notes into prompt files:
`data/sentences_raw/<lang>/prompt_<prefix>_###.txt`, one line per word:
```
word|pinyin|raw_meaning
```

### 2. LLM batch generation (speedy, parallel)
Use `src/75_generate_chinese_main.py` as the reference generator. It:
- reads a prompt batch, calls **deepseek flash** in **chunks of 20 words** (proven
  reliable; larger chunks truncate), retries on partial/failed responses,
- writes `out_*.txt` in strict `===word: WORD===` blocks with all target fields,
- is **resumable** (skips already-complete batches),
- supports **parallel workers over batch ranges**:
  ```bash
  python3 src/75_generate_chinese_main.py 1 19 &   # worker A
  python3 src/75_generate_chinese_main.py 20 38 &  # worker B
  ...
  ```
Model/API: `deepseek/deepseek-v4-flash` via OpenRouter. API key in `~/.hermes/.env`
(`OPENROUTER_API_KEY=`). Use the project `.venv` python (has genanki + requests
helpers).

**Speed tips:** dispatch all ranges in parallel from the start (don't test 1 batch
first). Prefer the chunked local script over delegating each file to a subagent —
the local script is faster and fewer moving parts. If the model times out/truncates
repeatedly, add retries / shrink chunk size rather than rewriting the pipeline.

### 3. Refill gaps (optional, if coverage < ~99%)
`src/76_refill_chinese_main.py` regenerates only the entries still missing a field,
then patches them in place (preserves all other content byte-for-byte).

### 4. Migrate into the Enhanced notetype (in place)
Verified scripts (Anki closed, backup first, cards stay in their deck):
```bash
# Japanese new arrivals (Takoboto / WIP -> Japanese Enhanced, 13 fields)
python3 src/61_migrate_main.py          # maps old-model notes onto JP Enhanced

# Chinese (main + WIP -> Chinese Enhanced, 12 fields)
python3 src/79_migrate_chinese_all.py

# After it: merge examples/nuance and regenerate ruby reading
python3 src/78_merge_jp_examples.py     # JP only: re-merges Phase-3 examples+Nuance_JP
python3 src/66_fix_furigana.py          # JP only: Reading+Furigana in 漢字[かんな]
```
Migration scripts refuse to run if Anki is open and take a backup automatically.
They keep each card in its deck; unmatched non-vocab notes are left on the old model
(optionally move to `Japanese (Old)` / old deck).

### 5. Verify
Re-open read-only and assert, per Enhanced notetype:
- notes == cards (no duplicates),
- `PRAGMA integrity_check` == `ok`,
- expected field coverage (Meaning/Nuance ~100%, examples ~95%+).
Then tell the user to open Anki → **Check Database** → sync (first sync looks like
a big change count — normal, let it complete).

---

## Field layouts (authoritative)

### Japanese Enhanced — 13 fields (id 1738229000)
```
0 Expression | 1 Meaning | 2 Reading | 3 Nuance(empty) | 4 Example1 | 5 Example1_EN
6 Example2 | 7 Example2_EN | 8 Example3 | 9 Example3_EN | 10 Nuance_EN
11 Nuance_JP | 12 Furigana
```
- Reading and Furigana (fields 2 & 12) use **ruby format** `漢字[かんな]` (via
  `make_furigana()` from `src/50_build_japanese_enhanced.py`).
- Template front = `{{furigana:Reading}}`.

### Chinese Enhanced — 12 fields (id 1787807921282)
```
0 Expression | 1 Meaning | 2 Pinyin | 3 Nuance(empty) | 4 Example1 | 5 Example1_EN
6 Example2 | 7 Example2_EN | 8 Example3 | 9 Example3_EN | 10 Nuance_EN | 11 Nuance_CN
```
- Pinyin (field 2) comes from the source card — already correct, keep as-is.
- Chinese card: **red top** (`#d14949`), front shows Expression **only**; pinyin on back.

Reads use the `notetypes` / `fields` / `templates` tables (modern v5 schema) + a
`unicase` collation you must register:
```python
conn.create_collation('unicase', lambda a,b: (a.lower()>b.lower())-(a.lower()<b.lower()))
```

---

## Key IDs
| Kind | Name | ID |
|------|------|----|
| notetype | Japanese Enhanced | 1738229000 |
| notetype | Chinese Enhanced | 1787807921282 |
| notetype | Chinese (old) | 1351220176888 |
| notetype | Japanese (old) | 1351215240429 |
| deck | Japanese | 1355152451702 |
| deck | Japanese (Old) | 1787708123456 |
| deck | Japanese Enhanced: Takoboto | 1787581629780 |
| deck | Japanese WIP | 1754445304808 |
| deck | Chinese | 1351219999178 |
| deck | Pleco (ex-Chinese WIP) | 1754445298156 |

Values come from `"User 1/collection.anki2"`; re-verify with a read-only query if in doubt.

---

## Python interpreters (important)
- **Project `.venv` python** (`~/.dev/sino-korean/.venv/bin/python3`) — has `genanki`;
  use for building `.apkg` files and the LLM generator scripts.
- **Snap python** (`/snap/anki-desktop/85/bin/python3.12`) — can `import anki`
  (real Anki API). Use for template changes (`models.remove_template`),
  `change_notetype_of_notes`, or any schema edit where raw SQL is unsafe.
- **System python** (`/usr/bin/python3`) — cannot import `anki`; use only for
  pure-SQL read-only inspection. Register `unicase` collation.

---

## Conflicts / stale info in other docs
`MIGRATION_PLAN.md`, `ENGINEERING_NOTES.md`, `CHINESE_PLAN.md`, and parts of
`ANKI_REFERENCE.md` describe the **pre-migration "planned"** state and older
assumptions. Trust THIS doc for current ground truth. Specific stale items:
- "Japanese/Chinese still planned / old 3-field model" — both are DONE.
- Japanese Enhanced field count quoted as 10 in some places — it is **13**.
- Any suggestion to hand-write the `notetypes.config` blob — **never do that**;
  create/alter notetypes via genanki `.apkg` import or the Anki API.
- ANKI_REFERENCE's "flat table / no notetypes table" schema description — the
  current collection uses the **modern split-table** schema (`notetypes`,
  `fields`, `templates`). Use those.