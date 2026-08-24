#!/usr/bin/env python3
"""
Phase 4: Anki Exporter — generate Anki-compatible files.

Outputs:
  - Anki .apkg (via genanki) — the full imported deck with card styling
  - Preview .tsv — direct Anki import fallback
  - nuance_ready.json — JSON subset ready for LLM nuance generation
"""
import json
import html
from pathlib import Path
import genanki

OUT = Path(__file__).parent.parent / "output"
OUT.mkdir(parents=True, exist_ok=True)
DATA = Path(__file__).parent.parent / "data" / "processed"


# ── Card Model ──────────────────────────────────────────────────────────────

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


# ── Helpers ──────────────────────────────────────────────────────────────────

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

def fmt_examples(rec, limit=3):
    examples = rec.get("examples", [])
    results = []
    for ex in examples[:limit]:
        results.append({
            "kor": ex.get("kor", ""),
            "en": ex.get("en", ""),
            "ja": ex.get("ja", ""),
        })
    while len(results) < limit:
        results.append({"kor": "", "en": "", "ja": ""})
    return results

def esc(text):
    return html.escape(str(text))


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Phase 4: Anki Exporter")
    print("=" * 60)
    print()

    in_path = DATA / "sino_korean_common.jsonl"
    if not in_path.exists():
        print(f"✗ Sorted data not found at {in_path}")
        return

    with open(in_path, "r", encoding="utf-8") as f:
        all_records = [json.loads(line) for line in f]

    print(f"Loaded {len(all_records)} records")
    print()

    # Take first N (pass via env or default)
    import os
    limit = int(os.environ.get("DECK_SIZE", "500"))
    min_hanja = int(os.environ.get("MIN_HANJA", "2"))
    records = [r for r in all_records if len(r["hanja"]) >= min_hanja][:limit]

    print(f"Exporting top {len(records)} by frequency + data quality")
    print(f"  (dropped 1-character hanja entries, minimum {min_hanja} chars)")
    print()

    deck = genanki.Deck(DECK_ID, f"Sino-Korean (top {len(records)})")
    created = 0
    skipped = 0

    for rec in records:
        hangul = esc(rec["hangul"])
        en = esc(rec["gloss_en"])
        ja = esc(fmt_japanese(rec))
        zh = esc(fmt_chinese(rec))
        examples = fmt_examples(rec)

        if not hangul:
            skipped += 1
            continue

        note = genanki.Note(
            model=MODEL,
            fields=[
                hangul,
                esc(rec["hanja"]),
                en,
                ja,
                zh,
                "",
                esc(examples[0]["kor"]),
                esc(examples[0]["en"]),
                esc(examples[0]["ja"]),
                esc(examples[1]["kor"]),
                esc(examples[1]["en"]),
                esc(examples[1]["ja"]),
                esc(examples[2]["kor"]),
                esc(examples[2]["en"]),
                esc(examples[2]["ja"]),
            ],
            tags=[f"sino-korean", f"hanja::{rec['hanja'][:1] if rec['hanja'] else 'none'}"]
        )
        deck.add_note(note)
        created += 1

    apkg_path = OUT / "sino_korean.apkg"
    genanki.Package(deck).write_to_file(apkg_path)
    print(f"Created {created} Anki cards → {apkg_path}")
    if skipped:
        print(f"  (skipped {skipped} empty entries)")

    # Stats
    with_ja = sum(1 for r in records if r["jpn_matches"])
    with_zh = sum(1 for r in records if r["cmn_matches"])
    with_ex = sum(1 for r in records if r["examples"])
    print(f"  Stats: {with_ja} with JA match, {with_zh} with ZH match, {with_ex} with examples")


if __name__ == "__main__":
    main()