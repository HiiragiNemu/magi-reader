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
