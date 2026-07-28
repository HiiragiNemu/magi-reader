import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync('app/reader/[id]/page.tsx', 'utf8');

test('reader exposes persistent side-by-side and stacked bilingual layouts', () => {
  assert.match(source, /type BilingualLayout = 'side-by-side' \| 'stacked'/u);
  assert.match(source, /magi-reader-bilingual-layout-v1/u);
  assert.match(source, /window\.localStorage\.getItem/u);
  assert.match(source, /window\.localStorage\.setItem/u);
  assert.match(source, /左右排列/u);
  assert.match(source, /上下排列/u);
});

test('the selected layout is passed into normal and proofreading rows', () => {
  assert.match(source, /bilingualLayout=\{bilingualLayout\}/u);
  assert.match(source, /bilingualLayout === 'stacked'/u);
  assert.match(source, /适用于汉化输入框/u);
});

test('static Exedra Chinese uses the validated catalog path before the runtime API', () => {
  assert.match(
    source,
    /directSourceResolution\.sources\?\.kind === 'query' \|\|\s+Boolean\(currentStory\.path_cn\)/u,
  );
});
