# Exedra Wiki SP 台服资源交接合同 v1

该合同让 Exedra Wiki SP 发布物与 MagiReader 数据管线通过一个可独立验证的本地包交接。SP 负责生成并发布完整源包；Reader 的独立获取边界负责下载、整包认证、解包与重试；简体化、剧情 JSON/TXT 生成与站点构建属于后续确定性导入器。获取边界与导入核心只共享本文件规定的目录及 `exedra-tw-sp-handoff.v1.json`。

## 固定目录

```text
<handoff-root>/
├─ exedra-tw-sp-handoff.v1.json
└─ bundle/
   ├─ Resources/
   │  └─ Scenarios/
   │     └─ **/*.json
   └─ Manifests/
      └─ *.json
```

`bundle/Manifests` 必须在顶层包含：

- `getAdvMstList.json`
- `getCollectionConditionMstList.json`
- `getFieldStageMstList.json`

Manifest 子目录中的 JSON 会被拒绝。两个目录内的符号链接也会被拒绝，以免合同哈希到交接根目录之外的内容。

## 有效合同的硬条件

- 文件名固定为 `exedra-tw-sp-handoff.v1.json`。
- `schemaVersion` 必须是 `1`，`complete` 必须是 `true`。
- `provenance` 固定声明 `exedra-wiki-sp`、`zh-Hant-TW`、台服客户端官方权威来源、SP 原文未改动，以及繁转简由 Reader 执行。
- `diagnostics.missing`、`failure`、`parseFailure` 必须全部为 `0`。
- `sourceRevisions` 必须分别提供非空的 `sp`、`scenarios`、`manifests` 版本标识。
- 两个目录中的每个 JSON 都必须成功解析。
- 合同记录每个文件的包内 POSIX 路径、字节数和 SHA-256。
- 合同同时记录每个目录的文件数、总字节数、目录清单哈希和内容树哈希。
- 验证时重新扫描全部文件；新增、删除、改名、大小变化或单字节变化都会失败。

JSON Schema 位于 `docs/exedra_tw_sp_handoff_contract.schema.json`。Python 验证器还执行 Schema 无法表达的文件计数、总字节数、严格排序、大小写冲突、目录边界和实际哈希检查。

## 树哈希算法

算法标识固定为 `sha256-path-nul-size-nul-content-v1`。

1. 所有路径转换为相对于 `<handoff-root>` 的 `/` 分隔 POSIX 路径，并做 Unicode NFC 规范化。
2. 按规范化路径的 Unicode 码点顺序升序排列；大小写折叠后冲突的路径被拒绝。
3. 对每个文件依次向同一个 SHA-256 状态写入：
   - UTF-8 编码的包内路径；
   - 一个 NUL 字节 `00`；
   - 文件字节数的无前导零 ASCII 十进制表示；
   - 一个 NUL 字节 `00`；
   - 文件原始字节。
4. 文件内容以 1 MiB 分块读取。实现一次只打开一个文件，不把整棵目录或所有文件正文放入内存。

目录清单哈希算法标识为 `sha256-canonical-json-files-v1`：将已经按路径排序的 `files` 数组用 UTF-8 JSON 编码，`ensure_ascii=false`、对象键排序、无多余空白，再计算 SHA-256。

## 生成与验证

```powershell
python tools/tw_sp_handoff_contract.py build `
  --handoff-root D:\path\to\handoff `
  --sp-revision <SP_RELEASE_OR_COMMIT> `
  --scenario-revision <SCENARIO_REVISION> `
  --manifest-revision <MANIFEST_REVISION>

python tools/tw_sp_handoff_contract.py verify `
  --handoff-root D:\path\to\handoff
```

生成器先完成全部扫描、JSON 解析和哈希，再以同目录临时文件加原子替换写入合同。失败不会写出一份标记为 `complete=true` 的新合同。合同不含生成时间，因此相同输入与版本会产生逐字节相同的结果。

固定来源对象为：

```json
{
  "provider": "exedra-wiki-sp",
  "locale": "zh-Hant-TW",
  "authority": "official-tw-client",
  "originalTextUnmodified": true,
  "textTransformation": "reader-tw2sp"
}
```

当前安全上限为单个 JSON 256 MiB、单目录 100,000 个 JSON、合同 64 MiB。JSON 解析一次只处理一个文件；树哈希始终分块。未来提高上限必须同时增加资源测试，不能用超时替代内存边界。

## Reader 获取边界

Reader 的导入核心只消费已经验证的本地目录。Release 下载、整包认证和安全解压由独立边界工具完成：

```powershell
python tools/fetch_tw_sp_source_bundle.py `
  --output-root D:\path\to\verified-handoff

python tools/materialize_tw_official_cn.py `
  --source-bundle-root D:\path\to\verified-handoff `
  --source-provider exedra-wiki-sp `
  --expected-source-count 2780
```

默认来源固定为不可变版本路径：

- URL：`https://github.com/HiiragiNemu/MagiaExedraTWData/releases/download/tw-wiki-source-v1-20260806/exedra-tw-wiki-source-v1.zip`
- 整包 SHA-256：`503c4c9a518d0a992abe800fccde4a97b35b2e4ddaeb2359e63eaa8d572cd1ac`

边界工具在打开 ZIP 前先比较整包 SHA-256；随后以根合同的 `files` 清单建立精确成员 allowlist，拒绝路径穿越、重复/大小写冲突、符号链接、特殊文件、未知压缩算法、超限成员和额外文件。每个文件流式解压时再次比较声明字节数和 SHA-256，完整 `verify` 通过后才原子发布输出目录。`--archive` 可对已经下载的 ZIP 做同一套离线验证。工具不执行 Git、数据导入、站点构建或部署。

GitHub workflow 的手动入口可同时指定 `source_url` 与 `source_sha256`；只覆盖 URL 而保留旧摘要会因整包 SHA-256 不匹配而失败。固定生产版本的更新应把 URL 与摘要作为同一次代码审查变更。

## 后续导入器边界

MagiReader 在读取正文前必须先运行 `verify` 或调用同等验证逻辑。验证成功后才可把 `bundle/Resources/Scenarios` 和 `bundle/Manifests` 交给台服导入、繁转简及 JSON/TXT 生成器。导入器应把三个 `sourceRevisions`、两个 `treeSha256` 和两个 `catalogSha256` 写入最终 provenance，以便以后确定每部剧情来自哪次 SP 快照。
