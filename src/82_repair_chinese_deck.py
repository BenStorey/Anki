#!/usr/bin/env python3
"""
82_repair_chinese_deck.py — regenerate defective Chinese Enhanced notes IN PLACE.

Root cause of the errors: the original batch prompt fed the LLM
`word|pinyin|raw_meaning`, so on problem cards the model lazily echoed the raw
Pleco meaning back and/or emitted broken examples (pinyin in the EN field,
single-char fragments, missing sentence sets).

Root fix (this + cover_new_cards.py): prompt the model with ONLY `word|pinyin`
so it must generate every field itself.

This script:
  1. Detects affected Chinese Enhanced notes (heuristics + red/orange flags).
  2. Writes prompt files: word|pinyin ONLY.
  3. LLM-generates full blocks (deepseek flash, 20/call, resumable).
  4. Patches affected notes' 12 fields IN PLACE — cards stay in their deck,
     review history preserved, unaffected notes untouched.
  5. Writes a before/after review file.

Usage (Anki CLOSED, project venv):
    python3 src/82_repair_chinese_deck.py

Re-runnable: completes any failed batch, then re-applies. Backup taken first.
Regenerates ONLY affected notes (not the whole deck). Safe to run again later
once the user flags more cards.
"""
import json, os, re, sqlite3, subprocess, sys, time, urllib.request
from pathlib import Path

# ── config (env-overridable for throwaway testing) ──
HOME = Path.home()
COLLECTION = Path(os.environ.get(
    "ANKI_COLLECTION",
    HOME / "snap/anki-desktop/common/User 1/collection.anki2"))
ROOT = Path(os.environ.get("SINOKOREAN_ROOT", HOME / "dev/sino-korean"))
OUT_DIR = Path(os.environ.get(
    "REPAIR_OUT",
    ROOT / "data/sentences_raw/chinese_repair"))
BACKUP_DIR = ROOT / "backups"
ENHANCED_MID = 1787807921282   # Chinese Enhanced
API_KEY = next(
    (l.split("=", 1)[1].strip().strip('"').strip("'")
     for l in open(HOME / ".hermes" / ".env")
     if l.startswith("OPENROUTER_API_KEY=")),
    None)
MODEL = "deepseek/deepseek-v4-flash"
URL = "https://openrouter.ai/api/v1/chat/completions"
CHUNK = 10    # words per API call. Keep small: whole-chunk (0/20) parse failures at
              # 20 words showed truncation — shorter prompts parse cleanly far more often,
              # so fewer retries despite more calls.
BATCH = 100   # words per prompt batch file

SYSTEM = """You produce Mandarin (Simplified Chinese) vocabulary flashcards for a learner.

Input lines have the form: word|pinyin  (this is ALL you are given)

For EACH word you must generate EVERYTHING yourself, outputting exactly:
===word: WORD===
Meaning: clean English gloss, 1-5 words
Nuance_EN: English, 1-2 sentences on the natural meaning/usage/register
Nuance_CN: Simplified Chinese, 1-2 sentences on the nuance
Example1: a natural, COMPLETE Simplified Chinese sentence
Example1_EN: natural English translation
Example2: a natural, COMPLETE Simplified Chinese sentence
Example2_EN: natural English translation
Example3: a natural, COMPLETE Simplified Chinese sentence
Example3_EN: natural English translation

CRITICAL RULES:
- Generate all fields yourself; the input is ONLY the word + pinyin.
- Example_EN must be real English — never pinyin, never a fragment.
- Every Example sentence must be COMPLETE and grammatical.
- ===word: header matches the input word exactly; blank line after each block."""

FIELD_LABELS = [("Meaning:", "meaning"), ("Nuance_EN:", "nuance_en"),
                ("Nuance_CN:", "nuance_cn"), ("Example1:", "ex1"),
                ("Example1_EN:", "ex1_en"), ("Example2:", "ex2"),
                ("Example2_EN:", "ex2_en"), ("Example3:", "ex3"),
                ("Example3_EN:", "ex3_en")]

PINYIN_RE = re.compile(r"[āáǎàēéěèīíǐìōóǒòūúǔùüǖǘǚǜ]")


def unicase(a, b):
    return (a.lower() > b.lower()) - (a.lower() < b.lower())


def check_anki_closed():
    for proc in ["anki", "anki-qt", "anki-desktop"]:
        r = subprocess.run(["pgrep", "-x", proc], capture_output=True, text=True)
        if r.stdout.strip():
            sys.exit(f"ABORT: Anki ({proc}) is running. Close Anki and re-run.")


def is_affected(f):
    """Return True if the note's fields show a defect we want to regenerate.

    Deliberately over-inclusive (user OK regenerating a few hundred cards):
    we'd rather regenerate a borderline card than leave a broken translation.
    """
    if len(f) < 12:
        return True
    # missing ALL example sentence sets
    if not f[4].strip() and not f[6].strip() and not f[8].strip():
        return True
    for k in (5, 7, 9):
        v = f[k].strip() if k < len(f) else ""
        if not v:                         # missing EN
            return True
        # garbage: digits or tabs (e.g. '2\tsb.')
        if re.search(r"\d|\t", v):
            return True
        TERMINAL = ".!?…\"”“'"
        # short fragment with no terminal punct (fragments: 'uan','nr','u de',
        # 'OK.'/'Go.' end in punct and are real short English)
        if len(v) < 6 and v[-1] not in TERMINAL:
            return True
        # pinyin leak: accented + short (genuine leaks are <40 chars; café/déjà vu
        # only appear inside longer English sentences, which stay clean)
        if PINYIN_RE.search(v) and len(v) < 40:
            return True
        # truncated: long translation cut off with no terminal punctuation
        if len(v) > 12 and v[-1] not in TERMINAL:
            return True
    # Pleco-dump meaning
    m = f[1].strip() if len(f) > 1 else ""
    if ("LITERARY" in m or m[:1].isdigit() or "\t" in m or re.search(r"\d[^ ]", m)):
        return True
    # generic boilerplate nuance (model didn't explain this word)
    ne = (f[10] if len(f) > 10 else "").lower()
    if "commonly used as a " in ne:
        return True
    return False


def parse(content):
    """Parse ===word: {fields}=== blocks -> {word: {key: value}}.

    Tolerant of the model emitting the header EITHER as '===word: 下课==='
    (space after colon) or '===word:下课===' (no space) — a common, intermittent
    model quirk that previously made whole chunks parse as 0 (huge retry cost).
    """
    out = {}
    # locate every block header, tolerant of spacing after the colon
    heads = list(re.finditer(r"===word:\s*(.*?)===\s*\n", content, re.S))
    for i, h in enumerate(heads):
        word = h.group(1).strip()
        if not word:
            continue
        # body runs from just after this header up to the next header (or EOF)
        start = h.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(content)
        body = content[start:end]
        fields = {}
        for line in body.split("\n"):
            s = line.strip()
            for lab, key in FIELD_LABELS:
                if s.startswith(lab):
                    fields[key] = s[len(lab):].strip()
        out[word] = fields
    return out


def call(prompt):
    payload = {"model": MODEL,
               "messages": [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": prompt}],
               "temperature": 0.3, "max_tokens": 128000}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {API_KEY}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]


def main():
    check_anki_closed()

    # 1. detect affected notes (heuristic + red/orange flag)
    conn = sqlite3.connect(str(COLLECTION))
    conn.create_collation("unicase", unicase)
    rows = conn.execute(
        "SELECT n.id, c.flags, n.flds FROM notes n JOIN cards c ON c.nid=n.id "
        "WHERE n.mid=? GROUP BY n.id", (ENHANCED_MID,)).fetchall()
    affected = {}
    for nid, flags, flds in rows:
        f = flds.split(chr(31))
        word = f[0].strip() if f else ""
        pinyin = f[2].strip() if len(f) > 2 else ""
        if is_affected(f) or int(flags or 0) in (1, 2):
            affected[nid] = {"flags": flags, "word": word, "pinyin": pinyin}
    conn.close()
    print(f"Total Chinese Enhanced notes: {len(rows)}")
    print(f"Affected to repair: {len(affected)}")
    if not affected:
        print("Nothing to repair.")
        return

    # 2. backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"collection_pre_chinese_repair_{stamp}.anki2"
    src = sqlite3.connect(f"file:{COLLECTION}?mode=ro", uri=True)
    src.create_collation("unicase", unicase)
    dst = sqlite3.connect(str(backup))
    src.backup(dst); dst.close(); src.close()
    print(f"  Backup: {backup}")

    # 3. write prompt batches (word|pinyin ONLY).
    #    Write into a fresh per-run subdir so NO LLM output is ever lost —
    #    every run's prompts + outputs are preserved forever (useful for
    #    comparing a card across runs to spot consistent problems, or reusing
    #    an old output to recreate a card). We NEVER delete old out files;
    #    the "already done" check below only applies within this run's dir.
    stamp = time.strftime("%Y%m%d_%H%M%S")
    RUN_DIR = OUT_DIR / "runs" / stamp
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    items = list(affected.items())
    n_batches = (len(items) + BATCH - 1) // BATCH
    batch_plan = {}
    for i in range(0, len(items), BATCH):
        b = i // BATCH + 1
        chunk = items[i:i + BATCH]
        lines = [f"{info['word']}|{info['pinyin']}" for _nid, info in chunk]
        batch_plan[b] = [(nid, info["word"], info["pinyin"]) for nid, info in chunk]
        (RUN_DIR / f"prompt_{b:03d}_of_{n_batches:03d}.txt").write_text(
            "\n".join(lines), encoding="utf-8")
    print(f"  Wrote {n_batches} prompt batch(es) -> {RUN_DIR}")
    print(f"  (all runs preserved under {OUT_DIR / 'runs'})")

    # 4. generate + patch in place
    now = int(time.time() * 1000)
    conn = sqlite3.connect(str(COLLECTION))
    conn.create_collation("unicase", unicase)
    conn.execute("BEGIN")
    patched = 0
    review = []
    for b in sorted(batch_plan):
        of = RUN_DIR / f"out_{b:03d}_of_{n_batches:03d}.txt"
        plines = (RUN_DIR / f"prompt_{b:03d}_of_{n_batches:03d}.txt").read_text(
            encoding="utf-8").splitlines()
        want = len(plines)
        if of.exists() and of.read_text(errors="replace").count("===word:") >= want:
            print(f"[{b}] already done", flush=True)
        else:
            print(f"[{b}] {want} words", flush=True)
            entries = {}
            for i in range(0, want, CHUNK):
                chunk = plines[i:i + CHUNK]
                ok = False
                for attempt in range(6):
                    try:
                        t0 = time.time()
                        parsed = parse(call("\n".join(chunk)))
                        filled = sum(1 for l in chunk
                                     if l.split("|")[0].strip() in parsed
                                     and parsed[l.split("|")[0].strip()].get("meaning"))
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
            out_lines = []
            for _nid, w, _p in batch_plan[b]:
                e = entries.get(w, {})
                out_lines.append(f"===word: {w}===")
                for lab, key in FIELD_LABELS:
                    out_lines.append(f"{lab} {e.get(key, '')}")
                out_lines.append("")
            of.write_text("\n".join(out_lines), encoding="utf-8")
            print(f"[{b}] DONE", flush=True)

        # apply this batch's entries
        llm = parse(of.read_text(errors="replace")) if of.exists() else {}
        for nid, w, _p in batch_plan[b]:
            e = llm.get(w)
            if not e or not e.get("meaning"):
                continue
            old = conn.execute("SELECT flds FROM notes WHERE id=?", (nid,)).fetchone()[0].split(chr(31))
            # Build the base 12 CN Enhanced fields then pad to the model's LIVE
            # field count (13, incl. Image) so we never produce a wrong-field-count
            # note that would trip Check Database / risk sync.
            new_fields = [
                old[0], e.get("meaning", ""), old[2], "",
                e.get("ex1", ""), e.get("ex1_en", ""), e.get("ex2", ""), e.get("ex2_en", ""),
                e.get("ex3", ""), e.get("ex3_en", ""), e.get("nuance_en", ""), e.get("nuance_cn", ""),
            ]
            # pad to the model's current field count (currently 13 with Image)
            expected = len(conn.execute("SELECT 1 FROM fields WHERE ntid=?", (ENHANCED_MID,)).fetchall())
            while len(new_fields) < expected:
                new_fields.append("")
            new_flds = chr(31).join(new_fields)
            conn.execute("UPDATE notes SET flds=?, mod=?, usn=-1 WHERE id=?", (new_flds, now, nid))
            conn.execute("UPDATE cards SET mod=?, usn=-1 WHERE nid=?", (now, nid))
            review.append((w, old[1], new_flds.split(chr(31))[1]))
            patched += 1
    conn.execute("UPDATE col SET mod=?", (now,))
    conn.commit(); conn.close()
    print(f"  Patched {patched} notes in place (cards stayed in deck)")

    # 5. review export (into this run's dir)
    rv = RUN_DIR / "review_after.txt"
    with open(rv, "w", encoding="utf-8") as fh:
        fh.write("WORD\tOLD_MEANING\tNEW_MEANING\n")
        for w, oldm, newm in review:
            fh.write(f"{w}\t{oldm}\t{newm}\n")
    print(f"  Review list: {rv}")
    print("\nDone. Open Anki -> Check Database -> sync.")


if __name__ == "__main__":
    main()