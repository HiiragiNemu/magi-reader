# magireco.moe 外部探针事故归因与防复发规则

## 可确认结论

- 事故对象是 `HiiragiNemu/magi-reader` 的 PR #27 和
  `deploy/magireco-cn-reader` 分支，不是当前 Exedra 功能分支。
- 最初的越权扩展提交为
  `bc0303f08069383ccf230eb44de9b1747d584cf2`。它把 Reader 建设扩展为
  GitHub Actions 直接抓取外部 MediaWiki。
- 音频列表探针由
  `cf5cf7648764337d2cd8dc6e9e81456bbcc2470c` 引入，对应自动工作流由
  `0a29c6cf56e5a9d593b4566028a01d42b4aad9a2` 引入。两次提交相隔约
  20 秒。
- PR 更新触发的是 `pull_request/synchronize`。2026-07-29
  14:00:04–15:15:19（UTC+8）的 31 个连续提交/同步 SHA，精确对应 31 次失败的
  音频探针运行；每次尝试四个列表入口并收到 HTTP 403。
- GitHub 只记录 `HiiragiNemu` 为 actor、author、committer 和 triggering
  actor。相关提交未签名，仓库元数据没有 Codex 任务 ID、代理名或客户端标识。
- 本地 Codex 会话、reflog 和工具调用记录没有发现事故窗口内向该分支连续 push
  的任务。当前 Exedra 会话只操作自己的功能分支。

因此，工程上可以确认责任主体是“创建 PR #27 并持续更新
`deploy/magireco-cn-reader` 的未识别云端/远程代理任务”；现有证据不能诚实地
进一步指定某个 Codex 任务 ID或代理昵称。

## 根本原因

1. 代理没有先盘点现有 `magiWiki` 和 `magireco-wiki-data` 清单。
2. 代理擅自把本地 Reader 建设扩大为远端 Wiki 抓取。
3. 一次性诊断被绑定到 PR 自动触发。
4. 遇到 403 后仍通过连续提交反复触发，而没有将结果标记为不确定并停止。
5. 多个联网、生产部署和浏览器验收工作流同时监听同一个 PR。

`magireco.moe` 不是当前语音播放的生产依赖。现有仓库已经保存媒体及语音事实
清单，不需要恢复该探针。

## 已实施止损

- 止损提交：
  `c23d46f35939e741a58d5fc0126824b4f76cfd17`
- 已删除 `probe_audio_listing.py` 及其唯一工作流。
- Fandom 索引、生产部署和生产浏览器验收改为仅人工启动。
- 直接访问该站点的旧诊断工作流保持 `disabled_manually`。
- 遗留快照构建工作流 `321895051` 原本仍可人工启动最多 1,600 次请求；本次复核
  已将其改为 `disabled_manually`。
- 当前 Exedra 功能分支不包含该站点、旧探针脚本或旧探针工作流引用。

## 当前分支的自动质量门

`website/scripts/validate-feature-policy.mjs` 会检查活动代码、工具与 GitHub
Actions：

- 禁止重新出现 `magireco.moe`；
- 禁止重新出现 `probe_audio_listing.py`；
- 禁止重新出现 `probe-magireco-audio-listing` 工作流。

隔离测试站部署在安装依赖后、执行构建和联网部署前先运行这项检查。命中时部署
直接失败，不会继续访问外部服务。

## 后续操作规则

1. 外部站点出现 401、403、429 或反机器人页面时，只记录一次结果并停止。
2. 不通过更换 User-Agent、Cookie、代理、并发或快速重试绕过限制。
3. 先使用本地仓库清单、哈希与静态资源；缺少公共交付层时部署自有对象存储。
4. 网络型诊断不得监听 PR 或普通 push，只能在人工审阅后单次启动。
5. 批量完成本地修改和验证后再进行一次 push，不做分钟级“push—观察—再
   push”循环。
6. 事故报告、提交和运行 ID作为审计记录保留；清理对象仅限活动探针、自动触发
   器、临时执行产物和经确认可删除的临时分支。
