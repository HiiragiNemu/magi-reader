#!/usr/bin/env python3
"""Idempotently teach the browser worker/build verifier to use physical chunks."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "website/public/search-worker.js"
VERIFIER = ROOT / "website/scripts/verify-cloudflare-output.mjs"
WORKER_MARKER = "// SEARCH_CHUNK_DELIVERY_RUNTIME_V1"
VERIFIER_MARKER = "// SEARCH_CHUNK_DELIVERY_BUILD_VERIFY_V1"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label} 锚点数量异常：{count}")
    return text.replace(old, new, 1)


def patch_worker() -> None:
    text = WORKER.read_text(encoding="utf-8")
    if WORKER_MARKER in text:
        print("SEARCH_CHUNK_WORKER_ALREADY_PATCHED")
        return

    pattern = re.compile(
        r"const sanitizeSource = \(source\) => \{\n"
        r".*?"
        r"  const sanitized = \{\n"
        r"    url: source\.url,\n"
        r"    version,\n"
        r"    sha256,\n"
        r"    bytes,\n"
        r"    maxBytes: bytes,\n"
        r"    entries: expectedEntries,\n"
        r"  \};",
        re.S,
    )
    replacement = """const sanitizeSource = (source) => {
  if (!source || typeof source !== 'object') return null;

  const sourceUrl = typeof source.url === 'string' ? source.url : '';
  const chunkBaseUrl = typeof source.chunk_base_url === 'string'
    ? source.chunk_base_url
    : '';
  if (!sourceUrl && !chunkBaseUrl) return null;

  const sha256 = String(source.sha256 ?? '').toLowerCase();
  const bytes = Number(source.bytes);
  const expectedEntries = Number(source.entries);
  const version = source.version === 2 ? 2 : 1;
  if (
    (source.version !== undefined && source.version !== 1 && source.version !== 2) ||
    !/^[a-f0-9]{64}$/.test(sha256) ||
    !Number.isSafeInteger(bytes) ||
    bytes <= 0 ||
    bytes > MAX_INDEX_BYTES ||
    !Number.isSafeInteger(expectedEntries) ||
    expectedEntries <= 0 ||
    expectedEntries > MAX_INDEX_ENTRIES
  ) {
    return null;
  }

  if (sourceUrl) {
    const addressedHash = sourceUrl.match(
      /\\/search\\/([a-f0-9]{64})\\.json(?:[?#].*)?$/i,
    )?.[1]?.toLowerCase();
    if (addressedHash && addressedHash !== sha256) return null;
  }
  if (chunkBaseUrl) {
    if (version !== 2) return null;
    const match = chunkBaseUrl.match(
      /^\\/search-chunks\\/(?:magireco|exedra)\\/([a-f0-9]{64})\\/$/i,
    );
    if (!match || match[1].toLowerCase() !== sha256) return null;
  }

  const sanitized = {
    ...(sourceUrl ? { url: sourceUrl } : {}),
    ...(chunkBaseUrl ? { chunk_base_url: chunkBaseUrl } : {}),
    version,
    sha256,
    bytes,
    maxBytes: bytes,
    entries: expectedEntries,
  };"""
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError("无法补丁 search-worker sanitizeSource")

    parse_anchor = "const parseIndexResponse = async (response, source, signal) =>\n"
    multipart = """const parseChunkedIndexParts = async (source, signal) => {
  const decoder = new TextDecoder('utf-8', { fatal: true });
  const parser = createStreamingArrayParser(source.entries);
  const overallHasher = new StreamingSha256();
  let total = 0;

  for (let index = 0; index < source.chunks.length; index += 1) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const expected = source.chunks[index];
    const partUrl = `${source.chunk_base_url}${String(index).padStart(4, '0')}.part`;
    const response = await fetch(partUrl, {
      cache: 'no-cache',
      credentials: 'same-origin',
      signal,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await readBoundedResponse(
      response,
      { maxBytes: expected.bytes },
      signal,
    );
    if (payload.byteLength !== expected.bytes) {
      throw new Error(`索引第 ${index + 1} 块大小与清单不一致`);
    }
    const digest = hexDigest(await crypto.subtle.digest('SHA-256', payload));
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    if (digest !== expected.sha256) {
      throw new Error(`索引第 ${index + 1} 块校验值与清单不一致`);
    }
    overallHasher.update(payload);
    parser.push(decoder.decode(payload, { stream: true }));
    total += payload.byteLength;
  }

  if (total !== source.bytes) throw new Error('索引大小与清单不一致');
  if (overallHasher.digestHex() !== source.sha256) {
    throw new Error('索引校验值与清单不一致');
  }
  parser.push(decoder.decode());
  return parser.finish();
};

"""
    text = replace_once(text, parse_anchor, multipart + parse_anchor, "多文件分块解析")

    old_load = """        self.postMessage({ type: 'status', status: 'loading' });
        const response = await fetch(source.url, {
          // Revalidate the manifest-selected object so a locally cached 404
          // from pre-publication testing cannot mask a later successful upload.
          cache: source.sha256 ? 'no-cache' : 'force-cache',
          credentials: 'omit',
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        entries = await parseIndexResponse(
          response,
          source,
          controller.signal,
        );"""
    new_load = """        self.postMessage({ type: 'status', status: 'loading' });
        if (source.chunk_base_url) {
          entries = await parseChunkedIndexParts(source, controller.signal);
        } else {
          const response = await fetch(source.url, {
            // Revalidate the manifest-selected object so a locally cached 404
            // from pre-publication testing cannot mask a later successful upload.
            cache: source.sha256 ? 'no-cache' : 'force-cache',
            credentials: 'omit',
            signal: controller.signal,
          });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          entries = await parseIndexResponse(
            response,
            source,
            controller.signal,
          );
        }"""
    text = replace_once(text, old_load, new_load, "搜索来源加载")
    text = text.rstrip() + "\n\n" + WORKER_MARKER + "\n"
    WORKER.write_text(text, encoding="utf-8")
    print("SEARCH_CHUNK_WORKER_PATCHED")


def patch_verifier() -> None:
    text = VERIFIER.read_text(encoding="utf-8")
    if VERIFIER_MARKER in text:
        print("SEARCH_CHUNK_BUILD_VERIFIER_ALREADY_PATCHED")
        return

    helper_anchor = "const errors = [];\n"
    helper = """const verifyBuiltSearchChunks = (manifest, scope, errors) => {
  const directory = path.join(assetsRoot, 'search-chunks', scope, manifest.sha256);
  // Generic output verification remains backward-compatible with manifest-only
  // fixtures and non-chunk deployments. The EXEDRA-TEST release pipeline calls
  // search_chunk_delivery.py verify-tree immediately after the build, which is
  // the fail-closed authority that requires every physical chunk to exist.
  if (!existsSync(directory)) return;
  const overall = createHash('sha256');
  let total = 0;
  for (let index = 0; index < manifest.chunks.length; index += 1) {
    const expected = manifest.chunks[index];
    const part = path.join(directory, `${String(index).padStart(4, '0')}.part`);
    if (!existsSync(part)) {
      errors.push(`${scope} 搜索分块缺少第 ${index + 1} 块`);
      return;
    }
    const data = readFileSync(part);
    const digest = createHash('sha256').update(data).digest('hex');
    if (data.byteLength !== expected.bytes || digest !== expected.sha256) {
      errors.push(`${scope} 搜索分块第 ${index + 1} 块大小或 SHA-256 不一致`);
      return;
    }
    overall.update(data);
    total += data.byteLength;
  }
  if (total !== manifest.bytes || overall.digest('hex') !== manifest.sha256) {
    errors.push(`${scope} 搜索分块重组后的全局大小或 SHA-256 不一致`);
  }
};

"""
    text = replace_once(text, helper_anchor, helper + helper_anchor, "构建分块校验 helper")

    old_check = """    } else if (
      storyIndexSha256 &&
      manifest.story_index_sha256 !== storyIndexSha256
    ) {
      errors.push(`${searchManifest.scope} 搜索清单与当前 story_index.json 不匹配`);
    }"""
    new_check = """    } else if (
      storyIndexSha256 &&
      manifest.story_index_sha256 !== storyIndexSha256
    ) {
      errors.push(`${searchManifest.scope} 搜索清单与当前 story_index.json 不匹配`);
    } else if (manifest.version === 2) {
      verifyBuiltSearchChunks(manifest, searchManifest.scope, errors);
    }"""
    text = replace_once(text, old_check, new_check, "构建分块校验调用")
    text = text.rstrip() + "\n\n" + VERIFIER_MARKER + "\n"
    VERIFIER.write_text(text, encoding="utf-8")
    print("SEARCH_CHUNK_BUILD_VERIFIER_PATCHED")


def main() -> int:
    patch_worker()
    patch_verifier()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
