# Exedra 专用字体包

阅读器默认始终使用系统字体。只有用户在 Exedra 剧情页的设置面板中明确操作后，
下列字体才会加载；激活状态可随时撤销，缓存也可单独删除。CSS 同时要求
`.exedra-reader` 与正确的 `:lang(zh-Hans)` / `:lang(ja)`，因此不会改变 Magia
Record 页面或混合对照栏中的另一种语言。

## 简体中文主字体

- 字体：猫啃网糖圆体 `v0.12beta`，是 TW 客户端 `jf open 粉圆` 的直系简中衍生。
- 覆盖：实测 GB2312 `6763/6763`，GBK 汉字 `6765/20902`。
- 授权：SIL OFL 1.1。
- 固定上游 ZIP：`MaoKenTangYuan-beta0.12-20210702.zip`
- ZIP：`1,843,200` bytes，SHA-256
  `64eaeF7fffba29748749a87a7b6287c06a9efc00a9630e26837db392a044f55f`
- TTF：`2,881,764` bytes，SHA-256
  `ea4e2e85cc49ed7a0ea9f2347a9c5e6e9c3ea1a1c9130280796cceb77e0dc800`

浏览器只请求同源 `/api/fonts/exedra-tangyuan/v0.12beta`。该服务端路由从作者的
固定 GitHub Release 读取 ZIP，并在解压前后分别校验大小和 SHA-256；校验失败时
返回 502，不把上游字节交给浏览器。仓库中不存放字体二进制。

## GBK 回退

糖圆体之后的字体栈为：

1. `Resource Han Rounded CN v0.990`（可选本机导入）；
2. 操作系统已安装的 `Resource Han Rounded CN`；
3. 操作系统已安装的 `Noto Sans SC`；
4. 系统无衬线中文字体。

v0.990 的目标文件为 `ResourceHanRoundedCN-Regular.ttf`，`14,663,464` bytes，
SHA-256
`1c5c623f008eabef10c45135a48b01b46311f9369c28857355872cfe05f48dc0`，
实测覆盖 GBK 汉字 `20902/20902`。下载入口指向作者官方 v0.990 Release；用户从
压缩包选择 TTF 后，浏览器核对内部名、大小与哈希并存入本机 Cache API，文件不
上传。Noto Sans SC 是下一层同样覆盖 GBK 的系统 fallback。

## 日文原生字体

JP 客户端字体属于 Fontworks 商业字体，仓库、Release、服务器和网页都不提供其
二进制。用户需拥有合法副本，并一次选择两份文件：

| 作用 | 内部字体 | bytes | SHA-256 |
|---|---|---:|---|
| 正文 | `FOT-TsukuOldGothic Std B` v2.100 | 5,710,884 | `3e13805dacb081d44d06c16213319b45f044b777989afde7985fa2afaaf9684a` |
| 标题 | `FOT-NewCinemaA Std D` v1.300 | 4,697,304 | `e40f4d90a8010404511b6f113e95c54d5a56a39619076bcd8da4d42fafb3aee5` |

浏览器解析 SFNT `name` 表，再核对大小和完整 SHA-256。只有两份均吻合才会加载；
缓存键是站点内部虚拟 URL，不会产生网络上传。删除缓存或“全部恢复系统字体”会
撤销激活。

## 安全与可复现性

- 新访问者和未选择字体的用户产生 **0 个字体网络请求**。
- 所有远程字节都绑定固定版本、大小和 SHA-256。
- 本地商业字体只在浏览器内读取，限制单文件不超过 16 MiB。
- 任何校验或 FontFace 加载失败都会清理激活状态并回退系统字体。
- 大型字体文件不进入 Git 历史。
