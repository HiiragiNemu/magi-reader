import { unzipSync } from 'fflate';

export const TANGYUAN_V012_SOURCE = {
  releaseUrl:
    'https://github.com/NightFurySL2001/TangYuan-font/releases/tag/v0.12beta',
  assetUrl:
    'https://github.com/NightFurySL2001/TangYuan-font/releases/download/v0.12beta/MaoKenTangYuan-beta0.12-20210702.zip',
  licenseUrl:
    'https://github.com/NightFurySL2001/TangYuan-font/blob/561190610f7c34939396bd9f745a5393f4815ddd/LICENSE.txt',
  archiveBytes: 1_843_200,
  archiveSha256:
    '64eaef7fffba29748749a87a7b6287c06a9efc00a9630e26837db392a044f55f',
  fontEntry: 'MaoKenTangYuan-beta0.12-20210702.ttf',
  fontBytes: 2_881_764,
  fontSha256:
    'ea4e2e85cc49ed7a0ea9f2347a9c5e6e9c3ea1a1c9130280796cceb77e0dc800',
} as const;

export type VerifiedZipEntryExpectation = {
  archiveBytes: number;
  archiveSha256: string;
  entryName: string;
  entryBytes: number;
  entrySha256: string;
};

export const sha256Hex = async (
  data: ArrayBuffer | Uint8Array,
): Promise<string> => {
  const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
  const stableBytes = new Uint8Array(bytes.byteLength);
  stableBytes.set(bytes);
  const digest = await globalThis.crypto.subtle.digest(
    'SHA-256',
    stableBytes.buffer,
  );
  return [...new Uint8Array(digest)]
    .map(value => value.toString(16).padStart(2, '0'))
    .join('');
};

export const extractVerifiedZipEntry = async (
  archive: Uint8Array,
  expected: VerifiedZipEntryExpectation,
): Promise<Uint8Array> => {
  if (archive.byteLength !== expected.archiveBytes) {
    throw new Error('上游字体压缩包大小与固定版本不符。');
  }
  if (await sha256Hex(archive) !== expected.archiveSha256.toLowerCase()) {
    throw new Error('上游字体压缩包 SHA-256 校验失败。');
  }
  const entries = unzipSync(archive, { filter: entry => entry.name === expected.entryName });
  const font = entries[expected.entryName];
  if (!font) throw new Error('固定字体条目未出现在上游压缩包中。');
  if (font.byteLength !== expected.entryBytes) {
    throw new Error('解压后的字体大小与固定版本不符。');
  }
  if (await sha256Hex(font) !== expected.entrySha256.toLowerCase()) {
    throw new Error('解压后的字体 SHA-256 校验失败。');
  }
  return font;
};

export const extractPinnedTangYuanFont = (
  archive: Uint8Array,
): Promise<Uint8Array> => extractVerifiedZipEntry(archive, {
  archiveBytes: TANGYUAN_V012_SOURCE.archiveBytes,
  archiveSha256: TANGYUAN_V012_SOURCE.archiveSha256,
  entryName: TANGYUAN_V012_SOURCE.fontEntry,
  entryBytes: TANGYUAN_V012_SOURCE.fontBytes,
  entrySha256: TANGYUAN_V012_SOURCE.fontSha256,
});
