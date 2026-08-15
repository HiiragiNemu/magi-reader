import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getSearchIndexSources,
  isSearchIndexManifest,
  SEARCH_INDEX_SCOPE_CONFIG,
  type SearchIndexScope,
} from '../lib/search-index-scope.ts';

const storyIndexSha256 = 'b'.repeat(64);

const splitPayload = (bytes: number, chunkBytes: number) => {
  const chunks = [];
  let remaining = bytes;
  let index = 0;
  while (remaining > 0) {
    const size = Math.min(remaining, chunkBytes);
    chunks.push({ bytes: size, sha256: `${index % 10}`.repeat(64) });
    remaining -= size;
    index += 1;
  }
  return chunks;
};

const manifestFor = (scope: SearchIndexScope, sha256 = 'a'.repeat(64)) => ({
  version: 2 as const,
  sha256,
  bytes: 2 * 1024 * 1024 + 17,
  entries: 7,
  object_key: `${SEARCH_INDEX_SCOPE_CONFIG[scope].objectKeyPrefix}/${sha256}.json`,
  story_index_sha256: storyIndexSha256,
  chunk_bytes: 1024 * 1024,
  chunks: splitPayload(2 * 1024 * 1024 + 17, 1024 * 1024),
});

test('each game uses a distinct manifest and content-addressed object prefix', () => {
  assert.deepEqual(SEARCH_INDEX_SCOPE_CONFIG, {
    magireco: {
      label: '全魔法纪录',
      manifestUrl: '/search_index_manifest.magireco.json',
      objectKeyPrefix: 'search/magireco',
    },
    exedra: {
      label: '全 Exedra',
      manifestUrl: '/search_index_manifest.exedra.json',
      objectKeyPrefix: 'search/exedra',
    },
  });
});

test('a manifest is valid only for its declared game scope', () => {
  const magireco = manifestFor('magireco');
  assert.equal(isSearchIndexManifest(magireco, 'magireco'), true);
  assert.equal(isSearchIndexManifest(magireco, 'exedra'), false);
  assert.equal(
    isSearchIndexManifest(
      { ...magireco, object_key: `search/${magireco.sha256}.json` },
      'magireco',
    ),
    false,
  );
});

test('v2 exposes same-origin physical chunks first and R2 as a verified fallback', async () => {
  const calls: string[] = [];
  const manifest = manifestFor('exedra');
  const fetchManifest = (async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return new Response(JSON.stringify(manifest), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  }) as typeof fetch;

  const sources = await getSearchIndexSources(
    new AbortController().signal,
    storyIndexSha256,
    'exedra',
    fetchManifest,
  );

  assert.deepEqual(calls, ['/search_index_manifest.exedra.json']);
  assert.equal(sources.length, 2);
  assert.equal(
    sources[0].chunk_base_url,
    `/search-chunks/exedra/${manifest.sha256}/`,
  );
  assert.equal(sources[0].url, undefined);
  assert.match(
    sources[1].url ?? '',
    /pub-23cae552ecf24722bf572b29fa8dd03f\.r2\.dev\/search\/exedra\/[a-f0-9]{64}\.json$/u,
  );
  assert.equal(sources[1].chunk_base_url, undefined);
  for (const source of sources) {
    assert.equal(source.sha256, manifest.sha256);
    assert.equal(source.bytes, manifest.bytes);
    assert.equal(source.entries, manifest.entries);
    assert.deepEqual(source.chunks, manifest.chunks);
  }
});

test('a stale scope manifest is rejected before any search payload can load', async () => {
  const stale = {
    ...manifestFor('magireco'),
    story_index_sha256: 'c'.repeat(64),
  };
  const fetchManifest = (async () => new Response(JSON.stringify(stale), {
    status: 200,
  })) as typeof fetch;

  await assert.rejects(
    getSearchIndexSources(
      new AbortController().signal,
      storyIndexSha256,
      'magireco',
      fetchManifest,
    ),
    /当前剧情目录不匹配/u,
  );
});
