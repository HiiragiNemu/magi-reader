# 2026-07-29 GitHub Actions 外部探针与通知风暴

## 状态

- 事故已止损。
- `magireco.moe` 音频列表探针已确认不属于生产依赖，并从当前分支删除。
- Fandom、生产部署和生产浏览器验收不再由 PR 更新自动触发。
- `Probe Magireco Audio Listing`、`Probe Private Media Repository Access` 和旧
  `Probe Magireco Wiki Endpoints` 的 GitHub workflow 注册项保持停用。
- 本次修复没有访问 `magireco.moe`；验证只使用仓库、既有产物和静态检查。

## 影响范围

事故集中在 2026-07-29 14:00–15:15（UTC+8）：

- 仓库：`HiiragiNemu/magi-reader`
- PR：[#27](https://github.com/HiiragiNemu/magi-reader/pull/27)
- 基础分支：`main`
- 事发分支：`deploy/magireco-cn-reader`
- 事发末端提交：`db6885e1201b5bf09c2f51f871f1506d20b5a145`
- 事发时 PR 规模：143 个提交、59 个变更文件

邮件侧共观察到 59 封失败通知，其中 58 封属于本仓库的多工作流触发链，
另 1 封 `ma-ex-dataSP / Data Sheet Uploader` 属于独立仓库和独立事故。
GitHub 运行记录确认同一时段存在大量成功、失败和被并发取消的重复运行；
通知数量和运行数量不会一一对应。

## 根本原因

根本原因不是 Gmail 重发，也不是固定定时任务失控，而是：

```text
短时间内连续修改、commit、push
→ PR #27 连续收到 synchronize 事件
→ 多个 workflow 的 pull_request 路径过滤同时命中
→ 外部网络探针、生产部署和生产浏览器验收并发启动
→ 每个失败运行分别生成 GitHub 邮件
→ 下一次 push 再重复整条链
```

`pull_request.paths` 针对 PR 相对基础分支的累计变更集合判断，不只检查最新
一个提交。因此 PR 一旦同时包含脚本、静态资源和 workflow 文件，后续看似无关
的更新也可能继续命中多个工作流。

持续失败的直接原因是 GitHub 托管 Runner 访问
`magireco.moe/Special:ListFiles` 时收到 HTTP 403。示例：

- Workflow run：
  [30430982104](https://github.com/HiiragiNemu/magi-reader/actions/runs/30430982104)
- 事件：`pull_request`
- head SHA：`db6885e1201b5bf09c2f51f871f1506d20b5a145`
- 结果：4 个列表 URL 均为 HTTP 403、0 个 MP3 链接，脚本以退出码 1 结束

这表示“外站拒绝云端自动访问，结果不确定”，不表示 Reader 构建代码本身错误。

## `magireco.moe` 是否为音频必需依赖

结论：**不是。音频列表探针可以完全取消。**

代码引用审计显示：

- `probe_audio_listing.py` 只被
  `.github/workflows/probe-magireco-audio-listing.yml` 调用。
- Reader 的 build、integrate 和 runtime 均不读取该脚本的输出。
- 当前 `build_voice_audio_index.py` 从 Fandom API 发现文件名和标签，并生成
  `GitHub raw MP3 → cn-cdn MP3 → Fandom OGG` 三源列表。
- `integrate_voice_audio.py` 只消费本地 JSON；不访问 `magireco.moe`。

已有仓库足以充当音频事实层：

- `HiiragiNemu/magiWiki/images/meta.json` 记录 30,286 个媒体文件和
  21,225 个唯一 MP3，其中 21,218 个文件名符合 `Vo_char_*` 或 `Vo_game_*`。
- `magiWiki` 远端实际跟踪全部 21,218 个 `Vo_*` 语音 MP3。总 MP3 跟踪数为
  21,223；另外两个非 `Vo_*` 背景 MP3
  （`まだダメよ.mp3`、`日常、或いは友のまどろみに添えて.mp3`）
  只存在于本地未跟踪工作树。
- `HiiragiNemu/magireco-wiki-data` 已保存 `media_manifest.json`、
  `voice_manifest.json`、`voice_index.json`、`voice_sources.json` 和
  `voice_subtitles.json`。其校验报告记录 21,225 个音频、缺失 SHA-256 为 0，
  且整体校验通过。
- 当前线上 Reader 已有 21,081 条音频索引（20,807 条角色语音、274 条
  game 音频），覆盖 99.3216%；相对 21,225 的 144 条计数差可以通过现有
  `magiWiki` 清单离线补齐或分类，不需要重新探测 `magireco.moe`。

但“仓库中已有文件”不等于“匿名浏览器已经能直接播放 GitHub 主源”。目前仍有
两个独立的公开交付缺口：

1. `magiWiki` 是私有仓库，匿名 `raw.githubusercontent.com` 请求不能读取；
   禁止把私有访问令牌放进前端。
2. 仓库实际路径是 `images/<MD5 前两位>/<文件名>`，当前 Reader 生成器却构造
   `images/<MD5 首位>/<MD5 前两位>/<文件名>`。即使仓库变为公开，现有 URL
   也会因路径错位失败。

在建立受审阅的公共媒体发布层或修正路径前，线上播放实际上主要依赖
`cdn.mfjl.wiki`，再回退到 Fandom；这两个缺口不构成保留
`magireco.moe` 探针的理由。

## 来源归因边界

GitHub 只记录 GitHub 身份 `HiiragiNemu` 为 actor、triggering actor、
author 和 committer。两个关键提交均未签名：

- `e6adf255c1ffd9f9b1b1ba89c60b925794006391`
- `db6885e1201b5bf09c2f51f871f1506d20b5a145`

这些元数据不能区分人工操作、ChatGPT/Codex 云端任务、IDE 代理、本地脚本或
其他持有同一凭据的会话。

对事发时四个受监督的本地 Codex 任务进行只读核验后，没有发现它们向
`deploy/magireco-cn-reader` 执行 `git push`、手工启动涉事 workflow，或直接
运行 `probe_audio_listing.py` 的证据。至少一个任务使用不同仓库，使用
`magi-reader` 的任务也在独立 Exedra 功能分支工作。结论是：

- 事故窗口内四个任务及其他本地 Codex 会话均没有工具调用记录。
- `019fa932…` 使用 TW 研究仓库，`019fa937…` 使用 JP 研究分支，
  `019fa9ab…` 使用 Live2D Viewer 仓库。
- 唯一使用 `magi-reader` 的 `019fa936…` 只推送 Exedra 功能/修复分支，
  最晚在事故前约 12 小时完成。
- 本机 reflog 中，事发提交首次出现于本次调查的 clone/fetch，不是本地 push。
- 因此可用约 95% 的高置信度排除这四个本地任务是该轮连续推送的来源。
- 不能仅凭 GitHub 的账户字段确定真正执行 push 的具体客户端或会话。
- 剩余候选范围是其他云端任务、IDE/自动代理、脚本或人工会话。

## 已实施的修复

音频列表探针及其唯一 workflow 已从当前分支删除。以下现行 workflow 改为仅
允许 `workflow_dispatch` 人工启动：

- `.github/workflows/probe-fandom-voice-index.yml`
- `.github/workflows/deploy-magireco-ui-hotfix.yml`
- `.github/workflows/test-magireco-reader-v6.yml`
- `.github/workflows/inspect-magireco-character-html.yml`

仍保留的人工探针增加 `concurrency` 和 `cancel-in-progress: true`。

在修复推送前，以下 workflow 注册项被临时停用，防止修复提交本身再次触发
事故：

- `Probe Magireco Audio Listing`
- `Probe Fandom Voice Index`
- `Probe Private Media Repository Access`
- `Probe Magireco Wiki Endpoints`
- `Inspect Magireco Character HTML`
- `Deploy Magireco Reader UI`
- `Test Magireco Reader v6`

修复推送后，只恢复不直接访问 `magireco.moe`、仍有现行文件且已改为人工启动
的三个工作流：Fandom 索引、生产部署和生产浏览器验收。`Inspect Magireco
Character HTML` 虽已改为人工启动，但仍直接访问 `magireco.moe`，因此继续
保持停用。三个已删除定义的旧探针也继续保持停用。

## 后续 AI / 人工接手规则

1. 不得让外部站点探针、生产部署或生产浏览器验收监听 PR/push。
2. 不得把 HTTP 401、403、429 或反机器人页面解释为产品代码失败；标记为
   `inconclusive`，保存一次诊断后停止。
3. 不得快速重试同一外站，不得通过更换 User-Agent、代理或并发请求绕过限制。
4. 先在本地完成一批修改和离线验证，再进行一次经过审阅的 push；禁止
   “修改—push—看 CI—再修改—再 push”的分钟级循环。
5. 推送前检查 Actions 中是否已有同分支运行；重型/网络型 workflow 必须全局串行。
6. 不得重新启用 `Probe Magireco Audio Listing`、
   `Probe Private Media Repository Access`、`Probe Magireco Wiki Endpoints`
   或 `Inspect Magireco Character HTML`，除非取得人工批准。
7. 若确需人工探测，先确认站点允许自动访问，只运行一次，并审阅诊断文件中
   不含令牌、Cookie、私有 URL 或源码后再分享。
8. 任何新的邮件风暴应先停止 push 和禁用涉事 workflow，再调查具体客户端；
   不要用 GitHub 账户名臆断具体 AI 会话。
9. 后续音频索引补全优先消费 `magiWiki` / `magireco-wiki-data` 的清单和校验值；
   不得为了补齐 144 条计数差重新抓取 `magireco.moe`。
10. 若建设公共 GitHub 媒体读取层，必须先解决仓库可见性和两级/三级哈希路径
    不一致；不得在浏览器端嵌入私有仓库令牌。

## 验证清单

- [ ] workflow YAML 静态解析通过
- [ ] 音频列表探针及 workflow 已从目标分支删除
- [ ] 修复提交推送期间未创建新的涉事自动运行
- [ ] 三个非 `magireco.moe` 现行 workflow 恢复为 active，但只支持人工启动
- [ ] 四个直接访问或已删除的旧诊断 workflow 保持 `disabled_manually`
