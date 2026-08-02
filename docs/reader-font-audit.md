# 阅读器游戏字体审计与按需加载检查点

日期：2026-08-02
范围：仅 `website` 的阅读显示、设置项与字体资产；未改动语音数据、播放器或剧情索引生成器。

## 结论

- 中文正文 `TTDaYuanGB3.ttf` 与中文标题 `TTZhiHeiGB3-W4.ttf` 含 GB18030
  级别的大型 CJK 字形表，适合魔法纪录中文阅读内容。两者完整 WOFF2 合计
  **11.17 MiB**，所以不进入首屏，必须由用户在阅读设置中手动下载。
- 日文正文 `mbm_20160902.ttf` 与日文标题 `MTF4a5kp.ttf` 的完整 WOFF2
  合计 **2.25 MiB**。它们覆盖日文常用汉字与假名，但缺少大量简体中文字，
  因而只应用于日文栏，并始终保留系统 CJK fallback。
- WOFF2、FontFace API、Cache Storage 均为现代浏览器的成熟能力。当前实现以
  FontFace API 为启用门槛；不支持或加载失败时不会挂上自定义 font-family，
  阅读内容立即保持系统字体。因此可覆盖运行本 Next.js 应用的大部分现代桌面和
  移动设备，而不是假定单一字体在所有设备上都能工作。
- 资产是**完整格式转换**，没有做破坏性子集；转换后逐一回读并确认 glyph 数、
  Unicode cmap 与 OS/2 `fsType` 和源 TTF 一致。

## 精确资产审计

| 角色 | 源文件 | 源 TTF | 完整 WOFF2 | glyph / Unicode cmap | OS/2 `fsType` |
|---|---|---:|---:|---:|---:|
| 中文正文 | `TTDaYuanGB3.ttf` | 17,507,340 B | 8,071,072 B | 28,530 / 28,527 | `0x0008` Editable Embedding |
| 中文标题 | `TTZhiHeiGB3-W4.ttf` | 8,367,096 B | 3,642,144 B | 28,611 / 28,611 | `0x0008` Editable Embedding |
| 日文正文 | `mbm_20160902.ttf` | 2,450,636 B | 1,252,504 B | 7,604 / 7,493 | `0x0002` Restricted License Embedding |
| 日文标题 | `MTF4a5kp.ttf` | 2,618,612 B | 1,109,948 B | 9,846 / 9,470 | `0x0004` Preview & Print Embedding |

源 TTF SHA-256：

- `TTDaYuanGB3.ttf`: `01bbb65b3b21f8d445fe15412fc3b5864425033f534464be26de0aa7ed8150c0`
- `TTZhiHeiGB3-W4.ttf`: `01a4be2e5fca489c30219b3bec5edac0b7c98128c5fa629c34a0208ed5b0ba34`
- `mbm_20160902.ttf`: `37f266883643ca3e3168049a130396a4993b981747f73c4f5068afec2412f5c5`
- `MTF4a5kp.ttf`: `36dbe7b91d30d9d95713ba4b46bfa9b70f5d16bf759e45d3a043eae97da948a1`

完整 WOFF2 SHA-256 及构建记录见
`website/public/fonts/reader-font-manifest.json`。源文件没有被写入或改名。

`fsType` 是字体内的嵌入许可标志，不等同于完整授权文本。尤其日文正文的
`0x0002` 与日文标题的 `0x0004` 需要在对外分发前结合原始许可确认；“手动下载”
只改变性能和用户选择，不改变这些标志。中文字体的 name 表也没有随附完整许可正文。

## 字形覆盖抽样

- 两款中文字体：Basic Latin 95/95、平假名 87/96、片假名 89/96、
  CJK Unified Ideographs 20,902/20,992；抽样简体、繁体和日文常用汉字均完整。
- 两款日文字体：Basic Latin 95/95、平假名 87/96、片假名 90/96、
  CJK Unified Ideographs 6,682/20,992；简体中文抽样仅覆盖 14/30。
- 已知抽样缺字包括部分字体中的 `ゔ`、`・`、`—`、`·`。CSS 字体栈末尾
  保留系统 CJK 字体，让浏览器按字符回退。
- `mbm_20160902.ttf` 的 legacy 粗细元数据不一致（OS/2 bold bit 与
  `head.macStyle` 不一致，`usWeightClass=505`）。运行时为它创建独立 family、
  显式匹配 weight 500，并关闭合成字重，避免与其他字体错误合并。

## 加载与性能行为

1. 默认偏好是中文、日文字体包均关闭；页面初始化只检查 Cache Storage，不请求
   任一 `.woff2`。
2. 用户点击“下载并启用”后逐文件下载、校验精确字节数和 SHA-256（浏览器支持
   Web Crypto 时）、交给 FontFace 解码，成功后才设置根元素激活标志。
3. 两个 face 顺序处理，避免四个大文件并行下载/解码造成额外峰值内存。
4. Cache Storage 可用时保存完整响应；恢复系统字体只卸载 FontFace，不删除缓存，
   用户可另行删除缓存。缓存或配额不可用时，当前会话仍可启用。
5. 任何网络、完整性或字体解码错误都会删除已挂载 face、清除激活标志并显示错误，
   阅读文本继续使用原系统字体栈。

## 复现转换

```powershell
python website/scripts/build-reader-fonts.py `
  --source-dir D:\magia\MyProducts\MAGIA-RECORD-CN-repo\client-snapshot\fonts
```

构建脚本固定四个源 SHA-256，采用 fontTools 的完整 WOFF2 flavor 转换，并在替换
输出前回读校验 glyph、Unicode cmap 与 `fsType`。
