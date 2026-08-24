#!/usr/bin/env python3
"""Build final 6,500-card Korean Vocab deck from Evita + batch sentence files."""
import json, zipfile, sqlite3, tempfile, os, re, genanki
from pathlib import Path

ROOT = Path.home() / "dev" / "sino-korean"
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)

MODEL_ID, DECK_ID = 1738228000, 1738228001

MODEL = genanki.Model(MODEL_ID, "Korean Vocab", fields=[
    {"name": n} for n in ["Korean","English","Hanja","Audio","Nuance",
        "Example1","Example1_JA","Example1_EN",
        "Example2","Example2_JA","Example2_EN",
        "Example3","Example3_JA","Example3_EN"]],
    templates=[{
        "name": "Korean Vocab Card",
        "qfmt": '<div class="card"><div class="frontbg">{{Korean}}{{Audio}}</div></div>',
        "afmt": """<div class="card"><div class="frontbg" style="padding-bottom: 20px;">{{Korean}}{{Audio}}</div>
<div class="backbg">
  {{#Hanja}}<span class="hanja">{{Hanja}}</span><br>{{/Hanja}}
  <span class="en">{{English}}</span>
  {{#Nuance}}<div class="nuance">{{Nuance}}</div>{{/Nuance}}
  {{#Example1}}<div class="exgroup"><div class="ex">{{Example1}}</div>{{#Example1_JA}}<div class="extr-ja">{{Example1_JA}}</div>{{/Example1_JA}}{{#Example1_EN}}<div class="extr-en">{{Example1_EN}}</div>{{/Example1_EN}}</div>{{/Example1}}
  {{#Example2}}<div class="exgroup"><div class="ex">{{Example2}}</div>{{#Example2_JA}}<div class="extr-ja">{{Example2_JA}}</div>{{/Example2_JA}}{{#Example2_EN}}<div class="extr-en">{{Example2_EN}}</div>{{/Example2_EN}}</div>{{/Example2}}
  {{#Example3}}<div class="exgroup"><div class="ex">{{Example3}}</div>{{#Example3_JA}}<div class="extr-ja">{{Example3_JA}}</div>{{/Example3_JA}}{{#Example3_EN}}<div class="extr-en">{{Example3_EN}}</div>{{/Example3_EN}}</div>{{/Example3}}
</div>
</div>""",
    }], css="""
.card { font-family: Noto Sans CJK JP Regular; font-size: 50px; text-align: center; color: black; }
.android .card { font-family: Noto Sans CJK JP Regular; font-size: 30px; text-align: center; color: black; }
.frontbg { background-color: #b740c8; color: #fff; padding-top: 20px; padding-bottom: 15px; }
.backbg { background-color: #fff; padding: 20px 24px; color: #1a1a1a; font-size: 26px; text-align: left; }
.android .backbg { padding: 15px 16px; font-size: 20px; }
.hanja { font-size: 28px; color: #b740c8; margin-bottom: 4px; display: block; }
.en { font-size: 24px; color: #333; }
.nuance { color: #7b2c87; font-style: italic; font-size: 20px; margin: 12px 0; padding-top: 6px; border-top: 1px solid #e8c8ed; }
.exgroup { margin-top: 10px; padding-top: 6px; border-top: 1px solid #e8c8ed; }
.ex { font-size: 24px; color: #333; line-height: 1.4; }
.extr-ja { font-size: 20px; color: #b740c8; line-height: 1.3; margin-top: 2px; }
.extr-en { font-size: 19px; color: #888; line-height: 1.3; }
.android .ex { font-size: 19px; }
.android .extr-ja { font-size: 16px; }
.android .extr-en { font-size: 15px; }
""")

def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def parse_sentences(text):
    result, cur, exs, buf = {}, None, [], []
    for line in text.strip().split('\n'):
        s = line.strip()
        if not s:
            if len(buf) == 3: exs.append(tuple(buf))
            buf = []
            continue
        if s.startswith('==='):
            if cur is not None:
                if len(buf) == 3: exs.append(tuple(buf))
                result[cur] = exs
            m = re.match(r'===word:\s*(.+?)===', s)
            cur = m.group(1).strip() if m else s.replace('===','').strip()
            buf, exs = [], []
            continue
        if s.startswith('## '):
            if cur is not None:
                if len(buf) == 3: exs.append(tuple(buf))
                result[cur] = exs
            cur = s.split('(')[0].replace('##','').strip()
            buf, exs = [], []
            continue
        buf.append(s)
    if cur is not None:
        if len(buf) == 3: exs.append(tuple(buf))
        result[cur] = exs
    return result

# ── Load sentences ──────────────────────────────────────────────────────────
all_sents = {}
batch_dir = ROOT / "data" / "sentences_raw" / "batches_output"
skip = {"batch_009_done.txt", "batch_010_done.txt"}
for f in sorted(batch_dir.glob("batch_*.txt")):
    if f.name in skip: continue
    all_sents.update(parse_sentences(f.read_text(encoding="utf-8")))
clean = ROOT / "data" / "processed" / "sentences_clean.txt"
if clean.exists():
    all_sents.update(parse_sentences(clean.read_text(encoding="utf-8")))
print(f"Parsed examples for {len(all_sents)} unique words")

# ── Load Evita data + media ────────────────────────────────────────────────
apkg_src = ROOT / "Korean_Vocabulary_by_Evita.apkg"
with zipfile.ZipFile(apkg_src) as z:
    blob = z.read("collection.anki2")
    media_index = json.loads(z.read("media"))

tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
tmp.write(blob); tmp.close()
conn = sqlite3.connect(tmp.name)
sep = chr(31)
rows = conn.execute("SELECT flds FROM notes ORDER BY id").fetchall()
conn.close(); os.unlink(tmp.name)

# Extract media to temp filenames that match the Evita filenames
media_dir = ROOT / "data" / "media"
media_dir.mkdir(exist_ok=True)
media_files = {}
with zipfile.ZipFile(apkg_src) as z:
    for idx_str, fname in media_index.items():
        # The media_index maps "0" -> "yes.mp3", etc.
        data_path = media_dir / fname
        data_path.parent.mkdir(parents=True, exist_ok=True)
        if not data_path.exists():  # avoid re-extract
            with z.open(idx_str) as src, open(data_path, 'wb') as dst:
                dst.write(src.read())
        media_files[fname] = data_path

print(f"Extracted {len(media_files)} media files")

# ── Build deck ──────────────────────────────────────────────────────────────
deck = genanki.Deck(DECK_ID, "Korean Vocab")
built = with_ex = 0

for (raw,) in rows:
    fs = raw.split(sep)
    korean = fs[0].strip()
    english = fs[1].strip().replace('<div>', ', ').replace('</div>', '')
    hanja = fs[2].strip()
    audio_ref = fs[3].strip()
    
    exs = all_sents.get(korean, [])
    while len(exs) < 3:
        exs = list(exs) + [("", "", "")]
    if exs and exs[0][0]:
        with_ex += 1
    
    note = genanki.Note(model=MODEL, fields=[
        esc(korean), esc(english), esc(hanja), audio_ref, "",
        esc(exs[0][0]), esc(exs[0][1]), esc(exs[0][2]),
        esc(exs[1][0]), esc(exs[1][1]), esc(exs[1][2]),
        esc(exs[2][0]), esc(exs[2][1]), esc(exs[2][2]),
    ], tags=[])
    deck.add_note(note)
    built += 1

pkg = genanki.Package(deck)
for fpath in media_files.values():
    pkg.media_files.append(str(fpath))

out = OUT / "korean_vocab.apkg"
pkg.write_to_file(out)
sz = out.stat().st_size

print(f"Built {built} cards → {out}")
print(f"  With examples: {with_ex}/{built} ({with_ex/built*100:.1f}%)")
print(f"  Media files attached: {len(media_files)}")
print(f"  Size: {sz:,} bytes ({sz/1e6:.1f} MB)")