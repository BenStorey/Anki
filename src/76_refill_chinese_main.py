#!/usr/bin/env python3
"""
Refill entries missing Meaning across out_cm_*.txt files (offline, no DB).

Only the specific missing entries are regenerated and their blocks replaced
in place. All other content is preserved byte-for-byte.
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
MODEL = "deepseek/deepseek-v4-flash"
URL = "https://openrouter.ai/api/v1/chat/completions"
CHUNK = 10

SYSTEM = """You produce Chinese vocabulary flashcards.
Input lines: word|pinyin|meaning

For EACH input word output exactly:
===word: WORD===
Meaning: clean English gloss (1-5 words)
Nuance_EN: Chinese nuance/usage, 1-2 sentences
Nuance_CN: Chinese nuance, 1-2 sentences in Simplified Chinese
Example1: natural Simplified Chinese sentence
Example1_EN: English translation
Example2: Simplified Chinese sentence
Example2_EN: English translation
Example3: Simplified Chinese sentence
Example3_EN: English translation

RULES: === word matches input exactly; blank line between blocks;
all example sentences in Simplified Chinese; process every input word in order."""

LABELS = [("Meaning:","meaning"),("Nuance_EN:","nuance_en"),("Nuance_CN:","nuance_cn"),
          ("Example1:","ex1"),("Example1_EN:","ex1_en"),("Example2:","ex2"),
          ("Example2_EN:","ex2_en"),("Example3:","ex3"),("Example3_EN:","ex3_en")]

def call_llm(prompt):
    payload = {"model": MODEL,
               "messages": [{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],
               "temperature": 0.3, "max_tokens": 128000}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {API_KEY}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

def parse(content):
    out = {}
    for block in content.split("===word: ")[1:]:
        word = block.split("===")[0].strip()
        rest = block.split("===")[1] if "===" in block else block
        f = {}
        for line in rest.split("\n"):
            s = line.strip()
            for label, key in LABELS:
                if s.startswith(label):
                    f[key] = s[len(label):].strip()
        if word:
            out[word] = f
    return out

def has_meaning(rest):
    return any(l.startswith("Meaning:") and l[9:].strip() for l in rest.split("\n"))

def main():
    # Find all words missing Meaning
    missing = []
    for o in sorted(LLM_DIR.glob("out_cm_*.txt")):
        content = o.read_text(errors="replace")
        for block in content.split("===word: ")[1:]:
            word = block.split("===")[0].strip()
            rest = block.split("===")[1] if "===" in block else block
            if not has_meaning(rest):
                missing.append(word)
    missing = list(dict.fromkeys(missing))  # dedup preserve order
    print(f"Missing Meaning: {len(missing)}")

    # word -> (pinyin, meaning) from prompts
    pin = {}
    for p in LLM_DIR.glob("prompt_cm_*.txt"):
        for line in p.read_text(errors="replace").splitlines():
            if "|" in line:
                parts = line.split("|")
                pin[parts[0].strip()] = (parts[1].strip() if len(parts)>1 else "",
                                         parts[2].strip() if len(parts)>2 else "")

    filled = {}
    for i in range(0, len(missing), CHUNK):
        chunk = missing[i:i+CHUNK]
        lines = [f"{w}|{pin.get(w,('',''))[0]}|{pin.get(w,('',''))[1]}" for w in chunk]
        for attempt in range(5):
            try:
                t0 = time.time()
                parsed = parse(call_llm("\n".join(lines)))
                got = sum(1 for w in chunk if w in parsed and parsed[w].get("meaning"))
                if got >= len(chunk)*0.9:
                    filled.update(parsed)
                    print(f"  ch{i//CHUNK+1}: {got}/{len(chunk)} ({time.time()-t0:.0f}s)", flush=True)
                    break
                print(f"  ch{i//CHUNK+1}: {got}/{len(chunk)} att{attempt+1}", flush=True)
            except Exception as e:
                print(f"  ch{i//CHUNK+1} att{attempt+1}: {type(e).__name__}", flush=True)
            time.sleep(5)

    if not filled:
        print("Nothing filled; aborting"); return

    # Patch each file: replace only the missing blocks
    for o in sorted(LLM_DIR.glob("out_cm_*.txt")):
        content = o.read_text(errors="replace")
        original = content
        result = []
        # text between files is sequence of blocks starting with ===word:
        # split at each '===word: ' occurrence preserving everything
        parts = content.split("===word: ")
        # parts[0] is leading text (empty or whitespace) — keep as-is
        result.append(parts[0])
        for seg in parts[1:]:
            word = seg.split("===")[0].strip()
            if word in filled:
                e = filled[word]
                new_block = (f"===word: {word}===\n"
                             f"Meaning: {e.get('meaning','')}\n"
                             f"Nuance_EN: {e.get('nuance_en','')}\n"
                             f"Nuance_CN: {e.get('nuance_cn','')}\n"
                             f"Example1: {e.get('ex1','')}\n"
                             f"Example1_EN: {e.get('ex1_en','')}\n"
                             f"Example2: {e.get('ex2','')}\n"
                             f"Example2_EN: {e.get('ex2_en','')}\n"
                             f"Example3: {e.get('ex3','')}\n"
                             f"Example3_EN: {e.get('ex3_en','')}\n")
                result.append(new_block)
            else:
                result.append("===word: " + seg)
        o.write_text("".join(result), encoding="utf-8")

    still_missing = 0
    for o in LLM_DIR.glob("out_cm_*.txt"):
        for block in o.read_text(errors="replace").split("===word: ")[1:]:
            rest = block.split("===")[1] if "===" in block else block
            if not has_meaning(rest):
                still_missing += 1
    print(f"Filled {len(filled)}; still missing Meaning: {still_missing}")

if __name__ == "__main__":
    main()