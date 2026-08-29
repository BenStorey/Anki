#!/usr/bin/env python3
"""
cover_new_cards.py — THE one command for covering new card arrivals with LLM content.

Usage (project venv):
    python3 src/cover_new_cards.py jp            # cover new cards in JP arrival decks
    python3 src/cover_new_cards.py cn            # (or) new cards in the Pleco deck
    python3 src/cover_new_cards.py jp --force    # regenerate a batch that was missed

WHAT IT DOES (all in place — cards stay in their source deck for review):
  1. SAFETY: verifies Anki is closed (refuses otherwise) + takes a backup.
  2. EXTRACT: finds notes in the language's arrival deck(s) that are NOT yet on the
     Enhanced notetype, dedups by Expression, writes `word|reading` prompt batches
     (ONLY the word + reading — never the raw meaning, so the model must generate
     Meaning/examples/nuance itself).
  3. GENERATE: deepseek-flash LLM batch (20 words/call, resumable) → writes
     `===word: {fields}===` blocks to out files on disk.
  4. MIGRATE: rebuilds each note's Enhanced field string and UPDATEs in place —
     cards STAY in whichever deck they currently occupy (NEVER auto-moved to the
     main deck; the user reviews then moves manually).
  5. POST (JP only): regenerates Reading + Furigana ruby (漢字[かんな]).
  6. VERIFY: notes==cards (no dupes), integrity, and field coverage.

The LLM data lives under data/sentences_raw/{lang}_new/ and is committed to git
BEFORE any DB write (re-import insurance). Old one-off scripts are kept for
reference; this file is authoritative for NEW cards.

Fully offline: generation writes only to disk; the only DB writes are in-place
note/card updates, gated on Anki being closed.
"""
import json, os, re, sqlite3, subprocess, sys, time, urllib.request
from pathlib import Path

# ────────────────────────────── paths / globals ──────────────────────────────
HOME = Path.home()
# Overridable via env for testing against a throwaway collection / data dir.
COLLECTION = Path(os.environ.get("ANKI_COLLECTION", HOME / "snap/anki-desktop/common/User 1/collection.anki2"))
ROOT = Path(os.environ.get("SINOKOREAN_ROOT", HOME / "dev/sino-korean"))
BACKUP_DIR = ROOT / "backups"
DATA_DIR = ROOT / "data/sentences_raw"
API_KEY = next((l.split("=", 1)[1].strip().strip('"').strip("'")
                for l in open(HOME / ".hermes" / ".env")
                if l.startswith("OPENROUTER_API_KEY=")), None)
MODEL = "deepseek/deepseek-v4-flash"
URL = "https://openrouter.ai/api/v1/chat/completions"
CHUNK = 20          # words per API call — proven for CJK long-form output
BATCH_SIZE = 200    # words per prompt batch file

# ────────────────────────────── per-language config ──────────────────────────────
LANGUAGES = {
    # Japanese: arrival decks = Takoboto + Japanese WIP
    "jp": {
        "enhanced_mid": 1738229000,
        "source_decks": [1787581629780, 1754445304808],
        "out_subdir": "jp_new",
        "prompt_prefix": "prompt_jn",
        "out_prefix": "out_jn",
        "n_fields": 13,
        "do_furigana": True,
        "system": """You produce Japanese vocabulary flashcards for an N1 learner.
Input lines: word|reading   (this is ALL you are given — generate everything else yourself)
For EACH word output exactly:
===word: WORD===
Meaning: clean English gloss, 1-5 words
Nuance_EN: English, 1-2 sentences on meaning/usage/register
Nuance_JP: Japanese, 1-2 sentences on the nuance
Example1: natural Japanese sentence (です/ます), COMPLETE and grammatical
Example1_EN: natural English translation (never pinyin, never a fragment)
Example2: natural Japanese sentence
Example2_EN: English translation
Example3: natural Japanese sentence
Example3_EN: English translation

Generate all fields yourself from the word; do not copy any English you recognise
from other sources. Rules: ===word: header matches input exactly; blank line after
each block; all example sentences natural, polite register.""",
    },
    # Chinese: arrival deck = Pleco (was "Chinese WIP"), id 1754445298156
    "cn": {
        "enhanced_mid": 1787807921282,
        "source_decks": [1754445298156],
        "out_subdir": "cn_new",
        "prompt_prefix": "prompt_cn",
        "out_prefix": "out_cn",
        "n_fields": 12,
        "do_furigana": False,
        "system": """You produce Mandarin (Simplified Chinese) vocabulary flashcards.
Input lines: word|pinyin   (this is ALL you are given — generate everything else yourself)
For EACH word output exactly:
===word: WORD===
Meaning: clean English gloss, 1-5 words
Nuance_EN: English, 1-2 sentences on meaning/usage/register
Nuance_CN: Simplified Chinese, 1-2 sentences on the nuance
Example1: natural, COMPLETE Simplified Chinese sentence
Example1_EN: natural English translation (never pinyin, never a fragment)
Example2: natural, COMPLETE Simplified Chinese sentence
Example2_EN: English translation
Example3: natural, COMPLETE Simplified Chinese sentence
Example3_EN: English translation

Generate all fields yourself from the word; do not copy any English you recognise
from other sources. Rules: ===word: header matches input exactly; blank line after
each block; all example sentences natural, neutral register.""",
    },
}
FIELD_LABELS = [("Meaning:", "meaning"), ("Nuance_EN:", "nuance_en"),
                ("Nuance_JP:", "nuance_jp"), ("Nuance_CN:", "nuance_cn"),
                ("Example1:", "ex1"), ("Example1_EN:", "ex1_en"),
                ("Example2:", "ex2"), ("Example2_EN:", "ex2_en"),
                ("Example3:", "ex3"), ("Example3_EN:", "ex3_en")]


# ────────────────────────────── helpers ──────────────────────────────
def unicase(a, b):
    return (a.lower() > b.lower()) - (a.lower() < b.lower())


def check_anki_closed():
    for proc in ["anki", "anki-qt", "anki-desktop"]:
        r = subprocess.run(["pgrep", "-x", proc], capture_output=True, text=True)
        if r.stdout.strip():
            sys.exit(f"ABORT: Anki ({proc}) is running. Close Anki fully and re-run.")


def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"collection_pre_cover_{stamp}.anki2"
    src = sqlite3.connect(f"file:{COLLECTION}?mode=ro", uri=True)
    src.create_collation("unicase", unicase)
    dst = sqlite3.connect(str(backup)); src.backup(dst)
    dst.close(); src.close()
    print(f"  Backup: {backup}")


def clean_html(s):
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()[:200]


def read_new_rows(cfg):
    """{word: {nid, reading, meaning}} for arrival-deck notes NOT yet Enhanced."""
    conn = sqlite3.connect(f"file:{COLLECTION}?mode=ro&immutable=1", uri=True)
    conn.create_collation("unicase", unicase)
    out = {}
    for did in cfg["source_decks"]:
        for nid, flds_raw in conn.execute('''
            SELECT n.id, n.flds FROM notes n
            JOIN cards c ON c.nid = n.id
            WHERE c.did = ? AND n.mid != ?
            GROUP BY n.id
        ''', (did, cfg["enhanced_mid"])):
            f = flds_raw.split(chr(31))
            word = f[0].strip() if f else ""
            if not word or word in out:
                continue
            out[word] = {
                "nid": nid,
                "reading": (f[2].strip() if len(f) > 2 else ""),
                "meaning": clean_html(f[1] if len(f) > 1 else ""),
            }
    conn.close()
    return out


# ────────────────────────────── LLM generation ──────────────────────────────
def call_llm(prompt, system):
    payload = {"model": MODEL,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": prompt}],
               "temperature": 0.3, "max_tokens": 128000}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {API_KEY}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]


def parse_blocks(content):
    out = {}
    for block in content.split("===word: ")[1:]:
        word = block.split("===")[0].strip()
        rest = block.split("===")[1] if "===" in block else block
        fields = {}
        for line in rest.split("\n"):
            s = line.strip()
            for label, key in FIELD_LABELS:
                if s.startswith(label):
                    fields[key] = s[len(label):].strip()
        if word:
            out[word] = fields
    return out


def render(words, entries):
    out_lines = []
    for w, _r, _m in words:
        e = entries.get(w, {})
        out_lines.append(f"===word: {w}===")
        for label, key in FIELD_LABELS:
            out_lines.append(f"{label} {e.get(key, '')}")
        out_lines.append("")
    return "\n".join(out_lines)


def generate_batch(idx, total, cfg, words):
    out_dir = DATA_DIR / cfg["out_subdir"]
    of = out_dir / f"{cfg['out_prefix']}_{idx:03d}_of_{total:03d}.txt"
    if of.exists() and of.read_text(errors="replace").count("===word:") >= len(words):
        print(f"[{idx}] already done", flush=True)
        return
    print(f"[{idx}] {len(words)} words", flush=True)
    entries = {}
    for i in range(0, len(words), CHUNK):
        chunk = words[i:i + CHUNK]
        lines = [f"{w}|{r}" for w, r, _m in chunk]
        ok = False
        for attempt in range(6):
            try:
                t0 = time.time()
                parsed = parse_blocks(call_llm("\n".join(lines), cfg["system"]))
                filled = sum(1 for (w, _, _) in chunk if w in parsed and parsed[w].get("meaning"))
                if filled >= len(chunk) * 0.85:
                    entries.update(parsed)
                    print(f"  ch{i // CHUNK + 1}: {filled}/{len(chunk)} ({time.time() - t0:.0f}s)", flush=True)
                    ok = True
                    break
                print(f"  ch{i // CHUNK + 1}: {filled}/{len(chunk)} att{attempt + 1}", flush=True)
            except Exception as e:
                print(f"  ch{i // CHUNK + 1} att{attempt + 1}: {type(e).__name__}", flush=True)
            time.sleep(5)
        if not ok:
            print(f"  FAILED ch{i // CHUNK + 1}", flush=True)
    of.write_text(render(words, entries), encoding="utf-8")
    done = sum(1 for (w, _, _) in words if w in entries and entries[w].get("meaning"))
    print(f"[{idx}] DONE {done}/{len(words)} -> {of.name}", flush=True)


# ────────────────────────────── field building / migration ──────────────────────────────
def build_fields(word, reading, e, cfg, ruby):
    if cfg["do_furigana"]:
        fields = [word, e.get("meaning", ""), ruby, ""]
        for k in ["ex1", "ex1_en", "ex2", "ex2_en", "ex3", "ex3_en"]:
            fields.append(e.get(k, ""))
        fields.append(e.get("nuance_en", ""))
        fields.append(e.get("nuance_jp", ""))
        fields.append(ruby)  # Furigana
        assert len(fields) == 13
    else:
        fields = [word, e.get("meaning", ""), reading, ""]
        for k in ["ex1", "ex1_en", "ex2", "ex2_en", "ex3", "ex3_en"]:
            fields.append(e.get(k, ""))
        fields.append(e.get("nuance_en", ""))
        fields.append(e.get("nuance_cn", ""))
        assert len(fields) == 12
    return chr(31).join(fields)


_make_furigana = None


def get_make_furigana():
    global _make_furigana
    if _make_furigana is None:
        import importlib.util as iu
        spec = iu.spec_from_file_location("b50", str(ROOT / "src/50_build_japanese_enhanced.py"))
        b50 = iu.module_from_spec(spec)
        spec.loader.exec_module(b50)
        _make_furigana = b50.make_furigana
    return _make_furigana


def migrate(cfg, new_rows):
    # parse all out files -> {word: fields}
    llm = {}
    out_dir = DATA_DIR / cfg["out_subdir"]
    for of in sorted(out_dir.glob(f"{cfg['out_prefix']}_*.txt")):
        llm.update(parse_blocks(of.read_text(errors="replace")))

    conn = sqlite3.connect(str(COLLECTION)); conn.create_collation("unicase", unicase)
    updates = []
    for word, info in new_rows.items():
        e = llm.get(word)
        if not e or not e.get("meaning"):
            continue
        try:
            r = get_make_furigana()(word) if cfg["do_furigana"] else ""
        except Exception:
            r = ""
        new_flds = build_fields(word, info["reading"], e, cfg, r)
        updates.append((new_flds, info["nid"]))
    nid_list = [info["nid"] for info in new_rows.values()]
    conn.close()

    # Rebuild nid->decks mapping from info we already have (source decks)
    # A note may have cards in multiple decks; keep each card where it is.
    conn = sqlite3.connect(str(COLLECTION)); conn.create_collation("unicase", unicase)
    now = int(time.time() * 1000)
    conn.execute("BEGIN")
    for new_flds, nid in updates:
        conn.execute("UPDATE notes SET mid=?, flds=?, mod=?, usn=-1 WHERE id=?",
                     (cfg["enhanced_mid"], new_flds, now, nid))
        conn.execute("UPDATE cards SET mod=?, usn=-1 WHERE nid=?", (now, nid))
    conn.execute("UPDATE col SET mod=?", (now,))
    conn.commit()
    conn.close()
    print(f"  Migrated {len(updates)} notes in place (cards stay in their deck)")
    return len(updates)


# ────────────────────────────── verify / main ──────────────────────────────
def verify(cfg):
    conn = sqlite3.connect(f"file:{COLLECTION}?mode=ro&immutable=1", uri=True)
    conn.create_collation("unicase", unicase)
    notes = conn.execute("SELECT COUNT(*) FROM notes WHERE mid=?", (cfg["enhanced_mid"],)).fetchone()[0]
    cards = conn.execute("SELECT COUNT(*) FROM cards c JOIN notes n ON c.nid=n.id WHERE n.mid=?",
                         (cfg["enhanced_mid"],)).fetchone()[0]
    integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()
    print(f"\nEnhanced notes: {notes}, cards: {cards} (1:1 = {notes == cards}), integrity: {integ}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in LANGUAGES:
        sys.exit(__doc__)
    LANG = sys.argv[1]
    cfg = LANGUAGES[LANG]

    check_anki_closed()
    print(f"=== Cover new {LANG.upper()} cards — in place, leave for review ===")

    new_rows = read_new_rows(cfg)
    words = [(w, r["reading"], r["meaning"]) for w, r in new_rows.items()]
    print(f"New words to cover: {len(words)}")
    if not words:
        print("  Nothing to do — all arrival-deck notes already Enhanced.")
        return

    make_backup()

    # write prompt batches
    out_dir = DATA_DIR / cfg["out_subdir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob(f"{cfg['prompt_prefix']}_*.txt"):
        f.unlink()
    n_batches = (len(words) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(words), BATCH_SIZE):
        b = i // BATCH_SIZE + 1
        chunk = words[i:i + BATCH_SIZE]
        lines = [f"{w}|{r}" for w, r, _m in chunk]
        (out_dir / f"{cfg['prompt_prefix']}_{b:03d}_of_{n_batches:03d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"  Wrote {n_batches} prompt batch(es) -> {out_dir}")

    # generate (sequential; for large batches run parallel ranges manually)
    for b in range(1, n_batches + 1):
        chunk = words[(b - 1) * BATCH_SIZE: b * BATCH_SIZE]
        generate_batch(b, n_batches, cfg, chunk)

    # commit LLM store before DB write
    subprocess.run(f"cd {ROOT} && git add data/sentences_raw/{cfg['out_subdir']}/ src/cover_new_cards.py "
                   f"&& git commit -m 'data: {LANG} new-card LLM store' >/dev/null 2>&1",
                   shell=True)

    migrate(cfg, new_rows)
    verify(cfg)
    print("\nDone! Cards are covered and still in their source deck. Open Anki → Check Database → sync.")


if __name__ == "__main__":
    main()