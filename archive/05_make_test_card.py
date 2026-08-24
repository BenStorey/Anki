#!/usr/bin/env python3
"""Test card v3 — purple banner, clean definition layout underneath."""
import json, sys, time
from pathlib import Path
import genanki

OUT = Path.home() / "dev" / "sino-korean" / "output"
DATA = Path.home() / "dev" / "sino-korean" / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

MODEL_ID = 1738223460
DECK_ID = 1738223461

MODEL = genanki.Model(
    MODEL_ID,
    "Sino-Korean v3",
    fields=[
        {"name": "Hangul"},
        {"name": "Hanja"},
        {"name": "English"},
        {"name": "Japanese"},
        {"name": "Chinese"},
        {"name": "Nuance"},
        {"name": "Example1"},
        {"name": "Example1_EN"},
        {"name": "Example1_JA"},
        {"name": "Example2"},
        {"name": "Example2_EN"},
        {"name": "Example2_JA"},
        {"name": "Example3"},
        {"name": "Example3_EN"},
        {"name": "Example3_JA"},
    ],
    templates=[
        {
            "name": "Sino-Korean Card",
            "qfmt": """<div class="card">
<div class="frontbg">{{Hangul}}</div>
</div>""",
            "afmt": """<div class="card">
<div class="frontbg" style="padding-bottom: 20px;">{{Hangul}}</div>

<div class="backbg">
  {{#Japanese}}<span class="slabel">JA</span> {{Japanese}}<br>{{/Japanese}}
  {{#Chinese}}<span class="slabel">ZH</span> {{Chinese}}<br>{{/Chinese}}
  <span class="slabel">EN</span> {{English}}

  {{#Nuance}}
  <div class="nuance">{{Nuance}}</div>
  {{/Nuance}}

  {{#Example1}}
  <div class="exgroup">
    <div class="ex"><span class="exnum">①</span> {{Example1}}</div>
    <div class="extr">{{Example1_EN}}</div>
    {{#Example1_JA}}<div class="extr">{{Example1_JA}}</div>{{/Example1_JA}}
  </div>
  {{/Example1}}
  {{#Example2}}
  <div class="exgroup">
    <div class="ex"><span class="exnum">②</span> {{Example2}}</div>
    <div class="extr">{{Example2_EN}}</div>
    {{#Example2_JA}}<div class="extr">{{Example2_JA}}</div>{{/Example2_JA}}
  </div>
  {{/Example2}}
  {{#Example3}}
  <div class="exgroup">
    <div class="ex"><span class="exnum">③</span> {{Example3}}</div>
    <div class="extr">{{Example3_EN}}</div>
    {{#Example3_JA}}<div class="extr">{{Example3_JA}}</div>{{/Example3_JA}}
  </div>
  {{/Example3}}
</div>
</div>""",
        }
    ],
    css="""
.card {
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
 background-color: #b740c8;
 color: #fff;
 padding-top: 20px;
 padding-bottom: 15px;
}

.backbg {
 position: relative;
 top: -3px;
 background-color: #fff;
 padding: 20px 24px;
 color: #1a1a1a;
 font-size: 26px;
 text-align: left;
}

.android .backbg {
 top: -5px;
 padding: 15px 16px;
 font-size: 20px;
}

.slabel {
 display: inline-block;
 width: 40px;
 font-weight: 700;
 color: #b740c8;
 font-size: 18px;
 vertical-align: top;
}

.android .slabel {
 width: 32px;
 font-size: 15px;
}

.nuance {
 color: #7b2c87;
 font-style: italic;
 font-size: 22px;
 margin: 16px 0 12px;
 padding-top: 10px;
 line-height: 1.45;
 border-top: 1px solid #e8c8ed;
}

.android .nuance {
 font-size: 17px;
}

.exgroup {
 margin-top: 14px;
 padding-top: 10px;
 border-top: 1px solid #e8c8ed;
}

.ex {
 font-size: 24px;
 color: #333;
 line-height: 1.4;
}

.android .ex {
 font-size: 18px;
}

.exnum {
 color: #b740c8;
 margin-right: 4px;
}

.extr {
 font-size: 19px;
 color: #888;
 line-height: 1.3;
 margin-top: 3px;
}

.android .extr {
 font-size: 15px;
}
""",
)


def fmt_japanese(rec):
    for m in rec.get("jpn_matches", [])[:1]:
        return "/".join(m["kanji"])
    return ""

def fmt_chinese(rec):
    for m in rec.get("cmn_matches", [])[:1]:
        if m["trad"] != m["simp"]:
            return f"{m['trad']} / {m['simp']}"
        return m["trad"]
    return ""

def esc(text):
    return str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")


def find_word(hangul):
    with open(DATA / "sino_korean_enriched_v2.jsonl") as f:
        for line in f:
            r = json.loads(line)
            if r["hangul"] == hangul:
                return r
    return None


def main():
    record = find_word("가족")
    if not record:
        print("✗ Could not find 가족")
        return

    exs = record.get("examples", [])
    deck = genanki.Deck(DECK_ID, "Sino-Korean (test v3)")

    note = genanki.Note(
        model=MODEL,
        fields=[
            esc(record["hangul"]),
            esc(record["hanja"]),
            esc(record["gloss_en"]),
            esc(fmt_japanese(record)),
            esc(fmt_chinese(record)),
            "",  # Nuance — only filled for words that need it
            esc(exs[0]["kor"]) if len(exs) > 0 else "",
            esc(exs[0]["en"]) if len(exs) > 0 else "",
            esc(exs[0]["ja"]) if len(exs) > 0 else "",
            esc(exs[1]["kor"]) if len(exs) > 1 else "",
            esc(exs[1]["en"]) if len(exs) > 1 else "",
            esc(exs[1]["ja"]) if len(exs) > 1 else "",
            esc(exs[2]["kor"]) if len(exs) > 2 else "",
            esc(exs[2]["en"]) if len(exs) > 2 else "",
            esc(exs[2]["ja"]) if len(exs) > 2 else "",
        ],
        tags=["sino-korean", "test-card"]
    )
    deck.add_note(note)

    out_path = OUT / "sino_korean_test.apkg"
    genanki.Package(deck).write_to_file(out_path)

    print(f"✓ Test card v3: 가족")
    print(f"  → {out_path}")
    print(f"  Front: purple banner — 가족")
    print(f"  Back:  JA 家族  |  ZH 家族  |  EN Family")
    print(f"         Examples with ①②③ — no 'Examples' header, no EN/JA labels")
    print(f"  Hanja field: in model, NOT shown on card (you said skip it)")
    print(f"  Nuance: template renders it when filled; empty on this card")


if __name__ == "__main__":
    main()