import assert from 'node:assert/strict';
import test from 'node:test';

import {
  parseCachedExedraLocalization,
  parseExedraTxt,
  serializeExedraSections,
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
  assert.deepEqual(
    sections[0].blocks.map(block => block.kind),
    ['dialogue', 'narration'],
  );
  assert.equal(sections[1].blocks[0].speaker, '七海 やちよ');
  assert.equal(parseExedraTxt(serializeExedraSections(sections)).length, 2);
});

test('Exedra TXT parser rejects skipped section numbers', () => {
  assert.throws(() => parseExedraTxt([
    '--- [Section 1] (Source: a.json) ---',
    '旁白：第一节',
    '--- [Section 3] (Source: b.json) ---',
    '旁白：错误编号',
  ].join('\n')), /Section 编号不连续/u);
});

test('trusted cache accepts Wiki records and rejects legacy machine records', () => {
  const base = {
    version: 1,
    story_id: 'exedra_character_iroha_test',
    source_identity: 'exedra:3_Character:character_iroha',
    source_url: 'https://exedra.wiki/wiki/:Iroha_Tamaki/Story/Chinese',
    generated_at: '2026-07-28T00:00:00.000Z',
    jp_sha256: 'a'.repeat(64),
    cn_sha256: 'b'.repeat(64),
    text: '--- [Section 1] (Source: a.json) ---\n環 いろは：你好\n',
  };
  assert.ok(parseCachedExedraLocalization(JSON.stringify({
    ...base,
    provenance: 'exedra_wiki_human',
  })));
  assert.equal(parseCachedExedraLocalization(JSON.stringify({
    ...base,
    provenance: 'machine_translation',
  })), null);
});
