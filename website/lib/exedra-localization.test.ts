import assert from 'node:assert/strict';
import test from 'node:test';

import {
  augmentExedraCnPaths,
  exedraDynamicCnPath,
  parseExedraTxt,
} from './exedra-localization.ts';

test('Exedra TXT parser preserves exact section order and dialogue kinds', () => {
  const sections = parseExedraTxt([
    '--- [Section 1] (Source: character_iroha_1.json) ---',
    '環 いろは：わたしは環いろはです',
    'ナレーション：夜が明ける',
    '',
    '--- [Section 2] (Source: character_iroha_2.json) ---',
    '七海 やちよ：行きましょう',
  ].join('\n'));
  assert.equal(sections.length, 2);
  assert.equal(sections[0].number, 1);
  assert.equal(sections[0].source, 'character_iroha_1.json');
  assert.deepEqual(sections[0].blocks.map(block => block.kind), ['dialogue', 'narration']);
  assert.equal(sections[1].blocks[0].speaker, '七海 やちよ');
});

test('Exedra TXT parser rejects skipped section numbers', () => {
  assert.throws(() => parseExedraTxt([
    '--- [Section 1] (Source: a.json) ---',
    '旁白：第一节',
    '--- [Section 3] (Source: b.json) ---',
    '旁白：错误编号',
  ].join('\n')), /Section 编号不连续/u);
});

test('dynamic CN path is added only when Exedra has JP but no local CN', () => {
  const values = augmentExedraCnPaths([
    {
      id: 'exedra_character_iroha_test',
      game: 'exedra',
      path_jp: '/data/exedra_character/iroha_jp.txt',
      path_cn: '',
      has_cn: false,
      percent: 0,
    },
    {
      id: 'exedra_character_local',
      game: 'exedra',
      path_jp: '/data/exedra_character/local_jp.txt',
      path_cn: '/data/exedra_character/local_cn.txt',
      has_cn: true,
      percent: 100,
    },
    {
      id: '310011',
      game: 'magireco',
      path_jp: '/data/character_story/a_jp.txt',
      path_cn: '/data/character_story/a_cn.txt',
      has_cn: true,
      percent: 100,
    },
  ]);
  assert.equal(values[0].path_cn, exedraDynamicCnPath('exedra_character_iroha_test'));
  assert.equal(values[0].localization_dynamic, true);
  assert.equal(values[1].path_cn, '/data/exedra_character/local_cn.txt');
  assert.equal(values[1].localization_dynamic, undefined);
  assert.equal(values[2].path_cn, '/data/character_story/a_cn.txt');
});
