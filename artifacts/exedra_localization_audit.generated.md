# Exedra 中文化与人工处理清单

> 本文件由 `tools/generate_exedra_localization_audit.py` 确定性生成。

## 总览

| 项目 | 数量 |
|---|---:|
| 逻辑剧情总数 | 443 |
| 台服官方简体化 JSON/TXT | 395 |
| 保留的既有人工中文 | 18 |
| 已有中文合计 | 413 |
| 尚需 Wiki/人工/机器补齐（有可读正文） | 26 |
| 纯结构、无可读正文 | 4 |
| 台服导入失败/缺源记录 | 44 |
| 延后处理的部分来源文件 | 37 |
| 台服独有且当前无日服 organizer 的文件 | 28 |
| 未分类来源文件 | 0 |

## 尚需中文化（有可读正文）

| 来源身份 | 日文事件 | 台服拒绝/缺失理由 |
|---|---:|---|
| `exedra:10_Battle:battle_tart2` | 4 | missing_source: 缺少台服 JSON：10_Battle/battle_tart2_1/battle_tart2_1.json |
| `exedra:1_Main:main_crisis0` | 47 | missing_source: 缺少台服 JSON：1_Main/main_crisis0_3/main_crisis0_3.json；人工来源拒绝：no_exact_wiki_or_0728_candidate |
| `exedra:1_Main:main_magirekozero3` | 1019 | missing_source: 缺少台服 JSON：1_Main/main_magirekozero3_1/main_magirekozero3_1.json；人工来源拒绝：no_exact_wiki_or_0728_candidate |
| `exedra:1_Main:main_nightmare` | 332 | missing_source: 缺少台服 JSON：1_Main/main_nightmare_7/main_nightmare_7 (2).json；人工来源拒绝：no_exact_wiki_or_0728_candidate |
| `exedra:1_Main:main_tart2` | 815 | missing_source: 缺少台服 JSON：1_Main/main_tart2_1/main_tart2_1.json；人工来源拒绝：no_exact_wiki_or_0728_candidate |
| `exedra:2_Sub:sub_april2026` | 148 | missing_source: 缺少台服 JSON：2_Sub/sub_april2026_1/sub_april2026_1.json；人工来源拒绝：no_exact_wiki_or_0728_candidate |
| `exedra:2_Sub:sub_collabo1` | 1626 | missing_source: 缺少台服 JSON：2_Sub/sub_collabo1_1/sub_collabo1_1.json；人工来源拒绝：no_exact_wiki_or_0728_candidate |
| `exedra:3_Character:character_darc` | 180 | missing_source: 缺少台服 JSON：3_Character/character_darc_0/character_darc_0.json；人工来源拒绝：ambiguous_or_unprovable_alignment, rounddora_0728_event_count_or_identity_mismatch, wiki_event_count_or_structure_mismatch |
| `exedra:6_Reaction:cv_111601` | 14 | missing_source: 缺少台服 JSON：6_Reaction/cv_111601_other_evo_fee_01/cv_111601_other_evo_fee_01.json |
| `exedra:6_Reaction:cv_111701` | 14 | missing_source: 缺少台服 JSON：6_Reaction/cv_111701_other_evo_fee_01/cv_111701_other_evo_fee_01.json |
| `exedra:6_Reaction:cv_113401` | 5 | missing_source: 缺少台服 JSON：6_Reaction/cv_113401_1/cv_113401_1.json |
| `exedra:6_Reaction:cv_113501` | 5 | missing_source: 缺少台服 JSON：6_Reaction/cv_113501_1/cv_113501_1.json |
| `exedra:6_Reaction:cv_113601` | 5 | missing_source: 缺少台服 JSON：6_Reaction/cv_113601_1/cv_113601_1.json |
| `exedra:6_Reaction:cv_114801` | 4 | missing_source: 缺少台服 JSON：6_Reaction/cv_114801_1/cv_114801_1.json |
| `exedra:7_Namae:act_lock_tart` | 3 | missing_source: 缺少台服 JSON：7_Namae/act1_lock_tart_02/act1_lock_tart_02.json |
| `exedra:7_Namae:act_open_tart` | 3 | missing_source: 缺少台服 JSON：7_Namae/act2_open_tart_02/act2_open_tart_02.json |
| `exedra:7_Namae:crisis` | 39 | missing_source: 缺少台服 JSON：7_Namae/crisis0_1/crisis0_1.json |
| `exedra:7_Namae:gateopen_episode` | 23 | missing_source: 缺少台服 JSON：7_Namae/gateopen_episode0_03/gateopen_episode0_03.json |
| `exedra:7_Namae:gateopen_tart` | 16 | missing_source: 缺少台服 JSON：7_Namae/gateopen_tart_02/gateopen_tart_02.json |
| `exedra:7_Namae:pp_complete_episode` | 8 | missing_source: 缺少台服 JSON：7_Namae/pp_complete_episode0/pp_complete_episode0.json |
| `exedra:7_Namae:pp_complete_tart` | 8 | missing_source: 缺少台服 JSON：7_Namae/pp_complete_tart/pp_complete_tart.json |
| `exedra:7_Namae:pp_monogatari_episode_nightmare` | 6 | missing_source: 缺少台服 JSON：7_Namae/pp_monogatari_episode0_nightmare_03/pp_monogatari_episode0_nightmare_03.json |
| `exedra:7_Namae:pp_monogatari_episode_normal` | 37 | missing_source: 缺少台服 JSON：7_Namae/pp_monogatari_episode0_normal_03/pp_monogatari_episode0_normal_03.json |
| `exedra:7_Namae:pp_monogatari_tart_nightmare` | 4 | missing_source: 缺少台服 JSON：7_Namae/pp_monogatari_tart_nightmare_02/pp_monogatari_tart_nightmare_02.json |
| `exedra:7_Namae:pp_monogatari_tart_normal` | 34 | missing_source: 缺少台服 JSON：7_Namae/pp_monogatari_tart_normal_02/pp_monogatari_tart_normal_02.json |
| `exedra:7_Namae:story_namae` | 449 | missing_source: 缺少台服 JSON：7_Namae/story_namae13/story_namae13.json |

## 纯结构、无可读正文

- `exedra:1_Main:main_baraen1_prologue`
- `exedra:1_Main:main_scene0_film02_movie`
- `exedra:1_Main:main_scene0_film14_1`
- `exedra:7_Namae:story_prologue`

## 全部台服导入拒绝/缺源记录

- `1_Main/main_crisis0` — `missing_source` — 缺少台服 JSON：1_Main/main_crisis0_3/main_crisis0_3.json
- `1_Main/main_magirekozero3` — `missing_source` — 缺少台服 JSON：1_Main/main_magirekozero3_1/main_magirekozero3_1.json
- `1_Main/main_nightmare` — `missing_source` — 缺少台服 JSON：1_Main/main_nightmare_7/main_nightmare_7 (2).json
- `1_Main/main_tart2` — `missing_source` — 缺少台服 JSON：1_Main/main_tart2_1/main_tart2_1.json
- `2_Sub/sub_1stanniv` — `missing_source` — 缺少台服 JSON：2_Sub/sub_1stanniv_1/sub_1stanniv_1.json
- `2_Sub/sub_april2026` — `missing_source` — 缺少台服 JSON：2_Sub/sub_april2026_1/sub_april2026_1.json
- `2_Sub/sub_collabo1` — `missing_source` — 缺少台服 JSON：2_Sub/sub_collabo1_1/sub_collabo1_1.json
- `3_Character/character_darc` — `missing_source` — 缺少台服 JSON：3_Character/character_darc_0/character_darc_0.json
- `3_Character/character_fuka` — `missing_source` — 缺少台服 JSON：3_Character/character_fuka_0/character_fuka_0.json
- `3_Character/character_liz` — `missing_source` — 缺少台服 JSON：3_Character/character_liz_0/character_liz_0.json
- `3_Character/character_mayoi` — `missing_source` — 缺少台服 JSON：3_Character/character_mayoi_0/character_mayoi_0.json
- `3_Character/character_melissa` — `missing_source` — 缺少台服 JSON：3_Character/character_melissa_0/character_melissa_0.json
- `3_Character/character_senpai` — `missing_source` — 缺少台服 JSON：3_Character/character_senpai_0/character_senpai_0.json
- `3_Character/character_shinobu` — `missing_source` — 缺少台服 JSON：3_Character/character_shinobu_0/character_shinobu_0.json
- `3_Character/character_sumire` — `missing_source` — 缺少台服 JSON：3_Character/character_sumire_0/character_sumire_0.json
- `3_Character/character_yotsugi` — `missing_source` — 缺少台服 JSON：3_Character/character_yotsugi_0/character_yotsugi_0.json
- `4_Portrait/portrait_magirekozero3` — `missing_source` — 缺少台服 JSON：4_Portrait/portrait_magirekozero3_1/portrait_magirekozero3_1.json
- `4_Portrait/portrait_tart2` — `missing_source` — 缺少台服 JSON：4_Portrait/portrait_tart2_1/portrait_tart2_1.json
- `6_Reaction/cv_111601` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_111601_other_evo_fee_01/cv_111601_other_evo_fee_01.json
- `6_Reaction/cv_111701` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_111701_other_evo_fee_01/cv_111701_other_evo_fee_01.json
- `6_Reaction/cv_113401` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_113401_1/cv_113401_1.json
- `6_Reaction/cv_113501` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_113501_1/cv_113501_1.json
- `6_Reaction/cv_113601` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_113601_1/cv_113601_1.json
- `6_Reaction/cv_114401` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_114401_other_evo_fee_01/cv_114401_other_evo_fee_01.json
- `6_Reaction/cv_114501` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_114501_other_evo_fee_01/cv_114501_other_evo_fee_01.json
- `6_Reaction/cv_114601` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_114601_other_evo_fee_01/cv_114601_other_evo_fee_01.json
- `6_Reaction/cv_114801` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_114801_1/cv_114801_1.json
- `6_Reaction/cv_114901` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_114901_other_evo_fee_01/cv_114901_other_evo_fee_01.json
- `6_Reaction/cv_115001` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_115001_other_evo_fee_01/cv_115001_other_evo_fee_01.json
- `6_Reaction/cv_115101` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_115101_other_evo_fee_01/cv_115101_other_evo_fee_01.json
- `6_Reaction/cv_115201` — `missing_source` — 缺少台服 JSON：6_Reaction/cv_115201_other_evo_fee_01/cv_115201_other_evo_fee_01.json
- `7_Namae/act_lock_tart` — `missing_source` — 缺少台服 JSON：7_Namae/act1_lock_tart_02/act1_lock_tart_02.json
- `7_Namae/act_open_tart` — `missing_source` — 缺少台服 JSON：7_Namae/act2_open_tart_02/act2_open_tart_02.json
- `7_Namae/crisis` — `missing_source` — 缺少台服 JSON：7_Namae/crisis0_1/crisis0_1.json
- `7_Namae/gateopen_episode` — `missing_source` — 缺少台服 JSON：7_Namae/gateopen_episode0_03/gateopen_episode0_03.json
- `7_Namae/gateopen_tart` — `missing_source` — 缺少台服 JSON：7_Namae/gateopen_tart_02/gateopen_tart_02.json
- `7_Namae/pp_complete_episode` — `missing_source` — 缺少台服 JSON：7_Namae/pp_complete_episode0/pp_complete_episode0.json
- `7_Namae/pp_complete_tart` — `missing_source` — 缺少台服 JSON：7_Namae/pp_complete_tart/pp_complete_tart.json
- `7_Namae/pp_monogatari_episode_nightmare` — `missing_source` — 缺少台服 JSON：7_Namae/pp_monogatari_episode0_nightmare_03/pp_monogatari_episode0_nightmare_03.json
- `7_Namae/pp_monogatari_episode_normal` — `missing_source` — 缺少台服 JSON：7_Namae/pp_monogatari_episode0_normal_03/pp_monogatari_episode0_normal_03.json
- `7_Namae/pp_monogatari_tart_nightmare` — `missing_source` — 缺少台服 JSON：7_Namae/pp_monogatari_tart_nightmare_02/pp_monogatari_tart_nightmare_02.json
- `7_Namae/pp_monogatari_tart_normal` — `missing_source` — 缺少台服 JSON：7_Namae/pp_monogatari_tart_normal_02/pp_monogatari_tart_normal_02.json
- `7_Namae/story_namae` — `missing_source` — 缺少台服 JSON：7_Namae/story_namae13/story_namae13.json
- `10_Battle/battle_tart2` — `missing_source` — 缺少台服 JSON：10_Battle/battle_tart2_1/battle_tart2_1.json

## 延后处理的部分来源文件

- `1_main/main_nightmare_1/main_nightmare_1.json`
- `1_main/main_nightmare_10/main_nightmare_10.json`
- `1_main/main_nightmare_11/main_nightmare_11.json`
- `1_main/main_nightmare_12/main_nightmare_12.json`
- `1_main/main_nightmare_13/main_nightmare_13.json`
- `1_main/main_nightmare_14/main_nightmare_14.json`
- `1_main/main_nightmare_15/main_nightmare_15.json`
- `1_main/main_nightmare_2/main_nightmare_2.json`
- `1_main/main_nightmare_3/main_nightmare_3.json`
- `1_main/main_nightmare_4/main_nightmare_4.json`
- `1_main/main_nightmare_5/main_nightmare_5.json`
- `1_main/main_nightmare_6/main_nightmare_6.json`
- `1_main/main_nightmare_7/main_nightmare_7.json`
- `1_main/main_nightmare_8/main_nightmare_8.json`
- `1_main/main_nightmare_9/main_nightmare_9.json`
- `7_namae/gateopen_episode0_01/gateopen_episode0_01.json`
- `7_namae/gateopen_episode0_02/gateopen_episode0_02.json`
- `7_namae/gateopen_tart_01/gateopen_tart_01.json`
- `7_namae/pp_monogatari_episode0_nightmare_01/pp_monogatari_episode0_nightmare_01.json`
- `7_namae/pp_monogatari_episode0_nightmare_02/pp_monogatari_episode0_nightmare_02.json`
- `7_namae/pp_monogatari_episode0_normal_01/pp_monogatari_episode0_normal_01.json`
- `7_namae/pp_monogatari_episode0_normal_02/pp_monogatari_episode0_normal_02.json`
- `7_namae/pp_monogatari_tart_nightmare_01/pp_monogatari_tart_nightmare_01.json`
- `7_namae/pp_monogatari_tart_normal_01/pp_monogatari_tart_normal_01.json`
- `7_namae/story_namae00/story_namae00.json`
- `7_namae/story_namae01/story_namae01.json`
- `7_namae/story_namae02/story_namae02.json`
- `7_namae/story_namae03/story_namae03.json`
- `7_namae/story_namae04/story_namae04.json`
- `7_namae/story_namae05/story_namae05.json`
- `7_namae/story_namae06/story_namae06.json`
- `7_namae/story_namae07/story_namae07.json`
- `7_namae/story_namae08/story_namae08.json`
- `7_namae/story_namae09/story_namae09.json`
- `7_namae/story_namae10/story_namae10.json`
- `7_namae/story_namae11/story_namae11.json`
- `7_namae/story_namae12/story_namae12.json`

## 台服独有、当前无日服 organizer 的文件

- `2_sub/sub_100memorial_1/sub_100memorial_1.json`
- `2_sub/sub_100memorial_2/sub_100memorial_2.json`
- `2_sub/sub_100memorial_3/sub_100memorial_3.json`
- `2_sub/sub_100memorial_4/sub_100memorial_4.json`
- `2_sub/sub_100memorial_5/sub_100memorial_5.json`
- `2_sub/sub_100memorial_6/sub_100memorial_6.json`
- `2_sub/sub_100memorial_7/sub_100memorial_7.json`
- `2_sub/sub_100memorial_8/sub_100memorial_8.json`
- `4_portrait/portrait_hangyaku_homura_1/portrait_hangyaku_homura_1.json`
- `4_portrait/portrait_hangyaku_homura_2/portrait_hangyaku_homura_2.json`
- `4_portrait/portrait_hangyaku_mami_1/portrait_hangyaku_mami_1.json`
- `4_portrait/portrait_hangyaku_mami_2/portrait_hangyaku_mami_2.json`
- `4_portrait/portrait_kurumiwari_1/portrait_kurumiwari_1.json`
- `4_portrait/portrait_kurumiwari_2/portrait_kurumiwari_2.json`
- `4_portrait/portrait_nightmare_1/portrait_nightmare_1.json`
- `4_portrait/portrait_nightmare_2/portrait_nightmare_2.json`
- `6_reaction/test_madoka_kakusei_1/test_madoka_kakusei_1.json`
- `6_reaction/test_madoka_kakusei_2/test_madoka_kakusei_2.json`
- `6_reaction/test_madoka_kakusei_3/test_madoka_kakusei_3.json`
- `6_reaction/test_madoka_kakusei_4/test_madoka_kakusei_4.json`
- `6_reaction/test_madoka_kakusei_5/test_madoka_kakusei_5.json`
- `6_reaction/test_madoka_kakusei_6/test_madoka_kakusei_6.json`
- `6_reaction/test_madoka_kakusei_7/test_madoka_kakusei_7.json`
- `7_namae/contents_tutorial_gve_1/contents_tutorial_gve_1.json`
- `7_namae/contents_tutorial_gve_2/contents_tutorial_gve_2.json`
- `7_namae/contents_tutorial_gvg_1/contents_tutorial_gvg_1.json`
- `7_namae/contents_tutorial_gvg_2/contents_tutorial_gvg_2.json`
- `7_namae/map_chubossclose/map_chubossclose.json`

## 0728 主线候选家族拒绝记录

- `Opening` — `rejected_no_unique_explicit_main_mapping` — 事件数只能作为否决条件，不能证明字幕对应剧情；该 ASS 家族没有唯一的日文正文锚点和显式主线组映射。
- `Tutorial` — `rejected_no_unique_explicit_main_mapping` — 事件数只能作为否决条件，不能证明字幕对应剧情；该 ASS 家族没有唯一的日文正文锚点和显式主线组映射。
- `Main0` — `rejected_no_unique_explicit_main_mapping` — 事件数只能作为否决条件，不能证明字幕对应剧情；该 ASS 家族没有唯一的日文正文锚点和显式主线组映射。
- `Main1` — `rejected_no_unique_explicit_main_mapping` — 事件数只能作为否决条件，不能证明字幕对应剧情；该 ASS 家族没有唯一的日文正文锚点和显式主线组映射。
- `MagirecoCapture` — `rejected_no_unique_explicit_main_mapping` — 事件数只能作为否决条件，不能证明字幕对应剧情；该 ASS 家族没有唯一的日文正文锚点和显式主线组映射。
- `ChineseMagirecoCapture` — `rejected_no_unique_explicit_main_mapping` — 事件数只能作为否决条件，不能证明字幕对应剧情；该 ASS 家族没有唯一的日文正文锚点和显式主线组映射。
- `CrescentMemoriaMain` — `rejected_no_unique_explicit_main_mapping` — 事件数只能作为否决条件，不能证明字幕对应剧情；该 ASS 家族没有唯一的日文正文锚点和显式主线组映射。
- `TartMain` — `rejected_no_unique_explicit_main_mapping` — 事件数只能作为否决条件，不能证明字幕对应剧情；该 ASS 家族没有唯一的日文正文锚点和显式主线组映射。

## 输入证据

- manifest: `magiraexedra-source-master/Scenarios_full/exedra_manifest.json` — SHA-256 `b58f0410cda68de84c256b950bfec4e4bb646d9ee30737bb0c6fb32dfb2b8ab3`
- officialTwReport: `artifacts/exedra_official_tw_import_report.json` — SHA-256 `5543dc57f59379f84e6aacf48cdc12f427baf106879a677491063f91868f816d`
- officialTwMetadata: `artifacts/tw_official_metadata.generated.json` — SHA-256 `5e1d7d88b7ac8456858cd5235422b11af6cf21224aecaa1351622cc6bc73a938`
- storyIndex: `website/public/story_index.json` — SHA-256 `10193fb28f142e0481a23ca3e757eefefe533d905498e21fc349c2e27d50252d`
- humanSourceChecklist: `artifacts/exedra_human_processing_checklist_20260802.json` — SHA-256 `46134ab80e3faa6543a03bcf1c8d62a313b24de7151f2ae3d023c660d2efaebe`
