#!/usr/bin/env python3
"""Generate JP content for one batch with proper format and Japanese nuance."""
import json, os, sys, time, urllib.request
from pathlib import Path

LLM_DIR = Path.home() / "dev" / "sino-korean" / "data" / "sentences_raw" / "jp_main"
API_KEY = next((l.split("=",1)[1].strip().strip('"').strip("'") for l in open(Path.home()/".hermes"/".env") if l.startswith("OPENROUTER_API_KEY=")), None)
MODEL = "deepseek/deepseek-v4-flash"
URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM = """You are producing Japanese vocabulary flashcards for an N1 learner.

For each word, output EXACTLY this 8-line block with NO extra text:

===word: WORD===
Nuance: [JAPANESE ONLY — explain the nuance meaning, register, typical usage in Japanese]
Example1: [です/ます体 sentence in Japanese]
Example1_EN: [English translation]
Example2: [です/ます体 sentence in Japanese]
Example2_EN: [English translation]
Example3: [です/ます体 sentence in Japanese]
Example3_EN: [English translation]

CRITICAL RULES:
- "===word:" header uses the word ONLY, not the reading or meaning
- "Nuance:" text must be written in JAPANESE (not English)
- "Example1:", "Example1_EN:" etc labels are exact
- Each label on its own line
- Blank line between entries
- Do NOT skip any words — process ALL of them
- Do NOT include full sentences — only process individual vocabulary words"""

def process(batch_num):
    pf = LLM_DIR / f"prompt_{batch_num:05d}_of_00225.txt"
    of = LLM_DIR / f"out_{batch_num:05d}.txt"
    if of.exists() and of.stat().st_size > 5000:
        c = of.read_text(errors="replace")
        if c.count("===word:") > 20 and c.count("Nuance:") > 20:
            print(f"  [{batch_num}] already done ({c.count('===word:')} entries)")
            return
    text = pf.read_text(encoding="utf-8", errors="replace")
    prompt = text  # send the full prompt as-is
    print(f"  [{batch_num}] {len(prompt)//1000}KB...", flush=True)
    start = time.time()
    payload = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], "max_tokens": 128000}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        content = json.loads(resp.read().decode())["choices"][0]["message"]["content"]
    of.write_text(content, encoding="utf-8")
    entries = content.count("===word:")
    ex3 = content.count("Example3_EN:")
    print(f"    {entries} entries, {ex3} Ex3_EN, {of.stat().st_size}b in {time.time()-start:.0f}s", flush=True)

if __name__ == "__main__":
    for b in [69, 77]:
        process(b)