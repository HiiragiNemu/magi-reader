# 下一位 AI 交接：Exedra 中文、人工校验与魔法纪录语音

更新时间：2026-07-28  
仓库：`HiiragiNemu/magi-reader`  
长期开发分支：`feature/exedra-cn-and-magireco-voice`  
基线分支：`EXEDRA-TEST`  
禁止直接修改：`main`

## 1. 当前分支状态

- `feature/exedra-cn-and-magireco-voice` 从 `EXEDRA-TEST` 提交 `c68110c495a895be77e349ae85fe36939974d7bc` 继续开发。
- 写入本交接文档之前，长期分支头为 `cc96a51d6352e64dc2d8cceddfc627dc04553920`。
- 分支相对 `EXEDRA-TEST` 为纯前进关系；最近审计为 ahead 105、behind 0。
- 差异中没有修改任何既有魔法纪录/Exedra 剧情 JSON、人工中文 TXT 或 `main` 内容。
- 所有本阶段代码、工具、测试和设计文档已永久写入该 GitHub 分支。
- 当前测试 Worker `magireader-exedra-cn-test.crynetsystemscell.workers.dev` **尚未部署该长期分支**；线上仍是旧版本。

## 2. 已永久落盘的主要产物

### 2.1 魔法纪录语音技术

已建立目录：

- `magireco-voice-source-master/Scenarios_full/general_voice/`
- `magireco-voice-translate-data-master/Scenarios_full/general_voice/`

已实现：

- `website/lib/general-voice-source.ts`
- `website/lib/general-voice-runtime.ts`
- `website/lib/general-voice-source.test.ts`
- `tools/import_magireco_general_voice.py`
- `website/proxy.ts`

固定上游提交：`196f4bfcfa28c446539b4611e4cce7992b0c40d1`。  
固定不可变预览源：`https://566b00b8.magiaexedralive2dviewer.pages.dev/story/general`。  
上游清单预期为 411 个中文 general 模型脚本。

运行时具备：

- 语音清单和单脚本严格解析；
- JSON→MagiReader TXT；
- `general_voice`/“语音”目录条目；
- 实例缓存和旧缓存回退；
- 上游冷启动失败时退化到基础剧情目录；
- `/data/general_voice/<modelId>/<modelId>_cn.txt` 与 JSON 代理。

注意：411 个 JSON/TXT 尚未批量物理落盘提交；当前只有目录、运行时和离线导入器。

### 2.2 Exedra 基线和可信来源架构

已确认 Exedra manifest：

- 443 个逻辑组；
- 3,061 个剧情来源 JSON；
- 105,867 条文本事件；
- 仓库现有本地中文逻辑组约 5 个。

最终来源优先级：

1. 仓库现有人工中文；
2. 官方台服繁体中文转简体；
3. Exedra Wiki 人工中文；
4. 用户提供的人工文本包（本次为 `圆哆啦文本0728.rar`，权重低于 Wiki）。

Exedra 自动机器翻译计划已经取消。不得恢复 Workers AI、Exedra 机翻清单、Exedra 机翻高亮或模型调用。

已实现：

- `website/lib/exedra-localization.ts`
- `website/lib/exedra-wiki-exact.ts`
- `website/lib/exedra-localization.test.ts`
- `website/app/api/exedra/localized/[id]/route.ts`
- `website/app/api/exedra/localization-status/route.ts`
- `website/app/api/admin/exedra-localize/route.ts`
- `website/app/api/admin/exedra-localize/export/route.ts`
- `website/app/review/exedra-localization/page.tsx`
- `tools/import_exedra_official_tw.py`
- `tools/import_exedra_cache_export.py`

可信缓存只接受：

- `local_human`
- `official_tw_human`
- `exedra_wiki_human`

旧 `machine_translation` KV 记录不被解析，可通过管理员接口定向清除。

Wiki 当前实现包含显式角色英文页名映射，并优先尝试类似：

- `:Iroha_Tamaki/Story/Chinese`
- `Iroha_Tamaki/Story/Chinese`

只有块数/结构精确匹配时才接受；最终 TXT 使用 JP 源的说话人身份，只采用中文正文。

### 2.3 Exedra 官方台服导入器

`tools/import_exedra_official_tw.py` 已加固为：

- 按 manifest 完整相对来源路径优先匹配；
- JP/TW 动作、sheet、row、事件数逐项验证；
- 仅替换 JSON `Comment` 文本单元；
- 保留非中文化内容、动作、资源 ID、角色身份和 schema；
- OpenCC `tw2sp`；
- 临时目录事务生成；
- schema-v1 导入报告独立验证；
- 通过后一次性提交 JSON、`<groupKey>_cn.txt`、报告和 provenance；
- 拒绝覆盖已有/不完整中文组；
- 报告不记录用户电脑绝对路径。

尚未取得并导入真实台服解包剧情 JSON，因此官方台服新增覆盖数目前为 0。

### 2.4 Wiki 缓存回写器

`tools/import_exedra_cache_export.py`：

- 只接受 `trusted_exedra_sources_only` 导出；
- 只接受 `exedra_wiki_human`；
- URL 必须是 `https://exedra.wiki/wiki/.../Story/Chinese`；
- 绑定 story ID、source identity、JP/CN SHA-256；
- 事务生成中文 JSON、TXT、schema-v1 报告和 provenance；
- 拒绝覆盖任何既有中文。

### 2.5 分类显示决策

Exedra 最终分类显示：

- `exedra_main` → `主线`
- `exedra_sub` → `活动`
- `exedra_character` → `角色`
- `exedra_portrait` → `肖像`
- `exedra_reaction` → `语音`
- `exedra_namae` → `Namae`
- `exedra_dungeon` → `过场动画字幕`
- `exedra_battle` → `战斗`

数字前缀全部移除。阅读器 `website/components/Sidebar.tsx` 已源级修改；`CategoryLabelNormalizer.tsx` 只作为旧组件兼容兜底，并限制在导航/标题节点。

### 2.6 魔法纪录机器翻译人工校验

当前可信魔法纪录机器翻译基线：

- 507 部聚合剧情 TXT；
- 223 个唯一目录；
- `main` 是人工/官方译文可信基线；
- `main_story`、`scene0_main` 不属于机翻范围；
- Exedra 不属于这套清单。

魔法纪录在线投稿、审核、KV、GitHub 校对 PR 和机器翻译已校/待校状态来自此前 `EXEDRA-TEST` 工作，长期分支保留并限制为 `magireco`。

## 3. 无 clone/codeload 环境的恢复方案

已实现 `tools/github_api_checkout.py`，适用于 Git/codeload 被封锁但 `api.github.com` 可访问的环境。

它具备：

- commit/tree/blob REST 重建；
- Git blob SHA-1 校验；
- HTTPS API 根限制；
- 令牌不发送到任意绝对 URL；
- Windows 保留名、非法字符和大小写冲突检查；
- 符号链接越界防护；
- submodule 拒绝；
- 临时 checkout 后原子替换；
- 失败清理；
- ZIP 禁止写入 checkout 内部。

当前 ChatGPT 执行容器属于“完全无出站 TCP”，不仅是 DNS 故障。因此这里无法执行 git、npm、Wiki、Workers 或 Cloudflare 网络操作；GitHub 连接器仍可读写仓库。

## 4. 直接测试部署工具

已实现：

- `website/scripts/deploy-direct-test.mjs`
- `website/scripts/cloudflare-direct-deploy-utils.mjs`
- `website/scripts/cloudflare-direct-deploy-utils.test.mjs`
- `website/scripts/verify-cloudflare-output.mjs`
- `docs/DIRECT_EXEDRA_TEST_DEPLOYMENT.md`

固定测试资源：

- Worker：`magireader-exedra-cn-test`
- KV：`magi-submissions-exedra-cn-test`

命令：

```powershell
cd website
npm ci
npm run deploy:test:direct -- --dry-run
npm run deploy:test:direct
```

流程会验证政策、Python、ESLint、TypeScript、Node 测试，构建 OpenNext，暂存 61 MiB 全文搜索文件，解析测试 KV ID，生成临时测试配置，并确保不覆盖生产 Worker `magireader`。

纯部署工具测试曾在无依赖 Node 环境运行并通过 5/5；完整 npm/OpenNext/Cloudflare 验证尚未执行。

## 5. 质量门

已实现：

- `website/scripts/validate-feature-policy.mjs`
- `tools/run_python_checks.py`
- `website/scripts/run-python-checks.mjs`
- `tests/test_exedra_import_tools.py`
- `tests/__init__.py`
- Node `.test.ts` 使用 `node --experimental-strip-types --test`
- Node 最低版本 `>=22.6.0`

`npm run check` 当前包含可信来源政策、Python 编译/回归、ESLint、TypeScript、Node 测试和生产依赖审计。

## 6. 尚未完成、下一位 AI 必须继续的现状

### 6.1 当前用户的新最终目标

用户已上传 `圆哆啦文本0728.rar`。该附件**尚未解析、尚未写入仓库**。在当前会话沙箱中曾挂载为：

`/mnt/data/圆哆啦文本0728.rar`

该沙箱路径不保证跨会话存在；新窗口若无法读取，必须让用户重新上传。不得在未读取内容前猜测格式。

来源优先级要求：

1. 本地已有中文：保持原样；
2. Exedra Wiki 中文角色剧情：优先使用；
3. 0728 人工文本：仅填补 Wiki 不存在/未覆盖的 Exedra 内容；
4. 不使用机器翻译。

Wiki、现有本地中文、0728 人工文本均不标记为机器翻译。

### 6.2 必须生产可播放 JSON，再生产 TXT

用户要求的不只是 TXT：

- 0728/Wiki 中文必须生成与对应 Exedra JP JSON schema 对齐的中文 JSON；
- 只允许改角色名、对白、旁白、选择项等中文化文本字段；
- 动作、资源引用、事件顺序、分支、Section、Scene0 元数据和非文本字段必须保持；
- 每个 JSON 必须通过结构验证并能被现有播放器使用；
- JSON 通过后，才由 JSON 生产规范聚合 TXT；
- 不得先手工拼 TXT 再假定 JSON 可播放。

当前两条导入器已经提供“以 JP JSON 为结构基准、仅回填正文”的基础，但 0728 解析器、Wiki 真实页面到逐 JSON 事件映射尚未完成。

### 6.3 人工校验后台必须输出 JSON 和 TXT

现有社区校对主要以完整 TXT 投稿/审阅并创建只改 TXT 的 PR。下一阶段必须重构为：

1. 投稿者在中日对照界面修改中文；
2. 服务器/导出器把修改映射回全部来源 JSON 文本事件；
3. 严格验证 JSON 动作、事件数、分支、Section 和非文本字段；
4. 生成可播放中文 JSON；
5. 从验证后的 JSON 重新生成 TXT；
6. PR 同时包含规范 JSON、TXT、来源证明和校验报告；
7. 魔法纪录与 Exedra 都必须支持这一闭环；
8. 不能只创建一个 TXT-only PR。

现有 `tools/import_exedra_*` 的事务写入和 schema-v1 验证可复用；魔法纪录需新增对应 JSON 回填器和 JSON→TXT 重建验证。

### 6.4 中日对照布局

用户要求：

- 手机端中日对照布局可选择；
- PC 端增加“上下排列式中日对照”；
- 剧情阅读页和汉化/人工校验页都支持；
- 至少保留当前并排模式，同时允许上下模式；
- 选择应在页面/设备间按站点设置持久化；
- 不得通过改变文本结构实现，仅改变显示布局。

该功能尚未实现。

### 6.5 可信 Exedra 状态尚未接入目录

已新增 `/api/exedra/localization-status`，但客户端 `loadStoryIndex` 尚未读取它并为可信 Wiki 缓存注入 `/api/exedra/localized/<id>`。

下一位 AI 必须：

- 读取静态 `story_index.json`；
- 读取可信状态 API；
- 只对 ID/source identity 精确匹配的缓存条目设置中文路径和 `has_cn=true`；
- API 失败时保留静态目录；
- 不信任服务端任意路径，只在客户端由 story ID 构造同源 API 路径；
- 本地已落盘中文继续使用静态 `/data/..._cn.txt`，不经过动态缓存。

### 6.6 魔法纪录语音尚未物理落盘

运行时、代理和导入器已经实现，但 411 个 JSON/TXT 尚未实际写入分支。下一位 AI 可：

- 在可访问上游的环境运行 `tools/import_magireco_general_voice.py`；
- 校验 411 个模型和逐文件 SHA-256；
- 把生成 JSON/TXT/manifest 提交到现有两个 general_voice 目录；
- 重新生成 `story_index.json` 和搜索索引；
- 检查角色映射、模型/服装分组和语音条目数量。

### 6.7 尚未完成的构建与部署

仍必须完成：

```powershell
cd website
npm ci
npm run check
npm run build:worker
npm run deploy:test:direct -- --dry-run
npm run deploy:test:direct
```

部署目标：

`https://magireader-exedra-cn-test.crynetsystemscell.workers.dev/`

上线后必须烟雾测试：

- 分类名称；
- 411 语音目录与 TXT；
- 魔法纪录 507 机翻清单不受影响；
- Exedra 无机翻标记；
- Wiki/0728/本地人工来源不显示机翻；
- Exedra JSON/TXT 可播放；
- 手机和 PC 中日布局选项；
- 投稿→审核→JSON→TXT→PR 全闭环；
- 未授权管理员 API 返回 401；
- 生产 `main` 和生产 Worker 没有变化。

## 7. 禁止事项

- 不得修改或覆盖 `main` 中人工/官方魔法纪录译文。
- 不得恢复 Exedra 自动机器翻译。
- 不得把 0728 人工文本标为机翻。
- 不得以 0728 覆盖同一内容的 Exedra Wiki 中文。
- 不得以 TXT-only 结果宣称完成可播放 JSON。
- 不得猜测对齐；所有映射必须由事件顺序、动作类型、Section、来源 JSON 和哈希证明。
- 不得在测试通过前合并长期分支到 `EXEDRA-TEST`。
- 不得部署到生产 Worker `magireader`。
- 不得修改 `main`。

## 8. 建议接续顺序

1. 读取本交接文档和 `docs/FEATURE_REVIEW_CHECKLIST.md`。
2. 读取并盘点 0728 RAR，不写入；生成来源/角色/剧情/语言/结构清单。
3. 在线抓取所有可匹配 Exedra Wiki 角色中文剧情页，并保存页面来源哈希。
4. 建立“本地已有 > Wiki > 0728”的逐逻辑组 provenance 计划。
5. 完成 Wiki/0728 → Exedra JSON 文本事件映射与严格验证。
6. 从验证 JSON 生成 TXT 和导入报告。
7. 重构 Magia Record/Exedra 校对闭环，使 PR 同时生成 JSON+TXT。
8. 实现手机可选布局和 PC 上下中日对照。
9. 物理导入 411 个 general voice JSON/TXT。
10. 接入可信 Exedra 状态到目录。
11. 在可联网环境执行全部质量门和直接测试部署。
12. 完成线上烟雾测试后再决定是否合并到 `EXEDRA-TEST`。
