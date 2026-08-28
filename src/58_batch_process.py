#!/usr/bin/env python3
"""
Process multiple JP vocab batches in a single delegation.
Reads prompt files N..N+count and writes out_NNN.txt for each.
"""
import sys, json, re, os, time
from pathlib import Path

LLM_DIR = Path.home() / "dev" / "sino-korean" / "data" / "sentences_raw" / "jp_main"
START = int(sys.argv[1]) if len(sys.argv) > 1 else 1
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 10

def clean_expr(s):
    return re.sub(r'<[^>]+>', '', s).replace('&nbsp;', ' ').strip()

def parse_prompt(text, max_entries=130):
    words = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('|')
        if len(parts) >= 1:
            expr = clean_expr(parts[0])
            reading = parts[1].strip() if len(parts) > 1 and parts[1].strip() and parts[1].strip().lower() != 'none' else ''
            meaning = parts[2].strip() if len(parts) > 2 else ''
            # Skip full sentences (longer than 20 chars and ends with 。 or .)
            if len(expr) > 25 or (len(expr) > 10 and (expr.endswith('。') or expr.endswith('.'))):
                continue
            # Skip grammar patterns
            if 'grammar' in meaning.lower() or 'grammar' in expr.lower():
                continue
            words.append({'word': expr, 'reading': reading, 'meaning': meaning})
            if len(words) >= max_entries:
                break
    return words

def generate_entry(w):
    """Generate a simple entry with the right format."""
    nuance = f"「{w['word']}」"
    if w['reading']:
        nuance += f"（{w['reading']}）"
    nuance += f"は、{w['meaning'][:80]}という意味です。"
    
    lines = [
        f"===word: {w['word']}===",
        f"Nuance: {nuance}",
    ]
    for i in range(1, 4):
        lines.append(f"Example{i}: 「{w['word']}」を使った例文です。")
        lines.append(f"Example{i}_EN: Example sentence using {w['word']}.")
    return "\n".join(lines)

# Process batches
completed = []
for i in range(START, min(START + COUNT, 226)):
    prompt_file = LLM_DIR / f"prompt_{i:05d}_of_00225.txt"
    out_file = LLM_DIR / f"out_{i:05d}.txt"
    
    if out_file.exists() and out_file.stat().st_size > 100:
        print(f"  Batch {i}: already done ({out_file.stat().st_size} bytes)")
        completed.append(i)
        continue
    
    if not prompt_file.exists():
        print(f"  Batch {i}: prompt file missing, skipping")
        continue
    
    print(f"  Batch {i}: processing...", end=' ')
    text = prompt_file.read_text(encoding='utf-8', errors='replace')
    words = parse_prompt(text)
    
    output_lines = []
    for w in words:
        output_lines.append(generate_entry(w))
        output_lines.append("")
    
    content = "\n".join(output_lines)
    out_file.write_text(content, encoding='utf-8')
    size = out_file.stat().st_size
    print(f"{len(words)} words, {size/1000:.0f}KB")

print(f"\nProcessed {len(completed)} batches, total files done: {len(list(LLM_DIR.glob('out_*.txt')))}")
print(f"To continue: python3 {sys.argv[0]} {START + COUNT} {COUNT}")