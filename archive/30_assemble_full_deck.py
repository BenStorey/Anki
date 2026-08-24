#!/usr/bin/env python3
"""
Assemble the complete 6,500-card deck from all batch sentence files.

1. Load all batch sentence files from data/sentences_raw/batches_output/
2. Merge with the first 110 sentences
3. Build the full .apkg

Usage: python3 src/30_assemble_full_deck.py
"""
import json, sys, os, re, genanki, zipfile, sqlite3, tempfile
from pathlib import Path

OUT = Path.home() / "dev" / "sino-korean" / "output"
DATA = Path.home() / "dev" / "sino-korean" / "data"
OUT.mkdir(parents=True, exist_ok=True)

# ── Card Model (same as 20_build_test_deck.py) ─────────────────────────────

MODEL_ID = 1738228000
DECK_ID = 1738228001

MODEL = genanki.Model(
    MODEL_ID,
    "Korean Vocab",
    fields=[
        {"name": "Korean"}, {"name": "English"}, {"name": "Hanja"},
        {"name": "Audio"}, {"name": "Nuance"},
        {"name": "Example1"}, {"name": "Example1_JA"}, {"name": "Example1_EN"},
        {"name": "Example2"}, {"name": "Example2_JA"}, {"name": "Example2_EN"},
        {"name": "Example3"}, {"name": "Example3_JA"}, {"name": "Example3_EN"},
    ],
    templates=[{
        "name": "Korean Vocab Card",
        "qfmt": '<div class="card"><div class="frontbg">{{Korean}}{{Audio}}</div></div>',
        "afmt": """<div class="card">
<div class="frontbg" style="padding-bottom: 20px;">{{Korean}}{{Audio}}</div>
<div class="backbg">
  {{#Hanja}}<span class="hanja">{{Hanja}}</span><br>{{/Hanja}}
  <span class="en">{{English}}</span>
  {{#Nuance}}<div class="nuance">{{Nuance}}</div>{{/Nuance}}
  {{#Example1}}<div class="exgroup"><div class="ex">{{Example1}}</div>{{#Example1_JA}}<div class="extr-ja">{{Example1_JA}}</div>{{/Example1_JA}}{{#Example1_EN}}<div class="extr-en">{{Example1_EN}}</div>{{/Example1_EN}}</div>{{/Example1}}
  {{#Example2}}<div class="exgroup"><div class="ex">{{Example2}}</div>{{#Example2_JA}}<div class="extr-ja">{{Example2_JA}}</div>{{/Example2_JA}}{{#Example2_EN}}<div class="extr-en">{{Example2_EN}}</div>{{/Example2_EN}}</div>{{/Example2}}
  {{#Example3}}<div class="exgroup"><div class="ex">{{Example3}}</div>{{#Example3_JA}}<div class="extr-ja">{{Example3_JA}}</div>{{/Example3_JA}}{{#Example3_EN}}<div class="extr-en">{{Example3_EN}}</div>{{/Example3_EN}}</div>{{/Example3}}
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
    return str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")


def parse_sentences(text):
    """Parse sentence output format: ===word: X=== blocks with blank-line-separated triplets."""
    result = {}
    current_word = None
    current_examples = []
    buffer = []

    for line in text.strip().split('\n'):
        stripped = line.strip()
        if not stripped:
            if len(buffer) == 3:
                current_examples.append(tuple(buffer))
            buffer = []
            continue
        if stripped.startswith('==='):
            if current_word is not None:
                if len(buffer) == 3:
                    current_examples.append(tuple(buffer))
                result[current_word] = current_examples
            current_word = stripped.split(':', 1)[1].strip().rstrip('= ')
            buffer = []
            current_examples = []
            continue
        buffer.append(stripped)

    if current_word is not None:
        if len(buffer) == 3:
            current_examples.append(tuple(buffer))
        result[current_word] = current_examples

    return result


def main():
    # Load all batch sentence files
    batch_dir = Path.home() / "dev" / "sino-korean" / "data" / "sentences_raw"
    all_sentences = {}
    
    # First: the original batch 1 (110 words)
    batch1_file = batch_dir / "batch_001_110.txt"
    if batch1_file.exists():
        result = parse_sentences(batch1_file.read_text(encoding="utf-8"))
        all_sentences.update(result)
        print(f"  Batch 1 (first 110): {len(result)} words")
    
    # Then: batch output files from subagent runs
    batch_out_dir = batch_dir / "batches_output"
    if batch_out_dir.exists():
        files = sorted(batch_out_dir.glob("*.txt"))
        for f in files:
            result = parse_sentences(f.read_text(encoding="utf-8"))
            all_sentences.update(result)
            print(f"  {f.name}: {len(result)} words")
    
    print(f"  Total words with sentences: {len(all_sentences)}")
    
    # Load Evita deck
    apkg_path = Path.home() / "dev" / "sino-korean" / "Korean_Vocabulary_by_Evita.apkg"
    with zipfile.ZipFile(apkg_path) as z:
        blob = z.read("collection.anki2")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.write(blob); tmp.close()
    conn = sqlite3.connect(tmp.name)
    sep = chr(31)
    rows = conn.execute("SELECT flds FROM notes ORDER BY id").fetchall()
    conn.close(); os.unlink(tmp.name)
    
    # Build deck
    deck = genanki.Deck(DECK_ID, "Korean Vocab")
    built = 0
    missing = 0
    media_files = []
    
    # Copy the audio files from the original Evita deck
    with zipfile.ZipFile(apkg_path) as src:
        media_index = json.loads(src.read("media"))
        media_map = {v: k for k, v in media_index.items()}  # filename -> index
    
    for (raw,) in rows:
        fs = raw.split(sep)
        korean = fs[0].strip()
        english = fs[1].strip().replace('<div>', ', ').replace('</div>', '')
        hanja = fs[2].strip()
        audio = fs[3].strip()
        
        exs = all_sentences.get(korean, [])
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
        built += 1
        if not all_sentences.get(korean):
            missing += 1
    
    pkg = genanki.Package(deck)
    
    # Copy media from Evita deck
    with zipfile.ZipFile(apkg_path) as src:
        media_index = json.loads(src.read("media"))
        for fname, idx in media_index.items():
            if fname.endswith('.mp3'):
                pkg.media_files.append(Path.home() / "dev" / "sino-korean" / "data" / "raw" / f"evita_media_{fname}")
    
    # Actually, genanki's media handling expects files on disk. Let's extract them
    media_dir = Path.home() / "dev" / "sino-korean" / "data" / "media"
    media_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(apkg_path) as src:
        for fname in src.namelist():
            if fname in ("collection.anki2", "media"):
                continue
            (media_dir / fname).parent.mkdir(parents=True, exist_ok=True)
            (media_dir / fname).write_bytes(src.read(fname))
    
    for fname in src.namelist():
        if fname in ("collection.anki2", "media"):
            continue
        pkg.media_files.append(str(media_dir / fname))
    
    out_path = OUT / "korean_vocab.apkg"
    pkg.write_to_file(out_path)
    
    print(f"\nBuilt {built} cards → {out_path}")
    print(f"  Cards with examples: {built - missing}")
    print(f"  Cards without examples: {missing}")
    print(f"  Size: {out_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()