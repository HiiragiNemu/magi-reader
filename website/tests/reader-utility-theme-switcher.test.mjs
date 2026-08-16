import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const reader = readFileSync(
  new URL('../app/reader/[id]/page.tsx', import.meta.url),
  'utf8',
);
const css = readFileSync(
  new URL('../app/ui-refinements.css', import.meta.url),
  'utf8',
);

test('reader theme controls live in the floating utility panel', () => {
  const utilityStart = reader.indexOf('className="magi-reader-utility-actions"');
  const utilityEnd = reader.indexOf('</DraggableReaderWidget>', utilityStart);
  assert.ok(utilityStart >= 0 && utilityEnd > utilityStart);
  const utility = reader.slice(utilityStart, utilityEnd);

  assert.match(utility, /magi-reader-utility-theme-switcher/u);
  assert.match(utility, /aria-label="阅读主题"/u);
  for (const theme of ['light', 'paper', 'dark', 'green']) {
    assert.match(utility, new RegExp(`data-theme-option=\\{option\\.key\\}`));
    assert.match(reader, new RegExp(`key: '${theme}'`));
  }
  assert.match(utility, /onClick=\{\(\) => setTheme\(option\.key\)\}/u);
});

test('settings window no longer duplicates the theme selector', () => {
  const settingsStart = reader.indexOf('title="阅读设置"');
  const settingsEnd = reader.indexOf('</FloatingWindow>', settingsStart);
  assert.ok(settingsStart >= 0 && settingsEnd > settingsStart);
  const settings = reader.slice(settingsStart, settingsEnd);

  assert.doesNotMatch(settings, />主题</u);
  assert.doesNotMatch(settings, /setTheme\(/u);
  assert.match(settings, /字号（\{fontSize\}px）/u);
});

test('floating utility panel uses intrinsic width and themed icon buttons', () => {
  assert.match(
    css,
    /Reader UI V29[\s\S]*magi-reader-utility-widget[\s\S]*width: fit-content/u,
  );
  assert.match(css, /magi-reader-utility-content[\s\S]*flex-direction: column/u);
  assert.match(css, /magi-reader-utility-theme-switcher/u);
  for (const theme of ['light', 'paper', 'dark', 'green']) {
    assert.match(css, new RegExp(`data-theme-option='${theme}'`));
  }
  assert.match(css, /magi-reader-theme-option\[aria-pressed='true'\]/u);
});
