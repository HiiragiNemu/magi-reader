/// <reference lib="webworker" />

import {
  assertPlayableHca,
  MAX_HCA_PLAYBACK_SECONDS,
  parseHcaHeader,
} from './hca-header.ts';
import { decodeHca, initHcaDecoder } from './hca-wasm.ts';

const MAGIA_RECORD_HCA_KEY = 0x01395c51n;
const MAX_INPUT_BYTES = 8 * 1024 * 1024;

export interface HcaDecodeRequest {
  id: number;
  bytes: ArrayBuffer;
}

export interface HcaDecodeSuccess {
  id: number;
  ok: true;
  channels: Float32Array<ArrayBuffer>[];
  sampleRate: number;
  durationSeconds: number;
}

export interface HcaDecodeFailure {
  id: number;
  ok: false;
  error: string;
}

export type HcaDecodeResponse = HcaDecodeSuccess | HcaDecodeFailure;

function readWave(wave: Uint8Array): {
  channelCount: number;
  sampleRate: number;
  pcm: Int16Array;
} {
  if (wave.byteLength < 12) throw new Error('Decoder returned a short WAV');
  const view = new DataView(wave.buffer, wave.byteOffset, wave.byteLength);
  const tag = (offset: number) =>
    String.fromCharCode(
      wave[offset] ?? 0,
      wave[offset + 1] ?? 0,
      wave[offset + 2] ?? 0,
      wave[offset + 3] ?? 0,
    );
  if (tag(0) !== 'RIFF' || tag(8) !== 'WAVE') {
    throw new Error('Decoder did not return WAV');
  }

  let channelCount = 0;
  let sampleRate = 0;
  let bitsPerSample = 0;
  let offset = 12;
  while (offset + 8 <= wave.byteLength) {
    const chunkId = tag(offset);
    const size = view.getUint32(offset + 4, true);
    const bodyOffset = offset + 8;
    if (size > wave.byteLength - bodyOffset) {
      throw new Error('Truncated WAV chunk');
    }
    if (chunkId === 'fmt ') {
      if (size < 16) throw new Error('Invalid WAV format chunk');
      channelCount = view.getUint16(bodyOffset + 2, true);
      sampleRate = view.getUint32(bodyOffset + 4, true);
      bitsPerSample = view.getUint16(bodyOffset + 14, true);
    } else if (chunkId === 'data') {
      if (
        bitsPerSample !== 16 ||
        channelCount < 1 ||
        channelCount > 2 ||
        sampleRate < 8_000 ||
        sampleRate > 96_000
      ) {
        throw new Error('Unsupported decoded WAV format');
      }
      const copy = wave.slice(bodyOffset, bodyOffset + size);
      return {
        channelCount,
        sampleRate,
        pcm: new Int16Array(
          copy.buffer,
          copy.byteOffset,
          copy.byteLength >> 1,
        ),
      };
    }
    offset = bodyOffset + size + (size & 1);
  }
  throw new Error('WAV data chunk not found');
}

function deinterleave(
  pcm: Int16Array,
  channelCount: number,
): Float32Array<ArrayBuffer>[] {
  const frames = Math.floor(pcm.length / channelCount);
  const channels = Array.from(
    { length: channelCount },
    () => new Float32Array(frames),
  );
  for (let frame = 0, pointer = 0; frame < frames; frame += 1) {
    for (let channel = 0; channel < channelCount; channel += 1) {
      channels[channel][frame] = pcm[pointer] / 32768;
      pointer += 1;
    }
  }
  return channels;
}

const workerScope = self as unknown as DedicatedWorkerGlobalScope;
workerScope.onmessage = async (event: MessageEvent<HcaDecodeRequest>) => {
  const { id, bytes } = event.data;
  try {
    if (!(bytes instanceof ArrayBuffer) || bytes.byteLength > MAX_INPUT_BYTES) {
      throw new Error('HCA input exceeds safety limit');
    }
    const raw = new Uint8Array(bytes);
    const info = parseHcaHeader(raw);
    assertPlayableHca(info);

    await initHcaDecoder();
    const wave = decodeHca(raw, MAGIA_RECORD_HCA_KEY, 0);
    const { channelCount, sampleRate, pcm } = readWave(wave);
    const channels = deinterleave(pcm, channelCount);
    const durationSeconds =
      channels.length > 0 ? channels[0].length / sampleRate : 0;
    if (
      durationSeconds <= 0 ||
      durationSeconds > MAX_HCA_PLAYBACK_SECONDS
    ) {
      throw new Error('Decoded voice exceeds playback duration limit');
    }

    const response: HcaDecodeSuccess = {
      id,
      ok: true,
      channels,
      sampleRate,
      durationSeconds,
    };
    workerScope.postMessage(
      response,
      channels.map(channel => channel.buffer),
    );
  } catch (error) {
    const response: HcaDecodeFailure = {
      id,
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    };
    workerScope.postMessage(response);
  }
};

export {};
