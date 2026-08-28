#!/usr/bin/env python3
"""
Direct LLM batch processor for JP vocab — no delegation overhead.
Reads N prompt files, calls OpenRouter for each, writes out files.
Usage: python3 58_direct_batch.py <start> <count> [--model deepseek/deepseek-v4-flash]
"""
import os, sys, json, re, time, urllib.request
from pathlib import Path

LLM_DIR = Path.home() / "dev" / "sino-korean" / "data" / "sentences_raw" / "jp_main"
API_KEY = None
for line in open(Path.home() / ".hermes" / ".env"):
    if line.startswith("OPENROUTER_API_KEY="):
        API_KEY = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
        break
if not API_KEY:
    print("FATAL: no OPENROUTER_API_KEY")
    sys.exit(1)

MODEL = "deepseek/deepseek-v4-flash"
START = int(sys.argv[1]) if len(sys.argv) > 1 else 1
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 5
if "--model" in sys.argv:
    MODEL = sys.argv[sys.argv.index("--model") + 1]

URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are a Japanese language tutor for an N1-level learner. For each word provided, generate study content. Output EXACTLY this format per word, with blank lines between entries:

===word: EXPR===
Nuance: <Japanese nuance paragraph — natural です/ます体, explain usage, register, common contexts>
Example1: <natural Japanese sentence in です/ます体>
Example1_EN: <English translation>
Example2: <natural Japanese sentence in です/ます体>
Example2_EN: <English translation>
Example3: <natural Japanese sentence in です/ます体>
Example3_EN: <English translation>

Rules:
- Skip grammar patterns, full sentences, proverbs and non-vocabulary entries with: ===SKIP: reason===
- Example sentences must be natural, varied, and actually demonstrate the word's usage
- English translations must be accurate and natural"""

def call_llm(prompt_text):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
        ],
        "temperature": 0.7,
        "max_tokens": 64000,
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]

def clean_expr(s):
    s = re.sub(r'<[^>]+>', '', s)
    s = s.replace('&nbsp;', ' ')
    return s.strip()

def parse_prompt(text):
    words = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        parts = line.split('|')
        expr = clean_expr(parts[0] if parts else '')
        if not expr:
            continue
        # Skip obvious full sentences
        if len(expr) > 30:
            continue
        meaning = parts[2].strip() if len(parts) > 2 else ''
        reading = parts[1].strip() if len(parts) > 1 else ''
        # Skip grammar pattern markers
        if 'grammar' in expr.lower() or 'grammar' in meaning.lower():
            continue
        words.append((expr, reading, meaning))
    return words

results = []
for i in range(START, min(START + COUNT, 226)):
    prompt_file = LLM_DIR / f"prompt_{i:05d}_of_00225.txt"
    out_file = LLM_DIR / f"out_{i:05d}.txt"
    if out_file.exists() and out_file.stat().st_size > 100:
        print(f"[{i}] already done ({out_file.stat().st_size} bytes)")
        results.append(('skip', i, 0))
        continue
    if not prompt_file.exists():
        print(f"[{i}] MISSING prompt file, skipping")
        results.append(('missing', i, 0))
        continue
    
    text = prompt_file.read_text(encoding='utf-8', errors='replace')
    words = parse_prompt(text)
    # Build a compact prompt: show the word list
    lines = []
    for w in words:
        lines.append(f"{w[0]}|{w[1]}|{w[2][:60]}")
    prompt = "\n".join(lines)
    print(f"[{i}] dispatching {len(words)} words ({len(prompt)//1000}KB)...", flush=True)
    
    start = time.time()
    try:
        content = call_llm(prompt)
        out_file.write_text(content, encoding='utf-8')
        print(f"[{i}] DONE {out_file.stat().st_size} bytes in {time.time()-start:.0f}s", flush=True)
        results.append(('done', i, len(words)))
    except Exception as e:
        print(f"[{i}] ERROR: {type(e).__name__}: {str(e)[:200]}", flush=True)
        results.append(('error', i, 0))

print(f"\n=== Summary: {sum(1 for r in results if r[0]=='done')} done, {sum(1 for r in results if r[0]=='error')} errors ===")
for r in results:
    print(f"  {r[0]}: batch {r[1]} ({r[2]} words)" if r[0] != 'skip' else f"  {r[0]}: batch {r[1]}")