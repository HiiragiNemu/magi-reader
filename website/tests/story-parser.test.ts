import assert from 'node:assert/strict';
import test from 'node:test';

import {
  alignStoryLines,
  makeSectionAnchorId,
  parseStoryContent,
  serializeStoryLine,
} from '../lib/story-parser.ts';

test('parses Exedra spreadsheet JSON with dynamic headers and preserves text', () => {
  const input = JSON.stringify({
    bookTitle: '鹿目まどか_魔法少女_覚醒ボイス_1',
    sheetList: [{
      sheetName: 'script',
      headerRow: {
        cellList: [
          'ActionType',
          'Comment',
          'Name',
          'Motion',
          'FaceType',
          'Variable',
        ],
      },
      contentRowList: [
        { rowNumber: 2, cellList: ['Talk', '一行目\n二行目', '', '', '', ''] },
        { rowNumber: 3, cellList: ['OnlyText', '無署名の表示文', '', '', '', ''] },
        { rowNumber: 4, cellList: ['PlayVoice', '演出用ボイス注記', 'キュゥべえ', '', '', ''] },
        { rowNumber: 5, cellList: ['Wait', '内部コメント', '', '', '', '100'] },
      ],
    }],
  });

  const result = parseStoryContent(input, { filename: 'cv_100101_test.json' });

  assert.equal(result.format, 'exedra-json');
  assert.equal(result.title, '鹿目まどか_魔法少女_覚醒ボイス_1');
  assert.deepEqual(
    result.lines.map(line => [line.speaker, line.text, line.kind, line.sourceRow]),
    [
      ['鹿目まどか', '一行目\n二行目\n無署名の表示文', 'dialogue', 2],
    ],
  );
});

test('uses Exedra position state and non-numeric AssetID as speaker fallbacks', () => {
  const input = JSON.stringify({
    bookTitle: 'チュートリアル',
    sheetList: [{
      sheetName: 'script',
      headerRow: {
        cellList: ['ActionType', 'Name', 'Comment', 'AssetID', 'PositionID'],
      },
      contentRowList: [
        { rowNumber: 2, cellList: ['Put', '鹿目まどか', '', '100101', 'Left_2P'] },
        { rowNumber: 3, cellList: ['Talk', '', '位置から復元', '', 'Left_2P'] },
        { rowNumber: 4, cellList: ['Put', '', '', '801400', 'Left_2P'] },
        { rowNumber: 5, cellList: ['Talk', '', '空のPutで古い名前を消す', '', 'Left_2P'] },
        { rowNumber: 6, cellList: ['Talk', '', 'AssetIDから復元', 'A-Q', 'Right'] },
        { rowNumber: 7, cellList: ['Narration', '', '位置があっても旁白', '', 'Left_2P'] },
      ],
    }],
  });

  const result = parseStoryContent(input, { filename: 'world_dialogue.json' });
  assert.deepEqual(
    result.lines.map(line => line.speaker),
    ['鹿目まどか', '旁白', 'A-Q', '旁白'],
  );
});

test('prefers Exedra AssetID name history over normalized position collisions', () => {
  const input = JSON.stringify({
    bookTitle: '針の魔女',
    sheetList: [{
      sheetName: 'script',
      headerRow: {
        cellList: ['ActionType', 'Name', 'Comment', 'AssetID', 'PositionID'],
      },
      contentRowList: [
        { rowNumber: 2, cellList: ['Put', '生徒Ａ', '', '800101', 'Left_2P'] },
        { rowNumber: 3, cellList: ['Put', '生徒Ｂ', '', '800200', 'Right_2P'] },
        { rowNumber: 4, cellList: ['Put', '使い魔', '', 'adv_chara_03_007', 'Left'] },
        { rowNumber: 5, cellList: ['Talk', '', 'キャー！', '800101', 'Left_2P'] },
        { rowNumber: 6, cellList: ['Talk', '', '助けて！', '800200', 'Right_2P'] },
      ],
    }],
  });

  const result = parseStoryContent(input, { filename: 'main_hari_13.json' });
  assert.deepEqual(
    result.lines.map(line => [line.speaker, line.text]),
    [
      ['生徒Ａ', 'キャー！'],
      ['生徒Ｂ', '助けて！'],
    ],
  );
});

test('parses Magia Record object and array story variants', () => {
  const objectResult = parseStoryContent(JSON.stringify({
    story: {
      group_1: [
        { chara: [{ id: 1001, pos: 0 }], nameLeft: '環いろは' },
        { textLeft: 'こんにちは[br]世界' },
        { select: [{ textSelect: '進む', group: 'group_2' }] },
      ],
      group_2: [
        { narration: '[textBlack:記録]' },
      ],
    },
  }), { filename: '310011-1.json' });

  assert.equal(objectResult.format, 'magireco-json');
  assert.equal(objectResult.lines[1].speaker, '環いろは');
  assert.equal(objectResult.lines[1].text, 'こんにちは\n世界');
  assert.equal(objectResult.lines[2].choiceTargetId, '2');
  assert.equal(objectResult.lines[3].headerBranch, '2');
  assert.equal(objectResult.lines[4].text, '<black>記録</black>');

  const arrayResult = parseStoryContent(JSON.stringify({
    story: [{ nameCenter: '旁白役', textCenter: '配列形式' }],
  }), { filename: '400000-0.json' });
  assert.equal(arrayResult.lines[1].text, '配列形式');
});

test('keeps every dialogue when a Magia Record item contains multiple positions', () => {
  const result = parseStoryContent(JSON.stringify({
    story: {
      group_1: [{
        nameLeft: '左の子',
        textLeft: '左の台詞',
        nameRight: '右の子',
        textRight: '右の台詞',
      }],
    },
  }), { filename: '310371-3.json' });

  assert.deepEqual(
    result.lines.slice(1).map(line => [line.speaker, line.text, line.position]),
    [
      ['左の子', '左の台詞', 'left'],
      ['右の子', '右の台詞', 'right'],
    ],
  );
});

test('supports Magia Record Fnarration casing and remembered narrator names', () => {
  const result = parseStoryContent(JSON.stringify({
    story: {
      group_1: [
        { nameFnarration: '愛生まばゆ', Fnarration: '最初の独白' },
        { Fnarration: '続く独白' },
      ],
    },
  }), { filename: '320091-1.json' });

  assert.deepEqual(
    result.lines.slice(1).map(line => [line.speaker, line.text, line.kind]),
    [
      ['愛生まばゆ', '最初の独白\n続く独白', 'fnarration'],
    ],
  );
});

test('supports the rare Magia Record top-level text field', () => {
  const result = parseStoryContent(JSON.stringify({
    story: { group_1: [{ text: '％＆｜￥・＃＃＄＋＠！！' }] },
  }), { filename: '330041-1.json' });
  assert.deepEqual(
    [result.lines[1].speaker, result.lines[1].text, result.lines[1].position],
    ['旁白', '％＆｜￥・＃＃＄＋＠！！', 'center'],
  );
});

test('does not expose Exedra resource AssetIDs as speaker names', () => {
  const input = JSON.stringify({
    bookTitle: '胚胎之夜',
    sheetList: [{
      sheetName: 'script',
      headerRow: {
        cellList: ['ActionType', 'Name', 'Comment', 'AssetID', 'PositionID'],
      },
      contentRowList: [{
        rowNumber: 249,
        cellList: ['Talk', '', '｜!!*･;｡ﾟ(◎(工)◎)ﾟ｡;･*!!｜', 'adv_chara_01_023', 'Center'],
      }],
    }],
  });
  const result = parseStoryContent(input, { filename: 'main_embryoeve2_6.json' });
  assert.equal(result.lines[0].speaker, '旁白');
  assert.equal(result.lines[0].kind, 'narration');
});

test('keeps old TXT and extended @S0 formats compatible', () => {
  const input = [
    '\uFEFF--- [Section 010] (Source: 901101-010.json) ---',
    '鹿目まどか: 一行目',
    '鹿目まどか: 二行目',
    '@S0\t{"kind":"narration","speaker":"旁白","text":"A\\\\nB","command":"narration","position":"center"}',
    '选项: 【继续】→ group_2',
  ].join('\r\n');

  const result = parseStoryContent(input, { filename: 'legacy.txt' });
  assert.equal(result.format, 'scene0-text');
  assert.equal(result.lines[0].headerId, makeSectionAnchorId('901101-010', '010'));
  assert.equal(result.lines[1].text, '一行目\n二行目');
  assert.equal(result.lines[2].text, 'A\nB');
  assert.equal(result.lines[2].position, 'center');
  assert.equal(result.lines[3].choiceTargetId, '2');
  assert.match(serializeStoryLine(result.lines[2]), /^@S0\t/);
});

test('treats Exedra Narration labels as narration blocks', () => {
  const result = parseStoryContent([
    '--- [Section 1] (Source: main_demo_1.json) ---',
    'Narration: 〈新西区〉',
    'Narration: 风吹过街道',
    '環いろは: 到着したよ',
  ].join('\n'));

  assert.deepEqual(
    result.lines.map(line => [line.speaker, line.text, line.kind]),
    [
      ['', '--- [Section 1] (Source: main_demo_1.json) ---', undefined],
      ['旁白', '〈新西区〉\n风吹过街道', 'narration'],
      ['環いろは', '到着したよ', 'dialogue'],
    ],
  );
});

test('preserves parenthesized Exedra source filenames in section anchors', () => {
  const sourceId = 'main_nightmare_7 (2)';
  const result = parseStoryContent(
    '--- [Section 8] (Source: main_nightmare_7 (2).json) ---',
  );

  assert.equal(result.lines[0].headerSourceId, sourceId);
  assert.equal(result.lines[0].headerId, makeSectionAnchorId(sourceId, '8'));
});

test('attaches an exact Exedra cv cue from its section source without changing TXT', () => {
  const content = [
    '--- [Section 1] (Source: cv_100101_other_story_01.json) ---',
    '环彩羽: 我会继续前进。',
    '小丘比: 下一行不应重复整段音频按钮。',
  ].join('\n');
  const result = parseStoryContent(content);

  assert.equal(result.lines[1].audioCueId, 'cv_100101_other_story_01');
  assert.equal(result.lines[2].audioCueId, undefined);
  assert.equal(serializeStoryLine(result.lines[1]), '环彩羽: 我会继续前进。');
});

test('attaches a Magireco general voice cue from its visible metadata tag', () => {
  const result = parseStoryContent([
    '--- [Section 1] (Source: 303100.json) ---',
    '绫野梨花: 【vo_char_3031_00_01｜19秒】我是绫野梨花！',
  ].join('\n'));

  assert.equal(result.lines[1].audioCueId, 'vo_char_3031_00_01');
});

test('aligns strictly by utterance-block index regardless of text length', () => {
  const cn = parseStoryContent([
    '彩羽: 我最近总是做同一个梦。',
    '八千代: 怎么了？',
  ].join('\n')).lines;
  const jp = parseStoryContent([
    'いろは: 最近、私は同じ夢を見る\\n誰か知らない女の子が病室にいて\\n私は画面の向こうから眺めているだけだから',
    'やちよ: どうしたの？',
  ].join('\n')).lines;

  const aligned = alignStoryLines(cn, jp);
  assert.equal(aligned.length, 2);
  assert.equal(aligned[0].cn?.speaker, '彩羽');
  assert.equal(aligned[0].jp?.speaker, 'いろは');
  assert.equal(aligned[0].jp?.text.split('\n').length, 3);
  assert.equal(aligned[1].cn?.speaker, '八千代');
  assert.equal(aligned[1].jp?.speaker, 'やちよ');
});

test('merges adjacent same-speaker rows into one block and keeps tail-only blocks', () => {
  const cn = parseStoryContent([
    '彩羽: 第一段',
    '彩羽: 第二段',
    '鹤乃: 中文尾行',
  ].join('\n')).lines;
  const jp = parseStoryContent([
    'いろは: 一つ目\\n同じ吹き出しの改行',
    'いろは: 二つ目',
  ].join('\n')).lines;

  assert.equal(cn.length, 2);
  assert.equal(jp.length, 1);
  assert.equal(cn[0].text, '第一段\n第二段');
  assert.equal(jp[0].text, '一つ目\n同じ吹き出しの改行\n二つ目');

  const aligned = alignStoryLines(cn, jp);
  assert.deepEqual(
    aligned.map(row => [row.cn?.speaker, row.jp?.speaker]),
    [
      ['彩羽', 'いろは'],
      ['鹤乃', undefined],
    ],
  );
});

test('rejects malformed and unknown JSON with a useful error', () => {
  assert.throws(
    () => parseStoryContent('{broken', { filename: 'broken.json' }),
    /JSON 解析失败/,
  );
  assert.throws(
    () => parseStoryContent('{"unrelated":true}', { filename: 'unknown.json' }),
    /无法识别/,
  );
});

test('plain TXT serialization preserves embedded line breaks on round trip', () => {
  const line = {
    speaker: '鹿目まどか',
    text: '一行目\n二行目',
  };
  const serialized = serializeStoryLine(line);
  assert.equal(serialized, '鹿目まどか: 一行目\\n二行目');
  assert.deepEqual(
    parseStoryContent(serialized, { mergeConsecutiveTextLines: false }).lines
      .map(item => [item.speaker, item.text]),
    [['鹿目まどか', '一行目\n二行目']],
  );
});

test('does not mistake episode labels or timestamps for TXT speakers', () => {
  const result = parseStoryContent([
    '第30話：トリックアンドトリート',
    '12:30',
    '八雲みたま: 本当の台詞',
  ].join('\n'), { mergeConsecutiveTextLines: false });

  assert.deepEqual(
    result.lines.map(line => [line.speaker, line.text]),
    [
      ['旁白', '第30話：トリックアンドトリート'],
      ['旁白', '12:30'],
      ['八雲みたま', '本当の台詞'],
    ],
  );
});
