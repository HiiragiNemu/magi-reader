import { isMagirecoVoiceId } from './voice-cue.ts';

export const MAX_VOICE_BYTES = 8 * 1024 * 1024;
export const MAGIRECO_VOICE_R2_ORIGIN =
  'https://pub-70a248f1a6fe4ca597e7a10f8b95dfd8.r2.dev';

export function getMagirecoVoiceUpstreamUrl(voiceId: string): URL {
  if (!isMagirecoVoiceId(voiceId)) {
    throw new TypeError('Invalid Magia Record voice cue ID');
  }
  return new URL(`/voice/${voiceId}_hca.hca`, MAGIRECO_VOICE_R2_ORIGIN);
}

/**
 * Permit one byte range only. The requested span or suffix must fit inside the
 * same 8 MiB ceiling as a complete voice object.
 */
export function normalizeVoiceRange(value: string | null): string | null {
  if (value === null) return null;
  const match = /^bytes=([0-9]*)-([0-9]*)$/.exec(value);
  if (!match || (!match[1] && !match[2])) return null;

  const start = match[1] ? Number(match[1]) : null;
  const end = match[2] ? Number(match[2]) : null;
  if (
    (start !== null && !Number.isSafeInteger(start)) ||
    (end !== null && !Number.isSafeInteger(end))
  ) {
    return null;
  }
  if (start !== null && end !== null) {
    if (end < start || end - start + 1 > MAX_VOICE_BYTES) return null;
  } else if (start === null && (end === null || end < 1 || end > MAX_VOICE_BYTES)) {
    return null;
  }
  return value;
}

export function parseBoundedContentLength(
  value: string | null,
): number | null {
  if (value === null || !/^[0-9]+$/.test(value)) return null;
  const length = Number(value);
  if (!Number.isSafeInteger(length) || length < 0) return null;
  return length;
}

export function contentRangeTotalExceedsLimit(value: string | null): boolean {
  if (value === null) return false;
  const match = /^bytes [0-9]+-[0-9]+\/([0-9]+|\*)$/.exec(value);
  if (!match || match[1] === '*') return false;
  const total = Number(match[1]);
  return !Number.isSafeInteger(total) || total > MAX_VOICE_BYTES;
}

/**
 * Count bytes while preserving streaming. If an upstream omits or lies about
 * Content-Length, the stream is still cut off at the hard ceiling.
 */
export function createBoundedVoiceStream(
  source: ReadableStream<Uint8Array>,
  maxBytes = MAX_VOICE_BYTES,
): ReadableStream<Uint8Array> {
  let received = 0;
  return source.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        received += chunk.byteLength;
        if (received > maxBytes) {
          controller.error(new RangeError('Voice object exceeds size limit'));
          return;
        }
        controller.enqueue(chunk);
      },
    }),
  );
}
