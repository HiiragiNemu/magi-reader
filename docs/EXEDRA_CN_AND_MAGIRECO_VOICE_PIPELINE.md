# Exedra 中文化与魔法纪录语音管线

目标分支：`feature/exedra-cn-and-magireco-voice`（基于 `EXEDRA-TEST`）。`main` 不参与本项目写入。

## 可信度优先级

Exedra 中文文本按以下顺序选择，低优先级来源不得覆盖高优先级来源：

1. `local_human`：仓库中已经存在且通过现有导入报告验证的中文；保持原样，不标记机翻。
2. `exedra_wiki_human`：Exedra Wiki 的角色中文剧情页；生成 TXT 和导入报告，但不标记机翻。
3. `machine_translation`：仅用于前两类均不存在的日文剧情；必须进入独立 Exedra 机翻清单。

每个 Exedra 中文逻辑组必须记录：`story_id`、JP/CN 文件哈希、来源类型、来源 URL（Wiki 时）、导入时间、Section 映射、说话人顺序哈希和人工校验状态。

## 独立动态统计

魔法纪录与 Exedra 使用两套清单和两套 KV 状态命名空间：

- `magireco`: 当前可信基线为 `main`，现有机翻 507 部、223 个目录。
- `exedra`: 以现有本地中文和 Wiki 中文为人工基线，只把其余自动翻译标记为机翻。

首页切换游戏时只显示当前游戏的：总数、已校、剩余、目录高亮和“只看待校”筛选。

## 魔法纪录语音类别

新类别键：`general_voice`，显示名：`语音`。

来源：`HiiragiNemu/io.kamihama.totentanz` 中 `scenario/general`。导入目标：

- `magireco-voice-source-master/Scenarios_full/general_voice/`
- `magireco-voice-translate-data-master/Scenarios_full/general_voice/`

导入器必须：

1. 保留原始脚本与来源路径；
2. 生成可由 MagiReader 读取的聚合 TXT；
3. 建立角色 ID、显示名、脚本和语音资源的显式映射；
4. 不使用模糊匹配自动归属角色；
5. 参考 `MagiaExedraLive2DViewerPersonal` 最新分支的语音看板映射，但输出独立、可审计的 manifest；
6. 对缺失映射、重复 ID、无文本事件和未知结构 fail-closed。

## 当前审计

- 魔法纪录机翻：507 部剧情 TXT，223 个目录。
- Exedra JP：3,062 JSON，443 TXT，444 个含文件目录。
- Exedra CN：5 JSON，5 TXT，5 个含文件目录。
- 两个外部参考仓库均为私有仓库；GitHub Actions 默认 `GITHUB_TOKEN` 无法跨仓库读取，需使用仅对这些仓库具有 Contents: Read 的独立 fine-grained token，Secret 名称预留为 `SOURCE_REPOS_READ_TOKEN`。
