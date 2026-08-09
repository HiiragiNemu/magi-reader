import assert from 'node:assert/strict';
import test from 'node:test';

import { zipSync } from 'fflate';

import {
  TANGYUAN_V012_SOURCE,
  extractVerifiedZipEntry,
  sha256Hex,
} from './exedra-font-assets.ts';

test('TangYuan v0.12beta source is immutable and byte-pinned', () => {
  assert.match(TANGYUAN_V012_SOURCE.assetUrl, /releases\/download\/v0\.12beta/u);
  assert.equal(TANGYUAN_V012_SOURCE.archiveBytes, 1_843_200);
  assert.equal(
    TANGYUAN_V012_SOURCE.archiveSha256,
    '64eaef7fffba29748749a87a7b6287c06a9efc00a9630e26837db392a044f55f',
  );
  assert.equal(TANGYUAN_V012_SOURCE.fontBytes, 2_881_764);
  assert.equal(
    TANGYUAN_V012_SOURCE.fontSha256,
    'ea4e2e85cc49ed7a0ea9f2347a9c5e6e9c3ea1a1c9130280796cceb77e0dc800',
  );
  assert.match(TANGYUAN_V012_SOURCE.licenseUrl, /561190610f7c/u);
});

test('verified ZIP extraction accepts only the pinned archive and entry bytes', async () => {
  const font = new TextEncoder().encode('fixture-font-bytes');
  const archive = zipSync({ 'font.ttf': font });
  const expected = {
    archiveBytes: archive.byteLength,
    archiveSha256: await sha256Hex(archive),
    entryName: 'font.ttf',
    entryBytes: font.byteLength,
    entrySha256: await sha256Hex(font),
  };
  const extracted = await extractVerifiedZipEntry(archive, expected);
  assert.deepEqual(extracted, font);

  await assert.rejects(
    extractVerifiedZipEntry(archive, {
      ...expected,
      archiveSha256: '0'.repeat(64),
    }),
    /压缩包 SHA-256 校验失败/u,
  );
  await assert.rejects(
    extractVerifiedZipEntry(archive, {
      ...expected,
      entrySha256: 'f'.repeat(64),
    }),
    /字体 SHA-256 校验失败/u,
  );
});
