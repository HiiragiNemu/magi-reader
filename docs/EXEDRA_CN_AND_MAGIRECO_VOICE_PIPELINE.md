# Exedra 人工中文与魔法纪录语音生产管线

目标分支：`feature/exedra-cn-and-magireco-voice`，基于并最终合并到 `EXEDRA-TEST`。`main` 不参与写入。

## 1. 可信来源与优先级

Exedra 禁止自动机器翻译。来源顺序固定为：

```text
仓库既有人工中文
  > Exedra Wiki 精确匹配人工中文
  > 圆哆啦 0728 人工文本
```

允许的来源标记：

- `local_human`
- `exedra_wiki_human`
- `rounddora_0728_human`
- `trusted_human_mixed`
- `exedra_wiki_voice_human`
- `official_tw_human`（工具保留，本轮没有实际导入）

以上来源都不得进入机器翻译清单。没有可信中文的 Exedra 组保持日文。

## 2. 角色剧情导入

入口：

```text
tools/import_exedra_human_text.py
tools/import_exedra_wiki_translation.py
```

输入：

- `magiraexedra-source-master/Scenarios_full/exedra_manifest.json`
- 日文来源 JSON；
- 同角色 Exedra Wiki `/Story/Japanese` 和 `/Story/Chinese`；
- 已审计的 0728 ASS 清单。

安全映射规则：

1. 角色身份必须显式确定。
2. Wiki 中文必须由同角色日文 Wiki 页面作锚点。
3. 比较文本先做 NFKC、显示/注音规范化。
4. 只接受唯一、保持顺序的 1↔N 映射。
5. 标点拆分只能是确定性的，不允许模糊匹配、LCS 或重排。
6. Wiki 命中优先；0728 只补充该 Episode/Section 的空缺。
7. 失败的组完整拒绝，不生成部分目录。

当前结果：

- 61 个角色组中 51 个有中文，10 个安全拒绝。
- 新生成角色组 46 个，另保留 5 个旧本地中文组。
- Wiki：187 个 JSON、9,048 条事件、31 个组。
- 0728：181 个 JSON、9,004 条事件、40 个组。
- 25 个组混合使用两个来源。

## 3. Exedra Wiki 语音导入

入口：

```text
tools/import_exedra_wiki_voice.py
```

来源只接受主命名空间中以 `/Voice/zh` 结尾的页面。匹配依据：

- 日文正文完全一致；或
- 音频文件名完全一致；
- 只有经过显式审计的身份别名才可使用。

Wiki 全量审计：

- 158 页；
- 2,990 行；
- 2,987 个唯一音频文件名。

当前生成：

- 73 / 86 个 reaction 组；
- 1,022 个 JSON；
- 2,938 条事件；
- 13 个组因空中文、缺少精确文件名或日文正文不一致而拒绝。

`Lux☆Magica/Voice/zh` 的 62 行已纳入相同精确策略，其中 14 行用于 `cv_100101`。它不是用于按总行数填充所有缺口的模糊后备源。

## 4. JSON-first 事务

角色剧情和语音都先生产 JSON，再生成 TXT：

```text
日文 JSON 结构模板
  → 只替换已证明的可见文本
  → 校验所有中文 JSON
  → 从中文 JSON 生成规范 TXT
  → 写入导入报告和 provenance
  → 一次事务提交
```

必须保留：

- `ActionType`、资源 ID、角色 ID；
- 动作、音频、等待、镜头和分支；
- sheet、row、Section 和来源文件顺序；
- 所有未知或未来 schema 字段。

任何事件数、动作类型、说话人顺序、来源哈希或路径不一致都会 fail-closed。

`generate_story_index.py` 只在再次验证完整 JSON 集合后将其复制到 `website/public/data`，并在 `story_index.json` 写入 `json_paths_cn`。

## 5. 当前 Exedra 产物

| 指标 | 数量 |
|---|---:|
| JP 逻辑组 | 443 |
| 中文逻辑组 | 124 |
| 仍无中文 | 319 |
| 新 JSON-backed 中文组 | 119 |
| 旧本地 TXT 兼容组 | 5 |
| 新 Exedra 中文 JSON | 1,390 |
| 新 Exedra 中文事件 | 20,990 |

来源组分布：

- 5 个旧本地；
- 6 个纯 Wiki 角色；
- 15 个纯 0728 角色；
- 25 个 Wiki + 0728 混合角色；
- 73 个 Wiki 语音。

## 6. 魔法纪录 general voice

类别键：`general_voice`，显示名：`语音`。

目录：

```text
magireco-voice-source-master/Scenarios_full/general_voice/
magireco-voice-translate-data-master/Scenarios_full/general_voice/
```

入口：

```text
tools/import_magireco_general_voice.py
```

静态快照包含：

- 410 个有效模型；
- 16,753 个语音组；
- 18,233 条 manifest 语音；
- 9,107 个 `textHome` 事件；
- 8,727 个可编辑组；
- 8,026 个没有 `textHome` 的只读资源/动作组。

多 `textHome` 组必须保持一个事件一行，不能合并成一个校对输入。两个 manifest 必须字节一致并随 JSON/TXT 更新哈希。

## 7. 人工校验物化

入口：

```text
scripts/apply_proofreading_submission.py
scripts/materialize_proofreading_assets.py
.github/workflows/community-proofreading-pr.yml
```

适用范围：

- 魔法纪录剧情；
- 魔法纪录 general voice；
- Exedra 中文剧情/语音。

审核后的 TXT 是输入，不是 JSON 结构模板。物化器：

1. 验证剧情目录、目标分支、基准 SHA-256、source identity 和 Section 头；
2. 从目标分支或 `--base-ref` 读取可信 JSON 模板；
3. 只更新允许的文本/说话人显示字段；
4. 生成并校验可播放 JSON；
5. 从 JSON 重建规范 TXT；
6. 生成校验报告；
7. 事务写入并严格限制 PR 路径。

general voice 同步更新源/中文 manifest。CI 会把生成的 JSON、TXT和报告提交回原校对 PR，再运行完整质量门。

## 8. 目录与播放器

当前 `story_index.json`：

- 3,012 个总条目；
- 443 个 Exedra 条目，其中 124 个有中文；
- 410 个 general voice 条目；
- 119 个 Exedra 条目和全部 410 个 general voice 条目具有 `json_paths_cn`。

静态 Exedra 中文优先直接读取经过生成器验证的 public TXT/JSON。只有真正的可信动态 Wiki KV 项才使用 `/api/exedra/localized/<id>`；本地 Next 开发不应因缺少 Cloudflare context 而阻断静态中文。

## 9. 阅读与编辑布局

阅读器设置提供：

- `左右排列`
- `上下排列`

存储键：

```text
magi-reader-bilingual-layout-v1
```

手机和 PC 均可手动切换，选择同时应用于普通阅读和“协助汉化”输入行。

## 10. 分类与机翻边界

Exedra 分类显示：

- 主线
- 活动
- 角色
- 肖像
- 语音
- Namae
- 过场动画字幕
- 战斗

不显示数字前缀。Exedra 没有机器翻译统计、高亮或 AI 生成入口；魔法纪录 507 部、223 个目录的可信机翻清单保持独立。

## 11. 可复现检查

在仓库根目录：

```powershell
python generate_story_index.py
python tools/run_python_checks.py
```

在 `website`：

```powershell
npm ci
npm run check
npm run build:worker
npm run verify:cloudflare-output
npm run deploy:test:direct -- --dry-run
```

最后一次静态 Exedra 路由修复后已经重新完成：143 个 Python 测试、2 个跳过、83 个 Node 测试、完整 lint/type-check/check、生产依赖审计和 Worker 构建。直接部署 dry-run 也已在干净工作树通过，确认 9,029 个静态资源及隔离测试 Worker/KV 绑定。

## 12. 当前非完成项

- 尚未提交、推送、建立 PR 或合并进 `EXEDRA-TEST`。
- 尚未把最终版本部署到 `magireader-exedra-cn-test`。
- 79,001,794 字节全文搜索 payload 尚未上传 R2；当前令牌没有 R2 权限。

这些状态不得在部署完成前改写成“已上线”。
