# Exedra / General Voice 独立测试部署

本流程只允许部署测试 Worker，不修改 `main`，不覆盖生产 Worker `magireader`。

## 固定边界

- 本地仓库：`D:\magia\MyProducts\magi-reader-exedra-test`
- 开发分支：`feature/exedra-cn-and-magireco-voice`
- 合并目标：`EXEDRA-TEST`
- 测试 Worker：`magireader-exedra-cn-test`
- 测试域名：`magireader-exedra-cn-test.crynetsystemscell.workers.dev`
- 测试 KV 名称：`magi-submissions-exedra-cn-test`
- 禁止目标：`main`、生产 Worker `magireader`、生产 KV

直接部署脚本已经硬编码检查测试 Worker、测试 KV、测试域名和 `EXEDRA-TEST` 目标；工作树不干净时会拒绝执行真实部署。

## 1. 部署前数据验收

必须先确认生成结果：

- `story_index.json` 总条目为 3,012；
- Exedra 为 443 组，中文 124，仍缺 319；
- 119 个新 Exedra 中文组具有 `json_paths_cn`；
- Exedra 中文 JSON 为 1,390 个；
- general voice 为 410 个模型，全部有 TXT/JSON；
- 魔法纪录机翻清单仍为 507；
- Exedra provenance 中没有 `machine_translation`。

源优先级必须是：

```text
仓库既有中文 > Exedra Wiki > 0728 人工文本
```

## 2. 最终本地质量门

在最后一次源代码或数据改动后重新执行：

```powershell
Set-Location 'D:\magia\MyProducts\magi-reader-exedra-test'
python generate_story_index.py
python tools\run_python_checks.py

Set-Location 'D:\magia\MyProducts\magi-reader-exedra-test\website'
npm ci
npm run check
npm run build:worker
npm run verify:cloudflare-output
npm run deploy:test:direct -- --dry-run
```

当前历史验证记录：

- Python：143 通过，2 跳过；
- Node：83 / 83；
- ESLint、TypeScript、feature policy、生产依赖审计通过；
- OpenNext Worker 构建和 Cloudflare 输出验证通过；
- 搜索目录 3,012、搜索条目 5,242。

静态 Exedra 中文路由修复后，本节的 `npm run check`、Worker 构建、输出验证和 dry-run 已在干净工作树通过；Wrangler 已确认 9,029 个静态资源以及隔离测试 Worker/KV 绑定。

## 3. Git 与合并

真实部署要求干净工作树。先完成：

1. 审计所有改动，不提交 `.wrangler` 临时配置、秘密、缓存或生成备份。
2. 确认没有修改既有可信人工文本，也没有生产 Worker 配置。
3. 提交并推送 `feature/exedra-cn-and-magireco-voice`。
4. 建立以 `EXEDRA-TEST` 为目标的 PR。
5. 等待全部 CI；失败时修复，不绕过。
6. 使用 squash merge，避免长期开发分支历史污染目标分支。
7. 再从合并后的 `EXEDRA-TEST` 部署测试 Worker。

当前这些步骤尚未完成。

## 4. 直接部署

在干净、已同步的目标提交上：

```powershell
Set-Location 'D:\magia\MyProducts\magi-reader-exedra-test\website'
npx.cmd wrangler whoami
npm run deploy:test:direct
```

先验收配置但不部署：

```powershell
npm run deploy:test:direct -- --dry-run
```

如果已经独立确认测试 KV ID：

```powershell
npm run deploy:test:direct -- --kv-id 0123456789abcdef0123456789abcdef
```

真实 ID 只允许进入临时配置，不得写回仓库 `wrangler.jsonc`。

脚本会：

1. 验证可信来源政策；
2. 运行 Python、Lint、TypeScript 和 Node 测试；
3. 按名称精确解析测试 KV；
4. 生成 `.wrangler/direct-test/` 临时配置；
5. 同时锁定 Worker 名和 `WORKER_SELF_REFERENCE`；
6. 构建 OpenNext；
7. 暂存超过 Cloudflare 单文件上限的本地搜索 payload；
8. 暂存 OpenNext 自动生成的重定向配置；
9. 用显式测试配置执行严格部署；
10. 恢复配置并删除包含真实 KV ID 的临时文件。

## 5. GitHub 工作流部署

也可以在合并后的 `EXEDRA-TEST` 手动运行：

```text
Deploy Exedra Community Proofreading Test Site
```

当前仓库 Secrets 已能提供 Cloudflare 账户、API Token、测试 KV 和仓库写入 Token。当前没有确认：

- 真实 Turnstile site/secret keys；
- `SUBMISSIONS_ADMIN_TOKEN`；
- 独立 `PROOFREADING_GITHUB_TOKEN`。

因此如果以现有 Secrets 部署，Turnstile 可能继续处于官方测试模式；管理员可使用自己有仓库权限的 GitHub PAT。不得把这种配置描述为面向大规模公众的最终防滥用状态。

## 6. 线上烟雾测试

基础：

```powershell
$Base = 'https://magireader-exedra-cn-test.crynetsystemscell.workers.dev'
Invoke-WebRequest "$Base/" -UseBasicParsing
Invoke-WebRequest "$Base/story_index.json" -UseBasicParsing
Invoke-WebRequest "$Base/search_index_manifest.json" -UseBasicParsing
```

静态 general voice：

```powershell
Invoke-WebRequest "$Base/data/general_voice/100100/100100_cn.txt" -UseBasicParsing
Invoke-WebRequest "$Base/data/general_voice/100100/100100_cn.json" -UseBasicParsing
```

静态 Exedra Wiki/0728 中文：

```powershell
Invoke-WebRequest "$Base/data/exedra_character/character_iroha/character_iroha_cn.txt" -UseBasicParsing
Invoke-WebRequest "$Base/data/exedra_character/character_iroha/character_iroha_0.json" -UseBasicParsing
```

API：

```powershell
Invoke-WebRequest "$Base/api/proofreading/config" -UseBasicParsing
Invoke-WebRequest "$Base/api/proofreading/machine-status" -UseBasicParsing
Invoke-WebRequest "$Base/api/exedra/localization-status" -UseBasicParsing
```

必须验证：

- 首页和所有上述资源返回 200；
- `story_index.json` 为 3,012 条；
- Exedra 443 / 中文 124 / general voice 410；
- 魔法纪录机翻总数为 507；
- Exedra 状态 API 不返回 `machine_translation`；
- 分类为 `主线、活动、角色、肖像、语音、Namae、过场动画字幕、战斗`，没有数字；
- Magia Record 页面出现“语音”；
- 左右/上下排列在普通阅读和“协助汉化”都可切换；
- 环彩羽等静态 Exedra 中文直接读取公开 TXT/JSON；
- 未认证管理员 API 返回 401 或预期的不可用状态；
- `main`、生产 Worker 和生产 KV 没有变化。

## 7. 搜索 R2 限制

本地已验证的全文 payload 为 79,001,794 字节，对象键：

```text
search/0858dda73a7395000bfb0a60eb102bad8e7838e488d3bae64aa81765d91a7341.json
```

当前 Cloudflare Token 没有 R2 权限，所以该对象尚未上传。直接部署会避免把超限文件塞进 Worker 静态资产。目录浏览、标题检索和剧情阅读仍可验收；全文正文搜索要单独标为未恢复。

## 8. 禁止合并/部署条件

任一条件成立都应停止：

- 最后一次 `npm run check` 或 Worker 构建失败；
- dry-run 未通过；
- 工作树不干净；
- 既有人工中文被覆盖或删除；
- Exedra 出现机翻来源、机翻统计或 AI 入口；
- 124 个 Exedra 中文组或 410 个语音模型数量漂移且没有审计解释；
- JSON 与 TXT 不能往返验证；
- Worker/KV/域名指向生产资源；
- 目标分支不是 `EXEDRA-TEST`。

## 9. 回滚

测试 Worker 与生产 Worker 分离。若上线烟雾测试失败：

1. 不推进或回滚 `EXEDRA-TEST` 合并；
2. 将测试 Worker 回滚到上一版本；
3. 保留测试 KV 供投稿审计，除非明确确认可清理；
4. 不修改 `main`、生产 Worker、生产 KV 或 Release。
