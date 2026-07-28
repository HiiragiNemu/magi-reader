# `feature/exedra-cn-and-magireco-voice` 审查清单

目标基线：`EXEDRA-TEST`。禁止直接合并到 `main`。

## 产品决策

- [x] `Sub` 显示为 `活动`。
- [x] `Dungeon` 显示为 `过场动画字幕`。
- [x] Exedra 分类名称移除数字前缀。
- [x] Exedra 自动机翻计划取消。
- [x] 魔法纪录 507 部机器翻译校验保持独立。
- [x] Exedra 只接受本地人工、官方台服、Exedra Wiki 人工中文。

## 数据安全

- [x] 未修改既有 Exedra/魔法纪录人工中文语料。
- [x] 台服导入器按 manifest 完整来源路径匹配。
- [x] JP/TW 动作、sheet、row、事件数精确验证。
- [x] Wiki 缓存绑定 story ID、source identity、JP/CN SHA-256 和 exedra.wiki URL。
- [x] 两条导入器均使用临时目录、独立 schema-v1 验证和拒绝覆盖。
- [x] 可提交报告不包含用户电脑绝对路径。
- [x] 旧 Exedra 机翻缓存只可定向清除，不参与可信中文读取。

## 运行时

- [x] Exedra 目录从静态资源运行时加载，不把完整 story index 重复内嵌进 Worker。
- [x] 411 个魔法纪录语音模型使用固定上游提交。
- [x] 语音清单和脚本具备实例缓存及旧缓存回退。
- [x] 语音上游冷启动失败时基础剧情目录仍可用。
- [x] 全文索引明确声明 `general_voice` 尚未覆盖。

## 构建与部署

- [x] 无 Git/codeload checkout 备用工具。
- [x] 直接部署使用独立测试 Worker 和 KV。
- [x] 临时配置不写回仓库，包含真实 KV ID 的文件部署后删除。
- [x] OpenNext 61 MiB 本地全文文件在构建期间安全暂存。
- [x] Node 测试实际执行 `.test.ts`。
- [x] Python 工具编译和无网络回归测试纳入质量门。
- [x] 可信来源政策验证不可绕过。
- [ ] 在可访问 npm registry 的环境执行 `npm ci`。
- [ ] 执行 `npm run check`。
- [ ] 执行 `npm run build:worker`。
- [ ] 执行 `npm run deploy:test:direct -- --dry-run`。
- [ ] 部署 `magireader-exedra-cn-test`。
- [ ] 完成页面、API、语音和可信中文烟雾测试。

未完成最后六项前，不得合并到 `EXEDRA-TEST`。
