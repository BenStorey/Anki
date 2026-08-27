#!/usr/bin/env python3
"""Generate Chinese Enhanced content for WIP cards - simple version.

Reads prompt_cw_NNN.txt, calls API in chunks of 20 words,
writes out_cw_NNN.txt in ===word: format.
"""
import json, sys, time, urllib.request
from pathlib import Path

LLM_DIR = Path.home() / "dev/sino-korean/data/sentences_raw/chinese_wip"
with open(Path.home() / ".hermes" / ".env") as f:
    API_KEY = next((l.split("=",1)[1].strip().strip('"').strip("'") for l in f if l.startswith("OPENROUTER_API_KEY=")), None)
URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-v4-flash"

SYSTEM = """You are a Chinese vocabulary flashcard maker. Each input line is: word|pinyin|meaning

For each word, output exactly:
word|clean_meaning|nuance_en|nuance_cn|ex1|ex1_en|ex2|ex2_en|ex3|ex3_en

Rules:
- Clean meaning: short English gloss (1-5 words)
- nuance_en: 1 sentence in English
- nuance_cn: 1 sentence in Simplified Chinese  
- ex1-3: Chinese sentences in Simplified Chinese, neutral tone
- ex1_en-3_en: English translations
- Output EXACTLY one line per input, same order, with exactly 9 pipe separators per line
- Do NOT add any extra text, headers, or blank lines"""

def call_llm(prompt):
    payload = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 128000}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
end = int(sys.argv[2]) if len(sys.argv) > 2 else 6

for batch_num in range(start, end + 1):
    pf = LLM_DIR / f"prompt_cw_{batch_num:03d}_of_006.txt"
    of = LLM_DIR / f"out_cw_{batch_num:03d}_of_006.txt"
    if not pf.exists():
        continue
    if of.exists() and of.stat().st_size > 1000 and len([l for l in of.read_text(errors="replace").split('\n') if l.count('|') == 9]) > 160:
        print(f"[{batch_num}] already done", flush=True)
        continue
    
    text = pf.read_text(encoding="utf-8", errors="replace")
    lines = [l for l in text.strip().split('\n') if l.strip()]
    total = len(lines)
    print(f"[{batch_num}] {total} words...", flush=True)
    
    all_output = []
    for chunk_start in range(0, total, 20):
        chunk = lines[chunk_start:chunk_start + 20]
        prompt = '\n'.join(chunk)
        n = len(chunk)
        ok = False
        for attempt in range(5):
            try:
                t0 = time.time()
                content = call_llm(prompt)
                valid = [l for l in content.strip().split('\n') if l.count('|') == 9]
                if len(valid) >= n * 0.8:
                    all_output.extend(valid)
                    print(f"  chunk {chunk_start//20+1}: {len(valid)}/{n} in {time.time()-t0:.0f}s", flush=True)
                    ok = True
                    break
                else:
                    print(f"  chunk {chunk_start//20+1}: {len(valid)}/{n} (attempt {attempt+1})", flush=True)
            except Exception as e:
                print(f"  chunk {chunk_start//20+1}: {type(e).__name__} (attempt {attempt+1})", flush=True)
            time.sleep(5)
        if not ok:
            print(f"  FAILED chunk {chunk_start//20+1}", flush=True)
    
    if all_output:
        result = []
        for line in all_output:
            parts = line.split('|', 9)
            result.append(f"===word: {parts[0].strip()}===")
            result.append(f"Meaning: {parts[1].strip() if len(parts)>1 else ''}")
            result.append(f"Nuance_EN: {parts[2].strip() if len(parts)>2 else ''}")
            result.append(f"Nuance_CN: {parts[3].strip() if len(parts)>3 else ''}")
            result.append(f"Example1: {parts[4].strip() if len(parts)>4 else ''}")
            result.append(f"Example1_EN: {parts[5].strip() if len(parts)>5 else ''}")
            result.append(f"Example2: {parts[6].strip() if len(parts)>6 else ''}")
            result.append(f"Example2_EN: {parts[7].strip() if len(parts)>7 else ''}")
            result.append(f"Example3: {parts[8].strip() if len(parts)>8 else ''}")
            result.append(f"Example3_EN: {parts[9].strip() if len(parts)>9 else ''}")
            result.append("")
        of.write_text('\n'.join(result), encoding='utf-8')
        entries = len(result) // 11
        print(f"[{batch_num}] {entries}/{total} entries done", flush=True)