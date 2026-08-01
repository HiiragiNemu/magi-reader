export const HCA_SAMPLES_PER_BLOCK = 1024;
export const MAX_HCA_PLAYBACK_SECONDS = 60;
export const MAX_DECODED_CHANNEL_BYTES = 32 * 1024 * 1024;

export interface HcaInfo {
  channelCount: number;
  sampleRate: number;
  blockCount: number;
  encoderDelay: number;
  encoderPadding: number;
  cipherType: number;
  totalSamples: number;
}

function signatureAt(view: DataView, offset: number): string {
  let signature = '';
  for (let index = 0; index < 4; index += 1) {
    signature += String.fromCharCode(view.getUint8(offset + index) & 0x7f);
  }
  return signature;
}

function requireBytes(offset: number, length: number, limit: number): void {
  if (offset < 0 || length < 0 || offset + length > limit) {
    throw new Error('Truncated HCA header');
  }
}

export function parseHcaHeader(data: ArrayBuffer | Uint8Array): HcaInfo {
  const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
  if (bytes.byteLength < 8) throw new Error('Not an HCA file');

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (signatureAt(view, 0) !== 'HCA\0') throw new Error('Not an HCA file');

  const dataOffset = view.getUint16(6, false);
  const headerLimit = Math.min(dataOffset, bytes.byteLength);
  let channelCount = 0;
  let sampleRate = 0;
  let blockCount = 0;
  let encoderDelay = 0;
  let encoderPadding = 0;
  let cipherType = 0;

  let offset = 8;
  while (offset + 4 <= headerLimit) {
    const signature = signatureAt(view, offset);
    if (signature.startsWith('pad')) break;

    switch (signature) {
      case 'fmt\0':
        requireBytes(offset, 16, headerLimit);
        channelCount = view.getUint8(offset + 4);
        sampleRate =
          (view.getUint8(offset + 5) << 16) |
          (view.getUint8(offset + 6) << 8) |
          view.getUint8(offset + 7);
        blockCount = view.getUint32(offset + 8, false);
        encoderDelay = view.getUint16(offset + 12, false);
        encoderPadding = view.getUint16(offset + 14, false);
        offset += 16;
        break;
      case 'comp':
        requireBytes(offset, 16, headerLimit);
        offset += 16;
        break;
      case 'dec\0':
        requireBytes(offset, 12, headerLimit);
        offset += 12;
        break;
      case 'vbr\0':
      case 'rva\0':
        requireBytes(offset, 8, headerLimit);
        offset += 8;
        break;
      case 'ath\0':
      case 'ciph':
        requireBytes(offset, 6, headerLimit);
        if (signature === 'ciph') cipherType = view.getUint16(offset + 4, false);
        offset += 6;
        break;
      case 'loop':
        requireBytes(offset, 16, headerLimit);
        offset += 16;
        break;
      case 'comm': {
        requireBytes(offset, 5, headerLimit);
        const commentLength = view.getUint8(offset + 4);
        requireBytes(offset, 5 + commentLength, headerLimit);
        offset += 5 + commentLength;
        break;
      }
      default:
        offset = headerLimit;
        break;
    }
  }

  if (channelCount === 0 || sampleRate === 0) {
    throw new Error('HCA header missing fmt chunk');
  }
  const totalSamples =
    blockCount * HCA_SAMPLES_PER_BLOCK - encoderDelay - encoderPadding;
  if (!Number.isSafeInteger(totalSamples) || totalSamples <= 0) {
    throw new Error('Invalid HCA sample count');
  }

  return {
    channelCount,
    sampleRate,
    blockCount,
    encoderDelay,
    encoderPadding,
    cipherType,
    totalSamples,
  };
}

export function assertPlayableHca(info: HcaInfo): void {
  if (info.channelCount < 1 || info.channelCount > 2) {
    throw new Error('Unsupported HCA channel count');
  }
  if (info.sampleRate < 8_000 || info.sampleRate > 96_000) {
    throw new Error('Unsupported HCA sample rate');
  }
  if (info.totalSamples > info.sampleRate * MAX_HCA_PLAYBACK_SECONDS) {
    throw new Error('HCA voice exceeds playback duration limit');
  }
  if (
    info.totalSamples * info.channelCount * Float32Array.BYTES_PER_ELEMENT >
    MAX_DECODED_CHANNEL_BYTES
  ) {
    throw new Error('Decoded HCA channels exceed memory budget');
  }
}
