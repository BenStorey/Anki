#!/usr/bin/env python3
"""Process JP vocab batch via direct API with proper chunking."""
import json, time, urllib.request, sys
from pathlib import Path

LLM_DIR = Path("/home/ben/dev/sino-korean/data/sentences_raw/jp_main")
API_KEY = next((l.split("=",1)[1].strip().strip('"').strip("'") for l in open(Path.home()/".hermes"/".env") if l.startswith("OPENROUTER_API_KEY=")), None)
MODEL = "deepseek/deepseek-v4-flash"
URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM = """You are a Japanese language tutor for N1-level learners. Output EXACT format:

===word: WORD===
Nuance: Japanese explanation of meaning, usage, register.
Example1: Natural Japanese sentence in です/ます体.
Example1_EN: English translation.
Example2: Japanese sentence in です/ます体.
Example2_EN: English translation.
Example3: Japanese sentence in です/ます体.
Example3_EN: English translation.

Rules: ===word: WORD=== header. Nuance: only. Example1: etc. Blank line between entries. Skip full sentences."""

def call_llm(prompt):
    payload = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 128000}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

batch_num = int(sys.argv[1])
pf = LLM_DIR / f"prompt_{batch_num:05d}_of_00225.txt"
of = LLM_DIR / f"out_{batch_num:05d}.txt"
text = pf.read_text(encoding="utf-8", errors="replace")

words = []
for line in text.strip().split("\n"):
    parts = line.strip().split("|")
    if len(parts) >= 1 and parts[0].strip() and len(parts[0]) < 30 and not parts[0].strip().endswith('。'):
        words.append(f"{parts[0].strip()}|{(parts[1].strip() if len(parts)>1 else '')}|{(parts[2].strip()[:60] if len(parts)>2 else '')}")

# Process in chunks of 60 if > 60 words
chunk_size = 60
all_content = ""
for i in range(0, len(words), chunk_size):
    chunk = words[i:i+chunk_size]
    prompt = "\n".join(chunk)
    print(f"[{batch_num}] chunk {i//chunk_size+1}/{(len(words)+chunk_size-1)//chunk_size}: {len(chunk)} words", flush=True)
    start = time.time()
    content = call_llm(prompt)
    entries = content.count("===word:")
    all_content += content
    if i + chunk_size < len(words):
        all_content += "\n\n"
    print(f"  {entries} entries, {len(content)} bytes in {time.time()-start:.0f}s", flush=True)

of.write_text(all_content, encoding="utf-8")
total = all_content.count("===word:")
print(f"[{batch_num}] TOTAL: {total} entries, {of.stat().st_size} bytes", flush=True)