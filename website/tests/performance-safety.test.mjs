import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const globalCss = readFileSync('app/globals.css', 'utf8');
const homeSource = readFileSync('app/page.tsx', 'utf8');
const readerSource = readFileSync('app/reader/[id]/page.tsx', 'utf8');
const searchWorker = readFileSync('public/search-worker.js', 'utf8');

test('decorative layers stay viewport-bounded and avoid continuous GPU animation', () => {
  assert.doesNotMatch(globalCss, /height:\s*(?:340|500)vh/u);
  assert.doesNotMatch(globalCss, /animation:\s*(?:floatMist|balloonRainEnhanced)\b/u);
  assert.doesNotMatch(globalCss, /feTurbulence|mix-blend-mode/u);
  assert.match(globalCss, /\.magi-background\s*\{[\s\S]*?\binset:\s*0;/u);
  assert.match(globalCss, /\.magi-balloon-rain\s*\{[\s\S]*?\binset:\s*0;/u);
});

test('reduced-motion users do not receive decorative movement', () => {
  assert.match(globalCss, /@media\s*\(prefers-reduced-motion:\s*reduce\)/u);
  assert.match(
    globalCss,
    /@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*?\.magi-balloon-rain\s*\{[\s\S]*?display:\s*none;/u,
  );
});

test('reader bounds mounted story rows instead of rendering a whole long script', () => {
  assert.match(readerSource, /const STORY_ROWS_PER_PAGE = 200;/u);
  assert.match(
    readerSource,
    /const visibleRenderList = renderList\.slice\(/u,
  );
  assert.match(readerSource, /useDeferredValue\(searchQuery\)/u);
  assert.doesNotMatch(readerSource, /renderList\.map\(\(row, index\)/u);
});

test('large full-text search is explicit and keeps one compact parsed object graph', () => {
  assert.match(
    homeSource,
    /useState<SearchMode>\('title'\)/u,
  );
  assert.match(searchWorker, /return raw;/u);
  assert.doesNotMatch(searchWorker, /return raw\.map\(/u);
});
