import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_READER_FONT_SIZE,
  DEFAULT_READER_TEXT_WIDTH,
  READER_FONT_SIZE_MAX,
  READER_FONT_SIZE_MIN,
  READER_DISPLAY_PREFERENCES_STORAGE_KEY,
  READER_TEXT_WIDTH_MAX,
  READER_TEXT_WIDTH_MIN,
  getReaderDisplayPreferencesSnapshot,
  parseReaderDisplayPreferences,
  updateReaderDisplayPreferences,
} from './reader-display-preferences.ts';

test('reader display preferences default to visible line-break markers', () => {
  assert.deepEqual(parseReaderDisplayPreferences(null), {
    textWidthPx: DEFAULT_READER_TEXT_WIDTH,
    fontSizePx: DEFAULT_READER_FONT_SIZE,
    fontControlOpen: true,
    showLineBreaks: true,
  });
  assert.deepEqual(parseReaderDisplayPreferences('{broken'), {
    textWidthPx: DEFAULT_READER_TEXT_WIDTH,
    fontSizePx: DEFAULT_READER_FONT_SIZE,
    fontControlOpen: true,
    showLineBreaks: true,
  });
});

test('reader display preferences clamp and snap persisted widths', () => {
  assert.deepEqual(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 100, fontSizePx: 8, showLineBreaks: true }),
    ),
    {
      textWidthPx: READER_TEXT_WIDTH_MIN,
      fontSizePx: READER_FONT_SIZE_MIN,
      fontControlOpen: true,
      showLineBreaks: true,
    },
  );
  assert.deepEqual(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 5000, fontSizePx: 99, showLineBreaks: false }),
    ),
    {
      textWidthPx: READER_TEXT_WIDTH_MAX,
      fontSizePx: READER_FONT_SIZE_MAX,
      fontControlOpen: true,
      showLineBreaks: false,
    },
  );
  assert.equal(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 783, showLineBreaks: true }),
    ).textWidthPx,
    768,
  );
});

test('legacy or malformed marker choices fall back to the visible default', () => {
  assert.equal(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 768, showLineBreaks: 'true' }),
    ).showLineBreaks,
    true,
  );
  assert.equal(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 768, showLineBreaks: false }),
    ).showLineBreaks,
    false,
  );
});

test('legacy display snapshots gain the default font size without losing choices', () => {
  assert.deepEqual(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 896, showLineBreaks: true }),
    ),
    {
      textWidthPx: 896,
      fontSizePx: DEFAULT_READER_FONT_SIZE,
      fontControlOpen: true,
      showLineBreaks: true,
    },
  );
  assert.equal(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 768, fontSizePx: 16.6 }),
    ).fontSizePx,
    17,
  );
  assert.equal(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 768, fontControlOpen: false }),
    ).fontControlOpen,
    false,
  );
});

test('reader display preferences write the normalized choice to localStorage', () => {
  const originalWindow = globalThis.window;
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      localStorage: {
        getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => values.set(key, value),
      },
      dispatchEvent: () => true,
    },
  });

  try {
    updateReaderDisplayPreferences({
      textWidthPx: 1001,
      fontSizePx: 17,
      fontControlOpen: false,
      showLineBreaks: true,
    });
    const stored = values.get(READER_DISPLAY_PREFERENCES_STORAGE_KEY);
    assert.ok(stored);
    assert.deepEqual(parseReaderDisplayPreferences(stored), {
      textWidthPx: 992,
      fontSizePx: 17,
      fontControlOpen: false,
      showLineBreaks: true,
    });
    assert.equal(getReaderDisplayPreferencesSnapshot(), stored);
  } finally {
    if (originalWindow === undefined) {
      Reflect.deleteProperty(globalThis, 'window');
    } else {
      Object.defineProperty(globalThis, 'window', {
        configurable: true,
        value: originalWindow,
      });
    }
  }
});
