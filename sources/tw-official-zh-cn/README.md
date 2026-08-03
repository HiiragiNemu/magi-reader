# TW official Simplified-Chinese compact source

The Base64 parts reconstruct two XZ-compressed, deterministic JSON payloads derived from the user-supplied archives. They contain only the official visible story text and the exact master-data naming fields required for materialization.

- Source `Scenarios_zh-CN.7z` SHA-256: `64c86700651b845b484f6100fed61a8c2b860028cda8130456a57979ee907452`
- Compact scenario XZ SHA-256: `f3b6da2b207eb7adfc58a53b171f9b65ea1a8e03bd73fb3b2886867e0a07ab58`
- Source `Manifests_zh-CN.7z` SHA-256: `9125ae75d02ac69572fafc08fe2c1479ff872f6394d03b77f5bd046471ebda74`
- Compact naming XZ SHA-256: `8487f3555c21b05bbb55660aa8eadedadac43efc512926f14753056ceac8a103`

The materializer validates the compact payload hashes, per-file structural hashes, Japanese source structure, event counts, generated JSON/TXT, and provenance before replacing any translation group.
