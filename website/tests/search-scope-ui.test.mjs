import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const page = readFileSync(path.resolve('app', 'page.tsx'), 'utf8');

test('catalog uses only the existing game switch and omits a duplicate search scope selector', () => {
  assert.doesNotMatch(page, /aria-label="搜索对象覆盖范围"/u);
  assert.doesNotMatch(page, /\(\['magireco', 'exedra'\] as const\)\.map/u);
  assert.match(page, /onClick=\{switchStorySystem\}/u);
  assert.match(page, /切换到 Magia Exedra 剧情/u);
  assert.match(page, /切换到 Magia Record 剧情/u);
});

test('changing game scope rebuilds the worker and never uses the legacy combined object', () => {
  assert.match(
    page,
    /getSearchIndexSources\(controller\.signal, storyIndexSha256, storySystem\)/u,
  );
  assert.match(page, /\[storyIndexSha256, storySystem\]/u);
  assert.match(page, /worker\.terminate\(\)/u);
  assert.match(page, /searchSequenceRef\.current \+= 1/u);
  assert.doesNotMatch(page, /search_content\.json/u);
  assert.doesNotMatch(page, /search_index_manifest\.json/u);
});
