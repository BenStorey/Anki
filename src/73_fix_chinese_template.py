#!/usr/bin/env python3
"""
Regenerate chinese_enhanced.apkg with the CORRECTED card design.

KEEPS the original Chinese red-top card (frontbg, hira, backbg) and only ADDS
the nuance/example sections from the Japanese Enhanced template.
Same model ID (1787807921282) so importing updates the existing notetype in place.
"""
import genanki
from pathlib import Path

OUT = Path.home() / "dev/sino-korean" / "chinese_enhanced.apkg"

# ── Original Chinese red-top CSS (unchanged) ├ extended nuance/example styles ──
CSS = """.card {
 font-family: Noto Sans CJK JP Regular;
 font-size: 50px;
 text-align: center;
 color: black;

}

.android .card {
 font-family: Noto Sans CJK JP Regular;
 font-size: 30px;
 text-align: center;
 color: black;

}

.frontbg {
 background-color: #d14949;
 color: #fff;
 padding-top: 39px;
 padding-bottom: 34px;
line-height: 1.25;
}

.hira {
 font-size: 25px;
 padding-bottom: 10px;
 padding-top: 10px;
line-height: 1.25;
}

.android .hira {
 font-size: 18px;
}


.backbg {
 position: relative;
 top: -3px;
 background-color: #fff;
 padding: 25px 15px;
 color: #7a2626;
 font-size: 28px;
line-height: 1.5;
}

.android .backbg {
 position: relative;
 top: -5px;
 font-size: 20px;
line-height: 1.5;
}


.android br[data-start] \t{display:none}
.android p[data-start] \t{display:inline; margin:0}

ol[data-start] br:first-of-type\t{display:none}

/* Nuance + example sections (added, in the card's red/white palette) */
.nuance-en { color: #b85a5a; font-size: 17px; text-align:left; margin: 12px 0 4px 0; padding-top: 8px; border-top: 1px solid #e8cccc; line-height:1.4; }
.nuance-cn { color: #d14949; font-style: italic; font-size: 17px; text-align:left; margin: 4px 0 16px 0; line-height:1.3; }
.exgroup { text-align:left; margin-top: 14px; padding-top: 8px; border-top: 1px solid #e8cccc; }
.ex { font-size: 26px; color: #7a2626; line-height:1.4; }
.extr-en { font-size: 19px; color: #b07a7a; line-height:1.3; margin-top: 4px; }
.android .ex { font-size: 19px; }
.android .extr-en { font-size: 15px; }
"""

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

QFMT = r"""
<div class="frontbg">
{{Expression}}
{{#Pinyin}}
	<div class="hira">
		{{Pinyin}}
	</div>
{{/Pinyin}}
</div>
"""

AFMT = r"""
<div class="frontbg">
{{Expression}}
{{#Pinyin}}
	<div class="hira">
		{{Pinyin}}
	</div>
{{/Pinyin}}
</div>

<div class="backbg">
	{{Meaning}}

	{{#Nuance_EN}}<div class="nuance-en">{{Nuance_EN}}</div>{{/Nuance_EN}}
	{{#Nuance_CN}}<div class="nuance-cn">{{Nuance_CN}}</div>{{/Nuance_CN}}

	{{#Example1}}<div class="exgroup"><div class="ex">{{Example1}}</div>{{#Example1_EN}}<div class="extr-en">{{Example1_EN}}</div>{{/Example1_EN}}</div>{{/Example1}}
	{{#Example2}}<div class="exgroup"><div class="ex">{{Example2}}</div>{{#Example2_EN}}<div class="extr-en">{{Example2_EN}}</div>{{/Example2_EN}}</div>{{/Example2}}
	{{#Example3}}<div class="exgroup"><div class="ex">{{Example3}}</div>{{#Example3_EN}}<div class="extr-en">{{Example3_EN}}</div>{{/Example3_EN}}</div>{{/Example3}}
</div>
"""

TEMPLATE = {"name": "Recognition", "qfmt": QFMT, "afmt": AFMT}

MODEL_ID = 1787807921282  # SAME ID -> import updates the existing notetype in place

model = genanki.Model(
    MODEL_ID,
    "Chinese Enhanced",
    fields=FIELDS,
    templates=[TEMPLATE],
    css=CSS,
)

deck = genanki.Deck(1351219999178, "Chinese Dummy")
dummy_note = genanki.Note(model=model, fields=["", "", "", "", "", "", "", "", "", "", "", ""])
deck.add_note(dummy_note)

genanki.Package(deck).write_to_file(OUT)
print(f"Written: {OUT}")
print(f"Model id: {MODEL_ID}")
print("\nThis apkg KEEPS the original red-top card and only ADDS:")
print("  - nuance-en / nuance-cn sections (appended to back)")
print("  - 3 example + EN-translation sections")
print("\nImport it (File->Import). Since the model id matches the existing")
print("'Chinese Enhanced' notetype, the template/CSS are updated in place.")
print("One 'Chinese Dummy' card appears — delete it after import.")