import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const widget = readFileSync(
  new URL('../components/DraggableReaderWidget.tsx', import.meta.url),
  'utf8',
);
const reader = readFileSync(
  new URL('../app/reader/[id]/page.tsx', import.meta.url),
  'utf8',
);
const sidebar = readFileSync(
  new URL('../components/Sidebar.tsx', import.meta.url),
  'utf8',
);
const preferences = readFileSync(
  new URL('../lib/reader-display-preferences.ts', import.meta.url),
  'utf8',
);
const css = readFileSync(
  new URL('../app/ui-refinements.css', import.meta.url),
  'utf8',
);

test('reader floating widgets use pointer capture, viewport clamping and persisted positions', () => {
  assert.match(widget, /setPointerCapture/u);
  assert.match(widget, /releasePointerCapture/u);
  assert.match(widget, /window\.localStorage\.setItem\(storageKey/u);
  assert.match(widget, /window\.localStorage\.removeItem\(storageKey/u);
  assert.match(widget, /new ResizeObserver\(keepInsideViewport\)/u);
  assert.match(widget, /data-default-dock=\{defaultDock\}/u);
  assert.match(widget, /onDoubleClick=\{resetPosition\}/u);
  assert.match(widget, /magi-reader-floating-grip/u);
});

test('navigation and font controls are separate draggable upper/lower floating widgets', () => {
  assert.match(reader, /magi-reader-utility-widget-position-v1/u);
  assert.match(reader, /magi-reader-font-widget-position-v1/u);
  assert.equal((reader.match(/<DraggableReaderWidget/g) ?? []).length, 2);
  assert.match(reader, /defaultDock="top-right"/u);
  assert.match(reader, /defaultDock="bottom-right"/u);
  assert.match(reader, /magi-reader-utility-panel-floating/u);
  assert.match(reader, /magi-reader-utility-fab/u);
  assert.match(reader, /magi-reader-font-widget/u);
  assert.doesNotMatch(reader, /magi-reader-utility-dock/u);
  assert.doesNotMatch(sidebar, /magi-reader-utility-dock/u);
});

test('the first Episode header has no separator or reserved top band', () => {
  assert.match(reader, /firstStoryHeaderIndex/u);
  assert.match(reader, /data-reader-first-header=\{isFirstStoryHeader \|\| undefined\}/u);
  assert.match(reader, /isFirstStoryHeader[\s\S]*?\? 'mt-0 pt-0'[\s\S]*?: 'mt-6 border-t-2 pt-4'/u);
});

test('mobile reading width is viewport-efficient and remains adjustable', () => {
  assert.match(preferences, /READER_TEXT_WIDTH_MIN = 320/u);
  assert.match(preferences, /DEFAULT_READER_TEXT_WIDTH = 1024/u);
  assert.doesNotMatch(reader, /paddingInline: 'clamp\(3\.25rem, 6vw, 4rem\)'/u);
  assert.match(css, /\.magi-reader-main,[\s\S]*?\.magi-reader-main-paginated[\s\S]*?padding-right: 0\.3rem !important;[\s\S]*?padding-left: 0\.3rem !important;/u);
  assert.match(css, /\.magi-reader-document[\s\S]*?padding-right: 0\.18rem !important;[\s\S]*?padding-left: 0\.18rem !important;/u);
  assert.match(css, /\.magi-reader-page-turn-next[\s\S]*?right: -0\.48rem/u);
});
