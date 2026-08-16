# 507 部待校验剧情人工重译：接手指南

> 本文用于把 `reader/manual-gpt-retranslation-20260816` 分支上的人工重译工作安全交给其他 ChatGPT／Codex 窗口。接手者必须先完整阅读本文和 `PROCESSED_STORY_TITLES.md`，不得从聊天中的旧数字推断当前进度。

## 1. 唯一工作边界

- 仓库：`HiiragiNemu/magi-reader`
- 唯一允许写入的分支：`reader/manual-gpt-retranslation-20260816`
- 锁定任务范围：507 部标记为 `SOURCE_UNVERIFIED` 的候选剧情
- 严禁直接写入、合并或变基到：`main`、`EXEDRA-TEST` 及其他任何分支
- 严禁创建自动合并 PR；完成一批后只把提交推送到上述人工重译分支
- 当前准确完成数、剩余数和标题清单，以 `manual_retranslation/PROCESSED_STORY_TITLES.md` 为唯一准据
- 本文编写时记录为 70 / 507；接手时必须重新读取进度 MD，不得照抄该数字

建议接手后的第一条命令：

```bash
git fetch origin
git switch reader/manual-gpt-retranslation-20260816
git pull --ff-only origin reader/manual-gpt-retranslation-20260816
```

随后核对：

```bash
git branch --show-current
git status --short
git log -5 --oneline
```

如果当前分支不是 `reader/manual-gpt-retranslation-20260816`，立即停止写入。

## 2. 必须使用的文本来源

日文原文根目录：

```text
magireco-source-master/Scenarios_full
```

待替换的中文剧情根目录：

```text
magireco-translate-data-master/Scenarios_full
```

姓名与固定译名基准：

```text
website/app/config/dictionary.ts
```

人物称呼关系参考：

```text
https://github.com/HiiragiNemu/magireco-call-search-cn
```

现有待校验中文只能用于发现旧机翻问题和核对文件对应关系，**不得把旧中文当作翻译原文**。正文必须重新依据日文逐句判断。不得调用 Google 翻译、DeepSeek、百度翻译或其他机器翻译服务生成正文。

## 3. 可修改字段白名单

只允许修改以下十个字段中的字符串值：

```text
textLeft
textRight
textCenter
narration
progressNarration
textSelect
nameLeft
nameRight
nameCenter
nameNarration
```

禁止修改：

- JSON 对象层级、字段集合和字段顺序
- 数组长度及事件顺序
- 角色 ID、立绘、表情、动作、位置、口型、特效
- 背景、BGM、音效、转场、等待时间、镜头参数
- 素材 ID、变量、选择分支结构和其他功能性字段
- TXT、索引及与本批翻译无关的文件

## 4. 强制保留的功能性文本

翻译前后必须保持：

1. 每个字符串内 `@` 的数量完全相同。
2. 所有方括号控制码内容和顺序完全相同，例如：

```text
[chara:100702:effect_emotion_joy_0]
[se:7222_happy]
[bgEffect:shakeSmall]
[wait:0.8]
```

3. 花括号变量、格式化占位符和转义内容完全相同。
4. 空字符串仍为空字符串。
5. 原文中刻意保留的外语口癖要按角色语气判断。例如阿莉娜的英语夹杂不是漏译，不得机械全部汉化。

任何一项无法确认时，不得提交该剧情为“完成”。

## 5. 人名、昵称与称呼规则

- 先查 `dictionary.ts`，再查称呼关系仓库；不要凭旧机翻决定姓名。
- 全名、名字、昵称、敬称必须结合说话者与被称呼者的关系逐句判断。
- `ちゃん`、`さん`、`先輩`、亲属称谓等不能做全局字符替换。
- 已知命名冲突必须查异常记录。例如 `常盤ななか` 的规范中文名以词典中的“常盘七夏”为准，不能沿用旧文本中的“常盘七香”。
- 同一剧情内人名必须保持一致；若角色有故意改口或特殊称呼，应保留剧情意义。

## 6. 一批翻译的标准流程

### 6.1 选择下一批

1. 读取 `PROCESSED_STORY_TITLES.md`，提取所有 `[x]` ID。
2. 对照锁定的 507 部候选清单，只选择未标记完成的条目。
3. 同一候选剧情可能对应多个 JSON；必须把该条目引用的全部 JSON 都处理完，才能计入一部完成。
4. 优先每批处理 1—3 部，避免大包损坏后返工。
5. 开始前检查是否已有其他窗口正在处理同一 ID；不得重复或覆盖未合并的工作。

### 6.2 逐句翻译

对每个 JSON：

1. 从日文原始 JSON 按遍历顺序提取白名单字段。
2. 与中文 JSON 的字段路径逐项对齐。
3. 逐句翻译正文、旁白、选择项和说话人姓名。
4. 对看似可以保留的旧中文，也必须回到日文确认；“核对后保留”仍算人工复核字段。
5. 复查人物口癖、上下文指代、时态、敬语和情绪递进。
6. 不追求逐词直译；目标是符合《魔法纪录》既有汉化文风的自然中文，但不得增删剧情信息。

### 6.3 本地硬校验

每个 JSON 至少执行：

- JSON 重新解析
- 字段路径一致
- 白名单之外深度等值
- `@` 数量一致
- 方括号控制码序列一致
- 花括号变量和 printf 占位符一致
- 文件集合未变化

校验失败时，整部剧情不得计入完成。

## 7. 推荐提交格式：exact bundle

现有正式应用脚本：

```text
manual_retranslation/apply_exact_batches.py
```

现有 GitHub Actions 工作流：

```text
.github/workflows/manual-retranslation-apply.yml
```

对于较小翻译包，可放入：

```text
manual_retranslation/exact_bundles/<batch-name>.json.gz.b64
```

对于较大的翻译包，必须采用分片目录：

```text
manual_retranslation/exact_parts/<batch-name>/
├── 0001.part
├── 0002.part
├── ...
├── SHA256
└── READY
```

规则：

- `.part` 按文件名排序后直接拼接。
- `SHA256` 第一列为拼接后的完整 Base64 文本文件的 SHA-256。
- `READY` 必须最后提交；没有 `READY` 的目录会被工作流隔离跳过。
- 不得在分片尚未上传完整时提前创建 `READY`。
- 建议单片控制在 8—12 KiB，降低连接器截断或单文件写入损坏风险。

上传完成后，触发 `manual-retranslation-apply.yml`。只有工作流结论为 `success`，并且它已经产生正式剧情 JSON 提交，才算写入完成。

## 8. GitHub 同步闭环

每批必须完成以下闭环：

```text
日文逐句翻译
→ 本地结构校验
→ 上传 bundle／分片
→ 最后提交 READY
→ 等待 GitHub Actions 完成
→ 检查 Actions 日志中的字段数和改动数
→ 打开正式 Scenarios_full JSON 抽查
→ 更新 PROCESSED_STORY_TITLES.md
→ 提交进度 MD
```

不要只上传中间译稿后就宣称完成。必须确认正式文件位于：

```text
magireco-translate-data-master/Scenarios_full/...
```

建议每批记录：

- Actions run ID
- 正式剧情 JSON 提交 SHA
- 进度 MD 提交 SHA
- 完整剧情数量
- JSON 文件数量
- 复核字段数
- 实际替换字段数
- 核对后保留字段数

## 9. 进度 MD 更新规则

进度文件：

```text
manual_retranslation/PROCESSED_STORY_TITLES.md
```

每批成功后必须同时更新：

1. 文件顶部的 `已完成 / 507` 和剩余数。
2. `本轮新增`：列出剧情 ID、中文标题、日文标题。
3. 本轮字段统计、Actions run ID 和正式 JSON 提交 SHA。
4. `累计已处理` 对应分类中的 `[x]` 条目。
5. 新发现或已解决的问题文件。

计数原则：

- 只有完整候选剧情条目才加 1。
- 只翻译部分字段、部分 JSON 或只制作 worksheet，不增加完成数。
- 同一活动中多个候选 ID按 507 清单分别计数。
- 后续发现不完整时，要从完成数撤回，不能为了维持数字而保留错误标记。

## 10. 问题文件与异常处理

所有损坏包、不完整目录、来源漂移、命名冲突、控制码不一致或 Actions 校验失败，都必须写入 `PROCESSED_STORY_TITLES.md` 的“问题文件与异常记录”，至少包含：

```text
对象／剧情 ID
发现时间或批次
问题现象
是否影响正式 JSON
隔离方式
解决状态
解决提交或待办
```

当前接手时必须重点检查：

### 10.1 `spa-5188-8-manual-20260816`

历史分片目录不完整且没有有效 `READY`，应继续保持隔离。5188 的正式剧情 JSON 已由其他有效批次写入，因此不要把该残留目录重新启用，也不要重复增加完成数。确认无其他依赖后，可在单独维护提交中删除残留目录，并在异常记录中写明。

### 10.2 `event-513230-manual-20260816`

旧 Base64／gzip 包曾损坏；剧情已从日文重新构建并写入正式 JSON。后续窗口不得再次使用旧损坏包，也不得重复计数。

### 10.3 `costume-touka-alina-kushu-3-manual-20260816`

旧单文件包曾出现 gzip CRC 失败；现用带 SHA-256 的分片包替代。不得恢复旧单文件。

### 10.4 姓名冲突

`常盤ななか` 统一采用 `dictionary.ts` 的“常盘七夏”。发现其他姓名冲突时，先登记再修正，不得无记录地全局替换。

## 11. 接手前检查清单

接手窗口必须明确回答以下项目后再开始：

```text
[ ] 当前分支是否正确
[ ] 当前分支头 SHA
[ ] PROCESSED_STORY_TITLES.md 当前完成数
[ ] 下一批 ID 是否尚未完成
[ ] 下一批是否没有被其他窗口占用
[ ] 日文和中文 JSON 是否逐路径对齐
[ ] dictionary.ts 是否已读取
[ ] 称呼关系是否已核对
[ ] 已知问题文件是否保持隔离
```

## 12. 完成一批后的验收清单

```text
[ ] 所有相关 JSON 均已处理
[ ] 只修改十个白名单字段
[ ] 非文本字段深度等值
[ ] @ 数量一致
[ ] 控制码、变量和占位符一致
[ ] JSON 全部重新解析成功
[ ] GitHub Actions 结论为 success
[ ] 正式 Scenarios_full 文件已发生预期变化
[ ] PROCESSED_STORY_TITLES.md 已更新
[ ] 新异常已登记
[ ] 没有改动其他分支
```

任何一项未满足，都只能标记为“进行中”或“问题文件”，不能写成完成。

## 13. 建议的接手窗口首条任务文本

可把下面内容直接交给新的总控窗口：

```text
继续 HiiragiNemu/magi-reader 的 507 部 SOURCE_UNVERIFIED 剧情人工重译。
只允许写入 reader/manual-gpt-retranslation-20260816，禁止污染 main、EXEDRA-TEST 和其他分支。
先读取 manual_retranslation/HANDOFF_GUIDE.md、manual_retranslation/PROCESSED_STORY_TITLES.md、website/app/config/dictionary.ts，并核对当前分支头和完成数。
从锁定候选清单中选择尚未完成且未被其他窗口占用的 1—3 部；正文必须由你依据日文原始 JSON 逐句翻译，不使用 Google、DeepSeek 或其他机器翻译，也不以旧中文作为原文。
只修改十个白名单文本／姓名字段，保持 JSON 结构、@ 分行、控制码、变量和非文本字段不变。
完成本地校验后上传 exact bundle；大包采用分片、SHA256、最后提交 READY。等待 manual-retranslation-apply.yml 成功并确认正式 Scenarios_full JSON 已提交后，再更新 PROCESSED_STORY_TITLES.md 的标题、统计、提交 SHA 和问题文件记录。
每批结束必须报告：本轮标题、复核／替换／保留字段数、Actions run ID、正式 JSON 提交、进度 MD 提交、累计完成数和剩余数。
```

## 14. 最终完成标准

只有同时满足以下条件，才能宣布 507 部全部完成：

1. `PROCESSED_STORY_TITLES.md` 精确列出 507 个互不重复的完成条目。
2. 每个条目对应的全部 JSON 都有可追溯的人工翻译批次。
3. 全部正式 JSON 位于人工重译分支，且可被游戏／阅读器正常解析。
4. 全树结构与功能字段校验通过。
5. 所有问题文件均已解决或明确证明不影响正式剧情树。
6. 尚未合并到其他分支；是否合并由仓库所有者另行决定。
