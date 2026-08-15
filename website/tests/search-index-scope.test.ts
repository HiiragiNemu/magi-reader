import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getSearchIndexSources,
  isSearchIndexManifest,
  SEARCH_INDEX_SCOPE_CONFIG,
  type SearchIndexScope,
} from '../lib/search-index-scope.ts';

const storyIndexSha256 = 'b'.repeat(64);

const manifestFor = (scope: SearchIndexScope, sha256 = 'a'.repeat(64)) => ({
  version: 1 as const,
  sha256,
  bytes: 123,
  entries: 7,
  object_key: `${SEARCH_INDEX_SCOPE_CONFIG[scope].objectKeyPrefix}/${sha256}.json`,
  story_index_sha256: storyIndexSha256,
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

test('loading one scope exposes R2 first and a content-addressed GitHub Release fallback', async () => {
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
  assert.match(
    sources[0].url,
    /pub-23cae552ecf24722bf572b29fa8dd03f\.r2\.dev\/search\/exedra\/[a-f0-9]{64}\.json$/u,
  );
  assert.match(
    sources[1].url,
    /github\.com\/HiiragiNemu\/magi-reader\/releases\/download\/magireader-search-assets-v1\/search-exedra-[a-f0-9]{64}\.json$/u,
  );
  assert.doesNotMatch(sources[0].url, /magireco/u);
  assert.doesNotMatch(sources[1].url, /magireco/u);
  for (const source of sources) {
    assert.equal(source.sha256, manifest.sha256);
    assert.equal(source.bytes, manifest.bytes);
    assert.equal(source.entries, manifest.entries);
  }
});

test('a stale scope manifest is rejected before its large object can load', async () => {
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
