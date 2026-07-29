import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const read = (path) => readFileSync(path, 'utf8');

test('Magia Record and Exedra reader downloads use the shared UTF-8 helper', () => {
  const reader = read('app/reader/[id]/page.tsx');

  assert.match(reader, /import \{ triggerUtf8Download \} from '@\/lib\/browser-download'/u);
  assert.match(reader, /triggerUtf8Download\(\s*lines\.map\(serializeStoryLine\)\.join\('\\n'\),\s*`\$\{id\}_translated\.txt`/u);
  assert.match(reader, /triggerUtf8Download\(content, `\$\{currentStory\.id\}_submit\.txt`\)/u);
  assert.match(reader, /triggerUtf8Download\(\s*cnSource\.raw/u);
  assert.match(reader, /triggerUtf8Download\(\s*jpSource\.raw/u);
  assert.doesNotMatch(reader, /URL\.createObjectURL|new Blob/u);
});

test('admin review exports use the same mobile-safe download lifecycle', () => {
  const submissions = read('app/review/submissions/page.tsx');
  const exedra = read('app/review/exedra-localization/page.tsx');

  assert.match(submissions, /triggerUtf8Download/u);
  assert.match(submissions, /submitted_cn/u);
  assert.match(submissions, /current_cn/u);
  assert.match(submissions, /source_jp/u);
  assert.match(exedra, /triggerBlobDownload/u);
  assert.doesNotMatch(exedra, /URL\.revokeObjectURL/u);
});
