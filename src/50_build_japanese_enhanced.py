#!/usr/bin/env python3
"""
Build Japanese Enhanced deck from Takoboto source + LLM-generated sentences.

Usage: python3 src/50_build_japanese_enhanced.py

Reads:
  - data/takoboto_words.json (word list extracted from currentdeck.apkg)
  - data/sentences_raw/jp_batches/out_*.txt (LLM sentence outputs)

Outputs:
  - output/japanese_enhanced_takoboto.apkg (121 notes, 1 card each, JP→EN only)
"""
import json, re, genanki
from pathlib import Path
from fugashi import Tagger

ROOT = Path.home() / "dev" / "sino-korean"
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)

tagger = Tagger()

# ── Furigana helpers ────────────────────────────────────────────────────────

def kata_to_hira(s):
    """Convert katakana to hiragana, handling long vowels (ー)."""
    result = []
    for i, c in enumerate(s):
        if 'ァ' <= c <= 'ヶ':
            result.append(chr(ord(c) - 0x60))
        elif c == 'ー' and i > 0:
            prev = result[-1] if result else ''
            v = {'あ':'あ','か':'あ','さ':'あ','た':'あ','な':'あ','は':'あ','ま':'あ','や':'あ','ら':'あ','わ':'あ',
                 'い':'い','き':'い','し':'い','ち':'い','に':'い','ひ':'い','み':'い','り':'い',
                 'う':'う','く':'う','す':'う','つ':'う','ぬ':'う','ふ':'う','む':'う','ゆ':'う','る':'う',
                 'え':'え','け':'え','せ':'え','て':'え','ね':'え','へ':'え','め':'え','れ':'え',
                 'お':'お','こ':'お','そ':'お','と':'お','の':'お','ほ':'お','も':'お','よ':'お','ろ':'お'}
            result.append(v.get(prev, 'う'))
        else:
            result.append(c)
    return ''.join(result)

def is_kanji(c):
    return '\u4e00' <= c <= '\u9fff'

def is_kana(c):
    return 'ぁ' <= c <= 'ゟ' or 'ァ' <= c <= 'ヿ'

def token_furigana_clean(surface, reading):
    """
    Per-token furigana with spaces between kanji-kana groups.
    組み合わせ → 組[く]み 合[あ]わせ
    Pure kanji compounds → whole-word ruby: 無双[むそう]
    """
    if not any(is_kanji(c) for c in surface):
        return surface
    if not reading:
        return surface

    ri = 0
    rlen = len(reading)
    result = []
    # Track state for spacing
    after_kana_segment = False

    i = 0
    while i < len(surface):
        ch = surface[i]

        if is_kanji(ch):
            # Add space before this kanji if we just finished a kana segment
            # that followed a previous kanji group (okurigana → next kanji)
            if after_kana_segment:
                result.append(' ')
                after_kana_segment = False

            # Collect consecutive kanji
            kanji_buf = [ch]
            j = i + 1
            while j < len(surface) and is_kanji(surface[j]):
                kanji_buf.append(surface[j])
                j += 1
            kanji_str = ''.join(kanji_buf)

            # What kana follows these kanji in the surface?
            next_kana = ''
            for k in range(j, len(surface)):
                if is_kana(surface[k]):
                    next_kana = surface[k]
                    break

            # Consume kana from reading until we hit the next kana boundary
            kana_buf = []
            while ri < rlen:
                if next_kana and ri < rlen and reading[ri] == next_kana:
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
            # Collect the kana segment
            kana_start = i
            while i < len(surface) and is_kana(surface[i]):
                i += 1
            kana_seg = surface[kana_start:i]

            # Check if there's a kanji coming after this kana
            has_kanji_after = any(is_kanji(c) for c in surface[i:])

            result.append(kana_seg)

            # Advance reading past these kana
            for kch in kana_seg:
                if ri < rlen and reading[ri] == kch:
                    ri += 1

            # Mark that we're in a kana segment — next kanji gets a space
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
    """Tokenize and produce furigana for the whole expression."""
    parts = []
    for word in tagger(expr):
        surface = word.surface
        reading = kata_to_hira(word.feature.kana) if word.feature.kana else ''
        furi = token_furigana_clean(surface, reading)
        parts.append(furi)
    return ' '.join(parts)

# ── Model ───────────────────────────────────────────────────────────────────

MODEL_ID = 1738229000
DECK_ID = 1738229001

MODEL = genanki.Model(MODEL_ID, "Japanese Enhanced", fields=[
    {"name": n} for n in ["Expression", "Furigana", "Meaning", "Reading",
        "Nuance_EN", "Nuance_JP",
        "Example1", "Example1_EN",
        "Example2", "Example2_EN",
        "Example3", "Example3_EN"]],
    templates=[{
        "name": "Recognition",
        "qfmt": """<div class="card"><div class="frontbg">{{Expression}}</div></div>""",
        "afmt": """<div class="card">
<div class="frontbg" style="padding-bottom: 20px;">{{Furigana}}</div>
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
.frontbg { background-color: #408cc7; color: #fff; padding-top: 20px; padding-bottom: 15px; }
.backbg { background-color: #fff; padding: 20px 24px; color: #1a1a1a; font-size: 26px; text-align: left; }
.android .backbg { padding: 15px 16px; font-size: 20px; }
.en { font-size: 24px; color: #333; }
.nuance-en { color: #2c5f87; font-size: 20px; margin: 12px 0; padding-top: 6px; border-top: 1px solid #c8d8ed; line-height: 1.4; }
.nuance-jp { color: #5a8faf; font-style: italic; font-size: 18px; margin: 4px 0 12px 0; line-height: 1.3; }
.exgroup { margin-top: 10px; padding-top: 6px; border-top: 1px solid #c8d8ed; }
.ex { font-size: 24px; color: #333; line-height: 1.4; }
.extr-en { font-size: 19px; color: #888; line-height: 1.3; }
.android .ex { font-size: 19px; }
.android .extr-en { font-size: 15px; }
""")

def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def parse_sentences(text):
    """Parse the LLM output format into a dict: word -> {nuance_en, nuance_jp, ex1, ex1_en, ...}"""
    result = {}
    current_word = None
    current = {}
    for line in text.strip().split('\n'):
        s = line.strip()
        if not s:
            continue
        if s.startswith('===word:') or s.startswith('===Word:'):
            if current_word is not None:
                result[current_word] = current
            m = re.match(r'===word:\s*(.+?)(?:\|.*?)?(?:===|$)', s, re.IGNORECASE)
            current_word = m.group(1).strip() if m else s.replace('===','').strip().split('|')[0].strip()
            current = {}
            continue
        if s.startswith('Nuance_EN:'):
            current['nuance_en'] = s[10:].strip()
            continue
        if s.startswith('Nuance_JP:'):
            current['nuance_jp'] = s[10:].strip()
            continue
        if s.startswith('Nuance:'):
            current['nuance_jp'] = s[7:].strip()
            continue
        if s.startswith('Example1:'):
            current['ex1'] = s[9:].strip()
            continue
        if s.startswith('Example1_EN:'):
            current['ex1_en'] = s[12:].strip()
            continue
        if s.startswith('Example2:'):
            current['ex2'] = s[9:].strip()
            continue
        if s.startswith('Example2_EN:'):
            current['ex2_en'] = s[12:].strip()
            continue
        if s.startswith('Example3:'):
            current['ex3'] = s[9:].strip()
            continue
        if s.startswith('Example3_EN:'):
            current['ex3_en'] = s[12:].strip()
            continue
    if current_word is not None:
        result[current_word] = current
    return result

def main():
    words = json.loads((ROOT / "data" / "takoboto_words.json").read_text(encoding="utf-8"))
    print(f"Loaded {len(words)} words from Takoboto")

    # Load all sentence batch files
    batch_dir = ROOT / "data" / "sentences_raw" / "jp_batches"
    all_sentences = {}
    for f in sorted(batch_dir.glob("out_*.txt")):
        if f.name in ("out_nuance_en.txt", "out_nuance_jp.txt"):
            continue
        parsed = parse_sentences(f.read_text(encoding="utf-8"))
        all_sentences.update(parsed)
        words_in = sum(1 for w in words if w['word'] in parsed)
        print(f"  {f.name}: {len(parsed)} parsed ({words_in} matched)")

    # Load Nuance_EN translations
    nuance_en_file = batch_dir / "out_nuance_en.txt"
    if nuance_en_file.exists():
        current = None
        for line in nuance_en_file.read_text(encoding="utf-8").split('\n'):
            m = re.match(r'===word:\s*(.+?)(?:\|.*?)?(?:===|$)', line)
            if m:
                current = m.group(1).strip()
            if line.startswith('Nuance_EN:') and current:
                val = line[10:].strip()
                if current in all_sentences:
                    all_sentences[current]['nuance_en'] = val

    with_en = sum(1 for v in all_sentences.values() if v.get('nuance_en'))
    print(f"  Nuance_EN translations: {with_en}/{len(all_sentences)}")
    print(f"Total words with LLM content: {len(all_sentences)}")

    deck = genanki.Deck(DECK_ID, "Japanese Enhanced: Takoboto")
    built = 0
    with_nuance_en = 0
    with_nuance_jp = 0
    with_examples = 0

    for w in words:
        expression = w['word']
        meaning = w['meaning']
        reading = w['reading']

        # Generate furigana
        furigana = make_furigana(expression)

        llm = all_sentences.get(expression, {})
        nuance_en = llm.get('nuance_en', '')
        nuance_jp = llm.get('nuance_jp', '')
        ex1 = llm.get('ex1', '')
        ex1_en = llm.get('ex1_en', '')
        ex2 = llm.get('ex2', '')
        ex2_en = llm.get('ex2_en', '')
        ex3 = llm.get('ex3', '')
        ex3_en = llm.get('ex3_en', '')

        if nuance_en: with_nuance_en += 1
        if nuance_jp: with_nuance_jp += 1
        if ex1: with_examples += 1

        meaning_clean = re.sub(r'<[^>]+>', '', meaning).strip()

        note = genanki.Note(model=MODEL, fields=[
            esc(expression), esc(furigana), esc(meaning_clean), esc(reading),
            esc(nuance_en), esc(nuance_jp),
            esc(ex1), esc(ex1_en),
            esc(ex2), esc(ex2_en),
            esc(ex3), esc(ex3_en),
        ], tags=[])
        deck.add_note(note)
        built += 1

    pkg = genanki.Package(deck)
    out = OUT / "japanese_enhanced_takoboto.apkg"
    pkg.write_to_file(out)
    sz = out.stat().st_size

    print(f"\nBuilt {built} notes (1 card each) → {out}")
    print(f"  With Nuance_EN: {with_nuance_en}/{built}")
    print(f"  With Nuance_JP: {with_nuance_jp}/{built}")
    print(f"  With examples: {with_examples}/{built}")
    print(f"  Size: {sz:,} bytes ({sz/1e6:.2f} MB)")

if __name__ == "__main__":
    main()