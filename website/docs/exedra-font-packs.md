# Magia Exedra 专用字体

Exedra 页面使用独立字体选择，不再复用 Magia Record 的腾祥、TT-Gothic 或
Motoya 字体。三份网页字体均为完整字形转换的 WOFF2，由站点直接提供；点击启用
后浏览器会核对固定大小和 SHA-256，再写入专用缓存。无需下载到文件系统后手工导入。

## 简体中文：猫啃网糖圆体

- 网页文件：`exedra-zh-tangyuan.0901bb62ccd1.full.woff2`
- bytes：`1,386,160`
- SHA-256：`0901bb62ccd113f214201a8760146875bec0769664765a66172a5fe79e19b411`
- 源 TTF：`MaoKenTangYuan-beta0.12-20210702.ttf`
- 源 TTF SHA-256：`ea4e2e85cc49ed7a0ea9f2347a9c5e6e9c3ea1a1c9130280796cceb77e0dc800`
- 授权：SIL OFL 1.1

该字体用于 Exedra 简体中文正文。缺字继续由浏览器的系统 CJK 字体栈补齐。

## 日文：日服客户端原生字体

| 作用 | 原生字体 | WOFF2 | bytes | SHA-256 |
|---|---|---|---:|---|
| UI、标题、角色名 | `FOT-TsukuOldGothic Std B` | `exedra-jp-ui-tsuku.431afe7080dc.full.woff2` | 2,750,668 | `431afe7080dcb5c6337bf2ab6ec1d04449123aa4841a1f85a9bdfd3c5bd8b7b3` |
| 剧情、语音、旁白正文 | `FOT-NewCinemaA Std D` | `exedra-jp-story-newcinema.687768deeccd.full.woff2` | 3,370,224 | `687768deeccd50f66a4aefc7f30bc7d8095be462628507715f26be7f8eea7762` |

原始客户端证据：

| Unity 对象 | 原始文件 bytes | 原始文件 SHA-256 |
|---|---:|---|
| `FOT-TSUKUOLDGOTHICSTD-B` / PathID `3` | 5,710,884 | `3e13805dacb081d44d06c16213319b45f044b777989afde7985fa2afaaf9684a` |
| `FOT-NewCinemaAStd-D` / PathID `3` | 4,697,304 | `e40f4d90a8010404511b6f113e95c54d5a56a39619076bcd8da4d42fafb3aee5` |

转换过程未裁字；`reader-font-manifest.json` 记录源文件、输出文件、字形数量、
Unicode cmap 数量、大小和两侧 SHA-256。WOFF2 是压缩容器；更换 fontTools 或
Brotli 版本可能产生不同的压缩字节，因此发布资产以清单内固定 SHA-256 为准，
而重建验收同时比较源哈希、解压后的完整表集合、字形顺序、Unicode cmap 与
`OS/2.fsType`，不把压缩器版本差异误判为裁字。

## 页面分流

Exedra 直连 TXT/JSON 链接会按 `exedra-trusted-runtime` 识别为 Exedra，即使该条目
尚未出现在 `story_index.json`。设置面板因此只显示上述 Exedra 字体，不会错误显示
Magia Record 通用字体包。

CSS 同时要求 `.exedra-reader` 与正确的 `:lang(zh-Hans)` / `:lang(ja)`，因此不会
改变 Magia Record 页面或双语对照栏中的另一种语言。

## 可复现性

- 新访问者默认不下载字体；明确启用后才请求对应静态文件。
- 每份响应均校验固定长度与 SHA-256。
- Cache Storage 可用时，后续启用直接读取本地缓存。
- 校验或 FontFace 加载失败时清除激活状态并回退系统字体。
- “全部恢复系统字体”只撤销字体激活，不修改剧情数据。
