# Chinese Enhanced Deck: Migration Plan

## Current State

| Property | Value |
|----------|-------|
| Model | "Chinese" (3 fields: Expression, Meaning, Pinyin) |
| Total notes | 16,374 |
| Chinese deck | 15,189 cards |
| Chinese WIP deck | 1,183 cards |
| Model ID | 1351220176888 |

## Current Fields (3)
```
0: Expression  (hanzi, e.g. 体育馆, 回家, 火车站)
1: Meaning     (English, e.g. "Gym", "To go home", "Train Station")
2: Pinyin      (reading, e.g. "tǐyùguǎn", "huí jiā", "huǒchēzhàn")
```

Some Meaning fields already have HTML-wrapped nuance content embedded from Takoboto:
```
"<p>To reserve; to book</p><h3>Nuance</h3><div>预订 is...</div>"
```

## Target: "Chinese Enhanced" Model

Proposed 11 fields (matching Japanese Enhanced structure but with Pinyin instead of ruby):

```
0:  Expression   (hanzi — kept as-is)
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

## Template (CSS inspired by Japanese Enhanced)

```
Card front: {{Expression}} (hanzi in blue header)
Card back:  {{Pinyin}} below the word, then {{Meaning}}, {{Nuance_EN}}, {{Nuance_CN}}, then 3 example groups
```

Copy the Japanese Enhanced styling:
- Blue header (#408cc7)
- Min-height with proper padding
- Separate desktop/Android sizing
- Exgroup dividers with colored nuance text

## Phases

### Phase 1: Create Model
Create "Chinese Enhanced" notetype with 11 fields + template styling.
Model ID: need a new unique integer (e.g. 1756386463854 or similar)

### Phase 2: LLM Batch Generation
Generate a prompt file with all 16,374 Chinese notes:
```
word|pinyin|meaning
```
→ LLM produces: word|clean_meaning|en_nuance|cn_nuance|ex1|ex1_en|ex2|ex2_en|ex3|ex3_en

Same approach as Japanese: parallel batches of 200 words, deepseek flash.
Expected: ~82 batches of 200 words.

### Phase 3: Migration
In-place SQL migration on `collection.anki2`:
1. Backup collection
2. For each Chinese note, build 11-segment flds
3. UPDATE mid + flds
4. Move unmatched notes to "Chinese (Old)" deck
5. Move Chinese WIP cards to Chinese deck

### Phase 4: Verification
- Spot-check cards in Anki
- Verify all fields populated
- Verify review history preserved

## Key Differences from Japanese

| Aspect | Japanese | Chinese |
|--------|----------|---------|
| Reading format | Ruby `漢字[かんな]` | Pinyin `tǐyùguǎn` |
| Text direction | Left-to-right | Left-to-right |
| Font | Noto Sans CJK JP | Noto Sans CJK SC |
| Nuance field | Nuance_EN + Nuance_JP | Nuance_EN + Nuance_CN |
| Card count | ~27,000 | ~16,000 |
| Pinyin already correct | N/A | Yes — keep as-is |

## Estimated Effort
- LLM generation: 82 batches × ~3 min = ~4 hours (can parallelize 3-4 ways → ~1 hour)
- Model creation + migration: 15 min
- Total: ~1-2 hours of wall time