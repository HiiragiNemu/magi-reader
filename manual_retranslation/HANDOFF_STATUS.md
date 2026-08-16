# 人工重译接手状态快照

- 唯一工作分支：`reader/manual-gpt-retranslation-20260816`
- 锁定范围：507 部 `SOURCE_UNVERIFIED` 候选剧情
- 本快照建立时，`PROCESSED_STORY_TITLES.md` 记录：**70 / 507 已完成，437 部剩余**
- 准确实时数字始终以 `PROCESSED_STORY_TITLES.md` 为准；本文件只用于快速接手，不代替完成清单

## 最近一批已正式完成

- `513230` — 始于反复的梦
- `mirror_story_420131_0_bf5f5fd145` — 记忆博物馆·序章
- `730121` — 纯美雨 决胜服衣装剧情

最近一批正式剧情 JSON 提交：

```text
77a4afeff29e02644aa7db8bef07db9a8710a539
```

最近一批进度与问题记录提交：

```text
b66761d75c3bd36e752d644a081c552e87431b3f
```

接手者必须在开始前重新读取远端分支头；上述 SHA 只是建立接手资料时的已知基线。

## 接手资料

- 完整流程：`manual_retranslation/HANDOFF_GUIDE.md`
- 已完成标题与进度：`manual_retranslation/PROCESSED_STORY_TITLES.md`
- 推荐下一批：`manual_retranslation/NEXT_WORK_QUEUE.md`
- 日中对照工作表导出工具：`manual_retranslation/export_story_worksheet.py`
- 正式应用工作流：`.github/workflows/manual-retranslation-apply.yml`
- exact bundle 应用器：`manual_retranslation/apply_exact_batches.py`
- 姓名词典：`website/app/config/dictionary.ts`

## 当前已知异常

1. `spa-5188-8-manual-20260816`：残留分片目录不完整且没有有效 `READY`；保持隔离，不得重新启用。5188 正式剧情已由其他有效批次写入。
2. `event-513230-manual-20260816`：旧 Base64／gzip 包损坏；已经从日文重建并解决，不得复用旧包或重复计数。
3. `costume-touka-alina-kushu-3-manual-20260816`：旧单文件出现 gzip CRC 失败；已由带 SHA-256 的分片包替代。
4. `常盤ななか` 姓名冲突：统一采用 `dictionary.ts` 的“常盘七夏”。

新问题必须同时登记到 `PROCESSED_STORY_TITLES.md` 的问题文件区域。

## 下一窗口的最低交付要求

每一波至少交付以下证据：

```text
本轮完整剧情标题及 ID
JSON 文件数量
复核字段数
实际替换字段数
核对后保留字段数
GitHub Actions run ID
正式剧情 JSON 提交 SHA
进度 MD 提交 SHA
累计完成数及剩余数
新发现／已解决问题文件
```

只有 worksheet、翻译草稿或未通过 Actions 的 bundle，均不能计入完成数。
