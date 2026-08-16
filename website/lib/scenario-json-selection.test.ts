import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyScenarioJsonUploadToAggregate,
  buildScenarioJsonSourceOptions,
  mapAggregateEditsToScenarioJson,
  ScenarioJsonSelectionError,
} from './scenario-json-selection.ts';
import { createEditedScenarioJsonDownload } from './scenario-json-download.ts';
import { parseStoryContent, type StoryLine } from './story-parser.ts';

const parseTxt = (value: string): StoryLine[] =>
  parseStoryContent(value, {
    filename: 'aggregate_cn.txt',
    mergeConsecutiveTextLines: false,
  }).lines;

const exedraJson = (first: string, second: string) => JSON.stringify({
  bookTitle: '鹿目まどか_voice',
  sheetList: [{
    sheetName: 'script',
    headerRow: {
      cellList: [
        'ActionType',
        'Name',
        'Comment',
        'AssetID',
        'PositionID',
        'Motion',
      ],
    },
    contentRowList: [
      {
        rowNumber: 2,
        cellList: ['Put', '鹿目まどか', '', 'madoka', 'Left', 'Idle'],
      },
      {
        rowNumber: 3,
        cellList: ['Talk', '', first, 'madoka', 'Left', 'Talk'],
      },
      {
        rowNumber: 4,
        cellList: ['Talk', '', second, 'madoka', 'Left', 'Talk'],
      },
    ],
  }],
});

test('source options merge JP/CN indexes and show exact Section filenames', () => {
  const cnLines = parseTxt([
    '--- [Section 1] (Source: story-1.json) ---',
    '角色: 中文',
    '--- [Section 2] (Source: story-2.json) ---',
    '角色: 中文二',
  ].join('\n'));
  const options = buildScenarioJsonSourceOptions({
    story: {
      id: 'story',
      category: 'main_story',
      folder: 'fixture',
      percent: 100,
      has_cn: true,
      has_jp: true,
      json_sources_cn: [
        'magireco-translate-data-master/Scenarios_full/main/story-1.json',
      ],
      json_sources_jp: [
        'magireco-source-master/Scenarios_full/main/story-1.json',
        'magireco-source-master/Scenarios_full/main/story-2.json',
      ],
    },
    cnLines,
    jpLines: [],
  });
  assert.deepEqual(
    options.map(option => ({
      filename: option.filename,
      cnIndex: option.cnIndex,
      jpIndex: option.jpIndex,
      sections: option.sections,
    })),
    [
      {
        filename: 'story-1.json',
        cnIndex: 0,
        jpIndex: 0,
        sections: ['1'],
      },
      {
        filename: 'story-2.json',
        cnIndex: undefined,
        jpIndex: 1,
        sections: ['2'],
      },
    ],
  );
  assert.match(options[0].label, /第 1 节.*story-1\.json/u);
});

test('Japanese Exedra structure can safely receive current Chinese event rows', () => {
  const filename = 'cv_100101_other_story_01.json';
  const sourceJson = exedraJson('こんにちは', 'またね');
  const jpLines = parseTxt([
    `--- [Section 1] (Source: ${filename}) ---`,
    '鹿目まどか: こんにちは',
    '鹿目まどか: またね',
  ].join('\n'));
  const cnLines = parseTxt([
    `--- [Section 1] (Source: ${filename}) ---`,
    '鹿目まどか: 你好',
    '鹿目まどか: 再见',
  ].join('\n'));
  const edited = cnLines.map(line => ({ ...line }));
  edited[2].text = '下次见';

  const mapped = mapAggregateEditsToScenarioJson({
    sourceJson,
    sourceFilename: filename,
    aggregateSourceBaselineLines: jpLines,
    aggregateEditingBaselineLines: cnLines,
    aggregateEditedLines: edited,
  });
  assert.deepEqual(
    mapped.editedLines
      .filter(line => !line.isHeader)
      .map(line => line.speaker),
    ['鹿目圆', '鹿目圆'],
  );
  const download = createEditedScenarioJsonDownload({
    sourceJson,
    sourceFilename: filename,
    storyId: 'voice',
    editedLines: mapped.editedLines,
  });
  const output = JSON.parse(download.json) as {
    sheetList: Array<{
      contentRowList: Array<{ cellList: string[] }>;
    }>;
  };
  const rows = output.sheetList[0].contentRowList;
  assert.equal(rows[0].cellList[1], '鹿目圆');
  assert.equal(rows[1].cellList[1], '鹿目圆');
  assert.equal(rows[2].cellList[1], '鹿目圆');
  assert.equal(rows[1].cellList[2], '你好');
  assert.equal(rows[2].cellList[2], '下次见');
  assert.deepEqual(rows[1].cellList.slice(3), ['madoka', 'Left', 'Talk']);
});

test('mapping rejects merged or count-mismatched aggregate edits', () => {
  const filename = 'cv_100101_other_story_01.json';
  const sourceJson = exedraJson('一', '二');
  const unmerged = parseTxt([
    `--- [Section 1] (Source: ${filename}) ---`,
    '鹿目まどか: 一',
    '鹿目まどか: 二',
  ].join('\n'));
  const merged = parseStoryContent([
    `--- [Section 1] (Source: ${filename}) ---`,
    '鹿目まどか: 一',
    '鹿目まどか: 二',
  ].join('\n'), {
    filename: 'aggregate_cn.txt',
    mergeConsecutiveTextLines: true,
  }).lines;
  assert.throws(
    () => mapAggregateEditsToScenarioJson({
      sourceJson,
      sourceFilename: filename,
      aggregateSourceBaselineLines: unmerged,
      aggregateEditingBaselineLines: unmerged,
      aggregateEditedLines: merged,
    }),
    error =>
      error instanceof ScenarioJsonSelectionError &&
      /行数/u.test(error.message),
  );
});

test('uploaded JSON imports only editable event text into the selected aggregate', () => {
  const filename = 'cv_100101_other_story_01.json';
  const sourceJson = exedraJson('一', '二');
  const uploadedJson = exedraJson('中文一', '中文二');
  const aggregate = parseTxt([
    `--- [Section 1] (Source: ${filename}) ---`,
    '鹿目まどか: 一',
    '鹿目まどか: 二',
    '--- [Section 2] (Source: untouched.json) ---',
    '旁白: 保持不变',
  ].join('\n'));
  const imported = applyScenarioJsonUploadToAggregate({
    sourceJson,
    uploadedJson,
    sourceFilename: filename,
    aggregateEditingBaselineLines: aggregate,
    aggregateCurrentEditedLines: aggregate,
  });
  assert.equal(imported[1].speaker, '鹿目圆');
  assert.equal(imported[2].speaker, '鹿目圆');
  assert.equal(imported[1].text, '中文一');
  assert.equal(imported[2].text, '中文二');
  assert.equal(imported[4].text, '保持不变');

  const structurallyChanged = JSON.parse(uploadedJson) as {
    sheetList: Array<{
      contentRowList: Array<{ cellList: string[] }>;
    }>;
  };
  structurallyChanged.sheetList[0].contentRowList[2].cellList[4] = 'Right';
  assert.throws(
    () => applyScenarioJsonUploadToAggregate({
      sourceJson,
      uploadedJson: JSON.stringify(structurallyChanged),
      sourceFilename: filename,
      aggregateEditingBaselineLines: aggregate,
      aggregateCurrentEditedLines: aggregate,
    }),
    /结构与来源 JSON 不同/u,
  );
});
