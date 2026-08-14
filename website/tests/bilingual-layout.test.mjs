import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync('app/reader/[id]/page.tsx', 'utf8');
const styles = readFileSync('app/globals.css', 'utf8');
const preferences = readFileSync(
  'lib/reader-display-preferences.ts',
  'utf8',
);

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
  assert.match(source, /bilingualStoryPairClass\(\s*mode,\s*bilingualLayout,?\s*\)/u);
  assert.match(source, /bilingualLanguagePaneClass\(\s*mode,\s*bilingualLayout,\s*'jp',?\s*\)/u);
  assert.match(source, /适用于汉化输入框/u);
});

test('reader width is bounded, persistent, and shared by reading and editing', () => {
  assert.match(preferences, /DEFAULT_READER_TEXT_WIDTH = 768/u);
  assert.match(preferences, /READER_TEXT_WIDTH_MIN = 640/u);
  assert.match(preferences, /READER_TEXT_WIDTH_MAX = 1280/u);
  assert.match(preferences, /magi-reader-display-preferences-v1/u);
  assert.match(preferences, /useSyncExternalStore|subscribeReaderDisplayPreferences/u);
  assert.match(
    source,
    /style=\{\{ maxWidth: `\$\{readerDisplayPreferences\.textWidthPx\}px` \}\}/u,
  );
  assert.match(source, /同时作用于阅读和汉化输入/u);
  assert.match(source, /手机端自动限制为屏幕可用宽度/u);
});

test('line-break markers reach both languages and never replace the editable value', () => {
  assert.match(source, /显示换行符/u);
  assert.match(source, /showLineBreaks=\{readerDisplayPreferences\.showLineBreaks\}/u);
  assert.ok(
    (source.match(/showLineBreaks=\{showLineBreaks\}/gu) ?? []).length >= 2,
    'Chinese and Japanese StoryText calls must receive the marker choice',
  );
  assert.match(source, /value=\{editedText\}/u);
  assert.match(source, /<LineBreakMarkerText text=\{editedText\} markerOnly \/>/u);
  assert.doesNotMatch(source, /editedText\.replace\([^)]*↵/u);
  assert.match(source, /data-line-break-overlay="true"/u);
});

test('reader settings remain usable in a short mobile viewport', () => {
  assert.match(source, /<FloatingWindow/u);
  assert.match(source, /className="magi-settings-window"/u);
  assert.match(styles, /max-height:\s*min\(48rem, calc\(100dvh - 16px\)\)/u);
  assert.match(source, /overflow-y-auto/u);
  assert.match(source, /min-h-11/u);
});

test('static Exedra Chinese uses the validated catalog path before the runtime API', () => {
  assert.match(
    source,
    /directSourceResolution\.sources\?\.kind === 'query' \|\|\s+Boolean\(currentStory\.path_cn\)/u,
  );
});

test('unavailable language views are disabled and general voice explains the missing JP source', () => {
  assert.match(source, /disabled=\{!modeAvailability\[nextMode\]\}/u);
  assert.match(source, /currentStory\?\.category === 'general_voice'/u);
  assert.match(source, /不会伪造日文对照/u);
  assert.match(source, /Exedra 语音/u);
});

test('pressing Enter uses the current search text instead of stale deferred matches', () => {
  assert.match(source, /const immediateQuery = normalizeSearchText\(searchQuery\)/u);
  assert.match(source, /immediateQuery === normalizedQuery/u);
  assert.match(source, /findMatchedIndices\(immediateQuery\)/u);
});
