#!/usr/bin/env python3
"""
Phase 2: Cross-reference — build enriched Korean word records.

For each Sino-Korean word (has hanja), match against:
  - Japanese JMdict entries (same kanji compound, with variant normalization)
  - Chinese CC-CEDICT entries (trad/simp matching)
  - Tatoeba example sentences (Korean → EN + JA translations)

Output: JSON lines file for Phase 3 (enrichment) and Phase 4 (export).
"""
import csv
import json
import re
import gzip
import bz2
import zipfile
import tarfile
import io
import sys
import time
import unicodedata
from pathlib import Path
from collections import defaultdict

RAW = Path(__file__).parent.parent / "data" / "raw"
OUT = Path(__file__).parent.parent / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)


# ── Kyūjitai → Shinjitai normalization ──────────────────────────────────────
# Korean hanja use traditional forms (kyūjitai); Japanese JMdict uses shinjitai.
# This table maps common kyūjitai → shinjitai for matching.
KYUJITAI_TO_SHINJITAI = str.maketrans({
    '會': '会', '國': '国', '學': '学', '體': '体', '氣': '気',
    '關': '関', '對': '対', '發': '発', '從': '従', '當': '当',
    '變': '変', '畫': '画', '區': '区', '樂': '楽', '數': '数',
    '說': '説', '晝': '昼', '號': '号', '廣': '広', '爭': '争',
    '禮': '礼', '滿': '満', '藥': '薬', '萬': '万', '蟲': '虫',
    '亂': '乱', '擔': '担', '團': '団', '壯': '壮', '聲': '声',
    '盡': '尽', '條': '条', '續': '続', '覺': '覚', '觸': '触',
    '實': '実', '辭': '辞', '賣': '売', '讀': '読', '難': '難',
    '嚴': '厳', '虛': '虚', '劍': '剣', '獻': '献', '權': '権',
    '驗': '験', '顯': '顕', '縣': '県', '讓': '譲', '讚': '賛',
    '殘': '残', '燒': '焼', '職': '職', '眞': '真', '爭': '争',
    '巢': '巣', '驛': '駅', '圓': '円', '奧': '奥', '價': '価',
    '覺': '覚', '卷': '巻', '劍': '剣', '陷': '陥', '勳': '勲',
    '惠': '恵', '擧': '挙', '蔣': '蒋', '處': '処', '囑': '嘱',
    '尙': '尚', '狀': '状', '豫': '予', '兩': '両', '鎭': '鎮',
    '鎭': '鎮', '傳': '伝', '禪': '禅', '點': '点', '燈': '灯',
    '峽': '峡', '疊': '畳', '鐵': '鉄', '盜': '盗', '飜': '翻',
    '佛': '仏', '拂': '払', '步': '歩', '每': '毎', '默': '黙',
    '藥': '薬', '譯': '訳', '飮': '飲', '營': '営', '榮': '栄',
    '櫻': '桜', '應': '応', '橫': '横', '溫': '温', '價': '価',
    '廻': '回', '懷': '懐', '壞': '壊', '繪': '絵', '擴': '拡',
    '樂': '楽', '曆': '暦', '戀': '恋', '樓': '楼', '祿': '禄',
    '賣': '売', '腦': '脳', '澁': '渋', '肅': '粛', '濱': '浜',
    '邊': '辺', '豐': '豊', '寶': '宝', '沒': '没', '藥': '薬',
    '與': '与', '搖': '揺', '樣': '様', '來': '来', '賴': '頼',
    '覽': '覧', '龍': '竜', '錄': '録', '灣': '湾',
})

def normalize_to_shinjitai(text):
    """Convert kyūjitai Korean hanja to Japanese shinjitai for matching."""
    return text.translate(KYUJITAI_TO_SHINJITAI)


# ── 1. Load kengdic ──────────────────────────────────────────────────────────

def load_kengdic():
    """Load Korean-English dictionary, return list of dicts."""
    words = []
    with open(RAW / "kengdic.tsv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            hangul = row["surface"].strip()
            # Clean hanja: remove trailing ~, 공백, and common artifacts
            hanja_raw = row["hanja"].strip() if row.get("hanja") else ""
            # Remove suffixes like ~~, 공백, etc.
            hanja = re.sub(r'[~∼\s].*$', '', hanja_raw).strip()
            gloss = row["gloss"].strip() if row.get("gloss") else ""
            words.append({
                "hangul": hangul,
                "hanja_raw": hanja_raw,
                "hanja": hanja,  # cleaned
                "gloss_en": gloss,
                "source_id": row["id"],
            })
    print(f"  kengdic: {len(words)} entries total")
    sino = [w for w in words if w["hanja"]]
    print(f"  sino-korean (with hanja): {len(sino)}")
    return words, sino


# ── 2. Load hanja.txt character mapping ──────────────────────────────────────

def load_hanja_map():
    """Build {hanja_char: [hangul_readings]} from hanja.txt."""
    hanja_to_hangul = defaultdict(list)
    hangul_to_hanja = defaultdict(list)
    with open(RAW / "hanja.txt", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            if len(parts) >= 2:
                hangul_char = parts[0].strip()
                hanja_char = parts[1].strip()
                if len(hangul_char) == 1 and len(hanja_char) == 1:
                    hanja_to_hangul[hanja_char].append(hangul_char)
                    hangul_to_hanja[hangul_char].append(hanja_char)
    print(f"  hanja.txt: {len(hanja_to_hangul)} hanja → hangul mappings")
    return hanja_to_hangul, hangul_to_hanja


# ── 3. Load JMdict (full) ──────────────────────────────────────────────────

def load_jmdict():
    """
    Load full JMdict English JSON.
    Build index: kanji_text → [{id, reading, glosses}]
    Also build individual kanji → on'yomi readings.
    """
    zip_path = RAW / "jmdict-eng.json.zip"
    if not zip_path.exists():
        # Fallback to common
        zip_path = RAW / "jmdict-eng-common.zip"

    if not zip_path.exists():
        print("  ✗ JMdict zip not found")
        return {}, {}

    with zipfile.ZipFile(zip_path) as z:
        name = [n for n in z.namelist() if n.endswith(".json")][0]
        with z.open(name) as f:
            data = json.load(f)

    # Index by kanji compound (both original and normalized)
    compound_index = defaultdict(list)
    kanji_onyomi = defaultdict(list)

    for entry in data["words"]:
        eid = entry["id"]
        kanji_forms = [k["text"] for k in entry.get("kanji", [])]
        kana_forms = [k["text"] for k in entry.get("kana", [])]
        glosses = []
        for sense in entry.get("sense", []):
            for g in sense.get("gloss", []):
                if g.get("lang", "eng") == "eng" and g.get("text"):
                    glosses.append(g["text"])

        for kanji in kanji_forms:
            compound_index[kanji].append({
                "id": eid,
                "kanji": kanji_forms,
                "kana": kana_forms,
                "glosses": glosses,
            })

        # Extract on'yomi for individual kanji
        for kanji in kanji_forms:
            if len(kanji) == 1:
                for kana in kana_forms:
                    if all('\u30a0' <= c <= '\u30ff' or c in 'ー' for c in kana):
                        kanji_onyomi[kanji].append(kana)

    print(f"  JMdict: {len(data['words'])} entries, {len(compound_index)} kanji compounds, {len(kanji_onyomi)} single-kanji on'yomi")
    return compound_index, kanji_onyomi


# ── 4. Load CC-CEDICT ───────────────────────────────────────────────────────

def load_cedict():
    """Load CC-CEDICT and index by both trad and simp."""
    data = {}
    path = RAW / "cedict.txt"
    if not path.exists():
        print("  ✗ CC-CEDICT not found")
        return {}

    cedict_re = re.compile(
        r'^(?P<trad>\S+) (?P<simp>\S+) \[(?P<pinyin>[^\]]+)\] /(?P<defs>.+)/$'
    )
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            m = cedict_re.match(line.strip())
            if not m:
                continue
            trad = m.group("trad")
            simp = m.group("simp")
            pinyin = m.group("pinyin")
            defs = m.group("defs").split("/")
            entry = {"simp": simp, "trad": trad, "pinyin": pinyin, "defs": defs}
            data[trad] = entry
            data[simp] = entry
            count += 1

    print(f"  CC-CEDICT: {count} entries, {len(data)} indexed forms")
    return data


# ── 5. Load Tatoeba sentences and links ──────────────────────────────────────

def load_tatoeba():
    """Load Tatoeba sentences and cross-links for EN/JA/CMN translations."""
    langs = {
        "kor": "kor_sentences.tsv.bz2",
        "eng": "eng_sentences.tsv.bz2",
        "jpn": "jpn_sentences.tsv.bz2",
        "cmn": "cmn_sentences.tsv.bz2",
    }

    sentences = {}
    for code, fname in langs.items():
        path = RAW / fname
        if not path.exists():
            print(f"  ✗ Tatoeba {fname} not found")
            continue
        sents = {}
        opener = bz2.open if fname.endswith(".bz2") else open
        with opener(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t", 2)
                if len(parts) == 3:
                    sid, lang_code, text = parts
                    sents[sid] = text
        sentences[code] = sents
        print(f"  Tatoeba {code}: {len(sents)} sentences")

    # Build Korean → translation mapping
    links_path = RAW / "links.tar.bz2"
    kor_links = defaultdict(list)

    if links_path.exists():
        with tarfile.open(links_path, "r:bz2") as tar:
            csv_file = tar.extractfile("links.csv")
            if csv_file:
                reader = csv.reader(io.TextIOWrapper(csv_file, encoding="utf-8"), delimiter="\t")
                kor_set = set(sentences.get("kor", {}).keys())
                target_langs = {"eng": sentences.get("eng", {}),
                                "jpn": sentences.get("jpn", {}),
                                "cmn": sentences.get("cmn", {})}
                for row in reader:
                    if len(row) < 2:
                        continue
                    sid_a, sid_b = row[0].strip(), row[1].strip()

                    if sid_a in kor_set:
                        for lang, sents_map in target_langs.items():
                            if sid_b in sents_map:
                                kor_links[sid_a].append({
                                    "lang": lang, "text": sents_map[sid_b],
                                    "translation_id": sid_b,
                                })
                                break
                    elif sid_b in kor_set:
                        for lang, sents_map in target_langs.items():
                            if sid_a in sents_map:
                                kor_links[sid_b].append({
                                    "lang": lang, "text": sents_map[sid_a],
                                    "translation_id": sid_a,
                                })
                                break

        print(f"  Tatoeba links: {len(kor_links)} Korean sentences have EN/JA/CMN translations")
    else:
        print("  ✗ Tatoeba links file not found")

    return sentences, kor_links


# ── 6. Find best JA match ──────────────────────────────────────────────────

def find_japanese_match(hanja_str, jmdict_index):
    """Try to find the best JMdict match for a hanja compound.
    First tries the original form, then shinjitai-normalized form.
    Returns list of matched entries (max 3).
    """
    matches = []

    # Try original form
    if hanja_str in jmdict_index:
        matches.extend(jmdict_index[hanja_str])

    # Try shinjitai-normalized form
    normalized = normalize_to_shinjitai(hanja_str)
    if normalized != hanja_str and normalized in jmdict_index:
        for entry in jmdict_index[normalized]:
            if entry not in matches:
                matches.append(entry)

    return matches[:3]


# ── 7. Keyword validation for examples ────────────────────────────────────

# Stopwords to ignore when matching gloss keywords to translation text
GLOSS_STOPWORDS = frozenset({
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "with", "by",
    "and", "or", "but", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "can", "could", "not", "no", "it", "its",
    "that", "this", "these", "those", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "such",
    "some", "any", "every", "all", "both", "each", "few", "more", "most",
    "other", "into", "upon", "very", "just",
    "way", "use", "used", "new", "old", "big", "small", "get", "got",
    "set", "put", "make", "made", "take", "took",
})

def gloss_keywords(gloss):
    """Extract meaningful keywords from an English gloss string."""
    words = set()
    for token in gloss.lower().split():
        # Remove trailing punctuation
        clean = token.strip(".,;:!?()[]{}'\"-")
        if len(clean) >= 3 and clean not in GLOSS_STOPWORDS:
            words.add(clean)
        # Also include hyphenated parts
        if "-" in clean:
            for part in clean.split("-"):
                if len(part) >= 3 and part not in GLOSS_STOPWORDS:
                    words.add(part)
    return words

def translation_matches_gloss(gloss, trans_text, hanja, ja_text, cmn_text):
    """Check if an example is semantically relevant to the target word.
    Passes if ANY of these is true:
    1. An English gloss keyword appears in the English translation (word boundary)
    2. The JA translation contains the kanji characters (via normalize_to_shinjitai)
    3. The ZH translation contains the hanzi characters

    Only blocks examples when there's clear evidence of a mismatch.
    """
    # Check 1: English keyword match (most reliable)
    if gloss and trans_text:
        gloss_words = gloss_keywords(gloss)
        if gloss_words and any(re.search(rf'\b{re.escape(kw)}\b', trans_text.lower()) for kw in gloss_words):
            return True

    # Check 2: Japanese translation contains the target kanji
    if ja_text and hanja:
        ja_norm = normalize_to_shinjitai(hanja)
        if ja_norm in ja_text or hanja in ja_text:
            return True

    # Check 3: Chinese translation contains the target hanzi
    if cmn_text and hanja:
        if hanja in cmn_text:
            return True

    # Check 4: No clear gloss keywords — be permissive (accept)
    if not gloss_keywords(gloss):
        return True

    return False


# ── 8. Build enriched records ────────────────────────────────────────────────

def build_records(sino_words, hanja_to_hangul, jmdict_index, kanji_onyomi,
                  cedict_data, kor_links, sentences):
    """Cross-reference each Sino-Korean word against JA/ZH/Tatoeba."""
    records = []
    total = len(sino_words)
    start = time.time()
    kor_sents_map = sentences.get("kor", {})

    for idx, word in enumerate(sino_words):
        if (idx + 1) % 2000 == 0:
            elapsed = time.time() - start
            eta = (elapsed / (idx + 1)) * (total - idx - 1)
            print(f"  [{idx+1}/{total}] {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining")

        hanja_str = word["hanja"]
        hangul = word["hangul"]

        # Parse individual hanja characters
        hanja_chars = list(hanja_str)
        char_readings = []
        for ch in hanja_chars:
            h_readings = hanja_to_hangul.get(ch, [])
            j_readings = kanji_onyomi.get(ch, [])
            c_entry = cedict_data.get(ch, {}) if cedict_data else {}
            c_pinyin = c_entry.get("pinyin", "")
            char_readings.append({
                "hanja": ch,
                "kor": h_readings,
                "jpn_on": j_readings,
                "cmn_pinyin": c_pinyin,
            })

        # Match in JMdict (with variant normalization)
        jpn_matches = find_japanese_match(hanja_str, jmdict_index)

        # Match in CC-CEDICT (try original, trad, simp)
        cmn_matches = []
        if cedict_data:
            c = cedict_data.get(hanja_str)
            if c:
                cmn_matches.append(c)
            # Also try the shinjitai-normalized version (might match simplified)
            normalized = normalize_to_shinjitai(hanja_str)
            if normalized != hanja_str:
                c2 = cedict_data.get(normalized)
                if c2 and c2 not in cmn_matches:
                    cmn_matches.append(c2)

        # Find Tatoeba example sentences
        examples = []
        if kor_sents_map:
            for sid, sent_text in kor_sents_map.items():
                if hangul not in sent_text:
                    continue
                translations = kor_links.get(sid, [])
                en_trans = [t for t in translations if t["lang"] == "eng"]
                if not en_trans:
                    continue
                en_text = en_trans[0]["text"]
                ja_trans = [t for t in translations if t["lang"] == "jpn"]
                cmn_trans = [t for t in translations if t["lang"] == "cmn"]

                # Keyword + cross-lingual validation: check that the example
                # is about this word's meaning, not just a substring match.
                ja_text = ja_trans[0]["text"] if ja_trans else ""
                cmn_text = cmn_trans[0]["text"] if cmn_trans else ""
                if not translation_matches_gloss(word["gloss_en"], en_text,
                                                  word["hanja"], ja_text, cmn_text):
                    continue

                examples.append({
                    "kor": sent_text,
                    "en": en_text,
                    "ja": ja_text,
                    "cmn": cmn_text,
                    "sid": sid,
                })
                if len(examples) >= 5:
                    break

        record = {
            "hangul": hangul,
            "hanja": hanja_str,
            "gloss_en": word["gloss_en"],
            "char_readings": char_readings,
            "jpn_matches": jpn_matches,
            "cmn_matches": cmn_matches,
            "examples": examples,
            "source_id": word["source_id"],
        }
        records.append(record)

    print(f"  Built {len(records)} enriched records in {time.time()-start:.0f}s")
    return records


# ── 8. Stats ─────────────────────────────────────────────────────────────────

def print_stats(records):
    total = len(records)
    with_jpn = sum(1 for r in records if r["jpn_matches"])
    with_cmn = sum(1 for r in records if r["cmn_matches"])
    with_examples = sum(1 for r in records if r["examples"])
    with_both = sum(1 for r in records if r["jpn_matches"] and r["cmn_matches"])
    all_three = sum(1 for r in records if r["jpn_matches"] and r["cmn_matches"] and r["examples"])

    print(f"\n  ── Match Statistics ──")
    print(f"  Total Sino-Korean words: {total}")
    print(f"  With Japanese match:     {with_jpn} ({with_jpn/total*100:.1f}%)")
    print(f"  With Chinese match:      {with_cmn} ({with_cmn/total*100:.1f}%)")
    print(f"  With both JA+ZH:         {with_both} ({with_both/total*100:.1f}%)")
    print(f"  With example sentences:  {with_examples} ({with_examples/total*100:.1f}%)")
    print(f"  With all three:          {all_three} ({all_three/total*100:.1f}%)")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Phase 2: Cross-reference — Sino-Korean Deck (v2)")
    print("=" * 60)
    print()

    print("[1/6] Loading kengdic...")
    words, sino_words = load_kengdic()
    print()

    print("[2/6] Loading hanja character map...")
    hanja_to_hangul, hangul_to_hanja = load_hanja_map()
    print()

    print("[3/6] Loading full JMdict...")
    jmdict_index, kanji_onyomi = load_jmdict()
    print()

    print("[4/6] Loading CC-CEDICT...")
    cedict_data = load_cedict()
    print()

    print("[5/6] Loading Tatoeba sentences...")
    sentences, kor_links = load_tatoeba()
    print()

    print("[6/6] Building enriched records...")
    records = build_records(
        sino_words, hanja_to_hangul, jmdict_index, kanji_onyomi,
        cedict_data, kor_links, sentences
    )
    print()

    print_stats(records)
    print()

    # Save
    out_path = OUT / "sino_korean_enriched_v2.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Saved {len(records)} records to {out_path}")

    # Preview TSV
    tsv_path = OUT / "sino_korean_preview_v2.tsv"
    with open(tsv_path, "w", encoding="utf-8") as f:
        f.write("hangul\thanja\ten\tja\tzh\texamples\n")
        for r in records:
            ja = "; ".join(
                f"{'/'.join(e['kanji'])} [{', '.join(e['kana'])}]"
                for e in r["jpn_matches"][:1]
            ) or "-"
            zh = "; ".join(
                f"{e['trad']} ({e['pinyin']})"
                for e in r["cmn_matches"][:1]
            ) or "-"
            ex = len(r["examples"])
            f.write(f"{r['hangul']}\t{r['hanja']}\t{r['gloss_en']}\t{ja}\t{zh}\t{ex}\n")
    print(f"Preview TSV saved to {tsv_path}")

    # Save just the subset with JA+ZH+examples (the best cards)
    gold_path = OUT / "sino_korean_gold.jsonl"
    gold = [r for r in records if r["jpn_matches"] and r["cmn_matches"] and r["examples"]]
    with open(gold_path, "w", encoding="utf-8") as f:
        for rec in gold:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Gold set (JA+ZH+examples): {len(gold)} records → {gold_path}")


if __name__ == "__main__":
    main()