# 2026-07-28 Exedra 中文 JSON/TXT 与人工校验交接

> 本文件是下一位 AI 的权威交接入口。若其他旧文档与本文件或用户最新指令冲突，以本文件和最新用户指令为准。

## 1. 工作分支与保护边界

- 仓库：`HiiragiNemu/magi-reader`
- 长期开发分支：`feature/exedra-cn-and-magireco-voice`
- 基线分支：`EXEDRA-TEST`
- `main` 不得修改。
- 当前长期分支相对 `EXEDRA-TEST` 为纯前进关系；截至本交接前的审计结果为 ahead 105、behind 0。
- 当前差异只包含代码、工具、测试、文档和两个空的 `general_voice` 目标目录；没有修改既有魔法纪录/Exedra 剧情 JSON、TXT 或人工中文语料。
- 当前测试站 `https://magireader-exedra-cn-test.crynetsystemscell.workers.dev/` 尚未部署本长期分支的最新代码。

## 2. 已经落盘到长期分支的研究和生产文件

### Exedra 可信中文与 JSON/TXT 管线

- `website/lib/exedra-localization.ts`
- `website/lib/exedra-wiki-exact.ts`
- `website/app/api/exedra/localized/[id]/route.ts`
- `website/app/api/exedra/localization-status/route.ts`
- `website/app/api/admin/exedra-localize/route.ts`
- `website/app/api/admin/exedra-localize/export/route.ts`
- `website/app/review/exedra-localization/page.tsx`
- `tools/import_exedra_official_tw.py`
- `tools/import_exedra_cache_export.py`
- `tests/test_exedra_import_tools.py`

### 魔法纪录 general voice 管线

- `website/lib/general-voice-source.ts`
- `website/lib/general-voice-runtime.ts`
- `website/proxy.ts`
- `tools/import_magireco_general_voice.py`
- `magireco-voice-source-master/Scenarios_full/general_voice/.gitkeep`
- `magireco-voice-translate-data-master/Scenarios_full/general_voice/.gitkeep`

### 构建、恢复与直接部署

- `tools/github_api_checkout.py`
- `tools/run_python_checks.py`
- `website/scripts/run-python-checks.mjs`
- `website/scripts/validate-feature-policy.mjs`
- `website/scripts/cloudflare-direct-deploy-utils.mjs`
- `website/scripts/cloudflare-direct-deploy-utils.test.mjs`
- `website/scripts/deploy-direct-test.mjs`
- `docs/DIRECT_EXEDRA_TEST_DEPLOYMENT.md`
- `docs/FEATURE_REVIEW_CHECKLIST.md`

## 3. 已确定的产品决策

### Exedra 分类显示

- `exedra_main` → `主线`
- `exedra_sub` → `活动`
- `exedra_character` → `角色`
- `exedra_portrait` → `肖像`
- `exedra_reaction` → `语音`
- `exedra_namae` → `Namae`
- `exedra_dungeon` → `过场动画字幕`
- `exedra_battle` → `战斗`

数字前缀不得再显示。

### 机器翻译政策

- Exedra 自动机翻计划已经取消。
- 不得调用 Workers AI 或其他模型自动填充 Exedra 缺失中文。
- 魔法纪录现有 507 部机翻人工校验体系保持独立。
- Exedra 的人工/Wiki/0728 文本不得标记为机器翻译。

## 4. 下一阶段中文来源优先级

用户最新指令要求：

1. **仓库现有已中文化 Exedra 内容**：保持原样，不进一步改动，不覆盖，不标记机翻。
2. **Exedra Wiki 角色中文剧情页**：优先于 0728 包。存在 Wiki 中文且能严格映射时，使用 Wiki 中文，不标记机翻。
3. **`圆哆啦文本0728.rar`**：仅用于 Wiki 没有覆盖的 Exedra 剧情/语音。它属于人工剧情/语音文本，不标记机翻。
4. 前三者均无可信文本时，保持日文，不制造占位中文。

当前分支还保留官方台服繁中导入工具，但尚未实际导入任何台服数据。下一位 AI 不得让该工具覆盖仓库既有中文、Wiki 中文或 0728 人工文本；若要重新定义它在最终优先级中的位置，必须先与用户确认。

## 5. 0728 压缩包状态

用户上传文件名：`圆哆啦文本0728.rar`。

重要：该压缩包目前只存在于本次会话的上传环境，**没有提交到 GitHub 分支，也没有生成稳定 Release 资产**。分支中只有处理管线，没有 0728 原始文本内容。

若下一位 AI 在新会话或新执行环境继续工作，必须：

- 重新获得该 RAR 文件；或
- 先把它上传到受控的私有 Release/对象存储，并记录 SHA-256；
- 不得根据本交接文档臆造压缩包内容。

## 6. 下一位 AI 的核心目标

### A. 解析与映射 0728 文本

1. 解包并建立完整清单：路径、编码、文件大小、SHA-256、文本行数。
2. 识别角色剧情、活动、语音及其他文本类型。
3. 将文本映射到 `magiraexedra-source-master/Scenarios_full/exedra_manifest.json` 的 443 个逻辑组和 3,061 个来源 JSON。
4. 映射必须依赖明确 ID、Section、Episode、事件顺序和角色身份，不得使用模糊文件名猜测。
5. 生成来源侧车，至少记录：来源文件、来源哈希、目标 group、Section 映射和文本事件数量。

### B. 继续抓取 Exedra Wiki 人工中文

1. 对每个 Exedra 角色组查找 `/Story/Chinese` 页面，例如 `:Iroha_Tamaki/Story/Chinese`。
2. Wiki 中文优先于 0728 文本。
3. 必须验证角色身份、Section/Episode、文本事件数量、旁白/对白类型和说话人序列。
4. 无法精确证明时拒绝导入，不得通过 LCS、模糊匹配或重排强行套用。
5. 记录 Wiki URL、抓取时间、页面/正文哈希和映射证明。

### C. 先生产可播放中文 JSON，再生成 TXT

所有新增 Exedra 中文必须遵循：

1. 以日文 JSON 为结构基准。
2. 保留所有非文本字段、动作、资源 ID、角色 ID、分支、等待、镜头、音频及其他播放器字段。
3. 只替换经过证明的文本字段；不得把 TXT 反向粗暴覆盖整个 JSON。
4. 每个来源 JSON 都必须能通过解析、schema、事件顺序和播放器兼容验证。
5. 中文 JSON 验证通过后，再由 JSON 生成规范 `<groupKey>_cn.txt`。
6. TXT 必须保留规范 Section/Source 头、事件数量和说话人顺序。
7. 为每个逻辑组生成 schema-v1 导入报告和 provenance 侧车。
8. 任一组验证失败时 fail-closed，不留下半成品。

### D. 魔法纪录与 Exedra 人工校验界面必须生成双产物

当前社区校对体系仍以完整 TXT 投稿和单 TXT PR 为主，尚未完成“批准后 JSON + TXT 双产物”。下一位 AI 必须改造：

1. 魔法纪录校验批准后，生成与目标剧情对应的全部中文 JSON，并由已验证 JSON 再生成 TXT。
2. Exedra 校验批准后，同样生成全部中文 JSON，再生成 TXT。
3. PR 不得只修改 TXT；必须包含相应 JSON、TXT、来源/审核元数据和验证报告。
4. 批准前重新校验基准 SHA-256，阻止旧投稿覆盖新版本。
5. 验证 Section、Branch、Scene0、选项、动作和角色顺序。
6. CI/本地质量门必须确认产物可以被现有播放器实际解析和播放。
7. 未通过 JSON 播放验证的投稿不得取消“待校”状态或进入正式分支。

### E. 中日对照布局选项

阅读器和“协助汉化/人工校验”页面都需要统一布局选择：

- 保留当前手机端中日对照格式，并将其作为可选模式，而不是仅由设备自动决定。
- PC 端增加中日在上下方向排列的模式。
- 布局选择应同时作用于普通阅读页和汉化编辑页。
- 需要持久化用户选择，并在手机/PC 上都允许手动切换。
- 不得因布局变化破坏输入框、Section 定位、差异高亮或提交内容。

### F. 客户端可信 Exedra 中文目录接入

新公共 API `/api/exedra/localization-status` 已落盘，但客户端 `loadStoryIndex` 尚未完成合并可信 Wiki/人工中文状态。下一位 AI 需要：

1. 加载静态 story index。
2. 加载可信中文状态 API。
3. 只对 `story_id + source_identity` 精确匹配的可信记录注入 `/api/exedra/localized/<id>`。
4. 状态 API 失败时回退原始目录。
5. 不得把未命中可信来源的 Exedra 剧情伪装成有中文或 100%。

### G. 魔法纪录语音落盘与页面接入

1. 运行 `tools/import_magireco_general_voice.py`，实际生成 411 个模型的 JSON、TXT 和 manifest。
2. 验证角色映射、模型 ID、语音资源键、事件顺序和 TXT 格式。
3. 将 `general_voice` 纳入目录、播放器和搜索策略。
4. 当前运行时上游代理只能作为过渡方案；最终应优先使用仓库内落盘文件。

## 7. 完成前必须执行的验证和部署

在具备 npm、GitHub 和 Cloudflare 网络的环境：

```powershell
cd website
npm ci
npm run check
npm run build:worker
npm run deploy:test:direct -- --dry-run
npm run deploy:test:direct
```

测试 Worker 固定为：

```text
magireader-exedra-cn-test
```

测试 KV 固定名称：

```text
magi-submissions-exedra-cn-test
```

部署后必须检查：

- 分类名称；
- 手机/PC 中日布局选择；
- Magia Record 语音目录和 TXT；
- Wiki 与 0728 Exedra 中文 JSON/TXT；
- 两套人工校验批准后的 JSON/TXT 双产物 PR；
- Exedra 无机翻标记；
- 魔法纪录 507 部机翻清单不受影响；
- 生产 `main` 和生产 Worker 未变化。

## 8. 完成后汇报指标

至少报告：

- Exedra 443 组中：既有本地中文、Wiki 中文、0728 人工中文、官方台服中文、仍无中文的数量；
- 各来源 JSON 数、TXT 数、事件数；
- 成功/失败/需人工映射的组；
- Wiki 页面命中与拒绝原因；
- 0728 文件命中与未映射清单；
- 可播放 JSON 验证结果；
- 魔法纪录 general voice 角色/模型/语音数量；
- 校验界面产生的 JSON/TXT/PR 数量；
- 测试站部署提交 SHA 和线上烟雾测试结果。

## 9. 明确未完成状态

截至本交接：

- 0728 RAR 尚未解析或落盘仓库。
- Wiki 尚未完成全角色抓取与实际导入统计。
- 0728/Wiki Exedra 中文 JSON/TXT 尚未批量生产。
- 魔法纪录与 Exedra 校验批准后的 JSON/TXT 双产物尚未实现。
- 中日对照布局选项尚未实现。
- 客户端可信 Exedra 中文状态尚未接入 story index。
- 411 个 general voice JSON/TXT 尚未实际提交。
- 完整 npm/TypeScript/OpenNext 构建未执行。
- 最新长期分支尚未部署到测试站。
- 未合并到 `EXEDRA-TEST`，更未修改 `main`。

下一位 AI 应从本文件开始读取，再检查 `docs/FEATURE_REVIEW_CHECKLIST.md` 和 `docs/DIRECT_EXEDRA_TEST_DEPLOYMENT.md`，不要从旧聊天描述推断完成状态。
