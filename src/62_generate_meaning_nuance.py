#!/usr/bin/env python3
"""Generate clean English meaning + Nuance_EN for all Japanese Enhanced notes.

Reads prompt_mn_*.txt files (word|reading|nuance_jp), calls deepseek flash,
writes out_mn_*.txt files with format:
  ===word: WORD===
  Meaning: <clean English gloss>
  Nuance_EN: <English nuance explanation>
"""
import json, os, sys, time, urllib.request
from pathlib import Path

LLM_DIR = Path.home() / "dev" / "sino-korean" / "data" / "sentences_raw" / "jp_main"
API_KEY = next((l.split("=",1)[1].strip().strip('"').strip("'") for l in open(Path.home()/".hermes"/".env") if l.startswith("OPENROUTER_API_KEY=")), None)
MODEL = "deepseek/deepseek-v4-flash"
URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM = """You are producing Japanese vocabulary flashcards for an N1 learner.

For each word you are given: word|reading|nuance_jp (Japanese nuance explanation).

Output for EACH word EXACTLY:

===word: WORD===
Meaning: [CLEAN English gloss/translation of the word, 1-2 words]
Nuance_EN: [English translation/explanation of the Japanese nuance. 1-2 sentences explaining the nuance, usage, and register in English.]

CRITICAL RULES:
- "===word: WORD===" header with the word only
- "Meaning:" is a short, clean English gloss (like "Active Volcano" or "Energy / Vigour")
- "Nuance_EN:" is an English explanation of the nuance — NOT a translation of the word, but an explanation of when/how it's used
- Each field on its own line
- Blank line between entries
- Process ALL entries — do not skip any
- Keep nuance_EN concise but informative (1-2 sentences)"""

def call_llm(prompt):
    payload = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 64000}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

start_batch = int(sys.argv[1]) if len(sys.argv) > 1 else 1
end_batch = int(sys.argv[2]) if len(sys.argv) > 2 else 134

for batch_num in range(start_batch, end_batch + 1):
    pf = LLM_DIR / f"prompt_mn_{batch_num:03d}_of_134.txt"
    of = LLM_DIR / f"out_mn_{batch_num:03d}_of_134.txt"
    
    if not pf.exists():
        print(f"[{batch_num}] prompt file missing, skipping")
        continue
    if of.exists() and of.stat().st_size > 100:
        # Check if already has correct content
        existing = of.read_text(errors="replace")
        if existing.count("===word:") > 10 and existing.count("Meaning:") > 10:
            print(f"[{batch_num}] already done ({existing.count('===word:')} entries)")
            continue
    
    text = pf.read_text(encoding="utf-8", errors="replace")
    print(f"[{batch_num}] {text.count('|')} words ({len(text)//1000}KB)...", flush=True)
    start = time.time()
    try:
        content = call_llm(text)
        of.write_text(content, encoding="utf-8")
        entries = content.count("===word:")
        meanings = content.count("Meaning:")
        print(f"  {entries} entries, {meanings} meanings, {of.stat().st_size}b in {time.time()-start:.0f}s", flush=True)
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {str(e)[:200]}", flush=True)