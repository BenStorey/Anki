#!/usr/bin/env python3
"""
Build Anki deck from NIKL (National Institute of Korean Language) TOPIK vocabulary.

Source: julienshim/combined_korean_vocabulary_list — curated vocabulary
ordered by real frequency/importance, with hanja, TOPIK level, and
example phrases. English glosses merged from kengdic (99.3% coverage).

Pipeline:
1. Load NIKL vocab → filter to entries with hanja (Sino-Korean)
2. Merge English glosses from kengdic
3. Cross-reference against JMdict and CC-CEDICT
4. Collect Tatoeba example sentences
5. Export as Anki .apkg
"""
import json, csv, zipfile, html, bz2, tarfile, io, re, time, sys
from pathlib import Path
from collections import defaultdict
import genanki

RAW = Path(__file__).parent.parent / "data" / "raw"
OUT = Path(__file__).parent.parent / "output"
OUT.mkdir(parents=True, exist_ok=True)

# ── Card Model ──────────────────────────────────────────────────────────────

MODEL_ID = 1738223460
DECK_ID = 1738223461

MODEL = genanki.Model(
    MODEL_ID,
    "Sino-Korean v3",
    fields=[
        {"name": "Hangul"},
        {"name": "English"},
        {"name": "Japanese"},
        {"name": "Chinese"},
        {"name": "Level"},
        {"name": "Nuance"},
        {"name": "Example1"}, {"name": "Example1_EN"}, {"name": "Example1_JA"},
        {"name": "Example2"}, {"name": "Example2_EN"}, {"name": "Example2_JA"},
        {"name": "Example3"}, {"name": "Example3_EN"}, {"name": "Example3_JA"},
    ],
    templates=[{
        "name": "Sino-Korean Card",
        "qfmt": '<div class="card"><div class="frontbg">{{Hangul}}</div></div>',
        "afmt": """<div class="card">
<div class="frontbg" style="padding-bottom: 20px;">{{Hangul}}</div>
<div class="backbg">
  {{#Japanese}}<span class="slabel">JA</span> {{Japanese}}<br>{{/Japanese}}
  {{#Chinese}}<span class="slabel">ZH</span> {{Chinese}}<br>{{/Chinese}}
  <span class="slabel">EN</span> {{English}}
  {{#Nuance}}<div class="nuance">{{Nuance}}</div>{{/Nuance}}
  {{#Example1}}<div class="exgroup"><div class="ex"><span class="exnum">\u2460</span> {{Example1}}</div><div class="extr">{{Example1_EN}}</div>{{#Example1_JA}}<div class="extr">{{Example1_JA}}</div>{{/Example1_JA}}</div>{{/Example1}}
  {{#Example2}}<div class="exgroup"><div class="ex"><span class="exnum">\u2461</span> {{Example2}}</div><div class="extr">{{Example2_EN}}</div>{{#Example2_JA}}<div class="extr">{{Example2_JA}}</div>{{/Example2_JA}}</div>{{/Example2}}
  {{#Example3}}<div class="exgroup"><div class="ex"><span class="exnum">\u2462</span> {{Example3}}</div><div class="extr">{{Example3_EN}}</div>{{#Example3_JA}}<div class="extr">{{Example3_JA}}</div>{{/Example3_JA}}</div>{{/Example3}}
</div>
</div>""",
    }],
    css="""
.card { font-family: Noto Sans CJK JP Regular; font-size: 50px; text-align: center; color: black; }
.android .card { font-family: Noto Sans CJK JP Regular; font-size: 30px; text-align: center; color: black; }
.frontbg { background-color: #b740c8; color: #fff; padding-top: 20px; padding-bottom: 15px; }
.backbg { position: relative; top: -3px; background-color: #fff; padding: 20px 24px; color: #1a1a1a; font-size: 26px; text-align: left; }
.android .backbg { top: -5px; padding: 15px 16px; font-size: 20px; }
.slabel { display: inline-block; width: 40px; font-weight: 700; color: #b740c8; font-size: 18px; vertical-align: top; }
.android .slabel { width: 32px; font-size: 15px; }
.nuance { color: #7b2c87; font-style: italic; font-size: 22px; margin: 16px 0 12px; padding-top: 10px; line-height: 1.45; border-top: 1px solid #e8c8ed; }
.android .nuance { font-size: 17px; }
.exgroup { margin-top: 14px; padding-top: 10px; border-top: 1px solid #e8c8ed; }
.ex { font-size: 24px; color: #333; line-height: 1.4; }
.android .ex { font-size: 18px; }
.exnum { color: #b740c8; margin-right: 4px; }
.extr { font-size: 19px; color: #888; line-height: 1.3; margin-top: 3px; }
.android .extr { font-size: 15px; }
""",
)

# ── Kyûjitai → Shinjitai ───────────────────────────────────────────────────

KYUJITAI_TO_SHINJITAI = str.maketrans({
    '會':'会','國':'国','學':'学','體':'体','氣':'気','關':'関','對':'対',
    '發':'発','從':'従','當':'当','變':'変','畫':'画','區':'区','樂':'楽',
    '說':'説','晝':'昼','號':'号','廣':'広','禮':'礼','滿':'満','藥':'薬',
    '萬':'万','亂':'乱','擔':'担','團':'団','壯':'壮','聲':'声','實':'実',
    '賣':'売','讀':'読','難':'難','嚴':'厳','劍':'剣','權':'権','驗':'験',
    '縣':'県','讓':'譲','殘':'残','燒':'焼','眞':'真','巢':'巣','驛':'駅',
    '圓':'円','價':'価','卷':'巻','陷':'陥','惠':'恵','處':'処','兩':'両',
    '傳':'伝','點':'点','鐵':'鉄','佛':'仏','步':'歩','每':'毎','默':'黙',
    '榮':'栄','應':'応','溫':'温','橫':'横','擴':'拡','壞':'壊','繪':'絵',
    '戀':'恋','邊':'辺','豐':'豊','來':'来','賴':'頼','覽':'覧','龍':'竜',
    '錄':'録','鎭':'鎮',
})

def norm_jp(text):
    return text.translate(KYUJITAI_TO_SHINJITAI)


# ── 1. Load NIKL + kengdic ────────────────────────────────────────────────

def load_nikl_kengdic():
    """Load NIKL vocab, filter to hanja entries, merge English from kengdic."""
    # Load kengdic — prefer entries with hanja (they're more likely the
    # Sino-Korean meaning, not a slang homograph). For duplicates, keep first.
    kengdic = {}
    with open(RAW / "kengdic.tsv", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            hangul = row["surface"].strip()
            gloss = row.get("gloss", "").strip()
            hanja = row.get("hanja", "").strip() if row.get("hanja") else ""
            if not gloss or not hangul:
                continue
            if hangul not in kengdic:
                kengdic[hangul] = {"gloss": gloss, "hanja": hanja}
            elif hanja and not kengdic[hangul]["hanja"]:
                # Replace if new entry has hanja and old one doesn't
                kengdic[hangul] = {"gloss": gloss, "hanja": hanja}

    # Load NIKL
    words = []
    with open(RAW / "nikl_vocab.tsv", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            row = {k.strip(): v.strip() for k, v in row.items()}
            hanja = row.get("hanja", "")
            word = row.get("word", "")
            if not hanja or not word:
                continue
            word_clean = re.sub(r'\d+$', '', word)

            # Get EN gloss from kengdic
            en = ""
            if word_clean in kengdic and kengdic[word_clean]["gloss"]:
                en = kengdic[word_clean]["gloss"]
            elif word in kengdic and kengdic[word]["gloss"]:
                en = kengdic[word]["gloss"]

            words.append({
                "hangul": word_clean,
                "hanja": hanja,
                "en": en,
                "pos": row.get("part_of_speech", ""),
                "nikl_level": row.get("nikl_level", ""),
                "topik_level": row.get("topik_level", ""),
                "explanation": row.get("explanation", ""),
                "rank": int(row.get("rank", "99999") or "99999"),
            })

    # Sort by NIKL rank (ascending — lower rank = more important)
    words.sort(key=lambda w: w["rank"])

    with_en = sum(1 for w in words if w["en"])
    print(f"  NIKL: {len(words)} Sino-Korean entries")
    print(f"  With EN gloss: {with_en} ({with_en/len(words)*100:.1f}%)")
    return words


# ── 2. Load JMdict ─────────────────────────────────────────────────────────

def load_jmdict():
    zip_path = RAW / "jmdict-eng.json.zip"
    if not zip_path.exists():
        zip_path = RAW / "jmdict-eng-common.zip"
    if not zip_path.exists():
        return {}, {}
    with zipfile.ZipFile(zip_path) as z:
        name = [n for n in z.namelist() if n.endswith(".json")][0]
        with z.open(name) as f:
            data = json.load(f)
    idx = defaultdict(list)
    onyomi = defaultdict(list)
    for entry in data["words"]:
        kf = [k["text"] for k in entry.get("kanji", [])]
        is_common = any(k.get("common", False) for k in entry.get("kanji", []))
        ka = [k["text"] for k in entry.get("kana", [])]
        gl = []
        for s in entry.get("sense", []):
            for g in s.get("gloss", []):
                if g.get("lang", "eng") == "eng" and g.get("text"):
                    gl.append(g["text"])
        for k in kf:
            idx[k].append({"kanji": kf, "kana": ka, "glosses": gl, "common": is_common})
        for k in kf:
            if len(k) == 1:
                for a in ka:
                    if all('\u30a0' <= c <= '\u30ff' or c in 'ー' for c in a):
                        onyomi[k].append(a)
    print(f"  JMdict: {len(data['words'])} entries, {len(idx)} kanji compounds")
    return idx, onyomi


# ── 3. Load CC-CEDICT ──────────────────────────────────────────────────────

def load_cedict():
    path = RAW / "cedict.txt"
    if not path.exists():
        return {}
    data = {}
    pat = re.compile(r'^(?P<trad>\S+) (?P<simp>\S+) \[(?P<pinyin>[^\]]+)\] /(?P<defs>.+)/$')
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            m = pat.match(line.strip())
            if not m:
                continue
            entry = {"trad": m.group("trad"), "simp": m.group("simp"),
                     "pinyin": m.group("pinyin"), "defs": m.group("defs").split("/")}
            data[m.group("trad")] = entry
            data[m.group("simp")] = entry
    print(f"  CC-CEDICT: {len(data)} indexed forms")
    return data


# ── 4. Load Tatoeba ────────────────────────────────────────────────────────

def load_tatoeba():
    langs = {"kor": "kor_sentences.tsv.bz2", "eng": "eng_sentences.tsv.bz2",
             "jpn": "jpn_sentences.tsv.bz2", "cmn": "cmn_sentences.tsv.bz2"}
    sents = {}
    for code, fn in langs.items():
        p = RAW / fn
        d = {}
        if p.exists():
            with bz2.open(p, "rt", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("\t", 2)
                    if len(parts) == 3:
                        d[parts[0]] = parts[2]
        sents[code] = d
        print(f"  Tatoeba {code}: {len(d)} sentences")

    kor_links = defaultdict(list)
    lp = RAW / "links.tar.bz2"
    if lp.exists():
        with tarfile.open(lp, "r:bz2") as tar:
            cf = tar.extractfile("links.csv")
            if cf:
                rdr = csv.reader(io.TextIOWrapper(cf, encoding="utf-8"), delimiter="\t")
                kset = set(sents.get("kor", {}).keys())
                tgts = {c: sents.get(c, {}) for c in ["eng", "jpn", "cmn"]}
                for row in rdr:
                    if len(row) < 2:
                        continue
                    a, b = row[0].strip(), row[1].strip()
                    kid = a if a in kset else (b if b in kset else None)
                    oid = b if a in kset else a
                    if kid:
                        for ln, sm in tgts.items():
                            if oid in sm:
                                kor_links[kid].append({"lang": ln, "text": sm[oid]})
                                break
        print(f"  Tatoeba links: {len(kor_links)} Korean sentences linked")
    return sents, kor_links


# ── 5. Cross-reference ─────────────────────────────────────────────────────

def build_records(nikl_words, jmdict, cedict, kor_sents, kor_links):
    records = []
    total = len(nikl_words)
    for idx, word in enumerate(nikl_words):
        if (idx + 1) % 500 == 0:
            print(f"  [{idx+1}/{total}]")
        hanja = word["hanja"]
        hangul = word["hangul"]

        # JMdict
        jpn = []
        if hanja in jmdict:
            jpn.extend(jmdict[hanja])
        n = norm_jp(hanja)
        if n != hanja and n in jmdict:
            for e in jmdict[n]:
                if e not in jpn:
                    jpn.append(e)

        # CC-CEDICT
        cmn = []
        if cedict:
            if hanja in cedict:
                cmn.append(cedict[hanja])
            if n != hanja and n in cedict:
                c2 = cedict[n]
                if c2 not in cmn:
                    cmn.append(c2)

        # Tatoeba
        examples = []
        if kor_sents:
            for sid, st in kor_sents.items():
                if hangul in st:
                    tr = kor_links.get(sid, [])
                    en_t = [t for t in tr if t["lang"] == "eng"]
                    if not en_t:
                        continue
                    ja_t = [t for t in tr if t["lang"] == "jpn"]
                    cmn_t = [t for t in tr if t["lang"] == "cmn"]
                    examples.append({
                        "kor": st, "en": en_t[0]["text"],
                        "ja": ja_t[0]["text"] if ja_t else "",
                        "cmn": cmn_t[0]["text"] if cmn_t else "",
                    })
                    if len(examples) >= 5:
                        break

        records.append({
            "hangul": hangul, "hanja": hanja,
            "en": word["en"], "pos": word["pos"],
            "topik_level": word["topik_level"],
            "rank": word["rank"],
            "jpn_matches": jpn[:3], "cmn_matches": cmn,
            "examples": examples,
        })

    print(f"  Built {len(records)} records")
    return records


# ── 6. Export ──────────────────────────────────────────────────────────────

def export(records, limit=500):
    take = records[:limit] if limit else records
    deck = genanki.Deck(DECK_ID, "Sino-Korean")
    n_created = 0
    for rec in take:
        ja = ""
        for m in rec.get("jpn_matches", [])[:1]:
            ja = "/".join(m["kanji"])
        zh = ""
        for m in rec.get("cmn_matches", [])[:1]:
            zh = m["trad"] if m["trad"] == m["simp"] else f"{m['trad']} / {m['simp']}"
        exs = rec.get("examples", [])
        def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        note = genanki.Note(model=MODEL, fields=[
            esc(rec["hangul"]),
            esc(rec["en"] or rec.get("pos","")),
            esc(ja), esc(zh),
            f"TOPIK {rec['topik_level']}" if rec.get("topik_level") else "",
            "",
            *[esc(exs[i].get("kor","")) if i < len(exs) else "" for i in range(3)],
            *[esc(exs[i].get("en","")) if i < len(exs) else "" for i in range(3)],
            *[esc(exs[i].get("ja","")) if i < len(exs) else "" for i in range(3)],
        ], tags=["sino-korean", f"topik-{rec.get('topik_level','').lower()}"])
        deck.add_note(note)
        n_created += 1
    apkg_path = OUT / "sino_korean.apkg"
    genanki.Package(deck).write_to_file(apkg_path)
    print(f"Created {n_created} Anki cards → {apkg_path}")
    with_ja = sum(1 for r in take if r["jpn_matches"])
    with_zh = sum(1 for r in take if r["cmn_matches"])
    with_ex = sum(1 for r in take if r["examples"])
    print(f"  JA: {with_ja}, ZH: {with_zh}, Examples: {with_ex}")
    return take[:20]


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    import os
    limit = int(os.environ.get("DECK_SIZE", "500"))
    print("=" * 60)
    print("NIKL-based Sino-Korean Deck Builder")
    print(f"Generating {limit} cards")
    print("=" * 60)
    print()
    print("[1] Loading NIKL + kengdic...")
    nikl = load_nikl_kengdic()
    print()
    print("[2] Loading JMdict...")
    jmdict, _ = load_jmdict()
    print()
    print("[3] Loading CC-CEDICT...")
    cedict = load_cedict()
    print()
    print("[4] Loading Tatoeba...")
    sents, links = load_tatoeba()
    print()
    print("[5] Cross-referencing...")
    records = build_records(nikl[:limit], jmdict, cedict, sents.get("kor", {}), links)
    print()
    top = export(records)
    print()
    print("Top 20:")
    for r in top:
        ja = "/".join(r["jpn_matches"][0]["kanji"]) if r["jpn_matches"] else "-"
        zh = r["cmn_matches"][0]["trad"] if r["cmn_matches"] else "-"
        ex = len(r["examples"])
        lv = r["topik_level"]
        print(f"  {r['hangul']:12s} (TOPIK {lv:3s}) JA:{ja:12s} ZH:{zh:8s} ex:{ex} — {r['en'][:30]}")

if __name__ == "__main__":
    main()