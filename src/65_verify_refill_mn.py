#!/usr/bin/env python3
"""Verify all 134 meaning+nuance batches are complete; refill any gaps.

Compares each out_mn_NNN.txt against its prompt_mn_NNN.txt input count.
Any file with <90% coverage gets deleted and regenerated (with retries).
Run this AFTER all parallel generation processes have finished.
"""
import json, os, sys, time, urllib.request
from pathlib import Path

LLM_DIR = Path.home() / "dev" / "sino-korean" / "data" / "sentences_raw" / "jp_main"
API_KEY = next((l.split("=",1)[1].strip().strip('"').strip("'") for l in open(Path.home()/".hermes"/".env") if l.startswith("OPENROUTER_API_KEY=")), None)
MODEL = "deepseek/deepseek-v4-flash"
URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM = """You produce Japanese-English vocabulary flashcards. Each input line is:
word|reading|nuance_jp

For EACH line, output the EXACT format:
1. word|English meaning|English nuance explanation

RULES:
- English meaning: short clean gloss (1-5 words)
- English nuance: 1-2 sentences explaining the nuance in English
- Output EXACTLY one line per input line, same number and order
- Do NOT skip any entries
- Do NOT add any extra text, headers, or blank lines"""

def call_llm(prompt):
    payload = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 128000}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

def batch_done(batch_num):
    pf = LLM_DIR / f"prompt_mn_{batch_num:03d}_of_134.txt"
    of = LLM_DIR / f"out_mn_{batch_num:03d}_of_134.txt"
    if not pf.exists():
        return None
    p_lines = len([l for l in pf.read_text(errors="replace").split('\n') if '|' in l])
    if not of.exists():
        return 0, p_lines, 0
    o_entries = of.read_text(errors="replace").count("===word:")
    return o_entries, p_lines, p_lines - o_entries

def main():
    # First pass: find all incomplete
    incomplete = []
    total_done = 0
    total_prompt = 0
    for i in range(1, 135):
        status = batch_done(i)
        if status is None:
            continue
        done, prompt_n, _ = status
        total_done += done
        total_prompt += prompt_n
        if done < prompt_n * 0.9:
            incomplete.append((i, done, prompt_n))
    
    print(f"Total: {total_done}/{total_prompt} words ({total_done/total_prompt*100:.1f}%)")
    print(f"Incomplete batches: {len(incomplete)}")
    for i, done, prompt_n in incomplete:
        print(f"  Batch {i}: {done}/{prompt_n}")
    
    if not incomplete:
        print("All complete!")
        return
    
    # Delete incomplete files and regenerate
    print("\nRegenerating incomplete batches...")
    for i, done, prompt_n in incomplete:
        of = LLM_DIR / f"out_mn_{i:03d}_of_134.txt"
        if of.exists():
            of.unlink()
            print(f"  Deleted partial {of.name} ({done}/{prompt_n})")
    
    # Now regenerate each
    for i, done, prompt_n in incomplete:
        pf = LLM_DIR / f"prompt_mn_{i:03d}_of_134.txt"
        of = LLM_DIR / f"out_mn_{i:03d}_of_134.txt"
        text = pf.read_text(encoding="utf-8", errors="replace")
        print(f"  [{i}] regenerating {prompt_n} words...", flush=True)
        success = False
        for attempt in range(4):
            try:
                content = call_llm(text)
                valid_lines = [l for l in content.strip().split('\n') if l.count('|') == 2]
                count = len(valid_lines)
                if count >= prompt_n * 0.9:
                    of.write_text(content, encoding="utf-8")
                    print(f"    ok: {count} entries (attempt {attempt+1})", flush=True)
                    success = True
                    break
                else:
                    print(f"    attempt {attempt+1}: only {count}/{prompt_n}, retrying...", flush=True)
            except Exception as e:
                print(f"    attempt {attempt+1} error: {type(e).__name__}: {str(e)[:100]}", flush=True)
                time.sleep(5)
        if not success:
            print(f"    FAILED after 4 attempts — needs manual retry")

if __name__ == "__main__":
    main()