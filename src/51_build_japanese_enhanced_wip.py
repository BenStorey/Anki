#!/usr/bin/env python3
"""
Build Japanese Enhanced deck for WIP notes, preserving scheduling.

Usage: python3 src/51_build_japanese_enhanced_wip.py

Reads:
  - data/japanese_wip_words.json (5 words with scheduling data)
  - data/sentences_raw/jp_batches/out_wip.txt (LLM sentence outputs)

Workflow:
  1. Build deck with genanki (all new cards)
  2. Open the .apkg SQLite directly
  3. Inject old scheduling (ivl, reps, lapses, queue, type, due, factor)
  4. Save

Outputs:
  - output/japanese_enhanced_wip.apkg (5 notes, 5 cards, scheduling preserved)
"""
import json, re, genanki, zipfile, sqlite3, tempfile, os, shutil
from pathlib import Path
from fugashi import Tagger
from textwrap import dedent

ROOT = Path.home() / "dev" / "sino-korean"
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)

# Reuse the same tagger, overrides, and helpers from Phase 1
tagger = Tagger()

KANA_OVERRIDES = {
    "月": "ガツ", "土": "ド", "的": "テキ",
    "一人": "ヒトリ", "１人": "ヒトリ",
    "二人": "フタリ", "２人": "フタリ",
    "他": "ホカ",
}
EXPR_OVERRIDES = {}

def kata_to_hira(s):
    result = []
    vowel_map = {'あ':'あ','か':'あ','さ':'あ','た':'あ','な':'あ','は':'あ','ま':'あ','や':'あ','ら':'あ','わ':'あ',
                 'い':'い','き':'い','し':'い','ち':'い','に':'い','ひ':'い','み':'い','り':'い',
                 'う':'う','く':'う','す':'う','つ':'う','ぬ':'う','ふ':'う','む':'う','ゆ':'う','る':'う',
                 'え':'え','け':'え','せ':'え','て':'え','ね':'え','へ':'え','め':'え','れ':'え',
                 'お':'お','こ':'お','そ':'お','と':'お','の':'お','ほ':'お','も':'お','よ':'お','ろ':'お'}
    for i, c in enumerate(s):
        if 'ァ' <= c <= 'ヶ':
            result.append(chr(ord(c) - 0x60))
        elif c == chr(0x30FC) and i > 0:
            result.append(vowel_map.get(result[-1] if result else '', 'う'))
        else:
            result.append(c)
    return ''.join(result)

def is_kanji(c):
    return '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf'
def is_kana(c):
    return 'ぁ' <= c <= 'ゟ' or 'ァ' <= c <= 'ヿ'

def token_furigana_clean(surface, reading):
    if not any(is_kanji(c) for c in surface) or not reading:
        return surface
    ri, rlen = 0, len(reading)
    result = []
    after_kana_segment = False
    i = 0
    while i < len(surface):
        ch = surface[i]
        if is_kanji(ch):
            if after_kana_segment:
                result.append(' ')
                after_kana_segment = False
            kanji_buf = [ch]
            j = i + 1
            while j < len(surface) and is_kanji(surface[j]):
                kanji_buf.append(surface[j])
                j += 1
            kanji_str = ''.join(kanji_buf)
            next_kana = ''
            for k in range(j, len(surface)):
                if is_kana(surface[k]):
                    next_kana = surface[k]
                    break
            kana_buf = []
            while ri < rlen:
                if next_kana and reading[ri] == next_kana:
                    break
                kana_buf.append(reading[ri])
                ri += 1
            if kana_buf:
                result.append(f"{kanji_str}[{''.join(kana_buf)}]")
            else:
                result.append(kanji_str)
            after_kana_segment = False
            i = j
        elif is_kana(ch):
            kana_start = i
            while i < len(surface) and is_kana(surface[i]):
                i += 1
            kana_seg = surface[kana_start:i]
            has_kanji_after = any(is_kanji(c) for c in surface[i:])
            result.append(kana_seg)
            for kch in kana_seg:
                if ri < rlen and reading[ri] == kch:
                    ri += 1
            after_kana_segment = bool(has_kanji_after)
        else:
            result.append(ch)
            if ri < rlen and reading[ri] == ch:
                ri += 1
            i += 1
            after_kana_segment = False
    if ri < rlen:
        result.append(''.join(reading[ri:]))
    return ''.join(result)

def make_furigana(expr):
    if expr in EXPR_OVERRIDES:
        return EXPR_OVERRIDES[expr]
    parts = []
    for word in tagger(expr):
        surface = word.surface
        if surface in KANA_OVERRIDES:
            kana = KANA_OVERRIDES[surface]
            reading = kata_to_hira(kana)
        else:
            kana = word.feature.kana
            reading = kata_to_hira(kana) if kana else ''
        furi = token_furigana_clean(surface, reading)
        parts.append(furi)
    return ' '.join(parts)

# ── Model (same as Phase 1) ───────────────────────────────────────────────

MODEL_ID = 1738229000  # Same model ID — same note type
DECK_ID = 1738229002   # Different deck ID for WIP

MODEL = genanki.Model(MODEL_ID, "Japanese Enhanced", fields=[
    {"name": n} for n in ["Expression", "Reading", "Meaning",
        "Nuance_EN", "Nuance_JP",
        "Example1", "Example1_EN",
        "Example2", "Example2_EN",
        "Example3", "Example3_EN"]],
    templates=[{
        "name": "Recognition",
        "qfmt": """<div class="card"><div class="frontbg">{{Expression}}</div></div>""",
        "afmt": """<div class="card">
<div class="frontbg back"><div data-jrp-generate>{{furigana:Reading}}</div></div>
<div class="backbg">
  <span class="en">{{Meaning}}</span>
  {{#Nuance_EN}}<div class="nuance-en">{{Nuance_EN}}</div>{{/Nuance_EN}}
  {{#Nuance_JP}}<div class="nuance-jp">{{Nuance_JP}}</div>{{/Nuance_JP}}
  {{#Example1}}<div class="exgroup"><div class="ex">{{Example1}}</div>{{#Example1_EN}}<div class="extr-en">{{Example1_EN}}</div>{{/Example1_EN}}</div>{{/Example1}}
  {{#Example2}}<div class="exgroup"><div class="ex">{{Example2}}</div>{{#Example2_EN}}<div class="extr-en">{{Example2_EN}}</div>{{/Example2_EN}}</div>{{/Example2}}
  {{#Example3}}<div class="exgroup"><div class="ex">{{Example3}}</div>{{#Example3_EN}}<div class="extr-en">{{Example3_EN}}</div>{{/Example3_EN}}</div>{{/Example3}}
</div>
</div>""",
    }], css="""
.card { font-family: Noto Sans CJK JP Regular; font-size: 50px; text-align: center; color: black; }
.android .card { font-family: Noto Sans CJK JP Regular; font-size: 30px; text-align: center; color: black; }
.frontbg { background-color: #408cc7; color: #fff; min-height: 120px; padding: 25px 0 0 0; box-sizing: border-box; text-align: center; }
.frontbg.back { padding-top: 14px; }
.android .frontbg { min-height: 90px; padding-top: 24px; }
.android .frontbg.back { padding-top: 18px; }
.frontbg rt { line-height: 1; }
.frontbg ruby { line-height: 1; }
.backbg { background-color: #fff; padding: 20px 24px; color: #1a1a1a; font-size: 26px; text-align: left; }
.android .backbg { padding: 15px 16px; font-size: 20px; }
.en { font-size: 24px; color: #333; display: block; margin: 12px 0 24px 0; }
.nuance-en { color: #2c5f87; font-size: 18px; margin: 12px 0; padding-top: 6px; border-top: 1px solid #c8d8ed; line-height: 1.4; }
.nuance-jp { color: #5a8faf; font-style: italic; font-size: 18px; margin: 4px 0 16px 0; line-height: 1.3; }
.exgroup { margin-top: 14px; padding-top: 8px; border-top: 1px solid #c8d8ed; }
.ex { font-size: 24px; color: #333; line-height: 1.4; }
.extr-en { font-size: 19px; color: #888; line-height: 1.3; margin-top: 4px; }
.android .ex { font-size: 19px; }
.android .extr-en { font-size: 15px; }
""")

def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def parse_sentences(text):
    """Parse LLM output into dict: word -> {nuance_en, nuance_jp, ex1, ex1_en, ...}"""
    result, cur, data = {}, None, {}
    for line in text.strip().split('\n'):
        s = line.strip()
        if not s: continue
        if s.startswith('===word:') or s.startswith('===Word:'):
            if cur is not None:
                result[cur] = data
            m = re.match(r'===word:\s*(.+?)(?:\|.*?)?(?:===|$)', s, re.I)
            cur = m.group(1).strip() if m else s.replace('===','').strip().split('|')[0].strip()
            data = {}
            continue
        for prefix, key in [('Nuance_EN:', 'nuance_en'), ('Nuance_JP:', 'nuance_jp'), ('Nuance:', 'nuance_jp'),
                            ('Example1:', 'ex1'), ('Example1_EN:', 'ex1_en'),
                            ('Example2:', 'ex2'), ('Example2_EN:', 'ex2_en'),
                            ('Example3:', 'ex3'), ('Example3_EN:', 'ex3_en')]:
            if s.startswith(prefix):
                data[key] = s[len(prefix):].strip()
                break
    if cur is not None:
        result[cur] = data
    return result

def inject_scheduling(apkg_path, notes_data):
    """
    Open the .apkg (which is a zip containing collection.anki2 / SQLite),
    and inject scheduling into the cards table.
    
    notes_data is a list of dicts: each has 'scheduling' dict + the note's
    Expression (word) to match against.
    """
    # Extract collection.anki2
    import tempfile, os, shutil
    
    src = apkg_path
    
    # Work in a temp directory
    with zipfile.ZipFile(src) as z:
        collection_blob = z.read("collection.anki2")
        media_json = z.read("media") if "media" in z.namelist() else b"{}"
    
    # Patch the SQLite
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".anki2")
    tmp.write(collection_blob); tmp.close()
    
    conn = sqlite3.connect(tmp.name)
    sep = chr(31)
    
    # Build a map: Expression -> scheduling dict
    sched_by_word = {}
    for nd in notes_data:
        sched_by_word[nd['word']] = nd['scheduling']
    
    # Match notes by Expression (first field)
    updated = 0
    for row in conn.execute("SELECT id, flds FROM notes"):
        nid, flds = row
        parts = flds.split(sep)
        if len(parts) == 0: continue
        expr = parts[0]
        if expr in sched_by_word:
            s = sched_by_word[expr]
            conn.execute("""UPDATE cards SET ivl=?, reps=?, lapses=?, queue=?, type=?, due=?, factor=? WHERE nid=?""", 
                (s['ivl'], s['reps'], s['lapses'], s['queue'], s['type'], s['due'], s['factor'], nid))
            updated += 1
    
    conn.commit()
    conn.close()
    
    # Rebuild apkg
    with zipfile.ZipFile(src, 'w', zipfile.ZIP_DEFLATED) as zout:
        zout.writestr("collection.anki2", open(tmp.name, 'rb').read())
        zout.writestr("media", media_json)
    
    os.unlink(tmp.name)
    return updated

def main():
    # Load words
    words = json.loads((ROOT / "data" / "japanese_wip_words.json").read_text(encoding="utf-8"))
    print(f"Loaded {len(words)} words from Japanese WIP")
    
    # Load LLM content
    wip_file = ROOT / "data" / "sentences_raw" / "jp_batches" / "out_wip.txt"
    llm = {}
    if wip_file.exists():
        llm = parse_sentences(wip_file.read_text(encoding="utf-8"))
        print(f"  LLM content: {len(llm)} words")
    
    deck = genanki.Deck(DECK_ID, "Japanese Enhanced: WIP")
    built = 0
    
    for w in words:
        expression = w['word']
        meaning = w['meaning']
        reading = make_furigana(expression)
        
        wip_data = llm.get(expression, {})
        nuance_en = wip_data.get('nuance_en', '')
        nuance_jp = wip_data.get('nuance_jp', '')
        ex1 = wip_data.get('ex1', '')
        ex1_en = wip_data.get('ex1_en', '')
        ex2 = wip_data.get('ex2', '')
        ex2_en = wip_data.get('ex2_en', '')
        ex3 = wip_data.get('ex3', '')
        ex3_en = wip_data.get('ex3_en', '')
        
        meaning_clean = re.sub(r'<[^>]+>', '', meaning).strip()
        
        note = genanki.Note(model=MODEL, fields=[
            esc(expression), esc(reading), esc(meaning_clean),
            esc(nuance_en), esc(nuance_jp),
            esc(ex1), esc(ex1_en),
            esc(ex2), esc(ex2_en),
            esc(ex3), esc(ex3_en),
        ], tags=[])
        deck.add_note(note)
        built += 1
    
    pkg = genanki.Package(deck)
    out = OUT / "japanese_enhanced_wip.apkg"
    pkg.write_to_file(out)
    print(f"Built {built} notes → {out}")
    
    # Inject scheduling
    if wip_file.exists():
        updated = inject_scheduling(out, words)
        print(f"  Scheduling injected: {updated}/{built} cards")
    else:
        print("  No LLM content yet — skipping scheduling injection until LLM data arrives")
        print(f"  Wrote empty deck at {out}")
    
    sz = out.stat().st_size
    print(f"  Size: {sz:,} bytes ({sz/1e6:.2f} MB)")

if __name__ == "__main__":
    main()