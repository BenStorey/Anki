# Chinese Enhanced Deck: Migration Plan

## Current State

| Property | Value |
|----------|-------|
| Model | "Chinese" (3 fields: Expression, Meaning, Pinyin) |
| Model ID | 1351220176888 |
| Total notes | 16,374 |
| Chinese deck | 15,189 cards |
| Chinese WIP deck | 1,183 cards |

## Current Fields (3)
```
0: Expression  (hanzi, e.g. 体育馆, 回家, 火车站)
1: Meaning     (English gloss — often HTML-crusted from Pleco, e.g. `<div><p>...`)
2: Pinyin      (reading, e.g. "tǐyùguǎn", "huí jiā" — already correct)
```

## Strategy: Two-Phase
Phase 1: Chinese WIP (1,183 cards) — prove approach, verify quality
Phase 2: Full Chinese deck (16,374 cards) — scale up

## Target: "Chinese Enhanced" Model

11 fields (same structure as Japanese but with Pinyin instead of ruby):

```
0:  Expression   (hanzi, kept as-is)
1:  Meaning      (clean English gloss — LLM generated)
2:  Pinyin       (pinyin reading — kept as-is, already correct)
3:  Nuance       (empty — field alignment)
4:  Example1     (mandarin sentence)
5:  Example1_EN  (english translation)
6:  Example2     (mandarin sentence)
7:  Example2_EN  (english translation)
8:  Example3     (mandarin sentence)
9:  Example3_EN  (english translation)
10: Nuance_EN    (english nuance explanation — LLM generated)
11: Nuance_CN    (mandarin nuance explanation — LLM generated)
```

## Template CSS
Copy Japanese Enhanced styling but adapt for Chinese:
- Blue header (#408cc7), min-height
- Separate desktop/Android sizing
- Font: `Noto Sans CJK SC` (Simplified Chinese) instead of JP
- {{Pinyin}} on back instead of {{furigana:Reading}}
- Exgroup dividers, colored nuance text

## LLM Generation
Prompt format: `word|pinyin|meaning` (meaning is the raw existing meaning for context)
Output format: `===word: WORD===` blocks with Meaning, Nuance_EN, Nuance_CN, Example1-3, Example1-3_EN

Same approach as Japanese: parallel batches of 200 words, deepseek flash.
- WIP: ~6 batches of 200 words (~18 min)
- Full: ~82 batches of 200 words (~4 hours, can parallelize 3-4 ways → ~1 hour)

## Migration

In-place SQL on `collection.anki2`:
1. Create "Chinese Enhanced" notetype with 11 fields + template
2. Backup collection
3. For each Chinese note, build 11-segment flds
4. UPDATE mid + flds using LLM data
5. Move unmatched notes to "Chinese (Old)" deck
6. Move Chinese WIP cards to Chinese deck

## Key Differences from Japanese

| Aspect | Japanese | Chinese |
|--------|----------|---------|
| Reading format | Ruby `漢字[かんな]` | Pinyin `tǐyùguǎn` |
| Font | Noto Sans CJK JP | Noto Sans CJK SC |
| Nuance field | EN + JP | EN + CN |
| Card count | ~27,000 | ~16,000 |
| Pinyin already correct | N/A | Yes — keep as-is |
| HTML in meaning | Some | Heavy (1050/1183 WIP cards)