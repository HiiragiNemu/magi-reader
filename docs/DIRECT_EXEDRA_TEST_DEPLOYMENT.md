# Exedra / General Voice 独立测试部署

本流程不使用 GitHub Actions，不覆盖生产 Worker `magireader`，不修改 `main`。

## 固定测试资源

- 代码分支：`feature/exedra-cn-and-magireco-voice`
- 合并目标：`EXEDRA-TEST`，仅在完整验收后合并
- 测试 Worker：`magireader-exedra-cn-test`
- 测试 KV namespace 名称：`magi-submissions-exedra-cn-test`
- 生产 Worker：`magireader`，本流程不得部署到该名称

## 环境 A：Git、npm、Cloudflare 均可访问

```powershell
cd D:\magia\MyProducts\magi-reader
git fetch origin
git switch feature/exedra-cn-and-magireco-voice
git pull --ff-only

cd website
npm ci
npx.cmd wrangler whoami
npm run deploy:test:direct
```

`deploy:test:direct` 会依次：

1. 运行可信来源政策验证；
2. 编译 Python 工具并运行 Python 回归测试；
3. 根据 KV 名称精确解析真实 namespace ID；
4. 生成只存在于 `.wrangler/direct-test/` 的临时配置；
5. 将 Worker 名和 `WORKER_SELF_REFERENCE` 都改为测试 Worker；
6. 运行 ESLint、TypeScript、Node 测试；
7. 安全构建 OpenNext，并在构建期间暂存超过 Cloudflare 单文件上限的本地搜索文件；
8. 暂存 OpenNext 自动生成的 Wrangler 重定向配置；
9. 使用显式测试配置执行 `wrangler deploy --strict`；
10. 删除含真实 KV ID 的临时配置并恢复原配置。

先只验证、不部署：

```powershell
npm run deploy:test:direct -- --dry-run
```

已知 KV ID 时可跳过名称查询：

```powershell
npm run deploy:test:direct -- --kv-id 0123456789abcdef0123456789abcdef
```

不得把真实 KV ID 写回 `wrangler.jsonc`。

## 环境 B：Git/codeload 被封锁，但 api.github.com 可访问

```powershell
$env:GH_TOKEN = '仅需仓库读取权限的令牌'
py tools\github_api_checkout.py HiiragiNemu/magi-reader `
  --ref feature/exedra-cn-and-magireco-voice `
  --output D:\work\magi-reader `
  --zip D:\work\magi-reader.zip
```

该工具通过 GitHub commit/tree/blob REST API 重建分支，并验证每个 blob 的 Git SHA-1。它拒绝：

- 路径越界；
- 绝对路径；
- 不安全符号链接；
- submodule；
- 超过 100 MiB 的普通 Git blob；
- 非空目标目录，除非显式 `--force`。

恢复后进入 `website`，执行环境 A 的 `npm ci` 和部署命令。

## 环境 C：完全无出站网络

在这种环境中，修改 DNS、代理、Hosts、GitHub 域名或 codeload 地址均无法恢复克隆，因为 TCP 出站本身被禁止。此时只能：

- 使用已连接的 GitHub 服务读写仓库；
- 完成纯代码审计和连接器级提交；
- 在另一个具有 npm/Cloudflare 网络的执行环境完成真实构建与部署。

不得把“GitHub 连接器可以读写”误报成“容器可以克隆或部署”。

## 独立验收

部署后至少检查：

```powershell
$Base = 'https://magireader-exedra-cn-test.<你的 workers.dev 子域>'
Invoke-WebRequest "$Base/story_index.json" -UseBasicParsing
Invoke-WebRequest "$Base/search_index_manifest.json" -UseBasicParsing
Invoke-WebRequest "$Base/data/general_voice/100100/100100_cn.txt" -UseBasicParsing
```

页面验收：

- Exedra 分类依次显示：`主线、活动、角色、肖像、语音、Namae、过场动画字幕、战斗`；
- 分类名称前没有数字；
- Magia Record 出现 `语音` 分类；
- Exedra 没有机器翻译统计、橙色机翻标记或 AI 生成入口；
- 没有可信中文的 Exedra 剧情保持日文/无中文状态；
- `/review/machine-translations` 只管理魔法纪录 507 部基线；
- `/review/exedra-localization` 只检查 Wiki 人工中文、导出可信缓存和清除旧机翻缓存；
- 语音上游临时不可用时，原始剧情目录仍然可用；
- 生产站点和生产 Worker 未变化。

## 合并禁令

出现任一情况时不得合并到 `EXEDRA-TEST`：

- `npm run check` 未通过；
- `npm run build:worker` 未通过；
- `npm run deploy:test:direct -- --dry-run` 未通过；
- 测试 Worker 真实部署未通过；
- Exedra 分类仍显示旧数字或 `Sub/Dungeon`；
- Exedra 出现自动机翻入口或旧机翻缓存仍参与页面统计；
- 任何既有人工中文文件被覆盖；
- Worker 名或 KV 指向生产资源。

## 回滚

测试 Worker 与生产 Worker 完全分离。测试失败时：

1. 不合并长期分支；
2. 将测试 Worker 回滚到上一版本或删除测试 Worker；
3. 保留测试 KV 供审计，或在确认不含人工投稿后单独清空；
4. 不修改生产 `magireader` Worker、生产 KV 或 `main`。
