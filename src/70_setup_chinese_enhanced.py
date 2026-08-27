#!/usr/bin/env python3
"""
Phase 1: Create Chinese Enhanced model and migrate Chinese WIP (1,183 cards).

Creates the notetype directly in the Anki collection, then builds the 
LLM prompt for WIP cards. Migration happens after LLM generation completes.
"""

import sqlite3, json, re, time, zlib
from pathlib import Path

COLLECTION = Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
CHINESE_MODEL_ID = 1351220176888  # old "Chinese" model
NEW_MODEL_ID = int(time.time() * 1000)  # unique timestamp-based ID
WIP_DECK_ID = 1754445298156  # Chinese WIP deck
CHINESE_DECK_ID = 1351219999178  # main Chinese deck

def unicase(a, b):
    return (a.lower() > b.lower()) - (a.lower() < b.lower())

# ── Step 1: Build the model config ──
# The config blob uses CocoaPods-style framing. We'll copy the structure
# from Japanese Enhanced and adapt it.

CSS = """.card { font-family: Noto Sans CJK SC Regular; font-size: 50px; text-align: center; color: black; }
.android .card { font-family: Noto Sans CJK SC Regular; font-size: 30px; text-align: center; color: black; }
.frontbg { background-color: #408cc7; color: #fff; min-height: 120px; padding: 25px 0 0 0; box-sizing: border-box; text-align: center; }
.frontbg.back { padding-top: 14px; }
.android .frontbg { min-height: 90px; padding-top: 24px; }
.android .frontbg.back { padding-top: 18px; }
.backbg { background-color: #fff; padding: 20px 24px; color: #1a1a1a; font-size: 26px; text-align: left; }
.android .backbg { padding: 15px 16px; font-size: 20px; }
.en { font-size: 24px; color: #333; display: block; margin: 12px 0 24px 0; }
.nuance-en { color: #2c5f87; font-size: 18px; margin: 12px 0; padding-top: 6px; border-top: 1px solid #c8d8ed; line-height: 1.4; }
.nuance-cn { color: #5a8faf; font-style: italic; font-size: 18px; margin: 4px 0 16px 0; line-height: 1.3; }
.exgroup { margin-top: 14px; padding-top: 8px; border-top: 1px solid #c8d8ed; }
.ex { font-size: 24px; color: #333; line-height: 1.4; }
.extr-en { font-size: 19px; color: #888; line-height: 1.3; margin-top: 4px; }
.android .ex { font-size: 19px; }
.android .extr-en { font-size: 15px; }"""

FIELDS = [
    {"name": "Expression", "ord": 0, "sticky": False, "rtl": False, "font": "Noto Sans CJK SC", "size": 20, "media": []},
    {"name": "Meaning", "ord": 1, "sticky": False, "rtl": False, "font": "Noto Sans CJK SC", "size": 20, "media": []},
    {"name": "Pinyin", "ord": 2, "sticky": False, "rtl": False, "font": "Noto Sans CJK SC", "size": 20, "media": []},
    {"name": "Nuance", "ord": 3, "sticky": False, "rtl": False, "font": "Noto Sans CJK SC", "size": 20, "media": []},
    {"name": "Example1", "ord": 4, "sticky": False, "rtl": False, "font": "Noto Sans CJK SC", "size": 20, "media": []},
    {"name": "Example1_EN", "ord": 5, "sticky": False, "rtl": False, "font": "Noto Sans CJK SC", "size": 20, "media": []},
    {"name": "Example2", "ord": 6, "sticky": False, "rtl": False, "font": "Noto Sans CJK SC", "size": 20, "media": []},
    {"name": "Example2_EN", "ord": 7, "sticky": False, "rtl": False, "font": "Noto Sans CJK SC", "size": 20, "media": []},
    {"name": "Example3", "ord": 8, "sticky": False, "rtl": False, "font": "Noto Sans CJK SC", "size": 20, "media": []},
    {"name": "Example3_EN", "ord": 9, "sticky": False, "rtl": False, "font": "Noto Sans CJK SC", "size": 20, "media": []},
    {"name": "Nuance_EN", "ord": 10, "sticky": False, "rtl": False, "font": "Noto Sans CJK SC", "size": 20, "media": []},
    {"name": "Nuance_CN", "ord": 11, "sticky": False, "rtl": False, "font": "Noto Sans CJK SC", "size": 20, "media": []},
]

TEMPLATES = [{
    "name": "Recognition",
    "ord": 0,
    "qfmt": '<div class="card"><div class="frontbg">{{Expression}}</div></div>',
    "afmt": '<div class="card">\n<div class="frontbg back">{{Expression}}<br><span class="pinyin">{{Pinyin}}</span></div>\n<div class="backbg">\n  <span class="en">{{Meaning}}</span>\n  {{#Nuance_EN}}<div class="nuance-en">{{Nuance_EN}}</div>{{/Nuance_EN}}\n  {{#Nuance_CN}}<div class="nuance-cn">{{Nuance_CN}}</div>{{/Nuance_CN}}\n  {{#Example1}}<div class="exgroup"><div class="ex">{{Example1}}</div>{{#Example1_EN}}<div class="extr-en">{{Example1_EN}}</div>{{/Example1_EN}}</div>{{/Example1}}\n  {{#Example2}}<div class="exgroup"><div class="ex">{{Example2}}</div>{{#Example2_EN}}<div class="extr-en">{{Example2_EN}}</div>{{/Example2_EN}}</div>{{/Example2}}\n  {{#Example3}}<div class="exgroup"><div class="ex">{{Example3}}</div>{{#Example3_EN}}<div class="extr-en">{{Example3_EN}}</div>{{/Example3_EN}}</div>{{/Example3}}\n</div>\n</div>',
    "bafmt": "",
    "bfont": "",
    "bsize": 0,
}]

model_config = {
    "id": NEW_MODEL_ID,
    "name": "Chinese Enhanced",
    "type": "Normal",
    "mod": int(time.time()),
    "usn": -1,
    "sortf": 0,
    "did": None,
    "tmpls": TEMPLATES,
    "flds": FIELDS,
    "css": CSS,
    "latexPre": "\\documentclass[12pt]{article}\n\\special{papersize=3in,5in}\n\\usepackage{amssymb,amsmath}\n\\pagestyle{empty}\n\\setlength{\\parindent}{0in}\n\\begin{document}\n",
    "latexPost": "\\end{document}",
    "latexsvg": False,
    "req": [[0, "all", [0]]],
}

# ── Step 2: Insert into Anki ──
print(f"Connecting to {COLLECTION}...")
conn = sqlite3.connect(str(COLLECTION))
conn.create_collation("unicase", unicase)

# Check if model already exists
cursor = conn.execute('SELECT id, name FROM notetypes')
existing = {name: nid for nid, name in cursor.fetchall()}
if "Chinese Enhanced" in existing:
    print(f"  Chinese Enhanced model already exists (id={existing['Chinese Enhanced']})")
    NEW_MODEL_ID = existing["Chinese Enhanced"]
else:
    # Build the config blob — use same framing as Japanese Enhanced
    config_json = json.dumps(model_config).encode()
    # Add the CocoaPods-style header bytes (same as Japanese Enhanced)
    config_blob = b'\x1a\xab\n\n' + config_json
    
    conn.execute('INSERT INTO notetypes (id, name, mtime_secs, usn, config) VALUES (?, ?, ?, ?, ?)',
                (NEW_MODEL_ID, "Chinese Enhanced", int(time.time()), -1, config_blob))
    print(f"  Created Chinese Enhanced model (id={NEW_MODEL_ID})")

# ── Step 3: Extract WIP notes ──
print("\nExtracting Chinese WIP notes...")
cursor = conn.execute('''
    SELECT n.id, n.flds 
    FROM notes n 
    JOIN cards c ON c.nid = n.id 
    WHERE n.mid = ? AND c.did = ?
    GROUP BY n.id
''', (CHINESE_MODEL_ID, WIP_DECK_ID))

wip_notes = []
for row in cursor.fetchall():
    nid = row[0]
    fields = row[1].split(chr(31))
    if len(fields) >= 3:
        wip_notes.append((nid, fields[0].strip(), fields[1].strip(), fields[2].strip()))

print(f"  Found {len(wip_notes)} WIP notes")

# ── Step 4: Write prompt file ──
out_dir = Path.home() / "dev/sino-korean/data/sentences_raw/chinese_wip"
out_dir.mkdir(parents=True, exist_ok=True)

pf = out_dir / "prompt_chinese_wip.txt"
lines = []
for nid, word, meaning, pinyin in wip_notes:
    # Clean meaning — strip HTML
    clean_meaning = re.sub(r'<[^>]+>', '', meaning).strip()
    clean_meaning = re.sub(r'\s+', ' ', clean_meaning)[:200]
    lines.append(f"{word}|{pinyin}|{clean_meaning}")

pf.write_text('\n'.join(lines), encoding='utf-8')
print(f"  Written {len(lines)} lines to {pf}")

# Count batches
batch_size = 200
num_batches = (len(lines) + batch_size - 1) // batch_size
print(f"  Batches of {batch_size}: {num_batches} total")

# Clean up old batch files
for f in out_dir.glob("prompt_cw_*.txt"):
    f.unlink()

for i in range(0, len(lines), batch_size):
    batch = lines[i:i+batch_size]
    batch_num = i // batch_size + 1
    bf = out_dir / f"prompt_cw_{batch_num:03d}_of_{num_batches:03d}.txt"
    bf.write_text('\n'.join(batch), encoding='utf-8')

print(f"  Written {num_batches} batch prompt files")

# ── Step 5: Output LLM generation script ──
gen_script = f'''#!/usr/bin/env python3
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
    payload = {{"model": MODEL, "messages": [{{"role": "system", "content": SYSTEM}}, {{"role": "user", "content": prompt}}], "temperature": 0.3, "max_tokens": 128000}}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers={{"Authorization": f"Bearer {{API_KEY}}", "Content-Type": "application/json"}})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
end = int(sys.argv[2]) if len(sys.argv) > 2 else {num_batches}

for batch_num in range(start, end + 1):
    pf = LLM_DIR / f"prompt_cw_{{batch_num:03d}}_of_{num_batches:03d}.txt"
    of = LLM_DIR / f"out_cw_{{batch_num:03d}}_of_{num_batches:03d}.txt"
    if not pf.exists():
        continue
    if of.exists() and of.stat().st_size > 100 and of.read_text(errors="replace").count("===word:") > 10:
        print(f"[{{batch_num}}] already done", flush=True)
        continue
    text = pf.read_text(encoding="utf-8", errors="replace")
    n_words = text.count("|")
    print(f"[{{batch_num}}] {{n_words}} words ({{len(text)//1000}}KB)...", flush=True)
    start_time = time.time()
    for attempt in range(3):
        try:
            content = call_llm(text)
            entries = content.count("===word:")
            if entries >= n_words * 0.8:
                of.write_text(content, encoding="utf-8")
                print(f"  {{entries}} entries in {{time.time()-start_time:.0f}}s", flush=True)
                break
            else:
                print(f"  attempt {{attempt+1}}: {{entries}}/{{n_words}} entries, retrying...", flush=True)
        except Exception as e:
            print(f"  attempt {{attempt+1}}: {{type(e).__name__}}: {{str(e)[:100]}}", flush=True)
            time.sleep(5)
'''

gen_path = out_dir / "generate_chinese_wip.py"
gen_path.write_text(gen_script, encoding='utf-8')
print(f"\n  Written generator script: {gen_path}")

conn.close()
print("\nDone! Model created, prompts extracted, generator script ready.")