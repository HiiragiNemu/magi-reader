# 下一位 AI 交接（2026-07-28）

工作分支：`feature/exedra-cn-and-magireco-voice`，基线 `EXEDRA-TEST`；禁止修改 `main`。当前测试站尚未部署本分支。

## 最终目标

1. 完成魔法纪录语音分类：从 `io.kamihama.totentanz/scenario/general` 提取脚本，参考 `MagiaExedraLive2DViewerPersonal` 角色/语音映射，生成可播放 JSON 与 TXT。
2. 完成 Exedra 中文化。来源优先级：仓库既有中文 > Exedra Wiki 中文角色剧情 > 0728 人工文本。0728 文本不是机翻，不得标机翻；Exedra 自动机翻已取消。
3. 对每个中文来源只替换用户可见文本，保留动作、资源 ID、分支、Section、说话人顺序和其他非中文字段；生成并验证可播放 JSON，再生成 TXT。
4. 魔法纪录与 Exedra 人工校验均须支持：审核后生成可播放 JSON + TXT，不得只改 TXT。
5. 阅读/校验界面增加布局选项：手机端可选中日对照格式；PC 端支持上下排列中日对照，汉化页面同样适用。
6. 完成 `npm ci`、Python/Node/TS/Lint/测试、OpenNext 构建、Wrangler dry-run、独立 Worker 部署及线上烟雾测试；部署目标仅为 `magireader-exedra-cn-test`。

## 已落盘研究/实现

- 分类改名、Exedra 机翻取消、可信 Wiki/台服导入框架、事务式 JSON/TXT/报告生成器。
- 411 个魔法纪录 general voice 的运行时与离线导入框架。
- GitHub API checkout 备用工具、直接 Cloudflare 测试部署工具、质量门和交接文档。
- 0728 RAR 的完整文件清单与哈希已落盘 `artifacts/source-archives/rounddora-text-0728.manifest.json`；原始 RAR 是用户输入附件，下一位 AI 必须重新取得并验证 SHA-256 为 `2f55e92bd8ceb310ba37c7a7b5dd94dffe5849d1266017021ff52366595b572c`。

## 下一步先做

重建并解析 0728 包（640 个 `.ass`），建立文件名→Exedra manifest/story ID/Section 的显式映射；逐角色先抓 Wiki，Wiki 缺失才使用 0728；随后生成 JSON、验证播放结构、生成 TXT，再接通校验界面的 JSON/TXT 双输出和响应式中日布局。完成后构建并部署独立测试站。
