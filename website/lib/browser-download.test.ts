import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createUtf8DownloadBlob,
  DOWNLOAD_URL_REVOKE_DELAY_MS,
  safeDownloadFilename,
  UTF8_BOM_BYTES,
} from './browser-download.ts';
import { decodeStoryBuffer } from './local-story.ts';
import { normalizeProofreadingText } from './proofreading.ts';

const bytesOf = async (blob: Blob): Promise<Uint8Array> =>
  new Uint8Array(await blob.arrayBuffer());

test('TXT download has a single literal UTF-8 BOM and mobile-safe MIME type', async () => {
  const source = '环彩羽：大家好\n--- [Section 2] ---';
  const blob = createUtf8DownloadBlob(source, '100100_translated.txt');
  const bytes = await bytesOf(blob);

  assert.equal(blob.type, 'text/plain;charset=utf-8');
  assert.deepEqual(
    Array.from(bytes.subarray(0, UTF8_BOM_BYTES.length)),
    Array.from(UTF8_BOM_BYTES),
  );
  const decoded = new TextDecoder('utf-8').decode(bytes);
  assert.equal(decoded, source.replace(/\n/gu, '\r\n'));
  assert.equal(normalizeProofreadingText(decoded), source);
  assert.equal(
    normalizeProofreadingText(
      decodeStoryBuffer(await blob.arrayBuffer()),
    ),
    source,
  );
});

test('TXT download replaces an existing leading BOM instead of doubling it', async () => {
  const blob = createUtf8DownloadBlob('\uFEFF\uFEFF中文剧情', 'story.txt');
  const bytes = await bytesOf(blob);

  assert.deepEqual(Array.from(bytes.subarray(0, 3)), [0xef, 0xbb, 0xbf]);
  assert.notDeepEqual(Array.from(bytes.subarray(3, 6)), [0xef, 0xbb, 0xbf]);
  assert.equal(new TextDecoder('utf-8').decode(bytes), '中文剧情');
});

test('JSON download remains BOM-free and valid JSON for proofreading import', async () => {
  const raw = '{"Name":"環いろは","Comment":"你好"}';
  const blob = createUtf8DownloadBlob(raw, '100100_cn.json');
  const bytes = await bytesOf(blob);

  assert.equal(blob.type, 'application/json;charset=utf-8');
  assert.notDeepEqual(Array.from(bytes.subarray(0, 3)), [0xef, 0xbb, 0xbf]);
  assert.deepEqual(JSON.parse(new TextDecoder().decode(bytes)), JSON.parse(raw));
});

test('download filenames preserve story IDs and Chinese while removing path syntax', () => {
  assert.equal(
    safeDownloadFilename('  100100_人工校对:最终版?.txt  '),
    '100100_人工校对-最终版-.txt',
  );
  assert.equal(safeDownloadFilename('...   ', 'story.txt'), 'story.txt');
});

test('Blob URLs remain available long enough for deferred mobile downloads', () => {
  assert.equal(DOWNLOAD_URL_REVOKE_DELAY_MS, 30_000);
});
