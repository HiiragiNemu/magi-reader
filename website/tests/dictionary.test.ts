import assert from 'node:assert/strict';
import test from 'node:test';

import {
  normalizeSpeakerName,
  speakerColorFor,
  translateSpeakerName,
} from '../app/config/dictionary.ts';

test('normalizes invisible source contamination without rewriting visible names', () => {
  assert.equal(normalizeSpeakerName('  みふゆの母\r'), 'みふゆの母');
  assert.equal(normalizeSpeakerName('\n'), '');
  assert.equal(normalizeSpeakerName('A-Q'), 'A-Q');
  assert.equal(normalizeSpeakerName('*UserName'), '*UserName');
});

test('translates only exact or unambiguous whitespace variants', () => {
  assert.equal(translateSpeakerName('環いろは'), '环彩羽');
  assert.equal(translateSpeakerName('環　いろは'), '环彩羽');
  assert.equal(translateSpeakerName('みふゆ\r'), '美冬');
  assert.equal(translateSpeakerName('夜明すみれ'), '夜明すみれ');
  assert.equal(translateSpeakerName('A-Q'), 'A-Q');
});

test('reuses established speaker colors without inventing unknown colors', () => {
  assert.equal(speakerColorFor('環　いろは'), '#F57689');
  assert.equal(speakerColorFor('环彩羽'), '#F57689');
  assert.equal(speakerColorFor('夜明すみれ'), undefined);
  assert.equal(speakerColorFor('A-Q'), undefined);
});

test('treats inherited object keys as ordinary unknown speaker names', () => {
  for (const speaker of ['__proto__', 'constructor', 'toString']) {
    assert.equal(translateSpeakerName(speaker), speaker);
    assert.equal(speakerColorFor(speaker), undefined);
  }
});
