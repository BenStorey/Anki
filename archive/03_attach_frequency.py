#!/usr/bin/env python3
"""
Phase 2b: Attach frequency data and sort enriched records by importance.

Frequency sources (priority order):
1. ko_freq_full.txt — 688K word frequency list from web/twitter/news corpus
2. Hanja character frequency from freq-hanja.txt (fallback for unfound words)
3. Data quality sort for equal-frequency words

Output: sorted JSONL file ready for Phase 4 export.
"""
import json, csv, sys, urllib.request
from pathlib import Path
from collections import defaultdict

RAW = Path(__file__).parent.parent / "data" / "raw"
DATA = Path(__file__).parent.parent / "data" / "processed"
OUT = DATA
OUT.mkdir(parents=True, exist_ok=True)

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


def load_word_freq():
    """Load ko_freq_full.txt → {word: count} (688K entries)."""
    path = RAW / "ko_freq_full.txt"
    freq = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    freq[parts[0]] = int(parts[1])
        print(f"  Word frequency list: {len(freq)} words loaded")
    else:
        print(f"  ✗ ko_freq_full.txt not found — downloading...")
        resp = urllib.request.urlopen(
            "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
            "master/content/2018/ko/ko_full.txt"
        )
        text = resp.read().decode("utf-8")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        for line in text.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                freq[parts[0]] = int(parts[1])
        print(f"  Downloaded: {len(freq)} words")
    return freq


def load_char_freq():
    """Load hanja character frequency from hanja-rs."""
    path = RAW / "freq-hanja.txt"
    char_freq = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ":" in line:
                    char, count = line.split(":", 1)
                    count = int(count.strip())
                    if count > 0:
                        char_freq[char.strip()] = count
        print(f"  Hanja char frequency: {len(char_freq)} chars")
    else:
        resp = urllib.request.urlopen(
            "https://raw.githubusercontent.com/bekker/hanja-rs/master/data/freq-hanja.txt"
        )
        text = resp.read().decode("utf-8")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        for line in text.splitlines():
            line = line.strip()
            if ":" in line:
                char, count = line.split(":", 1)
                count = int(count.strip())
                if count > 0:
                    char_freq[char.strip()] = count
        print(f"  Downloaded: {len(char_freq)} chars")
    return char_freq


def quality_score(rec):
    """Sort key for same-freq words: more cross-references = better."""
    has_jpn = 1 if rec.get("jpn_matches") else 0
    has_cmn = 1 if rec.get("cmn_matches") else 0
    has_ex = min(len(rec.get("examples", [])), 3)
    return (has_jpn + has_cmn, has_ex)


def gloss_quality(g):
    """Score gloss richness: longer + more unique meaningful words = better."""
    words = [w for w in g.lower().split()
             if len(w) >= 3 and w not in GLOSS_STOPWORDS]
    return len(words) * 10 + len(g)


def main():
    print("=" * 60)
    print("Phase 2b: Attach frequency + sort by importance")
    print("=" * 60)
    print()

    in_path = DATA / "sino_korean_enriched_v2.jsonl"
    if not in_path.exists():
        print(f"✗ Enriched data not found: {in_path}")
        return

    with open(in_path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    print(f"Loaded {len(records)} enriched records")

    # Dedup by hangul — keep first occurrence only
    seen = set()
    deduped = []
    for rec in records:
        if rec["hangul"] not in seen:
            seen.add(rec["hangul"])
            deduped.append(rec)
    n_dups = len(records) - len(deduped)
    records = deduped
    print(f"  Deduped: removed {n_dups} homograph duplicates, {len(records)} remaining")
    print()

    # Load frequencies
    word_freq = load_word_freq()
    char_freq = load_char_freq()
    print()

    # Attach frequency
    real_freq_count = 0
    char_fallback_count = 0
    no_freq_count = 0

    for rec in records:
        hangul = rec["hangul"]
        wf = word_freq.get(hangul, 0)
        if wf > 0:
            rec["freq"] = wf
            rec["freq_source"] = "corpus"
            real_freq_count += 1
        else:
            # Fallback: mean hanja character frequency
            hanja = rec["hanja"]
            chars = list(hanja)
            if chars:
                scores = [char_freq.get(c, 0) for c in chars]
                rec["freq"] = sum(scores) / len(scores) if scores else 0
            else:
                rec["freq"] = 0
            rec["freq_source"] = "char_fallback"
            char_fallback_count += 1
            no_freq_count += 1 if rec["freq"] == 0 else 0

    print(f"  Real word frequency: {real_freq_count}")
    print(f"  Hanja char fallback: {char_fallback_count}")
    print(f"  No frequency data:   {no_freq_count}")
    print()

    # Sort:
    # Tier 1: words with real corpus frequency (sorted descending by freq)
    # Tier 2: words without corpus frequency — pushed to the bottom,
    #         sorted first by data quality, then by char frequency
    def sort_key(r):
        wf = word_freq.get(r["hangul"], 0)
        gq = gloss_quality(r.get("gloss_en", ""))
        hanja_chars = list(r["hanja"])
        avg_char_freq_cv = sum(char_freq.get(c, 0) for c in hanja_chars) / max(len(hanja_chars), 1) if hanja_chars else 0

        if r.get("freq_source") == "corpus":
            return (0, -wf, -quality_score(r)[0], -quality_score(r)[1], -gq)
        else:
            # Push all character-fallback words below corpus-frequency words
            # Within fallback, sort by data quality, then char freq
            return (1, -quality_score(r)[0], -quality_score(r)[1], -gq, -avg_char_freq_cv)

    records.sort(key=sort_key)

    # Save
    out_path = OUT / "sino_korean_sorted.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Saved sorted records → {out_path}")
    print()

    # Show top 30
    print("Top 30 by frequency + quality:")
    for r in records[:30]:
        ja = "/".join(r["jpn_matches"][0]["kanji"]) if r["jpn_matches"] else "-"
        zh = r["cmn_matches"][0]["trad"] if r["cmn_matches"] else "-"
        ex = len(r["examples"])
        wf = word_freq.get(r["hangul"], 0)
        src = "C" if r.get("freq_source") == "corpus" else "F"
        print(f"  {r['hangul']:12s} ({r['hanja']:10s}) [{src}] f:{wf or int(r['freq']):>8,}  JA:{ja:12s} ZH:{zh:8s} ex:{ex} — {r['gloss_en'][:35]}")

    # Show where the first fallback word appears
    first_fallback = next((i for i, r in enumerate(records) if r.get("freq_source") != "corpus"), None)
    if first_fallback:
        r = records[first_fallback]
        print(f"\n  First fallback word at rank #{first_fallback+1}: {r['hangul']} ({r['hanja']})")


if __name__ == "__main__":
    main()