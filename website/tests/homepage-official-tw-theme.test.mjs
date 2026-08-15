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
  assert.equal(
    page.match(/className="magi-card-meta"/gu)?.length,
    2,
    'folder and story metadata each use a non-overlapping status column',
  );
  assert.match(page, /magi-card-title-flow[^"]*break-words/u);
  assert.match(css, /\.magi-card-heading-grid\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) auto/u);
  assert.match(css, /\.magi-card-title-flow\s*\{[\s\S]*overflow-wrap:\s*anywhere/u);
});

test('warm archival bubbles cover light and paper while excluding green and dark', () => {
  assert.match(
    page,
    /const isDayArchiveTheme = \(theme: string\): boolean =>\s*theme === 'light' \|\| theme === 'paper';/u,
  );
  assert.match(
    page,
    /isDayArchiveTheme\(theme\)\s*\? 'magi-home-light-nav-active'/u,
  );
  assert.match(
    page,
    /isDayArchiveTheme\(theme\)\s*\? 'magi-home-light-sidebar'/u,
  );
  assert.match(
    page,
    /isDayArchiveTheme\(theme\)\s*\? 'magi-home-light-toolbar'/u,
  );
  assert.match(page, /theme === 'dark'[\s\S]*bg-emerald-900\/50/u);
  assert.match(page, /\{ key: 'green', icon: Leaf, label: '护眼' \}/u);
  assert.match(css, /\.magi-home-light-folder-header\s*\{/u);
  assert.match(css, /\.magi-home-light-nav-active\s*\{/u);
  assert.match(css, /\.magi-home-light-sidebar\s*\{/u);
  assert.match(css, /\.magi-home-light-root\s*\{[\s\S]*linear-gradient/u);
  assert.match(css, /\.magi-home-paper-root\s*\{[\s\S]*background-size:\s*22px 22px/u);
  assert.match(
    css,
    /\.magi-home-paper-root\s*\{[\s\S]*radial-gradient\(circle at 1px 1px,[\s\S]*background-size:\s*22px 22px, 22px 22px, 22px 22px/u,
  );
  assert.match(css, /\.magi-home-light-control\s*,/u);
  assert.match(css, /\.magi-home-light-button-active\s*\{/u);
  assert.match(page, /magi-home-search-input[^`]*h-10[^`]*leading-6/u);
  assert.match(page, /magi-home-catalog flex-1 overflow-y-auto/u);
  assert.match(
    css,
    /\.magi-home-light-root:not\(\.magi-home-paper-root\) \.magi-home-catalog\s*\{[\s\S]*background-color:\s*rgba\(255, 255, 255, 0\.97\)[\s\S]*background-size:\s*40px 40px/u,
  );
  assert.match(
    css,
    /\.magi-home-light-root:not\(\.magi-home-paper-root\) \.magi-home-light-sidebar\s*\{[\s\S]*background-image:\s*none[\s\S]*backdrop-filter:\s*none/u,
  );
  assert.match(
    css,
    /\.magi-home-light-root:not\(\.magi-home-paper-root\) \.magi-home-light-folder-card,[\s\S]*?\{\s*border-radius:\s*0\.16rem/u,
  );
  assert.match(
    css,
    /\.magi-home-paper-root \.magi-home-light-folder-card\s*\{[\s\S]*border-radius:\s*1rem/u,
  );
  assert.match(
    css,
    /\.magi-home-light-root:not\(\.magi-home-paper-root\) \.magi-home-light-sidebar\s*\{[\s\S]*box-shadow:\s*4px 0 10px rgba\(30, 33, 34, 0\.19\)/u,
  );
  assert.match(
    css,
    /\.magi-home-paper-root \.magi-home-light-sidebar\s*\{[\s\S]*box-shadow:\s*14px 0 34px/u,
  );
  assert.match(
    css,
    /\.magi-home-paper-root \.magi-home-light-folder-card::before,[\s\S]*pointer-events:\s*none/u,
  );
  assert.match(
    css,
    /\.magi-home-light-root:not\(\.magi-home-paper-root\) \.magi-floating-window-light\s*\{[\s\S]*box-shadow:\s*4px 5px 11px/u,
  );
  assert.match(
    css,
    /\.magi-home-paper-root \.magi-floating-window-paper\s*\{[\s\S]*box-shadow:\s*15px 18px 42px/u,
  );
  assert.match(css, /\[data-bg-theme='green'\]\s*\{\s*background-color:\s*#dcedc8;\s*\}/u);
  assert.match(css, /\[data-bg-theme='dark'\]\s*\{[\s\S]*background-color:\s*#0f172a;/u);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)[\s\S]*magi-home-light-folder-card/u);
});

test('home catalogue desktop sidebar resizes independently without changing mobile flow', () => {
  assert.match(page, /HOME_SIDEBAR_WIDTH_STORAGE_KEY/u);
  assert.match(page, /localStorage\.setItem\(HOME_SIDEBAR_WIDTH_STORAGE_KEY/u);
  assert.match(page, /--magi-home-sidebar-width/u);
  assert.match(page, /role="separator"[\s\S]*aria-label=\{`调整主目录宽度/u);
  assert.match(page, /magi-home-sidebar[^`]*hidden[^`]*md:flex/u);
  assert.match(page, /magi-sidebar-resize-handle[^"\n]*hidden[^"\n]*md:block/u);
  assert.match(page, /<main className="flex-1 flex flex-col min-w-0 bg-transparent">/u);
  assert.match(css, /@media \(min-width: 768px\)[\s\S]*\.magi-home-sidebar\s*\{[\s\S]*flex-basis:\s*var\(--magi-home-sidebar-width/u);
});
