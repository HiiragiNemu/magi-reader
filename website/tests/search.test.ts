import assert from 'node:assert/strict';
import test from 'node:test';

import {
  extractSearchSnippet,
  findNormalizedRanges,
  normalizeSearchText,
  splitHighlightSegments,
} from '../lib/search.ts';

test('normalizes Chinese, Japanese kana, Latin text, digits and punctuation', () => {
  assert.equal(
    normalizeSearchText(' 魔法☆少女・まどか Magia-123 '),
    '魔法少女まどかmagia123',
  );
});

test('maps a punctuation-insensitive match back to original text', () => {
  const text = 'それは「魔法・少女」まどかの物語';
  assert.deepEqual(findNormalizedRanges(text, '魔法少女'), [{
    start: text.indexOf('魔'),
    end: text.indexOf('」'),
  }]);

  const highlighted = splitHighlightSegments(text, '魔法少女');
  assert.equal(highlighted.filter(segment => segment.highlight)[0].text, '魔法・少女');
});

test('extracts readable snippets for kana searches', () => {
  assert.equal(
    extractSearchSnippet('前文です。鹿目まどかが登場します。後文です。', 'まどか', 4),
    'す。鹿目まどかが登場し',
  );
});
