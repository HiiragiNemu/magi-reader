import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const commit = 'a'.repeat(40);
const repositoryPath =
  'magireco-source-master/Scenarios_full/'
  + 'character_story/1001 - 环彩羽/story-1.json';

test('story JSON source selection is confined to a catalog allowlist', async () => {
  const {
    parseStoryJsonLanguage,
    parseStoryJsonSourceIndex,
    selectStoryJsonSource,
    StoryJsonSourceError,
  } = await import('../lib/story-json-source.ts');
  const stories = [{
    id: 'canonical-story',
    category: 'character_story',
    folder: 'fixture',
    percent: 100,
    has_cn: true,
    has_jp: true,
    path_cn: '/data/character_story/fixture/story_cn.txt',
    path_jp: '/data/character_story/fixture/story_jp.txt',
    json_sources_jp: [repositoryPath],
    legacy_ids: ['legacy-story'],
    game: 'magireco',
  }];

  assert.equal(parseStoryJsonLanguage('jp'), 'jp');
  assert.equal(parseStoryJsonSourceIndex('0'), 0);
  assert.equal(
    selectStoryJsonSource({
      stories,
      storyId: 'legacy-story',
      language: 'jp',
      index: 0,
    }),
    repositoryPath,
  );
  for (const operation of [
    () => parseStoryJsonLanguage('en'),
    () => parseStoryJsonSourceIndex('00'),
    () => parseStoryJsonSourceIndex('-1'),
    () => selectStoryJsonSource({
      stories,
      storyId: '../canonical-story',
      language: 'jp',
      index: 0,
    }),
    () => selectStoryJsonSource({
      stories,
      storyId: 'canonical-story',
      language: 'jp',
      index: 1,
    }),
  ]) {
    assert.throws(
      operation,
      error => error instanceof StoryJsonSourceError,
    );
  }
});

test('published Chinese JSON is selected and read from same-origin assets first', async () => {
  const {
    fetchPublishedStoryJsonSource,
    selectPublishedStoryJsonPath,
  } = await import('../lib/story-json-source.ts');
  const publishedPath = '/data/exedra_character/fixture/fixture_0.json';
  const stories = [{
    id: 'published-story',
    category: 'exedra_character',
    folder: 'fixture',
    percent: 100,
    has_cn: true,
    has_jp: true,
    path_cn: '/data/exedra_character/fixture/fixture_cn.txt',
    path_jp: '/data/exedra_character/fixture/fixture_jp.txt',
    json_paths_cn: [publishedPath],
    json_sources_cn: [
      'magiraexedra-translate-data-master/Scenarios_full/'
      + '3_Character/fixture/fixture_0.json',
    ],
  }];

  assert.equal(
    selectPublishedStoryJsonPath({
      stories,
      storyId: 'published-story',
      language: 'cn',
      index: 0,
    }),
    publishedPath,
  );
  assert.equal(
    selectPublishedStoryJsonPath({
      stories,
      storyId: 'published-story',
      language: 'jp',
      index: 0,
    }),
    undefined,
  );

  let requested: Request | undefined;
  const bytes = await fetchPublishedStoryJsonSource({
    requestUrl:
      'https://reader.example/api/story-json/published-story/cn/0',
    publishedPath,
    assets: {
      fetch: async input => {
        requested = input instanceof Request ? input : new Request(input);
        return Response.json({ story: { group_1: [] } });
      },
    },
  });
  assert.deepEqual(
    JSON.parse(new TextDecoder().decode(bytes)),
    { story: { group_1: [] } },
  );
  assert.equal(requested?.url, `https://reader.example${publishedPath}`);
  assert.equal(requested?.cache, 'force-cache');
});

test('missing published JSON cleanly falls back while invalid assets fail closed', async () => {
  const {
    fetchPublishedStoryJsonSource,
    StoryJsonSourceError,
  } = await import('../lib/story-json-source.ts');
  const base = {
    requestUrl: 'https://reader.example/api/story-json/story/cn/0',
    publishedPath: '/data/exedra_character/fixture/fixture_0.json',
  };
  assert.equal(
    await fetchPublishedStoryJsonSource({
      ...base,
      assets: { fetch: async () => new Response(null, { status: 404 }) },
    }),
    undefined,
  );
  await assert.rejects(
    fetchPublishedStoryJsonSource({
      ...base,
      assets: {
        fetch: async () => new Response('<html>bad asset</html>', {
          headers: { 'Content-Type': 'text/html' },
        }),
      },
    }),
    error =>
      error instanceof StoryJsonSourceError &&
      error.status === 502,
  );
});

test('repository JSON fetch uses only the fixed repository and fixed commit', async () => {
  const { fetchStoryJsonSource } = await import(
    '../lib/story-json-source.ts'
  );
  const token = 'fixture_token_1234567890';
  let capturedUrl = '';
  let capturedInit: RequestInit | undefined;
  const fetcher: typeof fetch = async (input, init) => {
    capturedUrl = String(input);
    capturedInit = init;
    return new Response('{"story":{"group_1":[]}}', {
      status: 200,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  };

  const bytes = await fetchStoryJsonSource({
    repositoryPath,
    language: 'jp',
    sourceCommit: commit.toUpperCase(),
    githubToken: token,
    fetcher,
  });
  assert.deepEqual(
    JSON.parse(new TextDecoder().decode(bytes)),
    { story: { group_1: [] } },
  );
  const url = new URL(capturedUrl);
  assert.equal(url.origin, 'https://api.github.com');
  assert.match(
    url.pathname,
    /^\/repos\/HiiragiNemu\/magi-reader\/contents\//u,
  );
  assert.equal(url.searchParams.get('ref'), commit);
  assert.equal(capturedUrl.includes(token), false);
  assert.equal(new Headers(capturedInit?.headers).get('authorization'), `Bearer ${token}`);
  assert.equal(capturedInit?.redirect, 'error');
  assert.equal(capturedInit?.cache, 'force-cache');
});

test('anonymous public repository fetch sends no authorization credential', async () => {
  const { fetchStoryJsonSource } = await import(
    '../lib/story-json-source.ts'
  );
  let capturedHeaders = new Headers();
  await fetchStoryJsonSource({
    repositoryPath,
    language: 'jp',
    sourceCommit: commit,
    fetcher: async (_input, init) => {
      capturedHeaders = new Headers(init?.headers);
      return Response.json({ story: { group_1: [] } });
    },
  });
  assert.equal(capturedHeaders.has('authorization'), false);
});

test('repository JSON fetch fails closed before unsafe paths or refs reach fetch', async () => {
  const {
    fetchStoryJsonSource,
    StoryJsonSourceError,
  } = await import('../lib/story-json-source.ts');
  let calls = 0;
  const fetcher: typeof fetch = async () => {
    calls += 1;
    return Response.json({});
  };
  for (const args of [
    {
      repositoryPath:
        'magireco-source-master/Scenarios_full/../secret.json',
      sourceCommit: commit,
      githubToken: undefined,
    },
    {
      repositoryPath,
      sourceCommit: 'EXEDRA-TEST',
      githubToken: undefined,
    },
    {
      repositoryPath,
      sourceCommit: commit,
      githubToken: 'bad\r\ntoken',
    },
  ]) {
    await assert.rejects(
      fetchStoryJsonSource({
        ...args,
        language: 'jp',
        fetcher,
      }),
      error => error instanceof StoryJsonSourceError,
    );
  }
  assert.equal(calls, 0);
});

test('repository JSON fetch enforces content type, size and object JSON', async () => {
  const {
    fetchStoryJsonSource,
    MAX_STORY_JSON_BYTES,
    StoryJsonSourceError,
  } = await import('../lib/story-json-source.ts');
  const invoke = (response: Response) =>
    fetchStoryJsonSource({
      repositoryPath,
      language: 'jp',
      sourceCommit: commit,
      fetcher: async () => response,
    });

  await assert.rejects(
    invoke(new Response('<html>not json</html>', {
      headers: { 'Content-Type': 'text/html' },
    })),
    error =>
      error instanceof StoryJsonSourceError &&
      error.status === 502,
  );
  await assert.rejects(
    invoke(new Response('[]', {
      headers: { 'Content-Type': 'application/json' },
    })),
    error =>
      error instanceof StoryJsonSourceError &&
      error.status === 502,
  );
  await assert.rejects(
    invoke(new Response('{}', {
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': String(MAX_STORY_JSON_BYTES + 1),
      },
    })),
    error =>
      error instanceof StoryJsonSourceError &&
      error.status === 413,
  );

  let cancelled = false;
  const oversized = new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new Uint8Array(MAX_STORY_JSON_BYTES));
        controller.enqueue(new Uint8Array([1]));
      },
      cancel() {
        cancelled = true;
      },
    }),
    { headers: { 'Content-Type': 'application/octet-stream' } },
  );
  await assert.rejects(
    invoke(oversized),
    error =>
      error instanceof StoryJsonSourceError &&
      error.status === 413,
  );
  assert.equal(cancelled, true);
});

test('story JSON catalog must be same-origin JSON and remains size bounded', async () => {
  const {
    loadStoryJsonCatalog,
    StoryJsonSourceError,
  } = await import('../lib/story-json-source.ts');
  const story = {
    id: 'catalog-story',
    category: 'main_story',
    folder: 'fixture',
    percent: 0,
    has_cn: false,
    has_jp: true,
    path_jp: '/data/main_story/fixture/story_jp.txt',
    json_sources_jp: [repositoryPath],
  };
  let requestedUrl = '';
  const assets: CloudflareAssetsBinding = {
    fetch: async input => {
      requestedUrl = input instanceof Request ? input.url : String(input);
      return new Response(JSON.stringify([story]), {
        headers: { 'Content-Type': 'application/json' },
      });
    },
  };
  const parsed = await loadStoryJsonCatalog({
    requestUrl: 'https://reader.example/api/story-json/id/jp/0',
    assets,
  });
  assert.equal(new URL(requestedUrl).pathname, '/story_index.json');
  assert.deepEqual(parsed, [story]);

  await assert.rejects(
    loadStoryJsonCatalog({
      requestUrl: 'https://reader.example/api/story-json/id/jp/0',
      assets: {
        fetch: async () => new Response('[]', {
          headers: { 'Content-Type': 'text/html' },
        }),
      },
    }),
    error =>
      error instanceof StoryJsonSourceError &&
      error.status === 503,
  );
});

test('public story JSON route never reuses the PR-writing token', () => {
  const route = readFileSync(
    new URL(
      '../app/api/story-json/[id]/[language]/[index]/route.ts',
      import.meta.url,
    ),
    'utf8',
  );
  assert.doesNotMatch(route, /env\.PROOFREADING_GITHUB_TOKEN/u);
  assert.match(route, /env\.STORY_JSON_GITHUB_TOKEN/u);
  assert.ok(
    route.indexOf('const publishedBytes = publishedPath') <
      route.indexOf('const bytes = publishedBytes ??'),
  );
});
