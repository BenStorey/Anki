# Anki Collection Reference: Enhanced Migration

> **UPDATE (2026-08-28):** The collection now uses Anki's **modern v5 schema** with
> split tables `notetypes`, `fields`, `templates`, `decks`, `config` (NOT the older
> flat `col.models` JSON blob). Read the current table structure via
> `PRAGMA table_info(...)` rather than assuming the text below. For the *added* new
> -cards workflow, see **`HANDOFF.md`**.

## Collection Location
```
/home/ben/snap/anki-desktop/common/User 1/collection.anki2
```

Read-only access (register the `unicase` collation):
```python
import sqlite3
def uc(a,b): return (a.lower()>b.lower())-(a.lower()<b.lower())
conn = sqlite3.connect(f"file:/home/ben/snap/anki-desktop/common/User 1/collection.anki2?mode=ro", uri=True)
conn.create_collation("unicase", uc)
```

## Database Schema (current — modern split tables)

### `notetypes` — the note type definitions
| Column | Type |
|--------|------|
| `id` | INTEGER (PK, matches notes.mid) |
| `name` | TEXT |
| `mtime_secs` | INTEGER |
| `usn` | INTEGER |
| `config` | BLOB (CSS + latex + req metadata) |

### `fields` — field definitions per notetype
| Column | Type | Notes |
|--------|------|-------|
| `ntid` | INTEGER | foreign key → notetypes.id |
| `ord` | INTEGER | 0-based field index |
| `name` | TEXT | field name |

### `templates` — card templates per notetype
| Column | Type | Notes |
|--------|------|-------|
| `ntid` | INTEGER | foreign key → notetypes.id |
| `ord` | INTEGER | 0-based card (template) index |
| `name` | TEXT | e.g. "Recognition" |
| `config` | BLOB | qfmt/afmt (protobuf-framed) |

> **Critical:** the `ord` in `cards` is the template index. A notetype with
> **N template rows** will expect up to **N cards per note** (one per `ord`). If a
> note ends up on a model with MORE templates than it has cards, Anki auto-generates
> the missing card(s) as **New** — this is the exact bug that previously produced
> ~28 K duplicate Production cards. Both Enhanced models are deliberately
> **single-template (Recognition only)**. Never add a 2nd template unless you intend
> duplicate-able cards.

### `notes`
| Column | Type |
|--------|------|
| `id` | INTEGER PK |
| `mid` | INTEGER (→ notetypes.id) |
| `flds` | TEXT, fields joined by `\x1f` (chr(31)) |

### `cards`
| Column | Type |
|--------|------|
| `id` | INTEGER PK |
| `nid` | INTEGER (→ notes.id) |
| `did` | INTEGER (→ decks.id) |
| `ord` | INTEGER (template index, 0-based) |
| `type` / `queue` / `due` / `ivl` / `reps` / `lapses` | scheduling |

### `decks`
| Column | Type |
|--------|------|
| `id` | INTEGER PK (matches cards.did) |
| `name` | TEXT |

## Model IDs (from this collection)
| ID | Name | Fields | Notes |
|----|------|--------|-------|
| `1738229000` | Japanese Enhanced | 13 | ACTIVE — see HANDOFF |
| `1787807921282` | Chinese Enhanced | 12 | ACTIVE — see HANDOFF |
| `1351215240429` | Japanese | 3 | Old model (124 leftover non-vocab) |
| `1351220176888` | Chinese | 3 | Old model (4 leftover non-vocab) |
| `1738228000` | Korean Vocab | 15 | Unrelated |
| `1373015105001` | Proper Nouns | 3 | Unrelated |
| `1653807843980` | jp.takoboto | ? | Takoboto import — source of new JP cards |
| `1756386463853` | Spanish | 2 | Unrelated |
| `1756386214382` | Korean | 2 | Unrelated |

## Deck IDs
| ID | Name | Notes |
|----|------|-------|
| `1355152451702` | Japanese | Main target deck |
| `1787708123456` | Japanese (Old) | 124 leftover old-format cards |
| `1787581629780` | Japanese Enhanced: Takoboto | Source deck for new JP arrivals |
| `1754445304808` | Japanese WIP | Source deck for new JP arrivals |
| `1351219999178` | Chinese | Main target deck |
| `1754445298156` | Chinese WIP | Pleco import — source deck for new CN arrivals |

## The 13 Japanese Enhanced Fields
```
0:  Expression  (the word)
1:  Meaning     (clean English gloss)
2:  Reading     (ruby format 漢字[かんな])
3:  Nuance      (EMPTY — kept for field-count alignment)
4:  Example1    (LLM-generated)
5:  Example1_EN (LLM-generated)
6:  Example2    (LLM-generated)
7:  Example2_EN (LLM-generated)
8:  Example3    (LLM-generated)
9:  Example3_EN (LLM-generated)
10: Nuance_EN   (English nuance)
11: Nuance_JP   (Japanese nuance)
12: Furigana    (ruby format — used by {{furigana:Reading}} template)
```

## The 12 Chinese Enhanced Fields
```
0: Expression | 1: Meaning (clean gloss) | 2: Pinyin | 3: Nuance (EMPTY)
4: Example1 | 5: Example1_EN | 6: Example2 | 7: Example2_EN
8: Example3 | 9: Example3_EN | 10: Nuance_EN | 11: Nuance_CN
```

## Working migration approach (READ HANDOFF.md for the full workflow)
The proven pipeline is captured in **`HANDOFF.md`**. Summary:
1. Extract new words → prompt files (read-only SQL, src/74).
2. LLM batch via src/75 (deepseek flash, 20-word chunks, parallel ranges).
3. Optional refill gaps src/76.
4. Migrate in place (Anki closed, backup first):
   - JP: src/61_migrate_main.py (+ 78_merge_jp_examples.py, 66_fix_furigana.py)
   - CN: src/79_migrate_chinese_all.py
5. Verify notes==cards and integrity; user runs Check Database + sync.

## Key Pitfalls
1. **`unicase` collation** — register it on every SQLite connection that touches
   `decks`/`notetypes` name joins, else `no such collation sequence: unicase`.
2. **Field separator** — Anki joins fields with `\x1f` (chr(31)). Always split/join
   with `chr(31)`.
3. **Mod timestamp** — set `mod = int(time.time()*1000)` and `usn = -1` when updating.
4. **Writing while Anki is open corrupts the DB** — always confirm closed first
   (`pgrep -x anki` empty), back up, then write.
5. **Never hand-write the `notetypes.config` blob** — create/aliter notetypes via
   genanki `.apkg` import (project venv) or the Anki API (snap python).
6. **First sync** after a migration shows a huge change count — normal; let it finish.

## LLM Output Format
All output files at `data/sentences_raw/jp_main/out_*.txt` and
`data/sentences_raw/chinese_*/out_*.txt` use `===word: WORD===` blocks:

```
===word: WORD===
Meaning: ...
Nuance_EN: ...
Nuance_CN: ...     (Chinese only)
Example1: ...
Example1_EN: ...
Example2: ...
...
```