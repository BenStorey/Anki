#!/usr/bin/env python3
"""Generate a Chinese Enhanced .apkg with 11 fields, ready for import into Anki.

Import this .apkg (File → Import) to create the model.
Then I can do the SQL migration to move the WIP cards onto it.
"""

import genanki, json
from pathlib import Path

OUT = Path.home() / "dev/sino-korean" / "chinese_enhanced.apkg"

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
.android .extr-en { font-size: 15px; }
.pinyin { font-size: 28px; color: #d0e4f5; display: block; margin-top: 8px; }"""

FIELDS = [
    {"name": "Expression"},
    {"name": "Meaning"},
    {"name": "Pinyin"},
    {"name": "Nuance"},
    {"name": "Example1"},
    {"name": "Example1_EN"},
    {"name": "Example2"},
    {"name": "Example2_EN"},
    {"name": "Example3"},
    {"name": "Example3_EN"},
    {"name": "Nuance_EN"},
    {"name": "Nuance_CN"},
]

TEMPLATE = {
    "name": "Recognition",
    "qfmt": '<div class="card"><div class="frontbg">{{Expression}}</div></div>',
    "afmt": '<div class="card">\n<div class="frontbg back">{{Expression}}<br><span class="pinyin">{{Pinyin}}</span></div>\n<div class="backbg">\n  <span class="en">{{Meaning}}</span>\n  {{#Nuance_EN}}<div class="nuance-en">{{Nuance_EN}}</div>{{/Nuance_EN}}\n  {{#Nuance_CN}}<div class="nuance-cn">{{Nuance_CN}}</div>{{/Nuance_CN}}\n  {{#Example1}}<div class="exgroup"><div class="ex">{{Example1}}</div>{{#Example1_EN}}<div class="extr-en">{{Example1_EN}}</div>{{/Example1_EN}}</div>{{/Example1}}\n  {{#Example2}}<div class="exgroup"><div class="ex">{{Example2}}</div>{{#Example2_EN}}<div class="extr-en">{{Example2_EN}}</div>{{/Example2_EN}}</div>{{/Example2}}\n  {{#Example3}}<div class="exgroup"><div class="ex">{{Example3}}</div>{{#Example3_EN}}<div class="extr-en">{{Example3_EN}}</div>{{/Example3_EN}}</div>{{/Example3}}\n</div>\n</div>',
}

MODEL_ID = 1787807921282  # same as before so the migration script matches

model = genanki.Model(
    MODEL_ID,
    "Chinese Enhanced",
    fields=FIELDS,
    templates=[TEMPLATE],
    css=CSS,
)

# Create a dummy deck with one dummy note so the apkg includes the model
deck = genanki.Deck(1351219999178, "Chinese Dummy")

# One dummy note — user will delete this after import
dummy_note = genanki.Note(
    model=model,
    fields=["", "", "", "", "", "", "", "", "", "", "", ""],
)
deck.add_note(dummy_note)

genanki.Package(deck).write_to_file(OUT)
print(f"Written: {OUT}")
print(f"Model ID: {MODEL_ID}")
print(f"Import this .apkg file into Anki (File → Import)")
print(f"\nThe import will create:")
print(f"  - 'Chinese Enhanced' note type (12 fields)")
print(f"  - 'Chinese Dummy' deck with 1 empty card (delete it)")
print(f"\nAfter import, let me know and I'll run the migration.")