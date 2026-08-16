import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const readerPath = new URL('../app/reader/[id]/page.tsx', import.meta.url);
const cssPath = new URL('../app/globals.css', import.meta.url);

test('reader exposes desktop search and compact utility-panel mobile search', async () => {
  const reader = await readFile(readerPath, 'utf8');
  assert.equal((reader.match(/placeholder="页内搜索"/g) ?? []).length, 2);
  assert.match(reader, /magi-reader-search-shell[\s\S]*min-w-48/);
  assert.match(reader, /magi-reader-search-shell[\s\S]*lg:flex/);
  assert.match(reader, /magi-reader-utility-search[\s\S]*lg:hidden/);
  assert.doesNotMatch(reader, /magi-reader-mobile-search/);
  assert.match(reader, /magi-reader-search-input h-9[\s\S]*leading-5/);
  assert.match(reader, /title="输入关键词后按 Enter 跳到下一处"/);
});

test('reader offers a closable quick font ruler backed by persisted display preferences', async () => {
  const reader = await readFile(readerPath, 'utf8');
  assert.match(reader, /magi-reader-font-control-open/);
  assert.match(reader, /role="group"\s+aria-label="快速字号调节"/);
  assert.match(reader, /aria-label="调整阅读字号"/);
  assert.match(reader, /aria-label="收起字号调节"/);
  assert.match(reader, /aria-label="展开字号调节"/);
  assert.match(reader, /fontControlOpen = readerDisplayPreferences\.fontControlOpen/);
  assert.match(
    reader,
    /updateReaderDisplayPreferences\(\{ fontControlOpen: false \}\)/,
  );
  assert.match(
    reader,
    /updateReaderDisplayPreferences\(\{ fontControlOpen: true \}\)/,
  );
  assert.match(reader, /updateReaderDisplayPreferences\(\{\s*fontSizePx:/);
});

test('day Reader themes put the stronger grid on the document instead of chrome', async () => {
  const css = await readFile(cssPath, 'utf8');
  assert.match(
    css,
    /\.magi-reader-theme-light \.magi-reader-sidebar[\s\S]*?background-image:\s*none !important;/,
  );
  assert.match(
    css,
    /\.magi-reader-theme-light \.magi-reader-document[\s\S]*?background-size:\s*12px 12px;/,
  );
  assert.match(
    css,
    /\.magi-reader-theme-light \.magi-floating-window-light[\s\S]*?border-radius:\s*0;[\s\S]*?background-image:\s*none;/,
  );
  assert.match(
    css,
    /\.magi-reader-theme-paper \.magi-reader-document[\s\S]*?border-radius:\s*1\.15rem;[\s\S]*?background-size:\s*13px 13px;/,
  );
  assert.match(
    css,
    /\.magi-reader-theme-paper \.magi-floating-window-paper[\s\S]*?border-radius:\s*1\.1rem;[\s\S]*?background-size:\s*28px 28px;/,
  );
  assert.match(
    css,
    /\.magi-reader-theme-paper \.magi-reader-sidebar[\s\S]*?background-image:\s*none !important;[\s\S]*?box-shadow:/,
  );
  assert.match(
    css,
    /\.magi-reader-theme-paper \.magi-reader-document::before,[\s\S]*?pointer-events:\s*none;/,
  );
  assert.match(
    css,
    /\.magi-reader-theme-light \.magi-reader-main\s*\{[\s\S]*?background:\s*#fff;/,
  );
});

test('reader keeps edge pagination while merging page status into a closable utility window', async () => {
  const [reader, pageTurnCss, refinements] = await Promise.all([
    readFile(readerPath, 'utf8'),
    readFile(cssPath, 'utf8'),
    readFile(new URL('../app/ui-refinements.css', import.meta.url), 'utf8'),
  ]);
  assert.match(reader, /pageCount > 1 && \([\s\S]*?aria-label="剧情快速翻页"/);
  assert.match(reader, /visiblePage > 0 && \([\s\S]*?aria-label="上一页"/);
  assert.match(reader, /visiblePage \+ 1 < pageCount && \([\s\S]*?aria-label="下一页"/);
  assert.match(reader, /magi-reader-utility-panel/);
  assert.match(reader, /aria-label="关闭阅读导航栏"/);
  assert.match(reader, /magi-reader-page-summary/);
  assert.match(reader, /第 \{visiblePage \+ 1\} \/ \{pageCount\} 页/);
  assert.match(reader, /magi-reader-utility-reopen/);
  assert.doesNotMatch(reader, /<StoryPagination/);
  assert.doesNotMatch(reader, /← 上一页/);
  assert.doesNotMatch(reader, /下一页 →/);
  assert.match(reader, /window\.addEventListener\('keydown', handlePageTurnKeyDown\)/);
  assert.match(reader, /onTouchStart=\{handlePageTouchStart\}/);
  assert.match(reader, /onTouchEnd=\{handlePageTouchEnd\}/);
  assert.match(reader, /paddingInline: 'clamp\(3\.25rem, 6vw, 4rem\)'/);
  assert.match(refinements, /\.magi-reader-utility-panel[\s\S]*backdrop-filter:/);
  assert.match(pageTurnCss, /\.magi-reader-page-turn[\s\S]*?min-width:\s*2\.8rem;/);
});

test('day Reader chrome is neutral while official status badges use a darker title-bar treatment', async () => {
  const [reader, sidebar, css] = await Promise.all([
    readFile(readerPath, 'utf8'),
    readFile(new URL('../components/Sidebar.tsx', import.meta.url), 'utf8'),
    readFile(cssPath, 'utf8'),
  ]);
  assert.match(reader, /magi-reader-source-badge/);
  assert.match(sidebar, /aria-current=\{active \? 'page' : undefined\}/);
  assert.match(sidebar, /magi-reader-source-badge/);
  assert.match(css, /\.magi-reader-theme-light \.magi-reader-source-badge,[\s\S]*?background:\s*#555c5d !important;/);
  assert.match(css, /\.magi-reader-theme-paper \.magi-reader-source-badge[\s\S]*?background:\s*#665235 !important;/);
  assert.match(css, /\.magi-reader-theme-light \.magi-reader-sidebar \[id\^='nav-item-'\]\[aria-current='page'\]/);
  assert.match(css, /\.magi-reader-theme-light \[class\*='text-emerald'\]:not\(\[style\]\)/);
  assert.match(css, /\.magi-reader-theme-paper button:not\(\.magi-retro-window-close\)/);
  assert.match(css, /\.magi-reader-theme-light \.magi-floating-window-light \.magi-floating-window-titlebar[\s\S]*?background-image:\s*none;/);
});

test('quick font ruler stays compact on mobile without changing dark or green Reader surfaces', async () => {
  const css = await readFile(cssPath, 'utf8');
  assert.match(css, /\.magi-reader-font-control-open[\s\S]*?width:\s*min\(21rem/);
  assert.match(css, /@media \(max-width: 767px\)[\s\S]*?width:\s*min\(15rem/);
  assert.doesNotMatch(css, /\.magi-reader-theme-(?:dark|green) \.magi-reader-document/);
});
