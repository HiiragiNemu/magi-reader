# Scene0 修复包

包含：

- `rebuild_scene0_txt.py`：只处理 `magireco-source-master/Scenarios_full` 与 `magireco-translate-data-master/Scenarios_full` 下的 Scene0主线 / Scene0支线目录。
- `website/app/reader/[id]/page.tsx`：前端 reader 的完整替换版，支持 `@S0\t{json}` 扩展格式，同时兼容旧纯文本格式。
- `generate_story_index.py`：完整替换版，修复 `#U4e3b#U7ebf` / `#U652f#U7ebf` 路径识别和 Section 标题提取。
- `build_search_index_v6.py`：完整替换版，搜索索引支持 `@S0\t{json}` 扩展行。

## 推荐执行顺序

1. 先把这几个文件复制到仓库根目录对应位置。
2. 先 dry-run：

```bash
python rebuild_scene0_txt.py --root . --format plain
```

3. 确认输出目标只在 Scene0 目录后，写入：

```bash
python rebuild_scene0_txt.py --root . --format plain --write
```

4. 重建网站数据索引：

```bash
python generate_story_index.py
python build_search_index_v6.py
cd website
npm run build
```

## 可选：保留 Scene0 左/中/右与 Fnarration 元信息

使用扩展格式：

```bash
python rebuild_scene0_txt.py --root . --format extended --write
python generate_story_index.py
python build_search_index_v6.py
cd website
npm run build
```

`plain` 格式最稳，只解决文本丢失；`extended` 格式会额外保留：

- `textAvLeft / textAvCenter / textAvRight` 的 position
- `Fnarration / progressFnarration` 的 kind/sourceCommand

前端替换版 `page.tsx` 两种格式都能读。
