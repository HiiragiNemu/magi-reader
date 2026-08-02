import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createEditedScenarioJsonDownload,
  createOriginalScenarioJsonDownload,
  scenarioJsonFilename,
  ScenarioJsonDownloadError,
} from './scenario-json-download.ts';
import { parseStoryContent, type StoryLine } from './story-parser.ts';

const magirecoDocument = {
  version: 3,
  story: {
    group_1: [
      {
        bg: 'bg_adv_11061.jpg',
        motion: 200,
        pos: 0,
        nameLeft: 'いろは',
        textLeft: '[chara:1001]こんにちは@世界',
      },
      {
        autoTurnLast: 0.2,
        select: [{ textSelect: '進む', group: 'group_2' }],
      },
    ],
    group_2: [
      {
        bgm: 'bgm01_anime03',
        nameNarration: '',
        narration: '[textBlack:記録]',
      },
    ],
  },
};

const exedraDocument = {
  origin: 0,
  bookTitle: 'テスト',
  sheetList: [{
    sheetName: 'script',
    headerRow: {
      rowNumber: 1,
      cellList: [
        'ActionType',
        'Name',
        'Comment',
        'AssetID',
        'PositionID',
        'Motion',
        'SoundFile',
      ],
    },
    contentRowList: [
      {
        rowNumber: 2,
        cellList: ['Put', '環いろは', '', 'adv_1001', 'Left', 'Idle', ''],
      },
      {
        rowNumber: 3,
        cellList: ['Talk', '環いろは', 'こんにちは', 'adv_1001', 'Left', 'Talk', 'cv_1'],
      },
      {
        rowNumber: 4,
        cellList: ['Narration', '', '風が吹く', '', '', '', ''],
      },
    ],
  }],
};

const cloneLines = (lines: readonly StoryLine[]): StoryLine[] =>
  lines.map(line => ({ ...line }));

const linesFrom = (document: unknown, filename: string): StoryLine[] =>
  parseStoryContent(JSON.stringify(document), {
    filename,
    mergeConsecutiveTextLines: false,
  }).lines;

const objectKeysShape = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map(objectKeysShape);
  if (typeof value === 'object' && value !== null) {
    return Object.fromEntries(
      Object.keys(value as Record<string, unknown>)
        .sort()
        .map(key => [
          key,
          objectKeysShape((value as Record<string, unknown>)[key]),
        ]),
    );
  }
  return typeof value;
};

test('original JP and CN exports are BOM-free UTF-8 JSON with stable filenames', async () => {
  const jp = createOriginalScenarioJsonDownload({
    sourceJson: `\uFEFF${JSON.stringify(magirecoDocument)}`,
    sourceFilename: '310011-1.json',
    storyId: '310011-1',
    language: 'jp',
  });
  const cn = createOriginalScenarioJsonDownload({
    sourceJson: JSON.stringify(exedraDocument),
    sourceFilename: 'character_iroha_1.json',
    storyId: 'character_iroha',
    language: 'cn',
  });

  assert.equal(jp.filename, '310011-1_jp.json');
  assert.equal(cn.filename, 'character_iroha_cn.json');
  assert.equal(jp.blob.type, 'application/json;charset=utf-8');
  const bytes = new Uint8Array(await jp.blob.arrayBuffer());
  assert.notDeepEqual(Array.from(bytes.subarray(0, 3)), [0xef, 0xbb, 0xbf]);
  assert.equal(new TextDecoder().decode(bytes), jp.json);
  assert.deepEqual(JSON.parse(jp.json), magirecoDocument);
  assert.deepEqual(JSON.parse(cn.json), exedraDocument);
});

test('edited Magia Record JSON changes only visible text/name cells', () => {
  const filename = '310011-1.json';
  const originalLines = linesFrom(magirecoDocument, filename);
  const edited = cloneLines(originalLines);
  const dialogue = edited.find(line => line.sourceCommand === 'textLeft');
  const choice = edited.find(line => line.isChoice);
  const narration = edited.find(line => line.sourceCommand === 'narration');
  assert.ok(dialogue && choice && narration);
  dialogue.text = '你好\n世界';
  dialogue.speaker = '环彩羽';
  choice.text = '【继续】';
  choice.choiceLabel = '继续';
  narration.text = '<black>记录</black>';

  const result = createEditedScenarioJsonDownload({
    sourceJson: JSON.stringify(magirecoDocument),
    sourceFilename: filename,
    storyId: '310011-1',
    editedLines: edited,
  });
  const output = JSON.parse(result.json) as typeof magirecoDocument;

  assert.equal(result.filename, '310011-1_edited_cn.json');
  assert.equal(result.changedTextFields, 4);
  assert.equal(output.story.group_1[0].textLeft, '[chara:1001]你好@世界');
  assert.equal(output.story.group_1[0].nameLeft, '环彩羽');
  const selection = output.story.group_1[1].select?.[0];
  assert.ok(selection);
  assert.equal(selection.textSelect, '继续');
  assert.equal(selection.group, 'group_2');
  assert.equal(output.story.group_2[0].narration, '[textBlack:记录]');
  assert.equal(output.story.group_1[0].bg, 'bg_adv_11061.jpg');
  assert.equal(output.story.group_1[0].motion, 200);
  assert.equal(output.story.group_1[0].pos, 0);
  assert.equal(output.story.group_2[0].bgm, 'bgm01_anime03');
  assert.deepEqual(objectKeysShape(output), objectKeysShape(magirecoDocument));
});

test('edited Exedra JSON changes only Comment cells and preserves playback columns', () => {
  const filename = 'character_iroha_1.json';
  const originalLines = linesFrom(exedraDocument, filename);
  const edited = cloneLines(originalLines);
  edited[0].text = '你好';
  edited[1].text = '风吹过街道';

  const result = createEditedScenarioJsonDownload({
    sourceJson: JSON.stringify(exedraDocument),
    sourceFilename: filename,
    storyId: 'character_iroha',
    editedLines: edited,
  });
  const output = JSON.parse(result.json) as typeof exedraDocument;
  const rows = output.sheetList[0].contentRowList;

  assert.equal(result.changedTextFields, 2);
  assert.equal(rows[1].cellList[2], '你好');
  assert.equal(rows[2].cellList[2], '风吹过街道');
  assert.deepEqual(rows[1].cellList.slice(0, 2), ['Talk', '環いろは']);
  assert.deepEqual(rows[1].cellList.slice(3), ['adv_1001', 'Left', 'Talk', 'cv_1']);
  assert.deepEqual(rows[0], exedraDocument.sheetList[0].contentRowList[0]);
  assert.deepEqual(objectKeysShape(output), objectKeysShape(exedraDocument));
});

test('edited JSON fails closed on count, branch, position and speaker mismatches', () => {
  const magiaFilename = '310011-1.json';
  const magiaLines = linesFrom(magirecoDocument, magiaFilename);
  assert.throws(
    () => createEditedScenarioJsonDownload({
      sourceJson: JSON.stringify(magirecoDocument),
      sourceFilename: magiaFilename,
      storyId: '310011-1',
      editedLines: magiaLines.slice(0, -1),
    }),
    (error: unknown) =>
      error instanceof ScenarioJsonDownloadError &&
      /结构不匹配/u.test(error.message),
  );

  const changedBranch = cloneLines(magiaLines);
  const branchHeader = changedBranch.find(line => line.headerBranch === '2');
  assert.ok(branchHeader);
  branchHeader.headerBranch = '9';
  assert.throws(
    () => createEditedScenarioJsonDownload({
      sourceJson: JSON.stringify(magirecoDocument),
      sourceFilename: magiaFilename,
      storyId: '310011-1',
      editedLines: changedBranch,
    }),
    /动作、位置、分支或来源结构/u,
  );

  const changedPosition = cloneLines(magiaLines);
  const positioned = changedPosition.find(line => line.position === 'left');
  assert.ok(positioned);
  positioned.position = 'right';
  assert.throws(
    () => createEditedScenarioJsonDownload({
      sourceJson: JSON.stringify(magirecoDocument),
      sourceFilename: magiaFilename,
      storyId: '310011-1',
      editedLines: changedPosition,
    }),
    /动作、位置、分支或来源结构/u,
  );

  const exedraFilename = 'character_iroha_1.json';
  const changedSpeaker = cloneLines(linesFrom(exedraDocument, exedraFilename));
  changedSpeaker[0].speaker = '错误角色';
  assert.throws(
    () => createEditedScenarioJsonDownload({
      sourceJson: JSON.stringify(exedraDocument),
      sourceFilename: exedraFilename,
      storyId: 'character_iroha',
      editedLines: changedSpeaker,
    }),
    /Exedra 说话人身份不可修改/u,
  );
});

test('context-derived speaker edits are rejected instead of adding schema fields', () => {
  const document = {
    story: {
      group_1: [
        { nameLeft: 'いろは', textLeft: '第一句' },
        { textLeft: '第二句' },
      ],
    },
  };
  const filename = '100101-1.json';
  const edited = cloneLines(linesFrom(document, filename));
  const second = edited.filter(line => line.sourceCommand === 'textLeft')[1];
  second.speaker = '新名字';

  assert.throws(
    () => createEditedScenarioJsonDownload({
      sourceJson: JSON.stringify(document),
      sourceFilename: filename,
      storyId: '100101-1',
      editedLines: edited,
    }),
    /不能在不改变 schema 的情况下写回/u,
  );
});

test('general-voice JSON without parser-mapped events reports an explicit error', () => {
  const document = {
    version: 3,
    story: {
      group_1: [{
        chara: [{
          id: 100100,
          voice: 'vo_char_1001_00_01',
          textHome: 'こんにちは',
        }],
      }],
    },
  };
  const filename = '100100.json';
  const lines = linesFrom(document, filename);
  assert.throws(
    () => createEditedScenarioJsonDownload({
      sourceJson: JSON.stringify(document),
      sourceFilename: filename,
      storyId: '100100',
      editedLines: lines,
    }),
    /需要提供未合并的 baselineLines/u,
  );
});

test('general-voice baseline maps only editable textHome while preserving playback data', () => {
  const document = {
    version: 3,
    story: {
      group_1: [{
        autoTurnFirst: 2.5,
        chara: [{
          id: 100100,
          pos: 1,
          motion: 200,
          voice: 'vo_char_1001_00_01',
          textHome: 'こんにちは@世界',
        }],
      }],
    },
  };
  const filename = '100100.json';
  const baseline = parseStoryContent([
    '--- [Section 1] (Source: 100100.json) ---',
    '环彩羽: 【vo_char_1001_00_01｜2.5秒】こんにちは／世界',
  ].join('\n'), {
    filename: '100100_cn.txt',
    mergeConsecutiveTextLines: false,
  }).lines;
  const edited = cloneLines(baseline);
  edited[1].text = '【vo_char_1001_00_01｜2.5秒】你好／世界';

  const result = createEditedScenarioJsonDownload({
    sourceJson: JSON.stringify(document),
    sourceFilename: filename,
    storyId: '100100',
    baselineLines: baseline,
    editedLines: edited,
  });
  const output = JSON.parse(result.json) as typeof document;
  const chara = output.story.group_1[0].chara[0];

  assert.equal(result.changedTextFields, 1);
  assert.equal(chara.textHome, '你好@世界');
  assert.equal(chara.voice, 'vo_char_1001_00_01');
  assert.equal(chara.motion, 200);
  assert.equal(chara.pos, 1);
  assert.equal(output.story.group_1[0].autoTurnFirst, 2.5);
  assert.deepEqual(objectKeysShape(output), objectKeysShape(document));

  const changedPrefix = cloneLines(baseline);
  changedPrefix[1].text = '【vo_char_1001_00_99｜2.5秒】你好／世界';
  assert.throws(
    () => createEditedScenarioJsonDownload({
      sourceJson: JSON.stringify(document),
      sourceFilename: filename,
      storyId: '100100',
      baselineLines: baseline,
      editedLines: changedPrefix,
    }),
    /语音资源或时长标签不可修改/u,
  );
});

test('general-voice missing subtitle inserts textHome without changing playback fields', () => {
  const document = {
    version: 3,
    story: {
      group_1: [{
        autoTurnFirst: 20.1,
        bg: 'keep-background.jpg',
        chara: [{
          id: 406200,
          pos: 1,
          motion: 200,
          face: 'keep.exp.json',
          voice: 'vo_char_4062_00_01',
        }],
      }],
    },
  };
  const filename = '406200.json';
  const baseline = parseStoryContent([
    '--- [Section 1] (Source: 406200.json) ---',
    '井之上泷奈: 【vo_char_4062_00_01｜20.1秒】',
  ].join('\n'), {
    filename: '406200_cn.txt',
    mergeConsecutiveTextLines: false,
  }).lines;
  const edited = cloneLines(baseline);
  edited[1].text = '【vo_char_4062_00_01｜20.1秒】这是新增的中文字幕';

  const result = createEditedScenarioJsonDownload({
    sourceJson: JSON.stringify(document),
    sourceFilename: filename,
    storyId: '406200',
    baselineLines: baseline,
    editedLines: edited,
  });
  const output = JSON.parse(result.json) as typeof document & {
    story: { group_1: Array<{ chara: Array<{ textHome?: string }> }> };
  };
  const chara = output.story.group_1[0].chara[0];
  assert.equal(result.changedTextFields, 1);
  assert.equal(chara.textHome, '这是新增的中文字幕');
  assert.equal(chara.voice, 'vo_char_4062_00_01');
  assert.equal(chara.motion, 200);
  assert.equal(chara.face, 'keep.exp.json');
  assert.equal(output.story.group_1[0].autoTurnFirst, 20.1);
  assert.equal(output.story.group_1[0].bg, 'keep-background.jpg');

  const normalizedOutput = structuredClone(output);
  delete normalizedOutput.story.group_1[0].chara[0].textHome;
  assert.deepEqual(normalizedOutput, document);

  const changedSpeaker = cloneLines(baseline);
  changedSpeaker[1].speaker = '错误角色';
  changedSpeaker[1].text = '【vo_char_4062_00_01｜20.1秒】字幕';
  assert.throws(
    () => createEditedScenarioJsonDownload({
      sourceJson: JSON.stringify(document),
      sourceFilename: filename,
      storyId: '406200',
      baselineLines: baseline,
      editedLines: changedSpeaker,
    }),
    /角色名/u,
  );
});

test('general-voice duo subtitle is one row and synchronizes every voice chara', () => {
  const document = {
    version: 3,
    story: {
      group_1: [{
        autoTurnFirst: 2,
        chara: [
          { id: 111801, voice: 'vo_duo_01', textHome: '旧字幕', motion: 100 },
          { id: 111802, voice: 'vo_duo_01', textHome: '旧字幕', motion: 200 },
        ],
      }],
    },
  };
  const baseline = parseStoryContent([
    '--- [Section 1] (Source: 111800.json) ---',
    '天音姐妹: 【vo_duo_01｜2秒】旧字幕',
  ].join('\n'), {
    filename: '111800_cn.txt',
    mergeConsecutiveTextLines: false,
  }).lines;
  const edited = cloneLines(baseline);
  edited[1].text = '【vo_duo_01｜2秒】同步后的字幕';

  const result = createEditedScenarioJsonDownload({
    sourceJson: JSON.stringify(document),
    sourceFilename: '111800.json',
    storyId: '111800',
    baselineLines: baseline,
    editedLines: edited,
  });
  const output = JSON.parse(result.json) as typeof document;

  assert.equal(result.changedTextFields, 2);
  assert.equal(output.story.group_1[0].chara[0].textHome, '同步后的字幕');
  assert.equal(output.story.group_1[0].chara[1].textHome, '同步后的字幕');
  assert.equal(output.story.group_1[0].chara[0].motion, 100);
  assert.equal(output.story.group_1[0].chara[1].motion, 200);
});

test('general-voice missing duo subtitle inserts all mirrors and conflicts fail closed', () => {
  const missing = {
    version: 3,
    story: {
      group_1: [{
        chara: [
          { id: 111801, voice: 'vo_duo_02' },
          { id: 111802, voice: 'vo_duo_02' },
        ],
      }],
    },
  };
  const baseline = parseStoryContent([
    '--- [Section 1] (Source: 111800.json) ---',
    '天音姐妹: 【vo_duo_02｜2秒】',
  ].join('\n'), {
    filename: '111800_cn.txt',
    mergeConsecutiveTextLines: false,
  }).lines;
  const edited = cloneLines(baseline);
  edited[1].text = '【vo_duo_02｜2秒】补充字幕';
  const result = createEditedScenarioJsonDownload({
    sourceJson: JSON.stringify(missing),
    sourceFilename: '111800.json',
    storyId: '111800',
    baselineLines: baseline,
    editedLines: edited,
  });
  const output = JSON.parse(result.json) as typeof missing & {
    story: { group_1: Array<{ chara: Array<{ textHome?: string }> }> };
  };
  assert.equal(result.changedTextFields, 2);
  assert.equal(output.story.group_1[0].chara[0].textHome, '补充字幕');
  assert.equal(output.story.group_1[0].chara[1].textHome, '补充字幕');

  const conflict = structuredClone(missing) as typeof missing & {
    story: { group_1: Array<{ chara: Array<{ textHome?: string }> }> };
  };
  conflict.story.group_1[0].chara[0].textHome = '字幕甲';
  conflict.story.group_1[0].chara[1].textHome = '字幕乙';
  assert.throws(
    () => createEditedScenarioJsonDownload({
      sourceJson: JSON.stringify(conflict),
      sourceFilename: '111800.json',
      storyId: '111800',
      baselineLines: baseline,
      editedLines: edited,
    }),
    /内容冲突/u,
  );
});

test('filename normalization is deterministic and never includes a path', () => {
  assert.equal(
    scenarioJsonFilename(' ../角色:1001? ', 'edited_cn'),
    '角色-1001_edited_cn.json',
  );
});
