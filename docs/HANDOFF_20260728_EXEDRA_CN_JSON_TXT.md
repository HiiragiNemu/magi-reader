# 2026-07-29 Exedra 中文 JSON/TXT、魔法纪录语音与人工校验交接

> 本文件记录当前本地工作树的实际状态。若旧聊天或旧文档与本文件冲突，以用户最新指令、代码和可复现报告为准。

## 1. 仓库、分支与当前发布状态

- 本地工作目录：`D:\magia\MyProducts\magi-reader-exedra-test`
- 仓库：`HiiragiNemu/magi-reader`
- 开发分支：`feature/exedra-voice-playback-human-localization`
- 基线与最终合并目标：`EXEDRA-TEST`
- `main` 不得修改。
- 当前大批数据、代码和文档改动仍在本地工作树中，尚未完成最终提交、推送、PR、合并。
- `https://magireader-exedra-cn-test.crynetsystemscell.workers.dev/` 尚未部署本轮最终版本。
- 生产 Worker `magireader`、生产 KV 和 `main` 不在本项目的写入范围内。

不得把“本地生成/本地构建成功”表述成“已上线”，也不得在最终检查通过前合并。

## 2. 不可改变的来源政策

Exedra 自动机翻计划已经取消。只允许以下人工来源：

1. 仓库既有中文：保持原样，不覆盖。
2. 能与同角色 `/Story/Japanese` 精确对齐的 Exedra Wiki `/Story/Chinese`。
3. `圆哆啦文本0728.rar` 中的人工文本，仅补充 Wiki 没有可靠覆盖的部分。
4. Exedra Wiki `/Voice/zh` 中能以日文正文或音频文件名精确匹配的中文语音。

核心优先级为：

```text
仓库既有中文 > Exedra Wiki 精确匹配中文 > 0728 人工文本
```

- Wiki 和 0728 都属于人工文本，不得标记为机器翻译。
- Exedra 没有可信中文时继续显示日文，不生成占位中文。
- 禁止 LCS、模糊文件名、模糊角色名、重排或“数量差不多”的强行套用。
- 魔法纪录原有 507 部机器翻译人工校验清单保持独立；Exedra 不进入该清单。

## 3. 0728 包审计与使用结果

本地源文件：

```text
D:\magia\MyProducts\圆哆啦文本0728.rar
```

审计结果：

- RAR5，2,452,430 字节。
- SHA-256：`2f55e92bd8ceb310ba37c7a7b5dd94dffe5849d1266017021ff52366595b572c`
- 642 个归档条目：640 个 `.ass` 文件和 2 个目录。
- 解压后总大小：6,132,347 字节。
- 逐文件路径、大小、SHA-256、编码、行数和对白数已写入：
  `artifacts/source-archives/rounddora-text-0728.files.json`
- 原始 RAR 没有提交进 Git。

角色管线此前精确采用 181 个唯一 ASS。本轮又以显式音视频身份和严格等长事件映射导入 18 组、94 个 JSON、5,820 条事件；其余文本不能简单称为“错误”或“全部未匹配”，其中包括被更高优先级 Wiki 覆盖的文本和无法证明唯一播放脚本身份的文本。

## 4. Exedra 当前中文覆盖

Exedra 日文基线：

- 443 个逻辑剧情组。
- 3,061 个来源 JSON。
- 105,867 条可读文本事件。

当前生成后的目录：

- 中文逻辑组：142 / 443。
- 仍无中文：301 / 443。
- 其中 137 个新生成组具备经验证的中文 JSON、规范 TXT、导入报告和 provenance。
- 5 个旧有本地中文组保留原状，以历史 TXT 兼容方式继续工作，没有被本轮改写。
- 新生成 Exedra 中文 JSON：1,484 个。
- 新生成 JSON 内文本事件：26,810 条。
- `story_index.json` 为 137 个 JSON 支持组发布 `json_paths_cn`。

142 个中文组分布如下：

| 范围 | 已中文 | 总数 | 仍缺 |
|---|---:|---:|---:|
| 主线 | 0 | 51 | 51 |
| 活动 | 6 | 44 | 38 |
| 角色剧情 | 53 | 61 | 8 |
| 肖像 | 10 | 54 | 44 |
| Exedra 语音 | 73 | 86 | 13 |
| Namae | 0 | 105 | 105 |
| 过场动画字幕 | 0 | 41 | 41 |
| 战斗 | 0 | 1 | 1 |
| 全部 Exedra | 142 | 443 | 301 |

### 4.1 角色剧情来源分布

53 个角色组由以下部分组成：

- 5 个旧有本地中文组；
- 6 个纯 Wiki 组；
- 17 个纯 0728 组；
- 25 个 Wiki + 0728 混合组。

按实际 JSON 来源计数：

- Wiki：187 个 JSON、9,048 条事件、覆盖 31 个角色组；
- 0728：197 个 JSON、9,762 条事件、覆盖 42 个角色组；
- 两种来源在 25 个组内按 Episode/Section 精确混合，因此组数不能直接相加。

角色剧情采用同角色 `/Story/Japanese` 作为锚点，对显示文本执行 NFKC、显示/注音规范化和唯一顺序匹配。只有可以证明为唯一的 1↔N 顺序映射才导入；没有模糊匹配和重排。

仍被安全拒绝的 8 个角色组：

```text
character_darc
character_felicia
character_hanna
character_kyoko
character_mami
character_nagisa
character_reira
character_sayaka
```

这些拒绝是安全边界的一部分，不得为了提高数字强行填充。

### 4.2 Exedra Wiki 中文语音

已审计：

- 158 个 `/Voice/zh` 页面；
- 2,990 行 Wiki 语音；
- 2,987 个唯一音频文件名；
- 成功生成 73 / 86 个 Exedra reaction 语音组；
- 1,022 个 JSON、2,938 条事件。

`Lux☆Magica/Voice/zh`：

- 页面提供 62 个可信行；
- 其中 14 行被 `cv_100101` 精确使用；
- 使用日文正文/音频文件名匹配，不以中文行数硬套；
- 已支持经过证明的 `cv_100803 → cv_100805` 文件身份别名。

13 个拒绝组及原因：

- Wiki 对应中文行为空：`cv_100106`、`cv_100301`、`cv_100403`、`cv_111501`、`cv_111601`、`cv_111701`、`cv_113301`、`cv_113801`。
- 找不到完全一致的音频文件名：`cv_113401`、`cv_113501`、`cv_113601`、`cv_114801`。
- 日文正文不完全一致：`cv_100401` 的 `聴けて` / `聞けて`。

报告：

- `artifacts/exedra_wiki_voice_import_report.json`
- `artifacts/exedra_wiki_voice_character_match_report.json`
- `artifacts/exedra_human_text_import_report.json`

## 5. 可播放 JSON 必须先于 TXT

所有新 Exedra 中文遵守同一规则：

1. 日文 JSON 是结构模板。
2. 只替换已经证明对应的玩家可见文本。
3. 保留动作、资源 ID、角色 ID、音频、等待、镜头、分支、sheet/row 和全部非文本字段。
4. 校验来源文件名、事件数、`ActionType`、说话人顺序、结构哈希和中文来源证明。
5. 中文 JSON 全部通过后，再从 JSON 生成规范 `<groupKey>_cn.txt`。
6. 生成 schema-v1 导入报告和 provenance。
7. 任一组失败时事务回滚，不留下半成品。

`generate_story_index.py` 在发布中文 JSON 时再次校验：

- Exedra manifest 中的完整 `source_names`；
- 导入报告的来源顺序、哈希和事件数；
- JP/CN 可读事件数、`ActionType` 和说话人顺序；
- 公开 JSON 路径必须安全且唯一。

当前 `website/public/story_index.json`：

- 总条目：3,012。
- Exedra：443，其中中文 142。
- 为 137 个新 Exedra 中文组发布 JSON 路径。
- 为 410 个魔法纪录 general voice 条目发布 JSON 路径。
- 公开中文 JSON 总数：1,894（Exedra 1,484 + general voice 410）。

## 6. 魔法纪录 general voice

新分类：

```text
general_voice → 语音
```

已经静态落盘并纳入目录：

- 410 个有效模型；上游 `xxxx.json` 无效占位文件被拒绝。
- 16,753 个语音组。
- manifest 中 18,233 条语音。
- 9,107 个 `textHome` 文本事件。
- 8,727 个可编辑组：
  - 8,412 个单 `textHome`；
  - 315 个多 `textHome`，现在按一个事件一行处理。
- 8,026 个没有 `textHome` 的资源/动作组保持只读，不伪造中文文本。

多 `textHome` 修复重建了 26 个模型 TXT。源清单与中文清单内容一致，SHA-256 都是：

```text
260fe3d38df77e9d220d20c23e63081fcc146389e4d8a5f7dbad5da76e49f89d
```

每个模型发布：

```text
/data/general_voice/<modelId>/<modelId>_cn.txt
/data/general_voice/<modelId>/<modelId>_cn.json
```

### 6.1 语音播放

- Exedra 86 个 reaction 组均获得可读角色/形态名称，1,167 个来源脚本均精确映射到同名音频资源。
- Exedra 优先使用受审计的本地 OGG；其余使用固定 Exedra Wiki 文件重定向，不接受任意外部 URL。
- 魔法纪录通过同源、限长的服务端代理读取固定 R2 HCA；浏览器在独立 Worker 中解码，单文件和时长均有硬上限。
- 播放器全站只允许一个活动音频，切换剧情、停止或组件卸载都会释放对象 URL、音频节点和解码 Worker。
- 本地外部 Chrome 已实际播放 Exedra 远端语音、Exedra 本地特殊语音和魔法纪录 HCA 三条链路。

## 7. 人工校验的 JSON + TXT 双产物

魔法纪录剧情、魔法纪录 general voice 和 Exedra 都已接入同一 fail-closed 物化器：

```text
scripts/materialize_proofreading_assets.py
```

重要语义：

- 审核后的 TXT 只是人工输入文档，不是结构来源。
- 物化器从目标分支的中文 JSON或日文 JSON读取结构模板。
- 只更新可见文本和经过允许的显示名。
- 先生成并验证可播放 JSON，再从该 JSON 重新生成规范 TXT。
- 使用 `--base-ref` 时，结构模板从 PR 基线读取，防止投稿夹带未审核 JSON 结构改动。
- 产物和报告作为一个可回滚事务写入。

`scripts/apply_proofreading_submission.py` 已在应用投稿时直接调用物化器。社区校对 PR 的流程是：

1. 初始 PR 只允许一个规范 TXT 输入；
2. CI 验证改动范围；
3. 物化可播放 JSON；
4. 从 JSON 重建规范 TXT；
5. 生成校验报告，并在 general voice 情况下同步两个 manifest 哈希；
6. 将严格限定的产物提交回同一个 PR；
7. 再运行 Python、目录生成、机翻清单、Lint、TypeScript、网站测试、搜索构建和 Worker 构建。

general voice 的校验变更严格限制为 5 个文件：模型 JSON、模型 TXT、校验报告、源 manifest、中文 manifest。

## 8. 中日对照布局

阅读器与“协助汉化”共用：

```text
magi-reader-bilingual-layout-v1
```

可选项：

- `左右排列`
- `上下排列`

PC 可以手动选择两种模式并写入 `localStorage`；手机端为避免双栏挤压始终采用上下排列。该选择同时作用于普通阅读和编辑输入行，不改变 Section、差异高亮或投稿文本结构。

本地浏览器已经确认：

- 设置面板显示两种排列选项；
- Magia Record 侧栏出现“语音”；
- Exedra 分类显示为 `主线、活动、角色、肖像、语音、Namae、过场动画字幕、战斗`；
- 分类没有数字前缀；
- Exedra 目录显示活动 6、角色 53、肖像 10、语音 73 个有中文；
- 修复后静态 Exedra 中文直接读取经验证的 public TXT，不再错误依赖本地不可用的 Cloudflare KV API；
- 环彩羽 Exedra 中文/日文内容可以在本地阅读器中加载。

最后一次“上下排列 + 协助汉化”点击验收和完整质量门重跑已经完成。

## 9. 本地验证记录

已经完成：

- 完整 `generate_story_index.py` 生成。
- Python 检查：167 通过，2 跳过。
- `npm ci`。
- 最终 `npm run check`：feature policy 97 项、Python 167 通过/2 跳过、ESLint、TypeScript、120 个 Node 测试、生产依赖审计全部通过。
- 搜索生成和一致性校验：3,012 个目录条目、5,260 个搜索条目。
- 最后一次静态 Exedra 中文路由修复后，OpenNext Worker 构建和 Cloudflare 输出验证通过。
- 本地外部 Chrome 完成主要目录、分类、中文加载、上下排列、普通阅读、汉化编辑、三条语音播放链和 1,642 行剧情分页验收；浏览器无错误或意外警告。

未完成：

- 提交、推送、PR、合并；
- 测试 Worker 真实部署和线上烟雾测试。

## 10. 搜索索引现状

本地搜索内容已生成并验证：

- 搜索条目：5,260。
- payload：79,334,357 字节，按 1 MiB 分成 76 块流式校验和解析。
- 对象键：
  `search/21cfaee1042d0e21eb5a03ca666f6f84f2b79cb7c16632465f7f40c4ded518d2.json`

当前 Cloudflare 凭据没有 R2 权限，因此该对象尚未上传。目录、标题搜索和剧情阅读不依赖此次 R2 上传；全文正文搜索是否可用必须在部署后单独报告，不得误报。

## 11. 最终发布顺序

1. 完成本地上下排列/编辑模式点击验收。
2. 重跑完整检查、Worker 构建与直接部署 dry-run。
3. 审计 Git 差异，确认没有秘密、临时文件、既有人工语料覆盖或生产配置。
4. 提交并推送 `feature/exedra-voice-playback-human-localization`。
5. 建立目标为 `EXEDRA-TEST` 的 PR，等待全部 CI。
6. 以 squash 方式合并，避免把长期开发分支的历史噪音带入目标分支。
7. 部署固定测试 Worker `magireader-exedra-cn-test`。
8. 在线验证目录、142 个 Exedra 中文组、410 个 general voice、语音播放、JSON/TXT、布局、校验 API 和魔法纪录 507 部机翻清单。
9. 确认 `main` SHA、生产 Worker 和生产 KV 均未变化。

当前文档不得勾选第 4～9 步为完成。
