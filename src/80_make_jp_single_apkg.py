#!/usr/bin/env python3
"""
Regenerate Japanese Enhanced as a SINGLE-template model (Recognition only).

Purpose: The Japanese Enhanced notetype currently has TWO templates
(Recognition + Production). The Production (reverse) template causes Anki to
auto-generate a duplicate 'New' card for every note migrated onto the model.
The user wants Recognition ONLY.

This builds an .apkg with the SAME model id (1738229000) and ONLY the
Recognition template. Importing it in Anki updates the existing notetype's
template set in place, dropping Production, so no more duplicate cards are
generated. Fields (13) and Recognition template are copied exactly from the
current collection.
"""
import genanki
from pathlib import Path

OUT = Path.home() / "dev/sino-korean/japanese_enhanced_single.apkg"
MODEL_ID = 1738229000

# Same 13 fields as the existing Japanese Enhanced model
FIELDS = [
    {"name": "Expression"}, {"name": "Meaning"}, {"name": "Reading"},
    {"name": "Nuance"}, {"name": "Example1"}, {"name": "Example1_EN"},
    {"name": "Example2"}, {"name": "Example2_EN"}, {"name": "Example3"},
    {"name": "Example3_EN"}, {"name": "Nuance_EN"}, {"name": "Nuance_JP"},
    {"name": "Furigana"},
]

# Exact Recognition template from the collection (front={furigana:Reading})
QFMT = """<div class="card"><div class="frontbg">{{Expression}}</div></div>"""

AFMT = """<div class="card">
<div class="frontbg back"><div data-jrp-generate>{{furigana:Reading}}</div></div>
<div class="backbg">
  <span class="en">{{Meaning}}</span>
  {{#Nuance_EN}}<div class="nuance-en">{{Nuance_EN}}</div>{{/Nuance_EN}}
  {{#Nuance_JP}}<div class="nuance-jp">{{Nuance_JP}}</div>{{/Nuance_JP}}
  {{#Example1}}<div class="exgroup"><div class="ex">{{Example1}}</div>{{#Example1_EN}}<div class="extr-en">{{Example1_EN}}</div>{{/Example1_EN}}</div>{{/Example1}}
  {{#Example2}}<div class="exgroup"><div class="ex">{{Example2}}</div>{{#Example2_EN}}<div class="extr-en">{{Example2_EN}}</div>{{/Example2_EN}}</div>{{/Example2}}
  {{#Example3}}<div class="exgroup"><div class="ex">{{Example3}}</div>{{#Example3_EN}}<div class="extr-en">{{Example3_EN}}</div>{{/Example3_EN}}</div>{{/Example3}}
</div>
</div>"""

# CSS — reuse the current JP Enhanced css (read from collection at runtime? We hardcode a reasonable one)
CSS = """.card { font-family: Noto Sans CJK JP Regular; font-size: 50px; text-align: center; color: black; }
.android .card { font-family: Noto Sans CJK JP Regular; font-size: 30px; text-align: center; color: black; }
.frontbg { background-color: #408cc7; color: #fff; min-height: 120px; padding: 25px 0 0 0; box-sizing: border-box; text-align: center; }
.frontbg.back { padding-top: 14px; }
.android .frontbg { min-height: 90px; padding-top: 24px; }
.android .frontbg.back { padding-top: 18px; }
.backbg { background-color: #fff; padding: 20px 24px; color: #1a1a1a; font-size: 26px; text-align: left; }
.android .backbg { padding: 15px 16px; font-size: 20px; }
.en { font-size: 24px; color: #333; display: block; margin: 12px 0 24px 0; }
.nuance-en { color: #2c5f87; font-size: 18px; margin: 12px 0; padding-top: 6px; border-top: 1px solid #c8d8ed; line-height: 1.4; }
.nuance-jp { color: #5a8faf; font-style: italic; font-size: 18px; margin: 4px 0 16px 0; line-height: 1.3; }
.exgroup { margin-top: 14px; padding-top: 8px; border-top: 1px solid #c8d8ed; }
.ex { font-size: 24px; color: #333; line-height: 1.4; }
.extr-en { font-size: 19px; color: #888; line-height: 1.3; margin-top: 4px; }
.android .ex { font-size: 19px; }
.android .extr-en { font-size: 15px; }"""

TEMPLATE = {"name": "Recognition", "qfmt": QFMT, "afmt": AFMT}

model = genanki.Model(
    MODEL_ID,
    "Japanese Enhanced",
    fields=FIELDS,
    templates=[TEMPLATE],
    css=CSS,
)

# Dummy deck+note to carry the model into the apkg
deck = genanki.Deck(1355152451702, "Japanese Dummy")
dummy = genanki.Note(model=model, fields=[""] * 13)
deck.add_note(dummy)
genanki.Package(deck).write_to_file(OUT)
print(f"Written: {OUT}")
print(f"Model id: {MODEL_ID}")
print("Template(s): Recognition (Production REMOVED)")
print("Import in Anki (same model id) -> updates model in place, drops Production.")