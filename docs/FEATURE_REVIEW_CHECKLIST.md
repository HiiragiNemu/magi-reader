# `feature/exedra-cn-and-magireco-voice` 最终审查清单

目标：仅合并到 `EXEDRA-TEST` 并部署独立测试 Worker。禁止写入 `main` 或生产 Worker。

## 来源政策

- [x] 仓库既有中文保持最高优先级且不覆盖。
- [x] Exedra Wiki 精确中文优先于 0728。
- [x] 0728 只补 Wiki 没有可靠覆盖的剧情。
- [x] Wiki、0728 和 Wiki Voice 都标为人工来源。
- [x] Exedra 自动机翻计划取消，代码和页面无 AI 入口。
- [x] 魔法纪录 507 部机器翻译校验保持独立。

## 0728 审计

- [x] RAR SHA-256 为 `2f55e92bd8ceb310ba37c7a7b5dd94dffe5849d1266017021ff52366595b572c`。
- [x] 清点 640 个 ASS、6,132,347 字节。
- [x] 写入逐文件路径、大小、SHA-256、编码、行数和对白数清单。
- [x] 原始 RAR 未提交 Git。
- [x] 181 个实际采用 ASS 有精确映射证明。
- [x] 未把剩余 459 个一律误报为错误或强行套用。

## Exedra 角色剧情

- [x] 61 个角色组中 51 个有中文。
- [x] 5 个旧本地中文组未改动。
- [x] 6 个纯 Wiki、15 个纯 0728、25 个混合组。
- [x] Wiki 187 JSON / 9,048 事件。
- [x] 0728 181 JSON / 9,004 事件。
- [x] 10 个无法安全匹配组保持拒绝。
- [x] 不使用 LCS、模糊匹配或重排。

## Exedra Wiki 语音

- [x] 审计 158 个 `/Voice/zh` 页面、2,990 行。
- [x] 使用日文正文或音频文件名精确匹配。
- [x] `Lux☆Magica` 62 行已审计，14 行用于 `cv_100101`。
- [x] 73 / 86 个 reaction 组已生成。
- [x] 1,022 JSON / 2,938 事件。
- [x] 13 个不满足精确条件组保持拒绝。

## JSON-first 与发布

- [x] 新中文以日文 JSON 为结构模板。
- [x] 只替换已证明的可见文本。
- [x] 动作、资源、音频、角色、sheet/row 和未知字段保持。
- [x] 中文 JSON 验证通过后才生成规范 TXT。
- [x] 失败组事务回滚，不留半成品。
- [x] `generate_story_index.py` 复核 manifest、报告、哈希、事件和说话人顺序。
- [x] Exedra 124 / 443 中文，119 个新 JSON-backed 组，319 个仍缺。
- [x] 发布 1,390 个 Exedra 中文 JSON 和 20,990 条事件。
- [x] `story_index.json` 为 119 个 Exedra 组发布 `json_paths_cn`。

## 魔法纪录 general voice

- [x] 分类键 `general_voice`，显示名“语音”。
- [x] 410 个有效模型静态落盘，`xxxx.json` 无效占位被拒绝。
- [x] 16,753 个语音组、18,233 条 manifest 语音。
- [x] 9,107 个 `textHome` 事件。
- [x] 8,727 个可编辑组；8,026 个无 `textHome` 组保持只读。
- [x] 315 个多 `textHome` 组按事件逐行生成。
- [x] 源/中文 manifest 字节一致且哈希已更新。
- [x] 410 个 TXT 和 410 个 JSON进入 public 与 story index。

## 人工校验双产物

- [x] 魔法纪录剧情支持从审核 TXT 物化 JSON，再重建 TXT。
- [x] 魔法纪录 general voice 支持 JSON、TXT、报告和两个 manifest 同步。
- [x] Exedra 支持从审核 TXT 物化全部对应 JSON，再重建 TXT。
- [x] 投稿基准 SHA-256、目录身份和 Section 结构 fail-closed。
- [x] `--base-ref` 阻止 PR 夹带非文本 JSON 结构。
- [x] PR CI 严格限制变更路径并把物化产物提交回同一 PR。
- [x] 物化后继续运行 Python、目录、机翻、前端、搜索和 Worker 质量门。

## 界面

- [x] `Sub` 显示为“活动”。
- [x] `Dungeon` 显示为“过场动画字幕”。
- [x] Exedra 分类移除数字前缀。
- [x] Exedra 页面没有机器翻译统计或橙色机翻标记。
- [x] 左右/上下中日排列选项共用持久化设置。
- [x] 布局代码同时作用于阅读和编辑行。
- [x] 本地浏览器已看到分类、51 / 61 角色覆盖、布局设置和环彩羽中文。
- [ ] 最终手动点击“上下排列”，并在“协助汉化”模式确认编辑布局。

## 数据与本地验证

- [x] 生成 3,012 条 story index。
- [x] Exedra 443 / 中文 124 / general voice 410。
- [x] 公开 JSON 总数 1,800。
- [x] 魔法纪录机翻清单为 507，可信人工覆盖/删除为 0。
- [x] Python 测试 143 通过、2 跳过。
- [x] `npm ci` 完成。
- [x] 最终 `npm run check`：feature policy 97 项、Python 143 通过/2 跳过、ESLint、TypeScript、83 / 83 Node、生产依赖审计通过。
- [x] 搜索生成/验证：5,242 条。
- [x] 在最后一次静态 Exedra 路由修复后重跑 OpenNext Worker 构建和 Cloudflare 输出验证。
- [x] 本地浏览器验证左右/上下排列、普通阅读、汉化编辑、Exedra 静态中文和 general voice。
- [x] `npm run deploy:test:direct -- --dry-run` 通过：9,029 个静态资源、测试 Worker/KV/域名/目标分支绑定正确。

## Git、部署与线上

- [x] 审计最终 Git 差异和秘密/临时文件：无凭据、超大文件、既有人工译文修改/删除或 `main` 变动。
- [ ] 提交并推送 `feature/exedra-cn-and-magireco-voice`。
- [ ] 建立目标为 `EXEDRA-TEST` 的 PR。
- [ ] 等待全部 CI 通过。
- [ ] squash merge 到 `EXEDRA-TEST`。
- [ ] 部署 `magireader-exedra-cn-test`。
- [ ] 在线验证首页、story index、410 general voice TXT/JSON。
- [ ] 在线验证 Wiki/0728 Exedra TXT/JSON。
- [ ] 在线验证布局、编辑、投稿和管理员 API。
- [ ] 确认 Exedra 无机翻来源，魔法纪录仍为 507。
- [ ] 确认 `main`、生产 Worker 和生产 KV 未变化。

## 已知非阻断/需单独披露项

- [x] 全文搜索 payload 已本地生成和验证。
- [ ] 当前 Cloudflare Token 没有 R2 权限，79,001,794 字节对象尚未上传。
- [ ] 真实 Turnstile 和共享管理员密钥尚未确认；测试站可能继续使用 Turnstile 测试模式。

Git、最终 dry-run 和线上项目未全部勾选前，不得表述为“已部署完成”。
