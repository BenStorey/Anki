#!/usr/bin/env python3
"""
Phase 2c: Filter Sino-Korean words to only those with cross-reference evidence.

If a word's hanja compound doesn't exist in Japanese (JMdict) or Chinese (CC-CEDICT),
the hanja can't serve as a visual bridge to the user's existing JA/ZH knowledge.
Filter those out — they're likely kengdic artifacts or native Korean words with
incorrect/spurious hanja assignments.
"""
import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "data" / "processed"
OUT = DATA


def main():
    print("=" * 60)
    print("Phase 2c: Filter to cross-referenced words only")
    print("=" * 60)
    print()

    in_path = DATA / "sino_korean_sorted.jsonl"
    if not in_path.exists():
        print(f"✗ Sorted data not found: {in_path}")
        return

    with open(in_path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    print(f"Loaded {len(records)} sorted records")

    # Filter: must have at least one JA or ZH compound match
    filtered = [r for r in records if r.get("jpn_matches") or r.get("cmn_matches")]

    print(f"  With JA or ZH match: {len(filtered)} ({len(filtered)/len(records)*100:.1f}%)")
    print(f"  Excluded (no bridge): {len(records) - len(filtered)}")
    print()

    # Save filtered
    out_path = OUT / "sino_korean_bridge.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in filtered:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Saved → {out_path}")
    print()

    # Stats
    with_ja = sum(1 for r in filtered if r["jpn_matches"])
    with_zh = sum(1 for r in filtered if r["cmn_matches"])
    with_both = sum(1 for r in filtered if r["jpn_matches"] and r["cmn_matches"])
    with_ex = sum(1 for r in filtered if r["examples"])
    print(f"  With JA match: {with_ja} ({with_ja/len(filtered)*100:.1f}%)")
    print(f"  With ZH match: {with_zh} ({with_zh/len(filtered)*100:.1f}%)")
    print(f"  With both:     {with_both} ({with_both/len(filtered)*100:.1f}%)")
    print(f"  With examples: {with_ex} ({with_ex/len(filtered)*100:.1f}%)")
    print()

    # Top 30
    print("Top 30 bridge words (frequency sorted):")
    for r in filtered[:30]:
        ja = "/".join(r["jpn_matches"][0]["kanji"]) if r["jpn_matches"] else "-"
        zh = r["cmn_matches"][0]["trad"] if r["cmn_matches"] else "-"
        ex = len(r["examples"])
        print(f"  {r['hangul']:12s} ({r['hanja']:10s}) JA:{ja:15s} ZH:{zh:10s} ex:{ex} — {r['gloss_en'][:35]}")
    print()
    print("First bridge words without examples:")
    no_ex = [r for r in filtered if not r["examples"]]
    for r in no_ex[:10]:
        ja = "/".join(r["jpn_matches"][0]["kanji"]) if r["jpn_matches"] else "-"
        zh = r["cmn_matches"][0]["trad"] if r["cmn_matches"] else "-"
        print(f"  {r['hangul']:12s} ({r['hanja']:10s}) JA:{ja:15s} ZH:{zh:10s} — {r['gloss_en'][:35]}")


if __name__ == "__main__":
    main()