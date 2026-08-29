# Stabilized — How to Add New Cards (Handoff Guide)

**Read this first. It is the current, authoritative workflow.** The other `*.md`
files in this repo are historical/planning docs (some stale — see Conflicts at the bottom).

Last validated: 2026-08-28. Both languages fully migrated:

| Language | Enhanced notetype | Fields | Notes | Templates | Cards (1:1) |
|----------|-------------------|--------|-------|-----------|--------------|
| Japanese | `Japanese Enhanced` (id `1738229000`) | 14 (incl Image) | 27,949 | 1 × Recognition | 27,949 |
| Chinese  | `Chinese Enhanced`  (id `1787807921282`) | 13 (incl Image) | 16,370 | 1 × Recognition | 16,370 |

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

### 🔎 Why `cover_new_cards.py` might report "0 new words" (debug this, don't assume)
- **Look the arrival deck up by NAME, not by a saved ID.** Anki deletes and
  recreates decks on sync/import, so a deck's ID is NOT stable. The script uses a
  `source_deck_names` config (e.g. "Takoboto", "Pleco") resolved at runtime via
  `resolve_source_decks()` → do not hardcode an arrival-deck ID anywhere.
- **The JP arrival model changed** — Takoboto now imports into a deck literally
  named "Takoboto" on the `jp.takoboto` (7-field) model, not the older
  `Japanese Enhanced: Takoboto`. `cover_new_cards.py` covers any note in the
  resolved deck whose `mid != enhanced`, so it picks these up automatically.
- **Ensure you actually ran the script.** `read_new_rows` is read-only; a
  "0 new" result can also mean the run preceded the word landing (Anki was still
  open / unsynced at the time) — always `pgrep -x anki` and look at the deck's
  current contents first.
- JP and CN arrival decks each hold the new word on the OLD model (`jp.takoboto`,
  `Chinese`) until covered — the card should show up there before cover runs.

### ⚠️ Field-count mismatch — why it happens and why it matters (IMPORTANT)
- **Symptom:** after running `cover_new_cards.py`, Anki's **Check Database** says
  "Fixed N notes with wrong field count." Root cause: `build_fields` wrote a
  hardcoded field count (13 JP / 12 CN) that became stale once the Image field was
  added (models are now 14 JP / 13 CN), leaving covered cards one field short.
- **The real risk (review loss):** a field-count mismatch makes Anki treat the note
  as locally-modified, which on a two-way sync is exactly what can trigger a
  conflict / "can't merge" state that risks losing the review. So the field count
  MUST exactly match the model **before** the user syncs.
- **Fix:** `build_fields` now calls `enhanced_field_count()` (reads the live
  `fields` table count) and pads with empty segments to that count. Covered cards
  always match the model — no mismatch, no Check Database-needed, no sync risk.
- **Rule:** whenever you add/remove a field on an Enhanced model, the cover script
  (and any other field builder) must be re-checked to pad to the new live count.
  Never hardcode a count in a field builder.

### ▶ THE one command (use this — it does everything)
After new cards land in an arrival deck, cover them with ONE command (Anki
closed, project venv):

```bash
cd ~/dev/sino-korean && source .venv/bin/activate
python3 src/cover_new_cards.py jp    # cover new JP arrivals (Takoboto + JP WIP)
python3 src/cover_new_cards.py cn    # cover new CN arrivals (Pleco)
```

`cover_new_cards.py` is deck-agnostic and language-parameterized in a config
table (LANGUAGES). It does, in order, with safety + in-place/review semantics
baked in:
1. **SAFETY** — refuses to run if Anki is open; takes a backup.
2. **EXTRACT** — finds arrival-deck notes NOT yet on the Enhanced notetype
   (`mid != enhanced` so covered cards are never reprocessed), dedups, writes
   `word|reading|raw_meaning` prompt batches.
3. **GENERATE** — deepseek-flash, 20 words/call, resumable; writes `===word:`
   blocks to `data/sentences_raw/{jp_new,cn_new}/`.
4. **MIGRATE** — rebuilds the Enhanced field string (13 jp / 12 cn), UPDATEs in
   place; cards STAY in their source deck.
5. **POST (jp)** — regenerates Reading + Furigana ruby via make_furigana().
6. **VERIFY** — notes==cards, integrity, coverage. Commits the LLM store to git
   before any DB write.

For a large stack, run the batch ranges in parallel manually (see below);
otherwise one command is enough for a small Pleco/Takoboto batch.


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

### 1-5. Manual / advanced path (only if you need to go piece-by-piece)

`cover_new_cards.py` handles the normal flow end-to-end. For ad-hoc steps or very
large stacks you can run the underlying scripts individually (a deck-agnostic
version of the pipeline; also see the per-deck `src/7x_*` / `src/6x_*` historical
scripts listed in `src/ABANDONED_SCRIPTS.md`):

1. **Extract** (offline, read-only): flatten deck notes → `word|reading|raw_meaning`
   prompt batches under `data/sentences_raw/<lang>/prompt_*_###.txt`.
2. **Generate** (deepseek flash, 20 words/call, resumable, parallel ranges):
   call the generator with `start end` batch-range args over
   `data/sentences_raw/<lang>/` out files in `===word: ===` format.
   ```bash
   python3 src/75_generate_chinese_main.py 1 19 &   # worker A (parallel)
   python3 src/75_generate_chinese_main.py 20 38 &
   ```
   Model/API: `deepseek/deepseek-v4-flash` via OpenRouter; key in `~/.hermes/.env`
   (`OPENROUTER_API_KEY=`). Use the project `.venv` python.
3. **Refill gaps** if coverage < ~99%: `src/76_refill_chinese_main.py` regenerates
   only missing-field entries and patches in place (byte-preserving).
4. **Migrate** in place (Anki closed, backup first, cards stay in their deck):
   ```bash
   python3 src/61_migrate_main.py          # JP: old-model notes -> JP Enhanced
   python3 src/79_migrate_chinese_all.py   # CN: main + Pleco -> CN Enhanced
   python3 src/78_merge_jp_examples.py     # JP: re-merge Phase-3 examples+Nuance_JP
   python3 src/66_fix_furigana.py          # JP: Reading+Furigana ruby 漢字[かんな]
   ```
5. **Verify**: notes==cards, integrity_check==ok, field coverage. Then tell the
   user to open Anki → Check Database → sync (big change count is normal).

**Parallel speed tips:** dispatch all batch ranges in parallel from the start
(don't test 1 batch first). Prefer the chunked local script over delegating each
file to a subagent. If the model times out/truncates repeatedly, add retries or
shrink the chunk size, don't rewrite the pipeline. Commit the LLM data store to
git immediately after generation, before any DB write.

---

## Field layouts (authoritative)

### Japanese Enhanced — 14 fields (id 1738229000)
```
0 Expression | 1 Meaning | 2 Reading | 3 Nuance(empty) | 4 Example1 | 5 Example1_EN
6 Example2 | 7 Example2_EN | 8 Example3 | 9 Example3_EN | 10 Nuance_EN
11 Nuance_JP | 12 Furigana | 13 Image
```
- Reading and Furigana (fields 2 & 12) use **ruby format** `漢字[かんな]` (via
  `make_furigana()` from `src/50_build_japanese_enhanced.py`).
- Field 13 Image: holds `<img>` (shown at top of back, above Meaning).
- Template front = `{{furigana:Reading}}`.

### Chinese Enhanced — 13 fields (id 1787807921282)
```
0 Expression | 1 Meaning | 2 Pinyin | 3 Nuance(empty) | 4 Example1 | 5 Example1_EN
6 Example2 | 7 Example2_EN | 8 Example3 | 9 Example3_EN | 10 Nuance_EN | 11 Nuance_CN
12 Image
```
- Pinyin (field 2) comes from the source card — already correct, keep as-is.
- Field 12 Image: holds `<img>` (shown at top of back, above Meaning).
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