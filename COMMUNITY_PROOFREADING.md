# MagiReader 社区中文校对系统

本系统让普通访客在阅读器中修订中文剧情，但不会让访客直接写入仓库。所有修订先进入独立 Cloudflare KV 审核队列，只有具有仓库写入权限的审核者批准后，系统才建立一个只修改单个中文 TXT 的 GitHub Pull Request。

## 数据流

1. 访客打开剧情，点击“协助汉化”。
2. 阅读器保留 Section、分支、角色位置和动作元数据，访客只编辑中文显示文本。
3. 投稿前由 Turnstile 进行人机验证。
4. 投稿保存到专用 KV，并记录：
   - 剧情 ID、中文/日文网页路径和完整 source identity；
   - 当前 `story_index.json` SHA-256；
   - 编辑前中文源文件 SHA-256；
   - 编辑前规范化文本 SHA-256；
   - 修订正文 SHA-256；
   - 部署来源提交、目标分支、昵称、修改说明和时间。
5. 投稿者取得只保存在浏览器中的回执，可在 `/proofreading/status` 查询状态。
6. 审核者打开 `/review/submissions`，查看当前中文、投稿中文、日文原文和逐行差异。
7. 审核者可暂缓、驳回或批准。批准时服务器会再次从 GitHub 读取 `EXEDRA-TEST` 当前源 TXT，验证基准哈希及 Section/Branch 结构。
8. 验证通过后，创建 `community-proofreading/...` 分支和 PR。PR 只能修改一个规范中文 TXT。
9. `Validate Community Proofreading PR` 执行完整 Python 数据管线、剧情目录生成、Lint、TypeScript、前端测试、搜索索引校验和 Cloudflare Worker 构建。
10. PR 合并后，投稿状态会在投稿者或审核者查询时同步为“已合并”。

## 审核权限

审核后台接受以下任一种凭据：

- GitHub fine-grained personal access token：必须能访问 `HiiragiNemu/magi-reader`，并具有 Contents Read and write、Pull requests Read and write 权限；
- `SUBMISSIONS_ADMIN_TOKEN` Worker secret。使用共享密钥批准 PR 时，还必须配置服务器端 `PROOFREADING_GITHUB_TOKEN`。

GitHub PAT 只保存在当前浏览器标签页的 `sessionStorage`，请求通过 HTTPS 发送到 Worker，仅用于验证仓库写权限和创建 PR，不写入 KV。

## Cloudflare 资源

测试站使用独立资源：

- Worker：`magireader-exedra-cn-test`
- KV：`magi-submissions-exedra-cn-test`
- 正式站 Worker 和正式投稿 KV 不会被测试部署覆盖。

测试部署工作流会自动发现或创建 KV。当前 Cloudflare API Token 需要：

- Workers Scripts Edit；
- Workers KV Storage Edit；
- Account Settings Read（Wrangler 可能需要）。

全文搜索索引仍需要 R2 Object Read and Write；缺少 R2 权限时只影响正文全文搜索，不影响剧情浏览、页内搜索、标题搜索和校对投稿。

## GitHub Secrets

仓库 Actions 建议设置：

| Secret | 必需 | 用途 |
| --- | --- | --- |
| `CF_API_TOKEN` | 是 | 部署 Worker、创建/读取 KV |
| `CF_ACCOUNT_ID` | 是 | Cloudflare 账户 |
| `TURNSTILE_SITE_KEY` | 正式开放前必需 | 真实 Turnstile 站点密钥 |
| `TURNSTILE_SECRET_KEY` | 正式开放前必需 | 真实 Turnstile 私钥 |
| `PROOFREADING_GITHUB_TOKEN` | 可选 | 允许共享管理员密钥批准 PR，并让公开状态页自动同步 PR 状态 |
| `SUBMISSIONS_ADMIN_TOKEN` | 可选 | 共享审核密钥，至少 32 字符 |

若未配置真实 Turnstile 密钥，测试部署会使用 Cloudflare 官方测试密钥，并在校对界面明确显示警告。测试密钥不能作为正式防滥用方案。

## Turnstile 正式配置

在 Cloudflare Dashboard 创建一个 Managed Turnstile widget，允许域名：

```text
magireader-exedra-cn-test.crynetsystemscell.workers.dev
```

将站点密钥和私钥分别保存为 GitHub Secrets `TURNSTILE_SITE_KEY`、`TURNSTILE_SECRET_KEY`，然后重新运行 `Deploy Exedra Community Proofreading Test Site`。

## 安全边界

- 公开投稿只接受当前剧情目录中的 ID。
- 单次请求最大 2 MiB，正文最大 500,000 字符。
- 每个来源每 10 分钟最多 5 次有效投稿。
- 完全相同的修订在 30 天内去重。
- 路径、source identity、SHA-256、UTF-8、Section/Branch 结构全部 fail-closed 校验。
- 审核详情不会返回投稿回执哈希或 KV 内部索引 key。
- PR 只能修改一个位于中文语料树中的 `.txt` 文件；备份、临时文件和其他代码改动会被 CI 拒绝。
- 源 TXT 或剧情目录变化后，旧投稿会标记为过期，不能覆盖新版。
- 所有 PR 仍需人工合并；路人没有直写 `EXEDRA-TEST` 或 `main` 的权限。

## 页面

- 访客校对：任意 `/reader/<id>` 页面中的“协助汉化”
- 投稿状态：`/proofreading/status`
- 管理员审阅：`/review/submissions`
