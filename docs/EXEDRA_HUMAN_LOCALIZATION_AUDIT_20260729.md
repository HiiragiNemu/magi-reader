# Exedra 人工中文化与 0728 文本安全导入审计

- 生成日期：2026-07-29
- 工作分支：`feature/exedra-voice-playback-human-localization`
- 数据范围：Exedra manifest 的 443 个逻辑组、当前 `story_index.json`、Exedra Wiki 人工中文、圆哆啦文本 0728 人工字幕包
机器翻译：未使用；本轮产物全部为 `machineTranslation=false`

## 1. 结论摘要

- Exedra 当前共有 **443** 个逻辑剧情/语音组。
- 当前可读取中文 TXT 的逻辑组为 **142**，剩余 **301**。
- 本轮从 Exedra Wiki 与圆哆啦文本 0728 中安全新增 **18** 个中文组：
  - 活动：6 组；
  - 肖像：10 组；
  - 角色：2 组。
- 本轮共生成：
  - **94** 个可播放中文 JSON；
  - **18** 个聚合中文 TXT；
  - **18** 个导入验证报告；
  - **18** 个来源侧车；
  - 合计 **148** 个新文件。
- 本轮覆盖 **5,820** 条可播放文本事件：
  - 活动与肖像严格 A 类：5,062 条；
  - 角色 `character_kush` 与 `character_meru`：758 条。
- 每个生成 JSON 都以日文 JSON 为结构模板，只替换可播放文本事件的 `Comment`；`Name`、`ActionType`、资源键、行号、工作表、动作及其他字段均保持不变。
- 18 组全部通过 Section、来源 JSON、文本事件数、说话人顺序、JSON/TXT 顺序和播放器结构校验。
- 日文源目录修改数为 0；既有受跟踪中文文件修改数为 0；现有中文组没有被覆盖。
- 最终四类剧情导入复扫结果为：

  ```text
  existing_local：69
  rejected：141
  failed：0
  ```

  其中 69 个已有中文组等于本轮前的 51 个角色组加本轮新增 18 组。另有 73 个中文语音组来自独立的 Exedra Wiki 语音导入，因此 `story_index.json` 中的 Exedra 中文总数为 142。

## 2. 443 组最终中文覆盖总账

以下数字直接按当前 `website/public/story_index.json` 中 `game=exedra` 的 443 条记录统计。

| 内部分类 | 页面名称 | 总数 | 已有中文 | 剩余 |
|---|---|---:|---:|---:|
| `exedra_main` | 主线 | 51 | 0 | 51 |
| `exedra_sub` | 活动 | 44 | 6 | 38 |
| `exedra_character` | 角色 | 61 | 53 | 8 |
| `exedra_portrait` | 肖像 | 54 | 10 | 44 |
| `exedra_reaction` | 语音 | 86 | 73 | 13 |
| `exedra_namae` | Namae | 105 | 0 | 105 |
| `exedra_dungeon` | 过场动画字幕 | 41 | 0 | 41 |
| `exedra_battle` | 战斗 | 1 | 0 | 1 |
| **合计** |  | **443** | **142** | **301** |

说明：

- 本轮 0728 剧情导入器只处理 `Main/Sub/Character/Portrait`；语音的 73 组中文来自独立的 Wiki 语音流程。
- `Namae`、过场动画字幕和战斗当前没有满足可信来源与结构证明的中文组，因此仍为 0。
- 本轮新增的 18 个组已全部出现在 `story_index.json`，`has_cn=true`，并具有规范 `/data/exedra_*/*/*_cn.txt` 路径。

## 3. 本轮实际导入的 18 组

### 3.1 活动：6 组

| `groupKey` | JSON | 文本事件 | 来源 | 中文 TXT |
|---|---:|---:|---|---|
| `sub_1stanniv` | 4 | 236 | 0728 人工字幕 | `/data/exedra_sub/sub_1stanniv/sub_1stanniv_cn.txt` |
| `sub_annameru` | 8 | 835 | 0728 人工字幕 | `/data/exedra_sub/sub_annameru/sub_annameru_cn.txt` |
| `sub_asakokoito` | 8 | 831 | 0728 人工字幕 | `/data/exedra_sub/sub_asakokoito/sub_asakokoito_cn.txt` |
| `sub_mannenzakura` | 24 | 956 | 0728 人工字幕 | `/data/exedra_sub/sub_mannenzakura/sub_mannenzakura_cn.txt` |
| `sub_valentine2026` | 5 | 217 | 0728 人工字幕 | `/data/exedra_sub/sub_valentine2026/sub_valentine2026_cn.txt` |
| `sub_yakumomitama` | 9 | 796 | 0728 人工字幕 | `/data/exedra_sub/sub_yakumomitama/sub_yakumomitama_cn.txt` |
| **小计** | **58** | **3,871** |  |  |

### 3.2 肖像：10 组

| `groupKey` | JSON | 文本事件 | 来源 | 中文 TXT |
|---|---:|---:|---|---|
| `portrait_Newyear2026_madoka` | 2 | 129 | 0728 人工字幕 | `/data/exedra_portrait/portrait_Newyear2026_madoka/portrait_Newyear2026_madoka_cn.txt` |
| `portrait_annameru` | 2 | 129 | 0728 人工字幕 | `/data/exedra_portrait/portrait_annameru/portrait_annameru_cn.txt` |
| `portrait_asakokoito` | 2 | 99 | 0728 人工字幕 | `/data/exedra_portrait/portrait_asakokoito/portrait_asakokoito_cn.txt` |
| `portrait_magirekozero1` | 2 | 119 | 0728 人工字幕 | `/data/exedra_portrait/portrait_magirekozero1/portrait_magirekozero1_cn.txt` |
| `portrait_magirekozero3` | 2 | 149 | 0728 人工字幕 | `/data/exedra_portrait/portrait_magirekozero3/portrait_magirekozero3_cn.txt` |
| `portrait_mannenzakura` | 2 | 104 | 0728 人工字幕 | `/data/exedra_portrait/portrait_mannenzakura/portrait_mannenzakura_cn.txt` |
| `portrait_snowdome_ren` | 2 | 99 | 0728 人工字幕 | `/data/exedra_portrait/portrait_snowdome_ren/portrait_snowdome_ren_cn.txt` |
| `portrait_tart1` | 2 | 141 | 0728 人工字幕 | `/data/exedra_portrait/portrait_tart1/portrait_tart1_cn.txt` |
| `portrait_tart2` | 2 | 112 | 0728 人工字幕 | `/data/exedra_portrait/portrait_tart2/portrait_tart2_cn.txt` |
| `portrait_yakumomitama` | 2 | 110 | 0728 人工字幕 | `/data/exedra_portrait/portrait_yakumomitama/portrait_yakumomitama_cn.txt` |
| **小计** | **20** | **1,191** |  |  |

### 3.3 角色：2 组

| `groupKey` | JSON | 文本事件 | 来源 | 中文 TXT |
|---|---:|---:|---|---|
| `character_kush` | 8 | 486 | Wiki + 0728 人工文本，逐 Episode 选择可信高优先级来源 | `/data/exedra_character/character_kush/character_kush_cn.txt` |
| `character_meru` | 8 | 272 | Wiki + 0728 人工文本，逐 Episode 选择可信高优先级来源 | `/data/exedra_character/character_meru/character_meru_cn.txt` |
| **小计** | **16** | **758** |  |  |

## 4. 采用的安全边界

来源优先级固定为：

1. 仓库已有人工中文；
2. 具有精确日文 Wiki/本地 JSON 锚点的 Exedra Wiki 中文；
3. 用户授权的圆哆啦文本 0728 人工字幕；
4. 证据不足时拒绝整个逻辑组。

0728 的非角色字幕必须同时满足：

- 本地日文 JSON 与 Exedra Wiki 日文页面具有唯一、完整的正文锚点；
- `ASS_STORY_FILES` 中存在显式故事映射；
- ASS 具有 `Video File` 或 `Audio File` 身份元数据；
- ASS 与目标 JSON 的文本事件数完全相等；
- 多个 ASS 拼接时，每个文件边界必须落在 JSON Section 边界；
- 整组 JSON、TXT、导入报告和来源侧车全部在暂存目录验证通过后才一次性提交；
- 任一 Section 失败即拒绝整个组，不留下半成品。

本轮没有使用 LCS、模糊匹配、语义猜测、自动补行、删行或重排。

## 5. 为什么 Main 仍为 0

0728 包中确实存在看起来可能与主线有关的字幕，不是“完全没有主线文本”。本轮对 8 个 Main 候选家族、43 个 ASS 文件进行了审计：

| 候选家族 | 文件数 | 可解析事件总数 | 结果 |
|---|---:|---:|---|
| `Opening` | 10 | 187 | 无唯一显式主线组映射 |
| `Tutorial` | 8 | 202 | 仅事件数碰巧等于 `main_scene0_film10`，不能证明内容身份 |
| `Main0` | 6 | 239 | 无唯一显式主线组映射 |
| `Main1` | 1 | 761 | 无唯一显式主线组映射 |
| `MagirecoCapture` | 9 | 无可靠家族总数 | 至少一个文件没有可解析 Dialogue；其余也没有唯一内容锚点 |
| `ChineseMagirecoCapture` | 3 | 74 | 无唯一显式主线组映射 |
| `CrescentMemoriaMain` | 3 | 5,819 | 无唯一显式主线组映射 |
| `TartMain` | 3 | 3,076 | 无唯一显式主线组映射 |

文件名和事件数只能用来否决错误映射，不能证明中文字幕属于某个日文 JSON 组。尤其 `Tutorial` 的 202 条与 `main_scene0_film10` 总数相同只是计数巧合；在没有日文正文锚点、视频身份到 manifest 组的明确关系和 Section 边界证明时直接导入，可能把完整人工译文放进错误剧情。

因此 Main 的安全导入数为 0。要导入这些文件，需要人工逐个确认视频内容、日文台词、目标 `groupKey` 和 Section 对应关系，并形成可审计的显式映射。

## 6. 141 个安全拒绝组

以下六类为互斥的主拒绝原因，合计正好 141 组：

| 主拒绝原因 | 组数 |
|---|---:|
| 没有唯一的日文 Wiki → 本地 JSON 精确映射 | 73 |
| 日文映射唯一，但 Wiki 中文页缺少已证明的 Episode | 49 |
| 日文 Wiki 映射存在歧义 | 3 |
| 显式 0728 ASS 与 JSON 事件数不一致 | 6 |
| ASS 缺少媒体身份元数据 | 2 |
| 角色组内至少一个 Episode 无法安全对齐 | 8 |
| **合计** | **141** |

### 6.1 无唯一日文映射：73 组

这些组无法把某个 Wiki 日文剧情页唯一对应到本地 JSON，因此不会继续套用中文页或 0728 文本。

主线 33 组：

`main_baraen1_prologue`, `main_chelatebigferris`, `main_crisis0`, `main_embryoeve1`, `main_embryoeve2`, `main_embryoeve3`, `main_kurumiwari`, `main_machibitouma`, `main_nanashi`, `main_nightmare`, `main_rakugaki`, `main_scene0_Film13_1`, `main_scene0_Film13_2`, `main_scene0_Film13_3`, `main_scene0_Film2_0`, `main_scene0_film02`, `main_scene0_film02_movie`, `main_scene0_film03`, `main_scene0_film04`, `main_scene0_film05`, `main_scene0_film06`, `main_scene0_film07`, `main_scene0_film08`, `main_scene0_film09`, `main_scene0_film1`, `main_scene0_film10`, `main_scene0_film11`, `main_scene0_film12`, `main_scene0_film14`, `main_scene0_film14_1`, `main_sunaba`, `main_tart2`, `main_walpurgis`

活动 27 组：

`sub_Christmas2025`, `sub_collabo1`, `sub_embryoeve1`, `sub_embryoeve2`, `sub_farewell`, `sub_halloween2025`, `sub_hari`, `sub_machibitouma`, `sub_memories`, `sub_patissier2026`, `sub_scene0_film00`, `sub_scene0_film01`, `sub_scene0_film02`, `sub_scene0_film03`, `sub_scene0_film04`, `sub_scene0_film05`, `sub_scene0_film06`, `sub_scene0_film07`, `sub_scene0_film08`, `sub_scene0_film09`, `sub_scene0_film11`, `sub_scene0_film12`, `sub_scene0_film13`, `sub_scene0_short`, `sub_sunaba`, `sub_sunny`, `sub_swimwear2025`

肖像 13 组：

`portrait_embryoeve3`, `portrait_kurumi_homura`, `portrait_nightmare_bebe`, `portrait_nightmare_mami`, `portrait_scene0_homura`, `portrait_scene0_kyoko`, `portrait_scene0_mabayu`, `portrait_scene0_madoka`, `portrait_scene0_mami`, `portrait_scene0_sayaka`, `portrait_snowdome_rika`, `portrait_swimwear2025_madoka`, `portrait_tsukuyo`

### 6.2 Wiki 中文页缺少已证明的 Episode：49 组

这些组已经找到唯一且完整的 Wiki 日文页，但对应中文页是待翻译占位页、缺少 Episode，或没有覆盖本地 JSON 所需的 Episode。报告中的具体分布为：

- 缺 Episode 1：45 组；
- 缺 Episode 5：1 组；
- 缺 Episode 7：2 组；
- 缺 Episode 9：1 组。

主线 18 组：

`main_baraen1`, `main_baraen2`, `main_geijutsuka`, `main_gin`, `main_hako`, `main_hari`, `main_iincho`, `main_inu`, `main_kage`, `main_kurayami`, `main_magirekozero1`, `main_magirekozero2`, `main_magirekozero3`, `main_maju`, `main_ningyo`, `main_okashi`, `main_tart1`, `main_torikago`

活动 5 组：

`sub_Newyear2026`, `sub_april2025`, `sub_birthday2025_madoka`, `sub_original1`, `sub_snowdome`

肖像 26 组：

`portrait_Christmas2025_kyoko`, `portrait_Christmas2025_sayaka`, `portrait_baraen1`, `portrait_baraen2`, `portrait_chelatebigferris`, `portrait_embryoeve1`, `portrait_geijutsuka`, `portrait_gin`, `portrait_hako`, `portrait_hari`, `portrait_iincho`, `portrait_inu`, `portrait_kage`, `portrait_kurayami`, `portrait_kurumi_kyoko`, `portrait_machibitouma`, `portrait_maju`, `portrait_nanashi`, `portrait_nightmare_sayaka`, `portrait_ningyo`, `portrait_okashi`, `portrait_rakugaki`, `portrait_sunaba`, `portrait_swimwear2025_sayaka`, `portrait_torikago`, `portrait_walpurgis`

### 6.3 日文 Wiki 映射歧义：3 组

下列组各自能够匹配多个日文页面，不能自动决定应使用哪个页面：

`portrait_halloween2025_arina`, `portrait_halloween2025_mami`, `portrait_swimwear2025_mami`

### 6.4 显式 0728 ASS 与 JSON 事件数不一致：6 组

| `groupKey` | ASS | JSON | 差值 | 处理 |
|---|---:|---:|---:|---|
| `sub_amaneshimai` | 797 | 799 | -2 | 拒绝；缺失位置不能唯一证明 |
| `sub_april2026` | 198 | 197 | +1 | 拒绝；不能猜测删除哪一行 |
| `sub_birthday2025_iroha` | 164 | 167 | -3 | 拒绝；缺失位置不能唯一证明 |
| `sub_chelatebigferris` | 945 | 944 | +1 | 拒绝；不能猜测删除哪一行 |
| `sub_embryoeve3` | 1,136 | 1,129 | +7 | 拒绝；不能猜测删除或合并位置 |
| `portrait_tsukasa` | 114 | 115 | -1 | 拒绝；缺失位置不能唯一证明 |

### 6.5 ASS 缺少媒体身份元数据：2 组

- `portrait_magirekozero2`：`CreMemo2_Bonus.ass` 缺少 `Video File/Audio File`。
- `sub_nanashi`：Bilibili 命名 ASS 缺少 `Video File/Audio File`。

这两个文件即使文件名或事件数看起来接近，也不能只凭猜测绑定到目标剧情。

### 6.6 角色组内 Episode 无法安全对齐：8 组

角色组采用整组事务：只要一个 Episode 无法证明，整个组都不会落盘。

| `groupKey` | 失败 Episode | Wiki / 日文 / JSON / ASS 数量 | 主要原因 |
|---|---|---|---|
| `character_darc` | 1、2 | `-/51/51/50`；`-/53/53/52` | 缺行无法由唯一静默标点位置解释；另一节存在多个等价位置 |
| `character_felicia` | 4 | `64/65/65/64` | Wiki 中文说话人结构无法锚定；ASS 缺口也不唯一 |
| `character_hanna` | 7 | `88/89/89/84` | Wiki 中日存在多个结构对齐；ASS 缺口无法唯一解释 |
| `character_kyoko` | 3、7 | `-/42/42/不可采用`；`-/62/62/61` | Episode 3 的 ASS 缺媒体身份；Episode 7 缺口位置歧义 |
| `character_mami` | 2 | `-/63/63/62` | 静默标点缺口存在多个等价位置 |
| `character_nagisa` | 1 | `-/60/60/72` | ASS 多出 12 行，无法通过日文锚点投影 |
| `character_reira` | 6 | `59/60/60/53` | Wiki 中日结构对齐不唯一；ASS 缺口无法唯一解释 |
| `character_sayaka` | 5 | `-/60/60/61` | ASS 多出 1 行，无法证明应删除的位置 |

补充媒体身份问题：`character_kyoko` 的 `SakuraKyoko3.ass` 也属于“缺少媒体身份元数据”，但在互斥总账中按“角色整组不完整”计数，避免重复统计。

## 7. 后续人工处理建议

### 对 73 个无映射组

1. 人工观看 ASS 对应视频或读取可信日文字幕；
2. 确认唯一目标 `groupKey`；
3. 逐节记录 ASS 文件、视频身份、日文 Wiki URL、日文 Wiki SHA-256、本地 JSON SHA-256 和 Section 映射；
4. 把确认结果加入显式映射，而不是使用文件名相似度或总行数推断；
5. 先 dry-run，再执行 `--write`。

### 对 49 个 Wiki 中文缺 Episode 组

1. 在 Exedra Wiki 中文页补齐与日文页相同的 Episode 标题和正文；
2. 保持每个 Episode 的说话人顺序与文本事件结构；
3. 不要用“待翻译”占位文本；
4. 补齐后重新抓取并由精确日文锚点验证。

### 对 3 个歧义组

需要人工确认正确日文页面。确认依据应包括首尾日文台词、角色顺序、视频标题和本地 JSON Section，而不是只看剧情标题。

### 对 6 个数量不一致组和 8 个角色组

1. 逐行对照视频时间轴、ASS 和日文 JSON；
2. 明确哪些是漏译台词、重复字幕、合并字幕或纯标点事件；
3. 只有缺失/多余位置唯一时才建立顺序映射；
4. 若存在多个等价位置，必须由人工选择并在来源侧车中记录理由；
5. 修正后仍需整组通过 JSON/TXT/播放器结构校验。

### 对缺媒体身份文件

优先恢复原 ASS 工程的 `Video File` 或 `Audio File` 字段。若原文件无法恢复，可以新增独立、人工签署的映射清单，但至少要记录：

- ASS SHA-256；
- 视频或音频文件名及 SHA-256；
- 目标 `groupKey`；
- 日文页面 URL 与 SHA-256；
- 事件数和 Section 边界；
- 人工确认者与日期。

## 8. 报告与哈希

| 文件 | SHA-256 |
|---|---|
| `artifacts/exedra_human_text_import_report.json` | `709831DB46D284FA298171277A06D0AB148D874590D35FD4271A69049EC71B47` |
| `artifacts/exedra_human_text_coverage_report.json` | `709831DB46D284FA298171277A06D0AB148D874590D35FD4271A69049EC71B47` |
| `artifacts/source-archives/rounddora-text-0728.files.json` | `B8F1484CA401490BA59927E97F8700D7AF808A5E39DF7E657E9CD93EC761E238` |
| `website/public/story_index.json` | `033E48973777CFBC10F3B984F367D780D36A02A769E91DE7D764FC053B655F9A` |
| `magiraexedra-source-master/Scenarios_full/exedra_manifest.json` | `B58F0410CDA68DE84C256B950BFEC4E4BB646D9EE30737BB0C6FB32DFB2B8AB3` |
| `D:\magia\MyProducts\圆哆啦文本0728.rar` | `2F55E92BD8CEB310BA37C7A7B5DD94DFFE5849D1266017021FF52366595B572C` |

导入实现与定向测试：

- `tools/import_exedra_human_text.py`
- `tests/test_import_exedra_human_text.py`
- 定向测试：25/25 通过
- 18 组逐文件结构复验：全部通过
- 审计过程峰值私有内存约 110.2 MiB

## 9. 暂停前状态

- 文本导入进程已经全部退出；
- 当前没有后台 0728 导入任务；
- 没有提交或推送 Git；
- 没有触碰 GitHub Actions、Release、PR 或分支；
- 本 0728 导入子任务没有执行网站部署；最终部署状态以集成主任务的线上验收记录为准；
- 下一阶段应由集成流程重新执行完整数据管线、前端测试、生产构建和隔离测试站部署。
