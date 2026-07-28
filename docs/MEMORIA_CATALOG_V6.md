# Memoria Catalog v6

记忆结晶图鉴使用经过验证的500页快照中的1,042个普通文章入口作为目录成员，详情数据来自对应普通文章的展开表格。抓取采用分批、多轮和择优合并，网络失败不会删除目录成员。

运行时文件：

- `data/structured/memoria/manifest.json`
- `data/structured/memoria/memoria-index.json`
- `data/structured/memoria/shards/*.json`
- `data/structured/memoria/failures.json`

路由：

- `#/memoria`
- `#/memoria/<key>`

图鉴入口按唯一普通文章展示，不把同编号客户端导入副本重复显示为第二张卡。来源差异可在详情和清单中保留。
