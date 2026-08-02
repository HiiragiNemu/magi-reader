import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const readerPath = new URL('../app/reader/[id]/page.tsx', import.meta.url);

test('reader exposes bounded Section JSON downloads and guarded edit generation', async () => {
  const source = await readFile(readerPath, 'utf8');

  assert.match(source, /data-scenario-json-tools="true"/u);
  assert.match(source, /来源 JSON（按 Section）/u);
  assert.match(source, /下载日文原始 JSON/u);
  assert.match(source, /下载中文原始 JSON/u);
  assert.match(source, /下载本次编辑 JSON/u);
  assert.match(
    source,
    /\/api\/story-json\/\$\{encodeURIComponent\(currentStory\.id\)\}/u,
  );
  assert.match(source, /MAX_STORY_SOURCE_BYTES/u);
  assert.match(source, /readBoundedResponseBody/u);
  assert.match(source, /jsonDownloadBusyRef\.current/u);
  assert.match(source, /createOriginalScenarioJsonDownload/u);
  assert.match(source, /createEditedScenarioJsonDownload/u);
  assert.match(source, /mapAggregateEditsToScenarioJson/u);
  assert.match(source, /baselineLines: cnEventLines/u);
  assert.match(source, /使用日文 JSON 作为结构模板/u);
});

test('reader keeps unmerged event rows for editing while reading merged blocks', async () => {
  const source = await readFile(readerPath, 'utf8');
  const parserFunction = source.slice(
    source.indexOf('const parseLoadedSource'),
    source.indexOf('export default function ReaderPage'),
  );

  assert.match(parserFunction, /mergeConsecutiveTextLines: false/u);
  assert.match(parserFunction, /mergeConsecutiveTextLines: true/u);
  assert.match(source, /seedEditableLines\(cnEventLines, jpEventLines, seed\)/u);
  assert.match(
    source,
    /isEditMode && jpEventLines\.length > 0 \? jpEventLines : jpLines/u,
  );
  assert.match(source, /applyScenarioJsonUploadToAggregate/u);
});
