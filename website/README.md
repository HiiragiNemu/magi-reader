# Magi Reader 网站

该目录是基于 Next.js 16、React 19 和 OpenNext for Cloudflare 的剧情阅读网站。生产环境部署目标是 Cloudflare Workers，静态文件由 Workers Assets 提供；服务端代码不会复制到静态资源目录。

## 本地运行

需要 Node.js 22 和 npm。

```bash
npm ci
npm run dev
```

打开 <http://localhost:3000>。

OpenNext 会从 `wrangler.jsonc` 创建本地 Cloudflare 运行环境。管理员查询接口所需的本地密钥应写入未受版本控制的 `.dev.vars`：

```dotenv
SUBMISSIONS_ADMIN_TOKEN=replace-with-at-least-32-random-characters
```

不要把该密钥放入 `next.config.ts`、`.env.production` 或任何以 `NEXT_PUBLIC_` 开头的变量。

## 检查与构建

```bash
npm run lint
npm run type-check
npm test
npm run build
```

`npm run check` 会依次执行 lint、类型检查和测试。

Cloudflare 构建还会执行 `verify:cloudflare-output`，一旦发现服务端目录被放入 `.open-next/assets` 就会中止预览或部署。正式部署还会执行 `verify:cloudflare-config`，阻止使用占位或与缓存共用的投稿 KV namespace。

生产构建的本地预览：

```bash
npm run preview
```

## Cloudflare 运行时绑定

`wrangler.jsonc` 声明了以下投稿接口绑定：

- `SUBMISSIONS_KV`：独立保存投稿和短期限流计数。
- `SUBMISSIONS_ADMIN_TOKEN`：只作为 Cloudflare Worker secret 配置，不写入仓库。

仓库中的 `SUBMISSIONS_KV` 使用全零占位 ID，以保证未完成配置时远程部署会失败。首次手动部署前创建独立 namespace，并把命令返回的 ID 填入本地 `wrangler.jsonc`：

```bash
npx wrangler kv namespace create SUBMISSIONS_KV
```

然后为 Worker `magireader` 配置管理员密钥：

```bash
npx wrangler secret put SUBMISSIONS_ADMIN_TOKEN
```

`POST /api/submit` 允许匿名贡献，但会校验请求类型和长度，并优先按 Cloudflare 提供的客户端 IP 进行短期限流。非 Cloudflare 本地环境会依次回退到代理 IP、受限客户端指纹或每请求随机标识，不会让所有未知客户端共用同一个限流键。

该限流使用 KV 固定窗口计数。由于 KV 最终一致性，它只是削减普通滥用的软限流，并非严格配额或安全边界；高流量生产环境应另行配置 Cloudflare Rate Limiting binding 或 Durable Object。

`GET /api/submit` 只接受管理员 Bearer token：

```bash
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  "https://YOUR_WORKER/api/submit?limit=50"
```

`SUBMISSIONS_ADMIN_TOKEN` 至少需要 32 个字符。如果没有配置或长度不足，查询接口会保持关闭。

## 搜索索引发布

`build_search_index_v6.py` 会从当前 `story_index.json` 和实际剧情文件重新生成两项产物：

- `search_content.json`：正文搜索大文件，只上传到 R2，不进入 Worker 静态资源。
- `search_index_manifest.json`：很小的内容寻址清单，随网站部署。

清单中的 R2 object key 包含搜索大文件的 SHA-256。浏览器始终先读取同源清单，再校验并加载对应的 R2 对象；旧的固定 R2 和 GitHub Release 地址只在清单或新对象不可用时回退。Cloudflare 输出检查会拒绝把 `search_content.json` 误打包进站点。

GitHub Actions 会完整重建并再次验证索引，完成网站构建后先上传哈希对象，最后才部署包含新清单的 Worker。这样部署失败只会留下一个无人引用的哈希对象，不会让已上线清单指向尚未上传的文件。

本地 `public/search_content.json` 只用于开发调试。Cloudflare 构建会在转换期间把它移到可恢复的本地备份目录，并在成功或失败后恢复，避免它进入部署产物。

## 部署

手动部署：

```bash
npm run deploy:worker
```

如果尚未替换 `SUBMISSIONS_KV` 的全零占位 ID，部署会在本地校验阶段停止，不会向 Cloudflare 提交。本站当前不使用 ISR，因此没有声明不会生效的旧缓存绑定；若将来启用 ISR，应同时在 `open-next.config.ts` 中配置 OpenNext 缓存适配器及其对应绑定。

GitHub Actions 只在推送到 `main` 时运行生产部署；`EXEDRA-TEST` 等测试分支不会触发。仓库需要配置 `CF_API_TOKEN`、`CF_ACCOUNT_ID` 和 `SUBMISSIONS_KV_NAMESPACE_ID` 三个 Actions secrets。流水线只把 namespace ID 写入临时部署配置，不改动或输出仓库模板；管理员 token 继续使用 Cloudflare Worker secret，不经过 Actions 构建。
