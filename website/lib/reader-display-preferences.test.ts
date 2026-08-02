import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_READER_TEXT_WIDTH,
  READER_DISPLAY_PREFERENCES_STORAGE_KEY,
  READER_TEXT_WIDTH_MAX,
  READER_TEXT_WIDTH_MIN,
  getReaderDisplayPreferencesSnapshot,
  parseReaderDisplayPreferences,
  updateReaderDisplayPreferences,
} from './reader-display-preferences.ts';

test('reader display preferences keep the current 768px width as the safe default', () => {
  assert.deepEqual(parseReaderDisplayPreferences(null), {
    textWidthPx: DEFAULT_READER_TEXT_WIDTH,
    showLineBreaks: false,
  });
  assert.deepEqual(parseReaderDisplayPreferences('{broken'), {
    textWidthPx: DEFAULT_READER_TEXT_WIDTH,
    showLineBreaks: false,
  });
});

test('reader display preferences clamp and snap persisted widths', () => {
  assert.deepEqual(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 100, showLineBreaks: true }),
    ),
    { textWidthPx: READER_TEXT_WIDTH_MIN, showLineBreaks: true },
  );
  assert.deepEqual(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 5000, showLineBreaks: false }),
    ),
    { textWidthPx: READER_TEXT_WIDTH_MAX, showLineBreaks: false },
  );
  assert.equal(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 783, showLineBreaks: true }),
    ).textWidthPx,
    768,
  );
});

test('reader display preferences accept only an explicit boolean marker choice', () => {
  assert.equal(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 768, showLineBreaks: 'true' }),
    ).showLineBreaks,
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
      showLineBreaks: true,
    });
    const stored = values.get(READER_DISPLAY_PREFERENCES_STORAGE_KEY);
    assert.ok(stored);
    assert.deepEqual(parseReaderDisplayPreferences(stored), {
      textWidthPx: 992,
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
