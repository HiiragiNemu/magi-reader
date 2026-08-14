import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const floatingPath = new URL('../components/FloatingWindow.tsx', import.meta.url);
const readerPath = new URL('../app/reader/[id]/page.tsx', import.meta.url);
const aboutPath = new URL('../components/AboutModal.tsx', import.meta.url);
const cssPath = new URL('../app/globals.css', import.meta.url);

test('reader tool windows are modeless and do not render a blocking backdrop', async () => {
  const [floating, reader, about] = await Promise.all([
    readFile(floatingPath, 'utf8'),
    readFile(readerPath, 'utf8'),
    readFile(aboutPath, 'utf8'),
  ]);
  assert.match(floating, /data-modeless="true"/);
  assert.doesNotMatch(floating, /aria-modal/);
  assert.doesNotMatch(floating, /fixed inset-0/);
  assert.doesNotMatch(floating, /useDialog/);
  assert.match(reader, /<FloatingWindow[\s\S]*SYS:\/\/READER\.CONFIG/);
  assert.match(about, /<FloatingWindow[\s\S]*SYS:\/\/MAGIREADER\.LINKS/);
  assert.doesNotMatch(reader, /aria-modal="true"/);
  assert.doesNotMatch(about, /aria-modal="true"/);
});

test('day themes expose distinct retro light and paper window treatments', async () => {
  const css = await readFile(cssPath, 'utf8');
  assert.match(css, /\.magi-floating-window-light/);
  assert.match(css, /\.magi-floating-window-paper/);
  assert.match(css, /\.magi-retro-window-close/);
  assert.match(css, /backdrop-filter:\s*blur\((?:1|2)px\)/);
  assert.match(css, /\.magi-home-paper-root[\s\S]*color:\s*#29251e/);
});

test('one separator is painted only after an intact bilingual pair', async () => {
  const css = await readFile(cssPath, 'utf8');
  assert.match(css, /\.magi-bilingual-pair::after/);
  assert.match(css, /\.magi-bilingual-pair:last-child::after/);
  assert.doesNotMatch(css, /\.magi-bilingual-pair-stacked[^}]*border-top/s);
});
