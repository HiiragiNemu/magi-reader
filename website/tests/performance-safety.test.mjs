import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const globalCss = readFileSync('app/globals.css', 'utf8');
const homeSource = readFileSync('app/page.tsx', 'utf8');
const readerSource = readFileSync('app/reader/[id]/page.tsx', 'utf8');
const sidebarSource = readFileSync('components/Sidebar.tsx', 'utf8');
const searchWorker = readFileSync('public/search-worker.js', 'utf8');

test('decorative layers stay viewport-bounded and avoid continuous GPU animation', () => {
  assert.doesNotMatch(globalCss, /height:\s*(?:340|500)vh/u);
  assert.doesNotMatch(globalCss, /animation:\s*(?:floatMist|balloonRainEnhanced)\b/u);
  assert.doesNotMatch(globalCss, /feTurbulence|mix-blend-mode/u);
  assert.match(globalCss, /\.magi-background\s*\{[\s\S]*?\binset:\s*0;/u);
  assert.match(globalCss, /\.magi-balloon-rain\s*\{[\s\S]*?\binset:\s*0;/u);
});

test('balloon decoration is opt-in, viewport-bounded, and cannot cover controls', () => {
  const balloonRule = globalCss.match(
    /\.magi-balloon-rain\s*\{([\s\S]*?)\n\}/u,
  )?.[1] ?? '';
  assert.match(balloonRule, /\bdisplay:\s*none;/u);
  assert.match(balloonRule, /\bpointer-events:\s*none;/u);
  assert.match(balloonRule, /\bz-index:\s*0;/u);
  assert.match(balloonRule, /\bcontain:\s*strict;/u);
  assert.match(
    globalCss,
    /\.magi-balloon-rain\[data-balloon-enabled='true'\]\s*\{[\s\S]*?display:\s*block;/u,
  );
  for (const slot of [2, 3, 4, 5, 6]) {
    assert.match(globalCss, new RegExp(`\\.magi-balloon-rain-item:nth-child\\(${slot}\\)`, 'u'));
  }
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

test('bulk story links do not trigger route prefetch waves', () => {
  assert.match(
    homeSource,
    /const storyHref = `\/reader\/\$\{encodeURIComponent\(story\.id\)\}[\s\S]*?<Link[\s\S]*?href=\{storyHref\}[\s\S]*?prefetch=\{false\}/u,
  );
  assert.match(
    sidebarSource,
    /id=\{`nav-item-\$\{story\.id\}`\}[\s\S]*?prefetch=\{false\}/u,
  );
});

test('closed folder cards use intrinsic-size containment without hiding open folders', () => {
  assert.match(
    homeSource,
    /isOpen \? '' : 'magi-folder-card-collapsed'/u,
  );
  assert.match(
    sidebarSource,
    /folderOpen \? '' : 'magi-sidebar-folder-collapsed'/u,
  );
  assert.match(
    globalCss,
    /\.magi-folder-card-collapsed\s*\{[\s\S]*?content-visibility:\s*auto;[\s\S]*?contain-intrinsic-size:\s*auto 68px;/u,
  );
  assert.match(
    globalCss,
    /\.magi-sidebar-folder-collapsed\s*\{[\s\S]*?content-visibility:\s*auto;[\s\S]*?contain-intrinsic-size:\s*auto 44px;/u,
  );
});

test('large full-text search is explicit and keeps one compact parsed object graph', () => {
  assert.match(
    homeSource,
    /useState<SearchMode>\('title'\)/u,
  );
  assert.match(searchWorker, /return raw;/u);
  assert.doesNotMatch(searchWorker, /return raw\.map\(/u);
});
