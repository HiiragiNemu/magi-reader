# TW official Simplified-Chinese source authentication

The complete user-supplied archives are intentionally ingested from the private source release `tw-source-zh-cn-2026-08-04`; they are not duplicated into normal Git history.

Authenticated source archives:

- `Scenarios_zh-CN.7z` SHA-256: `64c86700651b845b484f6100fed61a8c2b860028cda8130456a57979ee907452`
- `Manifests_zh-CN.7z` SHA-256: `9125ae75d02ac69572fafc08fe2c1479ff872f6394d03b77f5bd046471ebda74`

`Manifests-names-compact.xz.b64.part001` is a deterministic audit snapshot containing only the exact naming fields from `getFieldStageMstList`, `getAdvMstList`, and their `getCollectionConditionMstList` linkage. Production materialization still downloads and verifies both complete source archives before replacing any content.

The importer validates source hashes, Japanese/Taiwan row and action alignment, event counts, generated JSON/TXT, import reports, and `official_tw_human` provenance before replacing a complete logical group.
