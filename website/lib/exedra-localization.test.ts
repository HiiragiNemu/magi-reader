import assert from 'node:assert/strict';
import test from 'node:test';

import {
  parseCachedExedraLocalization,
  parseExedraStoryIndex,
  parseExedraTxt,
  readExedraJapaneseText,
  serializeExedraSections,
} from './exedra-localization.ts';

test('Exedra asset reads stream with an abort signal and a fixed same-origin request', async () => {
  const received: Request[] = [];
  const text = await readExedraJapaneseText({
    request: new Request('https://reader.example/api/exedra'),
    env: {
      ASSETS: {
        fetch: async (request: Request) => {
          received.push(request);
          return new Response(new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(new TextEncoder().encode(
                '--- [Section 1] (Source: a.json) ---\n',
              ));
              controller.enqueue(new TextEncoder().encode('旁白：测试\n'));
              controller.close();
            },
          }));
        },
      },
    } as unknown as CloudflareEnv,
    entry: {
      id: 'test',
      category: 'exedra_main',
      folder: '测试',
      title: '测试',
      game: 'exedra',
      path_cn: '',
      path_jp: '/data/exedra_main/test/test_jp.txt',
      source_identity: 'exedra:1_Main:test',
    },
  });
  assert.match(text, /旁白：测试/u);
  assert.equal(received.length, 1);
  assert.equal(new URL(received[0]!.url).origin, 'https://reader.example');
  assert.ok(received[0]!.signal instanceof AbortSignal);
});

test('Exedra runtime catalog accepts exact trusted source identities', () => {
  const stories = parseExedraStoryIndex([
    {
      id: 'exedra_character_character_iroha_1234567890',
      category: 'exedra_character',
      folder: '环彩羽',
      title: '角色剧情',
      game: 'exedra',
      path_cn: '',
      path_jp: '/data/exedra_character/character_iroha/character_iroha_jp.txt',
      source_identity: 'exedra:3_Character:character_iroha',
    },
    {
      id: '310011',
      category: 'character_story',
      folder: '环彩羽',
      title: '魔法纪录剧情',
      game: 'magireco',
      path_cn: '/data/character_story/a_cn.txt',
      path_jp: '/data/character_story/a_jp.txt',
      source_identity: 'character_story/a',
    },
  ]);
  assert.equal(stories.length, 1);
  assert.equal(stories[0].source_identity, 'exedra:3_Character:character_iroha');
});

test('Exedra runtime catalog rejects a non-data Japanese path', () => {
  assert.throws(() => parseExedraStoryIndex([
    {
      id: 'exedra_character_character_iroha_1234567890',
      category: 'exedra_character',
      folder: '环彩羽',
      title: '',
      game: 'exedra',
      path_cn: '',
      path_jp: 'https://attacker.invalid/story.txt',
      source_identity: 'exedra:3_Character:character_iroha',
    },
  ]), /剧情目录条目无效/u);
});

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
