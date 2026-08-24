#!/usr/bin/env python3
"""
Phase 2c: Filter Sino-Korean words to only genuinely common cross-references.

Filter rules (apply per-word; keep if EITHER passes):
  1. JA filter: the hanja compound must exist in the common-only JMdict
  2. ZH filter: ALL individual hanja characters must be in top-2000 by frequency
     (this excludes rare/obscure characters like 齎, 沴, 赍 etc.)

Also removes entries with empty English glosses or obvious kengdic artifacts
(like entries whose hanja is just a suffix with ~).
"""
import json, zipfile
from pathlib import Path

RAW = Path(__file__).parent.parent / "data" / "raw"
DATA = Path(__file__).parent.parent / "data" / "processed"
OUT = DATA


def load_common_kanji():
    """Get the set of kanji compounds marked 'common' in the common-only JMdict."""
    path = RAW / "jmdict-eng-common.zip"
    if not path.exists():
        print("  ✗ common JMdict not found")
        return set()
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.endswith(".json")][0]
        with z.open(name) as f:
            data = json.load(f)
    common = set()
    for entry in data["words"]:
        for k in entry.get("kanji", []):
            if k.get("common", False):
                common.add(k["text"])
    print(f"  Common JMdict kanji compounds: {len(common)}")
    return common


def load_common_hanja(threshold_rank=2000):
    """Get the set of hanja characters above a frequency rank threshold."""
    path = RAW / "freq-hanja.txt"
    if not path.exists():
        print("  ✗ freq-hanja.txt not found")
        return set()
    freq_pairs = []
    with open(path) as f:
        for line in f:
            parts = line.strip().split(":")
            if len(parts) == 2:
                c, count = parts[0].strip(), int(parts[1].strip())
                if count > 0:
                    freq_pairs.append((c, count))
    freq_pairs.sort(key=lambda x: -x[1])
    common_chars = {c for c, _ in freq_pairs[:threshold_rank]}
    print(f"  Common hanja (top {threshold_rank}): {len(common_chars)} chars")
    return common_chars


def main():
    print("=" * 60)
    print("Phase 2c: Filter to genuinely common cross-references")
    print("=" * 60)
    print()

    # Load data
    in_path = DATA / "sino_korean_sorted.jsonl"
    if not in_path.exists():
        print(f"✗ Sorted data not found: {in_path}")
        return

    with open(in_path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    print(f"Loaded {len(records)} records")
    print()

    # Load common sets
    print("[1/2] Loading common JMdict kanji...")
    common_kanji = load_common_kanji()
    print()

    print("[2/2] Loading common hanja characters...")
    common_hanja = load_common_hanja(threshold_rank=2000)
    print()

    # Filter
    filtered = []
    excluded = []
    reasons = {"no_ja_or_zh": 0, "ja_not_common": 0, "zh_char_rare": 0, "both_failed": 0}
    seen_hangul = set()

    for rec in records:
        hanja = rec["hanja"]
        hanja_chars = list(hanja)
        has_ja = bool(rec.get("jpn_matches"))
        has_zh = bool(rec.get("cmn_matches"))

        # Dedup: skip if we've already seen this hangul
        if rec["hangul"] in seen_hangul:
            continue
        seen_hangul.add(rec["hangul"])

        # JA filter: compound must be in common JMdict
        ja_ok = has_ja and hanja in common_kanji

        # ZH filter: all individual chars must be common
        if has_zh and hanja_chars:
            zh_ok = all(c in common_hanja for c in hanja_chars)
        else:
            zh_ok = False

        # Also require a non-empty English gloss
        gloss_ok = bool(rec.get("gloss_en", "").strip())

        if (ja_ok or zh_ok) and gloss_ok:
            rec["filter_ja_common"] = ja_ok
            rec["filter_zh_common"] = zh_ok
            filtered.append(rec)
        else:
            if not has_ja and not has_zh:
                reasons["no_ja_or_zh"] += 1
            if has_ja and not ja_ok:
                reasons["ja_not_common"] += 1
            if has_zh and not zh_ok:
                reasons["zh_char_rare"] += 1
            if not ja_ok and not zh_ok and (has_ja or has_zh):
                reasons["both_failed"] += 1
            excluded.append(rec)

    print()
    print(f"  After filtering:")
    print(f"    Kept:    {len(filtered)} ({len(filtered)/len(records)*100:.1f}%)")
    print(f"    Excluded: {len(excluded)} ({len(excluded)/len(records)*100:.1f}%)")
    print()
    print("  Excluded by reason:")
    for reason, count in reasons.items():
        if count > 0:
            print(f"    - {reason}: {count}")
    print()

    # Save
    out_path = OUT / "sino_korean_common.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in filtered:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Saved → {out_path}")
    print()

    # Stats on kept set
    with_ja = sum(1 for r in filtered if r.get("jpn_matches"))
    with_zh = sum(1 for r in filtered if r.get("cmn_matches"))
    with_both = sum(1 for r in filtered if r.get("jpn_matches") and r.get("cmn_matches"))
    with_ja_common = sum(1 for r in filtered if r.get("filter_ja_common"))
    with_zh_common = sum(1 for r in filtered if r.get("filter_zh_common"))
    with_ex = sum(1 for r in filtered if r["examples"])
    print("  Kept set stats:")
    print(f"    With any JA match:   {with_ja}")
    print(f"    With common JA:      {with_ja_common} ({with_ja_common/len(filtered)*100:.1f}%)")
    print(f"    With any ZH match:   {with_zh}")
    print(f"    With common ZH:      {with_zh_common} ({with_zh_common/len(filtered)*100:.1f}%)")
    print(f"    With both common:    {sum(1 for r in filtered if r['filter_ja_common'] and r['filter_zh_common'])}")
    print(f"    With examples:       {with_ex} ({with_ex/len(filtered)*100:.1f}%)")
    print()

    # Top 30
    print("  Top 30 by frequency:")
    for r in filtered[:30]:
        ja = "/".join(r["jpn_matches"][0]["kanji"]) if r.get("filter_ja_common") else "-"
        zh = r["cmn_matches"][0]["trad"] if r.get("filter_zh_common") else "-"
        ex = len(r["examples"])
        print(f"    {r['hangul']:12s} ({r['hanja']:10s}) JA:{ja:12s} ZH:{zh:10s} ex:{ex} — {r['gloss_en'][:35]}")

    # Show some excluded examples
    print()
    print("  Sample excluded (first 15):")
    for r in excluded[:15]:
        ja = "/".join(r["jpn_matches"][0]["kanji"]) if r.get("jpn_matches") else "-"
        zh = r["cmn_matches"][0]["trad"] if r.get("cmn_matches") else "-"
        why = ""
        if r["jpn_matches"] and r["hanja"] not in common_kanji:
            why += "JA-rare "
        if r["cmn_matches"] and not all(c in common_hanja for c in list(r["hanja"])):
            why += "ZH-rare "
        print(f"    {r['hangul']:12s} ({r['hanja']:10s}) JA:{ja:12s} ZH:{zh:8s} [{why}]— {r['gloss_en'][:35]}")


if __name__ == "__main__":
    main()