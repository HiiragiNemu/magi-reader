import assert from 'node:assert/strict';
import test from 'node:test';

import {
  assertPlayableHca,
  HCA_SAMPLES_PER_BLOCK,
  parseHcaHeader,
} from '../lib/audio/hca/hca-header.ts';

function syntheticHca(options?: {
  blockCount?: number;
  channelCount?: number;
  sampleRate?: number;
}): Uint8Array {
  const channelCount = options?.channelCount ?? 2;
  const sampleRate = options?.sampleRate ?? 48_000;
  const blockCount = options?.blockCount ?? 100;
  const bytes = new Uint8Array(24);
  const view = new DataView(bytes.buffer);
  bytes.set([0x48, 0x43, 0x41, 0x00], 0);
  view.setUint16(6, bytes.length, false);
  bytes.set([0x66, 0x6d, 0x74, 0x00], 8);
  view.setUint8(12, channelCount);
  view.setUint8(13, (sampleRate >>> 16) & 0xff);
  view.setUint8(14, (sampleRate >>> 8) & 0xff);
  view.setUint8(15, sampleRate & 0xff);
  view.setUint32(16, blockCount, false);
  return bytes;
}

test('parses a bounded HCA format header', () => {
  const info = parseHcaHeader(syntheticHca());
  assert.equal(info.channelCount, 2);
  assert.equal(info.sampleRate, 48_000);
  assert.equal(info.totalSamples, 100 * HCA_SAMPLES_PER_BLOCK);
  assert.doesNotThrow(() => assertPlayableHca(info));
});

test('rejects malformed or truncated HCA headers', () => {
  assert.throws(() => parseHcaHeader(new Uint8Array([1, 2, 3])));
  const truncated = syntheticHca();
  truncated[6] = 0;
  truncated[7] = 12;
  assert.throws(() => parseHcaHeader(truncated), /Truncated HCA header/);
});

test('rejects decoded durations beyond the 60-second ceiling', () => {
  const blockCount = Math.ceil((48_000 * 61) / HCA_SAMPLES_PER_BLOCK);
  const info = parseHcaHeader(syntheticHca({ blockCount }));
  assert.throws(
    () => assertPlayableHca(info),
    /playback duration limit/,
  );
});

test('rejects a decoded channel allocation beyond the 32 MiB budget', () => {
  const blockCount = Math.ceil((96_000 * 50) / HCA_SAMPLES_PER_BLOCK);
  const info = parseHcaHeader(
    syntheticHca({ blockCount, channelCount: 2, sampleRate: 96_000 }),
  );
  assert.throws(
    () => assertPlayableHca(info),
    /memory budget/,
  );
});
