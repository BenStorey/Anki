#!/usr/bin/env python3
"""Generate Chinese Enhanced content for WIP cards.

Reads prompt_cw_NNN.txt (word|pinyin|meaning), calls deepseek flash,
writes out_cw_NNN.txt (===word: format with all fields).
"""
import json, os, sys, time, urllib.request
from pathlib import Path

LLM_DIR = Path.home() / "dev/sino-korean/data/sentences_raw/chinese_wip"
API_KEY = next((l.split("=",1)[1].strip().strip('"').strip("'") for l in open(Path.home()/".hermes"/".env") if l.startswith("OPENROUTER_API_KEY=")), None)
MODEL = "deepseek/deepseek-v4-flash"
URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM = """You produce Chinese vocabulary flashcards for an intermediate learner.

For each line you are given: word|pinyin|current_meaning

Output for EACH word EXACTLY:

===word: WORD===
Meaning: [CLEAN English gloss — 1-5 words, e.g. "Gym" or "To go home"]
Nuance_EN: [English explanation of meaning, usage, register — 1-2 sentences]
Nuance_CN: [Chinese explanation of the nuance — 1-2 sentences in Simplified Chinese]
Example1: [Chinese sentence in Simplified Chinese, です/ます体 equivalent — polite/neutral form]
Example1_EN: [English translation]
Example2: [Chinese sentence]
Example2_EN: [English translation]
Example3: [Chinese sentence]
Example3_EN: [English translation]

CRITICAL RULES:
- "===word: WORD===" header with the word only
- "Meaning:" is a short clean English gloss
- "Nuance_EN:" is English explanation of nuance/usage
- "Nuance_CN:" is Chinese explanation of nuance/usage
- Example sentences are in SIMPLIFIED CHINESE, natural and useful
- Each field on its own line
- Blank line between entries
- Process ALL entries — do not skip any"""

def call_llm(prompt):
    payload = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 128000}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
end = int(sys.argv[2]) if len(sys.argv) > 2 else 6

for batch_num in range(start, end + 1):
    pf = LLM_DIR / f"prompt_cw_{batch_num:03d}_of_006.txt"
    of = LLM_DIR / f"out_cw_{batch_num:03d}_of_006.txt"
    if not pf.exists():
        continue
    if of.exists() and of.stat().st_size > 100 and of.read_text(errors="replace").count("===word:") > 10:
        print(f"[{batch_num}] already done", flush=True)
        continue
    text = pf.read_text(encoding="utf-8", errors="replace")
    n_words = text.count("|")
    print(f"[{batch_num}] {n_words} words ({len(text)//1000}KB)...", flush=True)
    start_time = time.time()
    for attempt in range(3):
        try:
            content = call_llm(text)
            entries = content.count("===word:")
            if entries >= n_words * 0.8:
                of.write_text(content, encoding="utf-8")
                print(f"  {entries} entries in {time.time()-start_time:.0f}s", flush=True)
                break
            else:
                print(f"  attempt {attempt+1}: {entries}/{n_words} entries, retrying...", flush=True)
        except Exception as e:
            print(f"  attempt {attempt+1}: {type(e).__name__}: {str(e)[:100]}", flush=True)
            time.sleep(5)
