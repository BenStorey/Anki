#!/usr/bin/env python3
"""Process remaining JP vocab batches 135, 137, 138 via direct API - high token limit."""
import os, sys, json, re, time, urllib.request
from pathlib import Path

LLM_DIR = Path("/home/ben/dev/sino-korean/data/sentences_raw/jp_main")
API_KEY = next((line.split("=",1)[1].strip().strip('"').strip("'") for line in open(Path.home()/".hermes"/".env") if line.startswith("OPENROUTER_API_KEY=")), None)
if not API_KEY: print("FATAL: no API key"); sys.exit(1)

MODEL = "deepseek/deepseek-v4-flash"
URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM = """You are a Japanese language tutor for N1-level learners. Output EXACTLY this format per word:

===word: WORD===
Nuance: Japanese explanation of meaning, usage, register, common contexts.
Example1: Natural Japanese sentence in です/ます体.
Example1_EN: English translation.
Example2: Japanese sentence in です/ます体.
Example2_EN: English translation.
Example3: Japanese sentence in です/ます体.
Example3_EN: English translation.

Rules: Use "===word: WORD===" header. Use "Nuance:" only. Use "Example1:" etc. Skip full sentences. Blank line between entries."""

def call_llm(prompt):
    payload = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 128000}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

for batch_num in [135, 137, 138]:
    pf = LLM_DIR / f"prompt_{batch_num:05d}_of_00225.txt"
    of = LLM_DIR / f"out_{batch_num:05d}.txt"
    if of.exists() and of.stat().st_size > 100:
        print(f"[{batch_num}] already done")
        continue
    text = pf.read_text(encoding="utf-8", errors="replace")
    words = []
    for line in text.strip().split("\n"):
        parts = line.strip().split("|")
        if len(parts) >= 1 and parts[0].strip() and len(parts[0]) < 30 and not parts[0].strip().endswith('。'):
            words.append(f"{parts[0].strip()}|{(parts[1].strip() if len(parts)>1 else '')}|{(parts[2].strip()[:60] if len(parts)>2 else '')}")
    prompt = "\n".join(words)
    print(f"[{batch_num}] {len(words)} words ({len(prompt)//1000}KB)...", flush=True)
    start = time.time()
    try:
        content = call_llm(prompt)
        of.write_text(content, encoding="utf-8")
        entries = content.count("===word:")
        print(f"[{batch_num}] DONE {entries} entries, {of.stat().st_size} bytes in {time.time()-start:.0f}s", flush=True)
    except Exception as e:
        print(f"[{batch_num}] ERROR: {type(e).__name__}: {str(e)[:200]}", flush=True)