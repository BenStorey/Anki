#!/usr/bin/env python3
"""
Build a 10-card test deck from Evita's vocabulary with LLM-generated examples.

Usage: 
  1. First generate sentences with the subagent
  2. Parse the output into sentences.txt
  3. Run this script to build the .apkg
"""
import json, sys, os, re, genanki
from pathlib import Path
import zipfile, sqlite3, tempfile

OUT = Path.home() / "dev" / "sino-korean" / "output"
DATA = Path.home() / "dev" / "sino-korean" / "data"
OUT.mkdir(parents=True, exist_ok=True)

# ── Card Model ──────────────────────────────────────────────────────────────

MODEL_ID = 1738228000
DECK_ID = 1738228001

MODEL = genanki.Model(
    MODEL_ID,
    "Korean Vocab",
    fields=[
        {"name": "Korean"},
        {"name": "English"},
        {"name": "Hanja"},
        {"name": "Audio"},
        {"name": "Nuance"},
        {"name": "Example1"},
        {"name": "Example1_JA"},
        {"name": "Example1_EN"},
        {"name": "Example2"},
        {"name": "Example2_JA"},
        {"name": "Example2_EN"},
        {"name": "Example3"},
        {"name": "Example3_JA"},
        {"name": "Example3_EN"},
    ],
    templates=[{
        "name": "Korean Vocab Card",
        "qfmt": """<div class="card"><div class="frontbg">{{Korean}}{{Audio}}</div></div>""",
        "afmt": """<div class="card">
<div class="frontbg" style="padding-bottom: 20px;">{{Korean}}{{Audio}}</div>
<div class="backbg">
  {{#Hanja}}<span class="hanja">{{Hanja}}</span><br>{{/Hanja}}
  <span class="en">{{English}}</span>
  {{#Nuance}}<div class="nuance">{{Nuance}}</div>{{/Nuance}}
  {{#Example1}}
  <div class="exgroup">
    <div class="ex">{{Example1}}</div>
    {{#Example1_JA}}<div class="extr-ja">{{Example1_JA}}</div>{{/Example1_JA}}
    {{#Example1_EN}}<div class="extr-en">{{Example1_EN}}</div>{{/Example1_EN}}
  </div>
  {{/Example1}}
  {{#Example2}}
  <div class="exgroup">
    <div class="ex">{{Example2}}</div>
    {{#Example2_JA}}<div class="extr-ja">{{Example2_JA}}</div>{{/Example2_JA}}
    {{#Example2_EN}}<div class="extr-en">{{Example2_EN}}</div>{{/Example2_EN}}
  </div>
  {{/Example2}}
  {{#Example3}}
  <div class="exgroup">
    <div class="ex">{{Example3}}</div>
    {{#Example3_JA}}<div class="extr-ja">{{Example3_JA}}</div>{{/Example3_JA}}
    {{#Example3_EN}}<div class="extr-en">{{Example3_EN}}</div>{{/Example3_EN}}
  </div>
  {{/Example3}}
</div>
</div>""",
    }],
    css="""
.card { font-family: Noto Sans CJK JP Regular; font-size: 50px; text-align: center; color: black; }
.android .card { font-family: Noto Sans CJK JP Regular; font-size: 30px; text-align: center; color: black; }
.frontbg { background-color: #b740c8; color: #fff; padding-top: 20px; padding-bottom: 15px; }
.backbg { position: relative; top: -3px; background-color: #fff; padding: 20px 24px; color: #1a1a1a; font-size: 26px; text-align: left; }
.android .backbg { top: -5px; padding: 15px 16px; font-size: 20px; }
.hanja { font-size: 28px; color: #b740c8; margin-bottom: 4px; display: block; }
.en { font-size: 24px; color: #333; }
.nuance { color: #7b2c87; font-style: italic; font-size: 20px; margin: 12px 0; padding-top: 6px; line-height: 1.4; border-top: 1px solid #e8c8ed; }
.exgroup { margin-top: 12px; padding-top: 8px; border-top: 1px solid #e8c8ed; }
.ex { font-size: 24px; color: #333; line-height: 1.4; }
.extr-ja { font-size: 20px; color: #b740c8; line-height: 1.3; margin-top: 2px; }
.extr-en { font-size: 19px; color: #888; line-height: 1.3; }
.android .ex { font-size: 19px; }
.android .extr-ja { font-size: 16px; }
.android .extr-en { font-size: 15px; }
""",
)


def esc(text):
    s = str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace(";", ",")
    s = re.sub(r',\s*,', ', ', s)
    s = s.strip(' ,\t')
    return s

def parse_sentences(text):
    """Parse the sentence generation output into a dict: word -> [(ko, ja, en), ...]
    Format: blank-line-separated blocks of 3 lines (ko, ja, en) under ===word: X=== headers."""
    result = {}
    current_word = None
    current_examples = []
    buffer = []
    
    for line in text.strip().split('\n'):
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            # Check if buffer has a complete triplet
            if len(buffer) == 3:
                current_examples.append(tuple(buffer))
            buffer = []
            continue
        
        # Word header
        if stripped.startswith('==='):
            # Save previous word's examples
            if current_word is not None:
                if len(buffer) == 3:
                    current_examples.append(tuple(buffer))
                result[current_word] = current_examples
            
            # Start new word
            current_word = stripped.split(':', 1)[1].strip().rstrip('= ')
            buffer = []
            current_examples = []
            continue
        
        # Content line — accumulate
        buffer.append(stripped)
    
    # Last word
    if current_word is not None:
        if len(buffer) == 3:
            current_examples.append(tuple(buffer))
        result[current_word] = current_examples
    
    return result


def main():
    import sys
    # Number of cards to build (default 10)
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    if count > 6500:
        count = 6500
    sentences_file = DATA / "processed" / "sentences_clean.txt"
    if not sentences_file.exists():
        print(f"✗ Sentences file not found: {sentences_file}")
        print("  Run the sentence generation subagent first, then save its output there.")
        return
    
    sents_text = sentences_file.read_text(encoding="utf-8")
    examples = parse_sentences(sents_text)
    print(f"Parsed examples for {len(examples)} words")
    
    # Extract Evita deck words
    apkg_path = Path.home() / "dev" / "sino-korean" / "Korean_Vocabulary_by_Evita.apkg"
    with zipfile.ZipFile(apkg_path) as z:
        blob = z.read("collection.anki2")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.write(blob); tmp.close()
    conn = sqlite3.connect(tmp.name)
    sep = chr(31)
    rows = conn.execute("SELECT flds FROM notes ORDER BY id LIMIT ?", (count,)).fetchall()
    conn.close(); os.unlink(tmp.name)
    
    # Build test deck
    deck = genanki.Deck(DECK_ID, "Korean Vocab (test)")
    
    for (raw,) in rows:
        fs = raw.split(sep)
        korean = fs[0].strip()
        english = fs[1].strip().replace('<div>', ', ').replace('</div>', '')
        hanja = fs[2].strip()
        audio = fs[3].strip()
        
        exs = examples.get(korean, [])
        # Pad to 3
        while len(exs) < 3:
            exs = list(exs) + [("", "", "")]
        
        note = genanki.Note(
            model=MODEL,
            fields=[
                esc(korean), esc(english), esc(hanja), audio,
                "",  # Nuance
                esc(exs[0][0]), esc(exs[0][1]), esc(exs[0][2]),
                esc(exs[1][0]), esc(exs[1][1]), esc(exs[1][2]),
                esc(exs[2][0]), esc(exs[2][1]), esc(exs[2][2]),
            ],
            tags=[]
        )
        deck.add_note(note)
    
    apkg_path = OUT / "korean_vocab_test.apkg"
    genanki.Package(deck).write_to_file(apkg_path)
    print(f"Built {len(rows)} test cards → {apkg_path}")
    print()
    for (raw,) in rows:
        fs = raw.split(sep)
        k = fs[0].strip()
        e = fs[1].strip().replace('<div>', ', ').replace('</div>', '')
        h = fs[2].strip() or "(no hanja)"
        exs = examples.get(k, [])
        ex_count = len(exs)
        print(f"  {k:10s} — {e:30s} [{h}]  examples: {ex_count}")


if __name__ == "__main__":
    main()