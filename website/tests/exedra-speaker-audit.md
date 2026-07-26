# Exedra speaker dictionary audit

Audit source: all 3,061 JSON files below
`D:\magia\Madoka Magica Magia Exedra JP_GL\Resources\Scenarios`.

The audit resolved `ActionType` and `Name` by each sheet's `headerRow.cellList`;
it did not assume fixed column positions. Every JSON file parsed successfully,
and every inspected sheet exposed the required action header.

## Corpus totals

| Action | Rows | Empty/blank Name | Non-empty Name | Unique raw names |
| --- | ---: | ---: | ---: | ---: |
| Talk | 86,551 | 6,737 | 79,814 | 398 |
| OnlyText | 24,013 | 17,819 | 6,194 | 163 |
| Narration | 15,294 | 9,031 | 6,263 | 147 |
| CharacterTalk | 3,162 | 197 | 2,965 | 8 |
| **Total** | **129,020** | **33,784** | **95,236** | **455 normalized names** |

Blank `OnlyText` and `Narration` names are normal and must continue to fall
back to narration. They are not missing character translations.

## Current exact dictionary coverage

| Lookup | Unique names | Dialogue rows |
| --- | ---: | ---: |
| `NAME_TRANSLATE_MAP` | 110 / 455 | 78,190 / 95,236 |
| `SPEAKER_COLOR_MAP` | 63 / 455 | 72,424 / 95,236 |

An unmapped name remains readable: it is displayed unchanged and inherits the
normal text color. Therefore, adding an unverified translation or arbitrary
color would be more harmful than leaving the entry unmapped.

The most frequent exact translation misses are:

| Name | Rows |
| --- | ---: |
| A-Q | 1,774 |
| 夜明すみれ | 1,552 |
| `*UserName` | 1,233 |
| 日暮ふうか | 1,082 |
| 浅古小糸 | 904 |
| 愛生咲笑 | 699 |
| 斧乃木余接 | 677 |
| 和泉十七夜 | 615 |
| 八九寺真宵 | 552 |
| 忍野忍 | 519 |
| 志筑仁美 | 481 |
| 千秋理子 | 374 |
| キューブ | 330 |
| 優木沙々 | 300 |
| 上条恭介 | 295 |

No translations were inferred from spelling alone. This preserves the existing
dictionary's terminology until verified Chinese names are available.

## Source contamination and aliases

- No speaker `Name` contains Exedra `<color>`, `<r>`, or `<size>` markup.
- 11 rows contain `みふゆの母` followed by a carriage return.
- 4 rows contain `やちよの祖母` followed by a carriage return.
- 3 action rows contain only a newline in `Name`; these normalize to blank.
- Internal spacing variants are limited to `ともえ　まみ` (21 rows),
  `みき　さやか` (15 rows), and `志筑 仁美` (10 rows).
- The dictionary contains 415 color keys and 513 translation keys, with no
  duplicate object-literal keys.

`normalizeSpeakerName`, `translateSpeakerName`, and `speakerColorFor` now
handle invisible controls and only reuse whitespace-normalized entries when
the lookup is unambiguous. Unknown names remain unchanged, and unknown colors
remain undefined.
