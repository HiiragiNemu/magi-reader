# Exedra 中文化与魔法纪录语音管线

目标分支：`feature/exedra-cn-and-magireco-voice`（基于 `EXEDRA-TEST`）。`main` 不参与本项目写入。

## Exedra 中文来源政策

Exedra 自动机翻计划已经取消。中文文本只允许以下来源，低优先级来源不得覆盖高优先级来源：

1. `local_human`：仓库中已经存在且通过导入报告验证的人工中文；保持原样。
2. `official_tw_human`：官方台服繁体中文，转换为简体中文后保留官方来源证明。
3. `exedra_wiki_human`：Exedra Wiki 的人工中文剧情页；仅在 Section、文本事件数量和说话人顺序可以精确证明时导入。

没有上述来源的剧情保持日文，不生成占位中文，不把 `has_cn` 或进度伪装为 100%。旧 `machine_translation` KV 缓存和 Exedra 机器校验状态可从 `/review/exedra-localization` 定向清除。

每个新增 Exedra 中文逻辑组必须记录：`story_id`、JP/CN 文件哈希、来源类型、来源 URL、导入时间、Section 映射和说话人顺序哈希。

## Exedra 分类显示名

内部类别键保持稳定，界面显示名不再带来源目录数字：

- `exedra_main` → `主线`
- `exedra_sub` → `活动`
- `exedra_character` → `角色`
- `exedra_portrait` → `肖像`
- `exedra_reaction` → `语音`
- `exedra_namae` → `Namae`
- `exedra_dungeon` → `过场动画字幕`
- `exedra_battle` → `战斗`

## 魔法纪录机器翻译校验

机器翻译校验只适用于魔法纪录：当前可信基线为 `main`，现有清单为 507 部剧情、223 个目录。Exedra 不再拥有机器翻译清单、统计、页面高亮或 Workers AI binding。

## Exedra 可信中文工具

- `/review/exedra-localization`：检查角色 Exedra Wiki 人工中文、导出可信缓存、清除旧机翻缓存。
- `tools/import_exedra_cache_export.py`：将导出的 Wiki 人工中文写入规范 JSON/TXT 和 schema-v1 导入报告；拒绝任何非 Wiki 人工缓存。
- `tools/import_exedra_official_tw.py`：从解包后的官方台服剧情 JSON 生成简体中文 JSON/TXT 和 schema-v1 导入报告。

现有人工中文默认不可覆盖。任一 Section 来源、事件数量、事件类型或说话人序列不一致时必须 fail-closed。

## 魔法纪录语音类别

新类别键：`general_voice`，显示名：`语音`。

来源：`HiiragiNemu/io.kamihama.totentanz` 中 `scenario/general`。导入目标：

- `magireco-voice-source-master/Scenarios_full/general_voice/`
- `magireco-voice-translate-data-master/Scenarios_full/general_voice/`

`tools/import_magireco_general_voice.py` 可以直接下载 411 个中文模型语音脚本，生成原始 JSON、MagiReader TXT 和逐文件 SHA-256 manifest，不依赖 GitHub Actions。

运行时目录扩展只新增 `general_voice` 条目。静态全文索引继续覆盖原有剧情；响应清单通过 `fulltext_excluded_categories: ["general_voice"]` 明确声明语音正文尚未进入全文索引。

## 无 Git checkout 备用路径

当前部分执行容器可能完全禁用出站网络；这种情况下 DNS、代理、`git clone`、`raw.githubusercontent.com` 和 `codeload.github.com` 都不可用，只能通过已连接的 GitHub 服务读写，无法在容器内安装 npm 依赖或完成本地构建。

当环境允许 `api.github.com`、但 Git 协议或 codeload 被封锁时，使用：

```powershell
py tools/github_api_checkout.py HiiragiNemu/magi-reader `
  --ref feature/exedra-cn-and-magireco-voice `
  --output D:\work\magi-reader `
  --zip D:\work\magi-reader.zip
```

该工具通过 commit → tree → blob REST 端点重建分支，校验每个 Git blob SHA-1，拒绝路径越界和 submodule，可按 `--include website` 只恢复构建所需子树。它不使用 Actions。

## 当前已知基线

- 魔法纪录机翻：507 部剧情 TXT，223 个目录。
- Exedra JP：443 个逻辑组、3,061 个剧情来源 JSON、105,867 条文本事件。
- Exedra 已有本地中文：5 个逻辑组。
- 魔法纪录 general voice：411 个模型脚本。
