import assert from 'node:assert/strict';
import test from 'node:test';

test('story index validation rejects paths outside the public data boundary', async () => {
  const { parseStoryIndex } = await import('../lib/story-index.ts');
  const validStory = {
    id: 'safe-story',
    category: 'exedra_main',
    folder: 'main_demo',
    percent: 0,
    has_cn: false,
    has_jp: true,
    path_jp: '/data/exedra_main/main_demo/main_demo_jp.txt',
    game: 'exedra',
  };

  assert.deepEqual(parseStoryIndex([validStory]), [validStory]);

  for (const unsafePath of [
    'https://evil.invalid/story.txt',
    '/data/../api/submit',
    String.raw`/data\..\api\submit`,
    '/data/%2e%2e/api/submit',
    '/data/%2Fapi/submit',
    '/data/%5c..%5capi%5csubmit',
  ]) {
    assert.throws(
      () => parseStoryIndex([{ ...validStory, path_jp: unsafePath }]),
      /path|路径|data/i,
      unsafePath,
    );
  }
});

test('legacy routes resolve only to one validated canonical Magia Record story', async () => {
  const { findStoryByRouteId, parseStoryIndex } = await import(
    '../lib/story-index.ts'
  );
  const canonical = {
    id: 'character_story_310031_1-4_f5b139f09e',
    category: 'character_story',
    folder: '1003 - 由比鹤乃（由比 鶴乃）',
    percent: 100,
    has_cn: true,
    has_jp: true,
    path_cn:
      '/data/character_story/1003 - 由比鹤乃（由比 鶴乃）/310031_1-4_cn.txt',
    path_jp:
      '/data/character_story/1003 - 由比鹤乃（由比 鶴乃）/310031_1-4_jp.txt',
    game: 'magireco',
    legacy_ids: ['310031'],
  };
  const parsed = parseStoryIndex([canonical]);
  assert.equal(findStoryByRouteId(parsed, '310031')?.id, canonical.id);
  assert.equal(findStoryByRouteId(parsed, canonical.id)?.id, canonical.id);
  assert.equal(findStoryByRouteId(parsed, 'missing'), undefined);

  const collidingCanonical = {
    ...canonical,
    id: '310031',
    legacy_ids: undefined,
  };
  for (const stories of [
    [canonical, collidingCanonical],
    [collidingCanonical, canonical],
  ]) {
    assert.throws(() => parseStoryIndex(stories), /旧剧情编号冲突/);
  }
  assert.throws(
    () =>
      parseStoryIndex([
        canonical,
        {
          ...canonical,
          id: 'another-story',
          legacy_ids: ['310031'],
        },
      ]),
    /旧剧情编号冲突/,
  );
  assert.throws(
    () => parseStoryIndex([{ ...canonical, legacy_ids: ['../310031'] }]),
    /legacy_ids/,
  );
  assert.throws(
    () =>
      parseStoryIndex([
        {
          ...canonical,
          game: 'exedra',
        },
      ]),
    /legacy_ids/,
  );
});

test('reader resolves safe query paths without waiting for the full story index', async () => {
  const { resolveDirectStorySources } = await import('../lib/story-index.ts');

  assert.deepEqual(
    resolveDirectStorySources(
      'legacy-story',
      '/data/main_story/chapter/story_cn.txt',
      '/data/main_story/chapter/story_jp.txt',
    ),
    {
      pathCn: '/data/main_story/chapter/story_cn.txt',
      pathJp: '/data/main_story/chapter/story_jp.txt',
      optionalCn: false,
      kind: 'query',
    },
  );
});

test('reader derives deterministic Exedra paths for direct route visits', async () => {
  const {
    resolveDirectStorySources,
    verifyExedraStoryId,
  } = await import('../lib/story-index.ts');

  assert.deepEqual(
    resolveDirectStorySources(
      'exedra_character_character_rena_939abf8f5b',
      '/data/stale/path.txt',
      '/data/stale/path.txt',
    ),
    {
      pathCn: '/data/exedra_character/character_rena/character_rena_cn.txt',
      pathJp: '/data/exedra_character/character_rena/character_rena_jp.txt',
      optionalCn: true,
      kind: 'exedra-derived',
    },
  );
  assert.equal(
    await verifyExedraStoryId(
      'exedra_character_character_rena_939abf8f5b',
    ),
    true,
  );
  assert.equal(
    await verifyExedraStoryId(
      'exedra_character_character_rena_0000000000',
    ),
    false,
  );
  assert.equal(resolveDirectStorySources('not-an-exedra-route', null, null), null);
  assert.throws(
    () => resolveDirectStorySources(
      `exedra_character_character_${'a'.repeat(97)}_0000000000`,
      null,
      null,
    ),
    /编号|格式/i,
  );
});

test('reader rejects unsafe direct query paths', async () => {
  const { resolveDirectStorySources } = await import('../lib/story-index.ts');

  for (const unsafePath of [
    'https://evil.invalid/story.txt',
    '/data/../api/submit',
    String.raw`/data\..\api\submit`,
    '/data/%2e%2e/api/submit',
    '/data/%2Fapi/submit',
    '/data/%5c..%5capi%5csubmit',
    '/data/%252e%252e/api/submit',
    '/data/story.html',
  ]) {
    assert.throws(
      () => resolveDirectStorySources('safe-story', unsafePath, ''),
      /不安全|路径/i,
      unsafePath,
    );
  }
});

test('bounded story reads cancel a streamed body before buffering past the limit', async () => {
  const { readBoundedResponseBody } = await import('../lib/story-index.ts');
  let cancelled = false;
  const response = new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new Uint8Array([1, 2, 3]));
        controller.enqueue(new Uint8Array([4, 5, 6]));
      },
      cancel() {
        cancelled = true;
      },
    }),
  );

  await assert.rejects(
    readBoundedResponseBody(response, 4, '测试剧情'),
    /测试剧情超过大小限制/,
  );
  assert.equal(cancelled, true);
});

test('story index shares one request while aborted consumers can reattach', async () => {
  const { loadStoryIndex } = await import('../lib/story-index.ts');
  const originalFetch = globalThis.fetch;
  let fetchCalls = 0;
  let resolveResponse: ((response: Response) => void) | undefined;
  globalThis.fetch = (() => {
    fetchCalls += 1;
    return new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    });
  }) as typeof fetch;

  try {
    const firstController = new AbortController();
    const secondController = new AbortController();
    const first = loadStoryIndex(firstController.signal);
    const second = loadStoryIndex(secondController.signal);
    assert.equal(fetchCalls, 1);

    firstController.abort();
    await assert.rejects(first, error =>
      error instanceof DOMException && error.name === 'AbortError'
    );

    const story = {
      id: 'reattach-test',
      category: 'main_story',
      folder: 'fixture',
      percent: 0,
      has_cn: false,
      has_jp: true,
      path_jp: '/data/main_story/fixture/fixture_jp.txt',
    };
    resolveResponse?.(
      new Response(JSON.stringify([story]), {
        headers: { 'content-type': 'application/json' },
      }),
    );
    const loaded = await second;
    assert.equal(loaded.stories[0]?.id, story.id);
    assert.equal(fetchCalls, 1);

    const alreadyAborted = new AbortController();
    alreadyAborted.abort();
    await assert.rejects(
      loadStoryIndex(alreadyAborted.signal),
      error => error instanceof DOMException && error.name === 'AbortError',
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
