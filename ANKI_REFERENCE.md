# Anki Collection Reference: Japanese Enhanced Migration

## Collection Location
```
/home/ben/snap/anki-desktop/common/User 1/collection.anki2
```

Backups are stored in the same directory (`.before_*` suffixes).

## Database Schema

Older Anki (version 18, as seen in this collection) uses a **flat table layout** — not the newer `notetypes`/`decks`/`config` tables with zlib-compressed BLOBs. The relevant tables are:

### `col` — collection config
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | Always 1 |
| `ver` | INTEGER | Anki schema version (18 here) |
| `models` | TEXT | **Empty** in this version — model data is elsewhere |
| `decks` | TEXT | **Empty** — deck data is elsewhere |

### `notes` — the actual note data
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | Primary key |
| `mid` | INTEGER | Model ID (foreign key to notetypes.id) |
| `flds` | TEXT | Fields joined by `\x1f` (unit separator, chr(31)) |
| `sfld` | TEXT | Sort field (first field duplicated) |

### `cards` — the actual cards
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | Primary key |
| `nid` | INTEGER | Note ID (foreign key to notes.id) |
| `did` | INTEGER | Deck ID (foreign key to decks.id) |
| `ord` | INTEGER | Template index (0 = first template) |
| `type` | INTEGER | 0=new, 1=learning, 2=review |
| `queue` | INTEGER | Scheduling queue type |
| `ivl` | INTEGER | Interval in days |
| `reps` | INTEGER | Number of repetitions |
| `lapses` | INTEGER | Number of lapses |

### `revlog` — review history
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | Timestamp-based ID |
| `cid` | INTEGER | Card ID |
| `usn` | INTEGER | Update sequence number |
| `ease` | INTEGER | Button pressed (1-4) |
| `ivl` | INTEGER | New interval |
| `lastIvl` | INTEGER | Previous interval |
| `factor` | INTEGER | Ease factor |
| `time` | INTEGER | Time taken in ms |
| `type` | INTEGER | 0=learning, 1=review, 2=relearning |

### `notetypes` — the note type definitions
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | Primary key (matches notes.mid) |
| `name` | TEXT | Human-readable name |
| `config` | BLOB | JSON blob, **COCOAPOD** packed (not standard zlib) |

**Important:** The `config` blob uses CocoaPods-style zlib framing (header `\x1a\xce\r\n` or `\x1a\xab\n\n`), NOT standard zlib. Standard `zlib.decompress()` fails. To read it, you need to strip the first 4 bytes or use Anki's internal `from anki.utils import decompress` — but for migration purposes, you don't actually need to read the config. The model IDs and field counts are sufficient.

### `decks` — the deck definitions
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | Primary key (matches cards.did) |
| `name` | TEXT | Human-readable name |
| `common` | BLOB | Protobuf or packed data |
| `kind` | BLOB | Protobuf or packed data |

## Model IDs (from this collection)

| ID | Name | Fields | Notes |
|----|------|--------|-------|
| `1351215240429` | Japanese | 3 | Old model — Expression, Meaning, Reading |
| `1738229000` | Japanese Enhanced | 13 | New model — Expression, Meaning, Reading, Nuance(empty), Example1-3, Ex1-3_EN, Nuance_EN, Nuance_JP, Furigana |
| `1738228000` | Korean Vocab | 15 | Unrelated |
| `1351220176888` | Chinese | 3 | Unrelated |
| `1373015105001` | Proper Nouns | 3 | Unrelated |
| `1653807843980` | jp.takoboto | ? | Takoboto import — unused now |
| `1756386463853` | Spanish | 2 | Unrelated |
| `1756386214382` | Korean | 2 | Unrelated |

## Deck IDs

| ID | Name | Notes |
|----|------|-------|
| `1355152451702` | Japanese | Main target deck |
| `1787581629780` | Japanese Enhanced: Takoboto | Now obsolete — cards moved to Japanese |
| `1754445304808` | Japanese WIP | Now obsolete — cards moved to Japanese |
| `1787708123456` | Japanese (Old) | Houses 1,311 unmatched old-format cards |

## The 13 Japanese Enhanced Fields

```
0:  Expression  (the word)
1:  Meaning     (from original card)
2:  Reading     (from original card)
3:  Nuance      (EMPTY — kept for field-count alignment)
4:  Example1    (LLM-generated)
5:  Example1_EN (LLM-generated)
6:  Example2    (LLM-generated)
7:  Example2_EN (LLM-generated)
8:  Example3    (LLM-generated)
9:  Example3_EN (LLM-generated)
10: Nuance_EN   (from LLM nuance field)
11: Nuance_JP   (from LLM nuance field, Japanese only)
12: Furigana    (reading text, used by {{furigana:Reading}} template)
```

## Migration Strategy (proven approach)

### Step 1: Count old-model notes
```python
conn.execute('SELECT COUNT(*) FROM notes WHERE mid = ?', (OLD_MODEL_ID,))
```

### Step 2: Build LLM lookup
Read all `out_*.txt` files, parse `===word: WORD===` blocks, extract Nuance, Example1-3, Example1-3_EN into a dict keyed by word.

### Step 3: Match and UPDATE
For each note on old model, look up `fields[0]` (Expression) in the LLM dict. If found:
```python
new_flds = chr(31).join([word, meaning, reading, '', ex1, ex1_en, ex2, ex2_en, ex3, ex3_en, nuance_en, nuance_jp, reading])
conn.execute('UPDATE notes SET mid = ?, flds = ? WHERE id = ?', (NEW_MODEL_ID, new_flds, nid))
```

### Step 4: Move deck
```python
conn.execute('UPDATE cards SET did = ? WHERE did = ?', (TARGET_DECK_ID, OLD_DECK_ID))
```

### Step 5: Create legacy deck (if needed)
```python
conn.execute('INSERT INTO decks (id, name, mtime_secs, usn, common, kind) VALUES (?, ?, ?, ?, ?, ?)',
    (new_deck_id, 'Japanese (Old)', now, -1, wip_common, wip_kind))
conn.execute('UPDATE cards SET did = ? WHERE nid IN (SELECT id FROM notes WHERE mid = ?)', (new_deck_id, OLD_MODEL_ID))
```

## Key Pitfalls

1. **`unicase` collation** — Anki's SQLite driver registers a custom `unicase` collation. Queries on `decks` or `notetypes` tables that join on `name` will fail with `no such collation sequence: unicase` unless you register it:
   ```python
   conn.create_collation('unicase', lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
   ```

2. **Field separator** — Anki uses `\x1f` (unit separator, chr(31)) to join fields. Always split/join with `chr(31)`.

3. **Mod timestamp** — When updating cards/notes, set `mod = int(time.time() * 1000)` and `usn = -1` (pending sync).

4. **First sync** — After migration, the first Anki sync will show a large number of changes (possibly looking like 15K deletions followed by re-uploads). This is normal — Anki notices the field count changed and re-converts. Let it complete.

5. **CocoaPods blobs** — The `notetypes.config` and `decks.common`/`decks.kind` BLOBs use a non-standard zlib framing. You can copy them from existing decks when creating new ones — don't try to parse them.

## LLM Output Format

All output files at `data/sentences_raw/jp_main/out_*.txt` use this format:

```
===word: WORD===
Nuance: [Japanese-only explanation of meaning, usage, register]
Example1: [です/ます体 sentence]
Example1_EN: [English translation]
Example2: [です/ます体 sentence]
Example2_EN: [English translation]
Example3: [です/ます体 sentence]
Example3_EN: [English translation]
```

The `jp-vocab-enrichment` skill has the exact format spec. Early batches (1-55ish) used `===word: WORD (reading)===` format — the migration script handles both.