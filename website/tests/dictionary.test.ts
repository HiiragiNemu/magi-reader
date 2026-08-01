import assert from 'node:assert/strict';
import test from 'node:test';

import {
  characterFolderColorFor,
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
  assert.equal(translateSpeakerName('日暮ふうか'), '日暮风花');
  assert.equal(translateSpeakerName('夜明すみれ'), '夜明堇');
  assert.equal(translateSpeakerName('まどか先輩'), '小圆前辈');
  assert.equal(translateSpeakerName('A-Q'), 'A-Q');
});

test('reuses established speaker colors without inventing unknown colors', () => {
  assert.equal(speakerColorFor('環　いろは'), '#F57689');
  assert.equal(speakerColorFor('环彩羽'), '#F57689');
  assert.equal(speakerColorFor('常盘七香'), '#FF5B7E');
  assert.equal(speakerColorFor('日暮风花'), '#6C6299');
  assert.equal(speakerColorFor('夜明すみれ'), '#B96AF1');
  assert.equal(speakerColorFor('小圆前辈'), '#FA71BD');
  assert.equal(speakerColorFor('A-Q'), undefined);
});

test('colors Magia Record and Exedra character folders from established names', () => {
  assert.equal(
    characterFolderColorFor(
      'character_story',
      '1001 - 环彩羽（環 いろは）',
    ),
    '#F57689',
  );
  assert.equal(
    characterFolderColorFor(
      'character_story',
      '1101 - 环彩羽（泳装ver.）（環 いろは（水着ver.））',
    ),
    '#F57689',
  );
  assert.equal(
    characterFolderColorFor('exedra_character', '水波玲奈（水波 レナ）'),
    '#9BDAEB',
  );
  assert.equal(
    characterFolderColorFor(
      'costume_story',
      '1001 - 环彩羽（環 いろは）',
    ),
    undefined,
  );
  assert.equal(
    characterFolderColorFor('character_story', '9999 - 未知角色（Unknown）'),
    undefined,
  );
});

test('treats inherited object keys as ordinary unknown speaker names', () => {
  for (const speaker of ['__proto__', 'constructor', 'toString']) {
    assert.equal(translateSpeakerName(speaker), speaker);
    assert.equal(speakerColorFor(speaker), undefined);
  }
});
