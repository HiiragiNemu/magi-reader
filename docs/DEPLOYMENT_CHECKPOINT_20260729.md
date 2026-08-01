# MagiReader test deployment checkpoint — 2026-07-29

## Scope

- Target branch: `feature/exedra-voice-playback-human-localization`
- Target Worker: `magireader-exedra-cn-test`
- Protected branch not changed: `main`
- Full-text search object upload remains manual.
- No `magireco.moe` request, probe, workflow, or fallback is part of this work.

## Last deployment diagnosis

The deployed story, proofreading, Exedra localization, JSON, and TXT smoke
checks passed. The remaining failure was isolated to:

```text
/api/audio/magireco-voice/vo_char_3031_00_01
```

The deployed proxy returned HTTP 502, while the fixed R2 object returned a
valid 256-byte HTTP 206 range:

```text
bucket: live2dv4
key: voice/vo_char_3031_00_01_hca.hca
managed domain: pub-70a248f1a6fe4ca597e7a10f8b95dfd8.r2.dev
object size: 165744 bytes
range header: bytes 0-255/165744
```

## Remediation

1. The deployment discovers the bucket by exact managed-domain equality and
   binds it to the Worker as `MAGIRECO_VOICE_R2` only when the deployment
   credential can validate and use R2.
2. A Workers-only deployment credential does not receive an R2 binding,
   because Cloudflare rejects such configurations before publishing. In that
   case the reader uses the audited fixed-origin browser fallback.
3. The API route performs bounded, streamed R2 reads and preserves HTTP range
   metadata.
4. The fixed public R2 origin remains a bounded server fallback.
5. The browser player falls back to the same fixed origin only for transient
   proxy errors. Definitive 4xx responses are not retried. Deployment smoke
   testing verifies the exact CORS origin and a 256-byte HCA range when the
   Worker binding is unavailable.
6. The R2 CORS policy preserves all prior Viewer origins and additionally
   allows only the Exedra test Worker origin used by this site.

## Proofreading usability remediation

1. The ordinary reviewer login now defaults to one fixed team review
   passphrase. GitHub PAT login remains available only in the maintainer
   advanced section.
2. The fixed passphrase is stored only as the GitHub Actions secret
   `SUBMISSIONS_ADMIN_TOKEN` and the deployed Worker secret. The separate
   server-side GitHub credential creates proofreading PRs.
3. All story and review TXT downloads now use the literal UTF-8 BOM bytes
   `EF BB BF`, `text/plain;charset=utf-8`, and CRLF line endings.
4. Blob download URLs remain valid for a bounded 30 seconds so mobile download
   hand-off cannot race a 100 ms revocation. JSON downloads remain BOM-free.
5. Downloaded proofreading TXT is normalized back to canonical LF on upload,
   preserving the playable JSON-first then TXT materialization workflow.
6. The home-page machine-review status panel can be collapsed. A compact row
   showing the remaining count always remains available, and the preference is
   stored locally with an SSR-safe fallback.

The CORS before/after records and runnable rollback are stored outside the
repository at:

```text
D:\magia\MyProducts\magi-reader-exedra-test-recovery-links\cloudflare-live2dv4-cors-20260729
```

## Local verification

```text
feature policy: 98/98
Python: 167 passed, 2 explicit real-corpus skips
Node: 143/143
ESLint: passed
TypeScript: passed
production dependency audit: 0 high-severity findings
OpenNext Worker build: passed
Cloudflare output verification: passed
external Chrome direct R2 range: HTTP 206, 256 valid HCA bytes
TXT byte contract: EF BB BF + UTF-8 + CRLF, round-trip passed
machine-review collapse: persistence, keyboard, mobile and SSR tests passed
```

## Manual full-text search object

```text
local file:
D:\magia\MyProducts\magi-reader-manual-r2-upload\search\21cfaee1042d0e21eb5a03ca666f6f84f2b79cb7c16632465f7f40c4ded518d2.json

R2 bucket:
magi-assets

object key:
search/21cfaee1042d0e21eb5a03ca666f6f84f2b79cb7c16632465f7f40c4ded518d2.json

size:
79334357 bytes

SHA-256:
21cfaee1042d0e21eb5a03ca666f6f84f2b79cb7c16632465f7f40c4ded518d2
```

The isolated test-site workflow validates and reports this object key but does
not upload it.

## Deferred destructive action

Repository branch cleanup remains deferred until the user has manually
validated the deployed site. Incident and attribution records are retained.
