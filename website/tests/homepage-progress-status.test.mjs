import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const page = readFileSync(path.resolve('app', 'page.tsx'), 'utf8');

test('home catalogue exposes none, partial, and complete translation status', () => {
  assert.match(
    page,
    /type TranslationProgressStatus = 'none' \| 'partial' \| 'complete';/u,
  );
  assert.match(
    page,
    /percent === 0 \? 'none' : percent === 100 \? 'complete' : 'partial'/u,
  );
  assert.match(
    page,
    /const groupProgressStatus = translationProgressStatus\(avgPercent\);/u,
  );
  assert.match(page, /data-translation-status=\{groupProgressStatus\}/u);
});

test('expanded story cards expose their own translation status', () => {
  assert.match(
    page,
    /const itemProgressStatus = translationProgressStatus\(progress\);/u,
  );
  assert.match(page, /data-translation-status=\{itemProgressStatus\}/u);
});

test('day archive branding is CSS-addressable without changing dark or green branding', () => {
  assert.match(page, /className=\{`magi-reader-brand/u);
  assert.match(
    page,
    /isDayArchiveTheme\(theme\)\s*\? 'magi-reader-brand-day-archive'\s*: 'bg-clip-text text-transparent bg-gradient-to-r from-emerald-600 to-teal-500'/u,
  );
  assert.match(page, />Archive v3\.1</u);
  assert.doesNotMatch(page, />Archive v3\.0</u);
});
