import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createLocalStoryPayload,
  decodeStoryBuffer,
} from '../lib/local-story.ts';

const arrayBufferFrom = (bytes: Uint8Array): ArrayBuffer =>
  bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;

const scenarioFile = (name: string, raw: string): File => {
  const bytes = new TextEncoder().encode(raw);
  return {
    name,
    size: bytes.byteLength,
    arrayBuffer: async () => arrayBufferFrom(bytes),
  } as File;
};

test('decodes UTF-16LE text without a BOM from its null-byte pattern', () => {
  const bytes = Uint8Array.from(
    Buffer.from('旁白: 你好', 'utf16le'),
  );
  assert.equal(decodeStoryBuffer(arrayBufferFrom(bytes)), '旁白: 你好');
});

test('decodes long CJK UTF-16LE text with only sparse null bytes', () => {
  const expected = `旁白: ${'这是很长的中文剧情文本'.repeat(30)}`;
  const bytes = Uint8Array.from(Buffer.from(expected, 'utf16le'));
  assert.equal(decodeStoryBuffer(arrayBufferFrom(bytes)), expected);
});

test('rejects two explicitly same-language local story files', async () => {
  await assert.rejects(
    createLocalStoryPayload([
      scenarioFile('a_jp.txt', 'まどか: 一行目'),
      scenarioFile('b_jp.txt', 'ほむら: 二行目'),
    ]),
    /同一种语言/,
  );
});

test('reserves an explicit language before assigning an unlabeled file', async () => {
  const payload = await createLocalStoryPayload([
    scenarioFile('unlabeled.txt', '旁白: 中文内容'),
    scenarioFile('story_jp.txt', 'ナレーション: 日本語本文'),
  ]);

  assert.equal(payload.cn?.name, 'unlabeled.txt');
  assert.equal(payload.jp?.name, 'story_jp.txt');
});

test('rejects two unlabeled files instead of silently guessing CN/JP order', async () => {
  await assert.rejects(
    createLocalStoryPayload([
      scenarioFile('translation.txt', '彩羽: 中文内容'),
      scenarioFile('original.txt', 'いろは: 日本語本文'),
    ]),
    /语言标记|文件名.*中日文标记|无法判断.*语言|明确.*中日文/,
  );
});
