import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const page = readFileSync(path.resolve('app', 'page.tsx'), 'utf8');
const css = readFileSync(path.resolve('app', 'globals.css'), 'utf8');

test('official TW badges are limited to Exedra stories and their folder bubbles', () => {
  assert.match(
    page,
    /story => isExedraCategory\(story\.category\) && story\.official_tw/u,
  );
  assert.match(
    page,
    /isExedraCategory\(story\.category\) && story\.official_tw/u,
  );
  assert.match(page, /official_tw_label\?\.trim\(\) \|\| '台服'/u);
  assert.equal(
    page.match(/aria-label="台服官方中文"/gu)?.length,
    2,
    'folder and story title bubbles should each expose the badge accessibly',
  );
  assert.match(css, /\.magi-official-tw-badge\s*\{/u);
});

test('warm archival bubbles are selected only by the default light theme', () => {
  assert.match(page, /const isLight = theme === 'light';/u);
  assert.match(
    page,
    /theme === 'light'\s*\? 'magi-home-light-nav-active'/u,
  );
  assert.match(
    page,
    /theme === 'light'\s*\? 'magi-home-light-sidebar'/u,
  );
  assert.match(
    page,
    /theme === 'light'\s*\? 'magi-home-light-toolbar'/u,
  );
  assert.match(page, /theme === 'dark'[\s\S]*bg-emerald-900\/50/u);
  assert.match(page, /\{ key: 'green', icon: Leaf, label: '护眼' \}/u);
  assert.match(css, /\.magi-home-light-folder-header\s*\{/u);
  assert.match(css, /\.magi-home-light-nav-active\s*\{/u);
  assert.match(css, /\.magi-home-light-sidebar\s*\{/u);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)[\s\S]*magi-home-light-folder-card/u);
});
