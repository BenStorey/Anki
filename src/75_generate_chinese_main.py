#!/usr/bin/env python3
"""
Generate Chinese Enhanced fields for the main Chinese deck (offline).

Reads prompt_cm_###_of_076.txt, calls deepseek flash in small chunks, and
writes out_cm_###_of_076.txt in the ===word: === format. Only touches disk,
never the Anki collection — fields stay offline until migration.

Parallel usage:
  python3 75_generate_chinese_main.py 1 19      # worker A
  python3 75_generate_chinese_main.py 20 38     # worker B
  python3 75_generate_chinese_main.py 39 57     # worker C
  python3 75_generate_chinese_main.py 58 76     # worker D
Run without args to do all.
"""
import json, sys, time, urllib.request
from pathlib import Path

LLM_DIR = Path.home() / "dev/sino-korean/data/sentences_raw/chinese_main"
API_KEY = next(
    (l.split("=", 1)[1].strip().strip('"').strip("'")
     for l in open(Path.home() / ".hermes" / ".env")
     if l.startswith("OPENROUTER_API_KEY=")),
    None,
)
assert API_KEY, "OPENROUTER_API_KEY missing"
MODEL = "deepseek/deepseek-v4-flash"
URL = "https://openrouter.ai/api/v1/chat/completions"
CHUNK = 20

LABEL_KEYS = [
    ("Meaning:", "meaning"), ("Nuance_EN:", "nuance_en"), ("Nuance_CN:", "nuance_cn"),
    ("Example1:", "ex1"), ("Example1_EN:", "ex1_en"), ("Example2:", "ex2"),
    ("Example2_EN:", "ex2_en"), ("Example3:", "ex3"), ("Example3_EN:", "ex3_en"),
]

SYSTEM = """You produce Chinese vocabulary flashcards for an intermediate learner.

Input lines have the form: word|pinyin|reading_meaning

For EACH input word output EXACTLY this block:

===word: WORD===
Meaning: 1-5 word clean English gloss
Nuance_EN: English, 1-2 sentences on meaning/usage/register
Nuance_CN: Simplified Chinese, 1-2 sentences on the nuance
Example1: natural Simplified Chinese sentence, neutral register
Example1_EN: English translation of Example1
Example2: natural Simplified Chinese sentence
Example2_EN: English translation of Example2
Example3: natural Simplified Chinese sentence
Example3_EN: English translation of Example3

RULES:
- The ===word: WORD=== header must match the input word exactly
- Blank line after each block
- All example sentences in SIMPLIFIED CHINESE
- Process every input word in order; never skip any."""


def call_llm(prompt):
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 128000,
    }
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
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
            for label, key in LABEL_KEYS:
                if s.startswith(label):
                    fields[key] = s[len(label):].strip()
        if word:
            out[word] = fields
    return out


def render(words, entries):
    out = []
    for line in words:
        word = line.split("|")[0].strip()
        e = entries.get(word, {})
        out.append(f"===word: {word}===")
        out.append(f"Meaning: {e.get('meaning', '')}")
        out.append(f"Nuance_EN: {e.get('nuance_en', '')}")
        out.append(f"Nuance_CN: {e.get('nuance_cn', '')}")
        out.append(f"Example1: {e.get('ex1', '')}")
        out.append(f"Example1_EN: {e.get('ex1_en', '')}")
        out.append(f"Example2: {e.get('ex2', '')}")
        out.append(f"Example2_EN: {e.get('ex2_en', '')}")
        out.append(f"Example3: {e.get('ex3', '')}")
        out.append(f"Example3_EN: {e.get('ex3_en', '')}")
        out.append("")
    return "\n".join(out)


def generate_batch(idx, total):
    pf = LLM_DIR / f"prompt_cm_{idx:03d}_of_{total:03d}.txt"
    of = LLM_DIR / f"out_cm_{idx:03d}_of_{total:03d}.txt"
    if not pf.exists():
        print(f"[{idx}] missing", flush=True)
        return
    words = [l for l in pf.read_text(encoding="utf-8").splitlines() if "|" in l]
    want = len(words)
    if of.exists() and of.read_text(errors="replace").count("===word:") >= want:
        print(f"[{idx}] done", flush=True)
        return

    print(f"[{idx}] {want} words", flush=True)
    entries = {}
    for i in range(0, want, CHUNK):
        chunk = words[i:i + CHUNK]
        ok = False
        for attempt in range(6):
            try:
                t0 = time.time()
                content = call_llm("\n".join(chunk))
                parsed = parse_blocks(content)
                filled = sum(
                    1 for l in chunk if l.split("|")[0].strip() in parsed
                    and parsed[l.split("|")[0].strip()].get("meaning")
                )
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
    filled = sum(1 for l in words if l.split("|")[0].strip() in entries
                 and entries[l.split("|")[0].strip()].get("meaning"))
    print(f"[{idx}] DONE {filled}/{want} -> {of.name}", flush=True)


def main():
    total = 76
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end = int(sys.argv[2]) if len(sys.argv) > 2 else total
    for b in range(start, end + 1):
        generate_batch(b, total)


if __name__ == "__main__":
    main()