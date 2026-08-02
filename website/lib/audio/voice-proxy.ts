import { isMagirecoVoiceId } from './voice-cue.ts';

export const MAX_VOICE_BYTES = 8 * 1024 * 1024;
export const MAGIRECO_VOICE_R2_ORIGIN =
  'https://pub-70a248f1a6fe4ca597e7a10f8b95dfd8.r2.dev';

export type VoiceResponseMetadata = {
  status: 200 | 206;
  contentLength: number;
  contentRange: string | null;
  etag: string;
};

export function getMagirecoVoiceObjectKey(voiceId: string): string {
  if (!isMagirecoVoiceId(voiceId)) {
    throw new TypeError('Invalid Magia Record voice cue ID');
  }
  return `voice/${voiceId}_hca.hca`;
}

export function getMagirecoVoiceUpstreamUrl(voiceId: string): URL {
  return new URL(`/${getMagirecoVoiceObjectKey(voiceId)}`, MAGIRECO_VOICE_R2_ORIGIN);
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

/**
 * Convert an already validated HTTP byte range into the shape accepted by R2.
 * Keeping this conversion separate makes the route testable without a Worker
 * runtime or an actual bucket.
 */
export function voiceRangeToR2Range(
  value: string | null,
): CloudflareR2Range | undefined {
  if (value === null) return undefined;
  if (normalizeVoiceRange(value) === null) {
    throw new TypeError('Invalid or oversized voice byte range');
  }

  const match = /^bytes=([0-9]*)-([0-9]*)$/.exec(value);
  if (!match) throw new TypeError('Invalid voice byte range');
  if (!match[1]) return { suffix: Number(match[2]) };

  const offset = Number(match[1]);
  if (!match[2]) return { offset };
  return {
    offset,
    length: Number(match[2]) - offset + 1,
  };
}

/**
 * Validate R2 metadata and derive an HTTP response. R2 exposes the complete
 * object size even for a range read, so the 8 MiB object ceiling remains
 * enforceable without buffering the body.
 */
export function getR2VoiceResponseMetadata(
  object: Pick<
    CloudflareR2ObjectBody,
    'size' | 'etag' | 'httpEtag' | 'range'
  >,
): VoiceResponseMetadata {
  if (
    !Number.isSafeInteger(object.size) ||
    object.size < 0 ||
    object.size > MAX_VOICE_BYTES
  ) {
    throw new RangeError('Voice object exceeds size limit');
  }

  const etag = object.httpEtag || `"${object.etag}"`;
  if (!object.range) {
    return {
      status: 200,
      contentLength: object.size,
      contentRange: null,
      etag,
    };
  }

  const { offset, length } = object.range;
  if (
    !Number.isSafeInteger(offset) ||
    !Number.isSafeInteger(length) ||
    offset < 0 ||
    length < 1 ||
    offset >= object.size ||
    offset + length > object.size ||
    length > MAX_VOICE_BYTES
  ) {
    throw new TypeError('R2 returned invalid voice range metadata');
  }

  return {
    status: 206,
    contentLength: length,
    contentRange: `bytes ${offset}-${offset + length - 1}/${object.size}`,
    etag,
  };
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
  options: {
    readTimeoutMs?: number;
    onTimeout?: () => void;
  } = {},
): ReadableStream<Uint8Array> {
  let received = 0;
  const reader = source.getReader();
  let finished = false;
  const readTimeoutMs = options.readTimeoutMs;
  if (
    readTimeoutMs !== undefined &&
    (!Number.isSafeInteger(readTimeoutMs) || readTimeoutMs <= 0)
  ) {
    reader.releaseLock();
    throw new RangeError('Voice stream timeout is invalid');
  }

  const release = () => {
    if (finished) return;
    finished = true;
    try {
      reader.releaseLock();
    } catch {
      // A pending read keeps the lock until its cancellation settles.
    }
  };

  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      let timer: ReturnType<typeof setTimeout> | undefined;
      const timeout = new Promise<never>((_resolve, reject) => {
        if (readTimeoutMs === undefined) return;
        timer = setTimeout(() => {
          const error = new Error('Voice upstream read timed out');
          reject(error);
          options.onTimeout?.();
          void reader.cancel(error.message).catch(() => undefined);
        }, readTimeoutMs);
      });
      try {
        const result = readTimeoutMs === undefined
          ? await reader.read()
          : await Promise.race([reader.read(), timeout]);
        if (result.done) {
          release();
          controller.close();
          return;
        }
        received += result.value.byteLength;
        if (received > maxBytes) {
          const error = new RangeError('Voice object exceeds size limit');
          void reader.cancel(error.message).catch(() => undefined);
          release();
          controller.error(error);
          return;
        }
        controller.enqueue(result.value);
      } catch (error) {
        void reader.cancel(
          error instanceof Error ? error.message : 'Voice stream failed',
        ).catch(() => undefined);
        release();
        controller.error(error);
      } finally {
        if (timer !== undefined) clearTimeout(timer);
      }
    },
    cancel(reason) {
      const cancellation = reader.cancel(reason).catch(() => undefined);
      release();
      return cancellation;
    },
  });
}
