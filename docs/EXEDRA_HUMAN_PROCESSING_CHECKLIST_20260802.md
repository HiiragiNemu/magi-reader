# Exedra 人工中文处理与待办清单（2026-08-02）

本清单只采用本地既有人工文本、Exedra Wiki 人工中文与圆哆啦 0728 人工字幕；机器翻译已关闭。任何无法由剧情身份、日文锚点、事件数量和顺序共同证明的候选均保留为人工待办。

## 当前可播放覆盖

| 分类 | 总组 | 已有中文 JSON/TXT | 剩余 |
|---|---:|---:|---:|
| 主线 (`1_Main`) | 51 | 0 | 51 |
| 活动 (`2_Sub`) | 44 | 6 | 38 |
| 角色 (`3_Character`) | 61 | 53 | 8 |
| 肖像 (`4_Portrait`) | 54 | 10 | 44 |
| 语音 (`6_Reaction`) | 86 | 73 | 13 |
| Namae (`7_Namae`) | 105 | 0 | 105 |
| 过场动画字幕 (`8_Dungeon`) | 41 | 0 | 41 |
| 战斗 (`10_Battle`) | 1 | 0 | 1 |

**总计：443 组；已有可播放中文 JSON/TXT 142 组；剩余 301 组。**

## 0728 与 Wiki 核验结论

- 0728 包盘点：640 个文件，6132347 字节。
- 明确剧情映射：28 组。主线候选 8 个家族 / 43 个文件，因缺少唯一日文正文锚点，接受 0 组。
- 核心主线/活动/角色/肖像审计：69 组已有人工中文，141 组保留人工待办。
- 其中 133 组没有精确 Wiki 或 0728 候选；8 组存在数量、身份或结构歧义，逐条列于下表。
- Exedra Wiki 语音：已接受 73 组；剩余拒绝 13 组、132 个来源，均保留人工处理。

## 数量或结构不一致的 8 组

| 剧情组 | 分类 | 具体拒绝证据 |
|---|---|---|
| `character_darc` | 角色 | character_darc_1.json: JSON=51，Wiki-JP=51，0728 Tart1.ass=50，ass:ASS 缺口不能由逐项精确匹配的静默标点事件解释<br>character_darc_2.json: JSON=53，Wiki-JP=53，0728 Tart2.ass=52，ass:ASS 的静默标点缺口存在多个等价位置，拒绝猜测 |
| `character_felicia` | 角色 | character_felicia_4.json: JSON=65，Wiki-CN=64，Wiki-JP=65，0728 MitsukiFelicia4.ass=64，wiki:中文 Wiki 行无法按说话人结构锚定日文 Wiki；ass:ASS 缺口不能由逐项精确匹配的静默标点事件解释 |
| `character_hanna` | 角色 | character_hanna_7.json: JSON=89，Wiki-CN=88，Wiki-JP=89，0728 SarasaHanna7.ass=84，wiki:中文 Wiki 与日文 Wiki 存在多个结构对齐，拒绝猜测；ass:ASS 缺口不能由逐项精确匹配的静默标点事件解释 |
| `character_kyoko` | 角色 | character_kyoko_3.json: JSON=42，Wiki-JP=42，0728 SakuraKyoko3.ass=0，ass:0728 ASS 缺少 Video File/Audio File 身份元数据，拒绝只凭文件名和行数导入：SakuraKyoko3.ass<br>character_kyoko_7.json: JSON=62，Wiki-JP=62，0728 SakuraKyoko7.ass=61，ass:ASS 的静默标点缺口存在多个等价位置，拒绝猜测 |
| `character_mami` | 角色 | character_mami_2.json: JSON=63，Wiki-JP=63，0728 TomoeMami2.ass=62，ass:ASS 的静默标点缺口存在多个等价位置，拒绝猜测 |
| `character_nagisa` | 角色 | character_nagisa_1.json: JSON=60，Wiki-JP=60，0728 MomoeNagisa1.ass=72，ass:ASS 数量无法由日文 Wiki 精确锚点证明：ASS 72 / Wiki 60 / JSON 60 |
| `character_reira` | 角色 | character_reira_6.json: JSON=60，Wiki-CN=59，Wiki-JP=60，0728 IbukiReira6.ass=53，wiki:中文 Wiki 与日文 Wiki 存在多个结构对齐，拒绝猜测；ass:ASS 缺口不能由逐项精确匹配的静默标点事件解释 |
| `character_sayaka` | 角色 | character_sayaka_5.json: JSON=60，Wiki-JP=60，0728 MikiSayaka5.ass=61，ass:ASS 数量无法由日文 Wiki 精确锚点证明：ASS 61 / Wiki 60 / JSON 60 |

## 没有精确候选的 133 组

以下剧情在当前快照中没有可由日文锚点证明的 Wiki/0728 中文候选，需补充人工文本或显式映射：

```text
main_baraen1  main_baraen1_prologue  main_baraen2  main_chelatebigferris  main_crisis0  main_embryoeve1  main_embryoeve2  main_embryoeve3
main_geijutsuka  main_gin  main_hako  main_hari  main_iincho  main_inu  main_kage  main_kurayami
main_kurumiwari  main_machibitouma  main_magirekozero1  main_magirekozero2  main_magirekozero3  main_maju  main_nanashi  main_nightmare
main_ningyo  main_okashi  main_rakugaki  main_scene0_film1  main_scene0_film02  main_scene0_Film2_0  main_scene0_film02_movie  main_scene0_film03
main_scene0_film04  main_scene0_film05  main_scene0_film06  main_scene0_film07  main_scene0_film08  main_scene0_film09  main_scene0_film10  main_scene0_film11
main_scene0_film12  main_scene0_Film13_1  main_scene0_Film13_2  main_scene0_Film13_3  main_scene0_film14  main_scene0_film14_1  main_sunaba  main_tart1
main_tart2  main_torikago  main_walpurgis  sub_amaneshimai  sub_april2025  sub_april2026  sub_birthday2025_iroha  sub_birthday2025_madoka
sub_chelatebigferris  sub_Christmas2025  sub_collabo1  sub_embryoeve1  sub_embryoeve2  sub_embryoeve3  sub_farewell  sub_halloween2025
sub_hari  sub_machibitouma  sub_memories  sub_nanashi  sub_Newyear2026  sub_original1  sub_patissier2026  sub_scene0_film00
sub_scene0_film01  sub_scene0_film02  sub_scene0_film03  sub_scene0_film04  sub_scene0_film05  sub_scene0_film06  sub_scene0_film07  sub_scene0_film08
sub_scene0_film09  sub_scene0_film11  sub_scene0_film12  sub_scene0_film13  sub_scene0_short  sub_snowdome  sub_sunaba  sub_sunny
sub_swimwear2025  portrait_baraen1  portrait_baraen2  portrait_chelatebigferris  portrait_Christmas2025_kyoko  portrait_Christmas2025_sayaka  portrait_embryoeve1  portrait_embryoeve3
portrait_geijutsuka  portrait_gin  portrait_hako  portrait_halloween2025_arina  portrait_halloween2025_mami  portrait_hari  portrait_iincho  portrait_inu
portrait_kage  portrait_kurayami  portrait_kurumi_homura  portrait_kurumi_kyoko  portrait_machibitouma  portrait_magirekozero2  portrait_maju  portrait_nanashi
portrait_nightmare_bebe  portrait_nightmare_mami  portrait_nightmare_sayaka  portrait_ningyo  portrait_okashi  portrait_rakugaki  portrait_scene0_homura  portrait_scene0_kyoko
portrait_scene0_mabayu  portrait_scene0_madoka  portrait_scene0_mami  portrait_scene0_sayaka  portrait_snowdome_rika  portrait_sunaba  portrait_swimwear2025_madoka  portrait_swimwear2025_mami
portrait_swimwear2025_sayaka  portrait_torikago  portrait_tsukasa  portrait_tsukuyo  portrait_walpurgis
```

## 机器可读明细

完整逐组、逐来源拒绝数据：`artifacts/exedra_human_processing_checklist_20260802.json`。原始报告哈希也写入该 JSON，可复核本清单未脱离原始证据。
