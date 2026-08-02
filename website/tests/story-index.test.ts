import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
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
    json_paths_cn: [
      '/data/exedra_main/main_demo/main_demo_0.json',
    ],
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

  for (const unsafeJsonPaths of [
    [],
    ['/data/exedra_main/main_demo/main_demo_0.txt'],
    ['/data/../api/submit.json'],
    [
      '/data/exedra_main/main_demo/main_demo_0.json',
      '/DATA/EXEDRA_MAIN/MAIN_DEMO/MAIN_DEMO_0.JSON',
    ],
  ]) {
    assert.throws(
      () =>
        parseStoryIndex([
          { ...validStory, json_paths_cn: unsafeJsonPaths },
        ]),
      /json_paths_cn/i,
    );
  }
});

test('story index accepts only language-scoped repository JSON allowlists', async () => {
  const {
    isSafeRepositoryStoryJsonPath,
    parseStoryIndex,
  } = await import('../lib/story-index.ts');
  const validStory = {
    id: 'repository-json-story',
    category: 'character_story',
    folder: 'fixture',
    percent: 100,
    has_cn: true,
    has_jp: true,
    path_cn: '/data/character_story/fixture/story_cn.txt',
    path_jp: '/data/character_story/fixture/story_jp.txt',
    json_sources_jp: [
      'magireco-source-master/Scenarios_full/'
        + 'character_story/fixture/story-1.json',
    ],
    json_sources_cn: [
      'magireco-translate-data-master/Scenarios_full/'
        + 'character_story/fixture/story-1.json',
    ],
    game: 'magireco',
  };

  assert.deepEqual(parseStoryIndex([validStory]), [validStory]);
  assert.equal(
    isSafeRepositoryStoryJsonPath(validStory.json_sources_jp[0]!, 'jp'),
    true,
  );
  for (const unsafePath of [
    '/magireco-source-master/Scenarios_full/story.json',
    'magireco-source-master/Scenarios_full/../secret.json',
    String.raw`magireco-source-master\Scenarios_full\story.json`,
    'magireco-source-master/Scenarios_full/%2e%2e/secret.json',
    'magireco-source-master/Scenarios_full/story.txt',
    'magireco-translate-data-master/Scenarios_full/story.json',
  ]) {
    assert.equal(
      isSafeRepositoryStoryJsonPath(unsafePath, 'jp'),
      false,
      unsafePath,
    );
    assert.throws(
      () => parseStoryIndex([{
        ...validStory,
        json_sources_jp: [unsafePath],
      }]),
      /json_sources_jp/iu,
    );
  }
  assert.throws(
    () => parseStoryIndex([{
      ...validStory,
      json_sources_jp: [
        validStory.json_sources_jp[0],
        validStory.json_sources_jp[0].toUpperCase(),
      ],
    }]),
    /json_sources_jp/iu,
  );
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

test('combo component voice routes retain their own playable JSON and TXT', async () => {
  const { findStoryByRouteId, parseStoryIndex } = await import(
    '../lib/story-index.ts'
  );
  const raw = JSON.parse(
    readFileSync(
      new URL('../public/story_index.json', import.meta.url),
      'utf8',
    ),
  );
  const stories = parseStoryIndex(raw);
  const canonical = findStoryByRouteId(stories, 'voice_111800');
  const component = findStoryByRouteId(stories, 'voice_111801');

  assert.equal(canonical?.id, 'voice_111800');
  assert.equal(component?.id, 'voice_111801');
  assert.notEqual(component?.id, canonical?.id);
  assert.equal(
    component?.path_cn,
    '/data/general_voice/111801/111801_cn.txt',
  );
  assert.deepEqual(
    component?.json_paths_cn,
    ['/data/general_voice/111801/111801_cn.json'],
  );
  assert.ok(component?.json_sources_cn?.[0]?.endsWith('/111801_cn.json'));
  assert.equal(component?.source_count, 1);
  assert.equal(component?.voice_model_role, 'comboComponent');
  assert.doesNotMatch(component?.title ?? '', /legacy|alias/iu);
  assert.equal(
    canonical?.legacy_ids?.includes('voice_111801') ?? false,
    false,
  );
});

test('optional runtime Chinese failures do not block Japanese-only stories', async () => {
  const { isOptionalStorySourceUnavailable } = await import(
    '../lib/story-index.ts'
  );

  for (const status of [404, 502, 503]) {
    assert.equal(isOptionalStorySourceUnavailable(status), true);
  }
  for (const status of [200, 400, 401, 403, 500]) {
    assert.equal(isOptionalStorySourceUnavailable(status), false);
  }
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
      pathCn:
        '/api/exedra/localized/exedra_character_character_rena_939abf8f5b',
      pathJp: '/data/exedra_character/character_rena/character_rena_jp.txt',
      optionalCn: true,
      kind: 'exedra-trusted-runtime',
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
  globalThis.fetch = ((input: string | URL | Request) => {
    fetchCalls += 1;
    if (String(input) === '/api/exedra/localization-status') {
      return Promise.resolve(
        Response.json({
          version: 1,
          total: 0,
          entries: [],
          database_configured: false,
        }),
      );
    }
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
    assert.equal(fetchCalls, 2);

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

test('trusted Exedra status requires exact story and source identities', async () => {
  const {
    mergeTrustedExedraLocalizations,
    parseStoryIndex,
    parseTrustedExedraLocalizationStatus,
  } = await import('../lib/story-index.ts');
  const untranslated = {
    id: 'exedra_character_character_iroha_1234567890',
    category: 'exedra_character',
    folder: 'character_iroha',
    percent: 0,
    has_cn: false,
    has_jp: true,
    path_jp:
      '/data/exedra_character/character_iroha/character_iroha_jp.txt',
    game: 'exedra',
    source_identity: 'exedra:3_Character:character_iroha',
  };
  const staticChinese = {
    ...untranslated,
    id: 'exedra_character_character_rena_1234567890',
    source_identity: 'exedra:3_Character:character_rena',
    percent: 100,
    has_cn: true,
    path_cn:
      '/data/exedra_character/character_rena/character_rena_cn.txt',
  };
  const stories = parseStoryIndex([untranslated, staticChinese]);
  const status = parseTrustedExedraLocalizationStatus({
    version: 1,
    total: 3,
    database_configured: true,
    entries: [
      {
        story_id: untranslated.id,
        source_identity: untranslated.source_identity,
      },
      {
        story_id: staticChinese.id,
        source_identity: staticChinese.source_identity,
      },
      {
        story_id: 'exedra_character_character_other_1234567890',
        source_identity: 'exedra:3_Character:character_other',
      },
    ],
  });
  const merged = mergeTrustedExedraLocalizations(stories, status);
  assert.deepEqual(merged[0], {
    ...untranslated,
    percent: 100,
    has_cn: true,
    path_cn: `/api/exedra/localized/${untranslated.id}`,
  });
  assert.deepEqual(merged[1], staticChinese);

  const mismatched = mergeTrustedExedraLocalizations(
    stories,
    parseTrustedExedraLocalizationStatus({
      version: 1,
      total: 1,
      database_configured: true,
      entries: [{
        story_id: untranslated.id,
        source_identity: 'exedra:3_Character:character_wrong',
      }],
    }),
  );
  assert.deepEqual(mismatched, stories);
});

test('trusted Exedra status rejects malformed and duplicate entries', async () => {
  const { parseTrustedExedraLocalizationStatus } = await import(
    '../lib/story-index.ts'
  );
  assert.throws(
    () => parseTrustedExedraLocalizationStatus({
      version: 1,
      total: 2,
      database_configured: true,
      entries: [{
        story_id: 'same',
        source_identity: 'exedra:3_Character:a',
      }, {
        story_id: 'same',
        source_identity: 'exedra:3_Character:b',
      }],
    }),
    /身份无效/u,
  );
  assert.throws(
    () => parseTrustedExedraLocalizationStatus({
      version: 1,
      total: 2,
      database_configured: true,
      entries: [],
    }),
    /条目数无效/u,
  );
});

test('trusted Exedra status failures safely preserve the static catalog', async () => {
  const {
    applyTrustedExedraLocalizationStatus,
    parseStoryIndex,
  } = await import('../lib/story-index.ts');
  const stories = parseStoryIndex([{
    id: 'exedra_character_character_iroha_1234567890',
    category: 'exedra_character',
    folder: 'character_iroha',
    percent: 0,
    has_cn: false,
    has_jp: true,
    path_jp:
      '/data/exedra_character/character_iroha/character_iroha_jp.txt',
    game: 'exedra',
    source_identity: 'exedra:3_Character:character_iroha',
  }]);
  const originalWarn = console.warn;
  console.warn = () => {};
  try {
    const unavailableFetch: typeof fetch = () =>
      Promise.resolve(new Response('unavailable', { status: 503 }));
    const httpFailure = await applyTrustedExedraLocalizationStatus(
      stories,
      unavailableFetch,
    );
    assert.deepEqual(httpFailure, stories);

    const malformedFetch: typeof fetch = () => Promise.resolve(Response.json({
      version: 1,
      total: 1,
      database_configured: true,
      entries: [],
    }));
    const malformed = await applyTrustedExedraLocalizationStatus(
      stories,
      malformedFetch,
    );
    assert.deepEqual(malformed, stories);
  } finally {
    console.warn = originalWarn;
  }
});

test('general voice coverage is derived from translated textHome units', async () => {
  const { parseStoryIndex, isSafeRepositoryStoryJsonPath } = await import(
    '../lib/story-index.ts'
  );
  const untranslated = {
    id: 'voice_406200',
    category: 'general_voice',
    folder: '4062 - 井之上泷奈（井ノ上 たきな）',
    percent: 0,
    has_cn: true,
    has_jp: false,
    path_cn: '/data/general_voice/406200/406200_cn.txt',
    json_paths_cn: ['/data/general_voice/406200/406200_cn.json'],
    json_sources_cn: [
      'magireco-voice-translate-data-master/Scenarios_full/'
        + 'general_voice/406200/406200_cn.json',
    ],
    game: 'magireco',
    source_format: 'general_voice_json',
    source_count: 1,
    source_identity: 'general_voice/406200',
    translated_units_cn: 0,
    translation_units_total: 39,
    raw_voice_references: 39,
    groups_without_voice: 0,
    model_id: '406200',
    character_group_id: '4062',
    canonical_model_id: '406200',
    voice_model_role: 'standalone',
  };
  assert.deepEqual(parseStoryIndex([untranslated]), [untranslated]);
  assert.equal(
    isSafeRepositoryStoryJsonPath(untranslated.json_sources_cn[0], 'cn'),
    true,
  );
  assert.throws(
    () => parseStoryIndex([{ ...untranslated, percent: 100 }]),
    /汉化统计无效/u,
  );
  assert.throws(
    () => parseStoryIndex([{
      ...untranslated,
      translated_units_cn: 40,
    }]),
    /汉化统计无效/u,
  );
  assert.throws(
    () => parseStoryIndex([{
      ...untranslated,
      json_sources_cn: [
        'magireco-voice-source-master/Scenarios_full/'
          + 'general_voice/406200/406200.json',
      ],
    }]),
    /json_sources_cn/u,
  );
});
