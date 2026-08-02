import { getCloudflareContext } from '@opennextjs/cloudflare';

import {
  contentRangeTotalExceedsLimit,
  createBoundedVoiceStream,
  getMagirecoVoiceObjectKey,
  getMagirecoVoiceUpstreamUrl,
  getR2VoiceResponseMetadata,
  MAX_VOICE_BYTES,
  normalizeVoiceRange,
  parseBoundedContentLength,
  voiceRangeToR2Range,
} from '@/lib/audio/voice-proxy';
import { isMagirecoVoiceId } from '@/lib/audio/voice-cue';
import { cancelResponseBody } from '@/lib/http/bounded-response';

export const dynamic = 'force-dynamic';

const SECURITY_HEADERS = {
  'Cross-Origin-Resource-Policy': 'same-origin',
  'X-Content-Type-Options': 'nosniff',
};
const SUCCESS_HEADERS = {
  ...SECURITY_HEADERS,
  'Cache-Control': 'public, max-age=86400, stale-while-revalidate=604800',
};
const ERROR_HEADERS = {
  ...SECURITY_HEADERS,
  'Cache-Control': 'no-store',
};
const UPSTREAM_TIMEOUT_MS = 10_000;

async function getFromR2(
  bucket: CloudflareR2Bucket,
  voiceId: string,
  safeRange: string | null,
): Promise<Response> {
  let object: CloudflareR2ObjectBody | null;
  try {
    object = await bucket.get(getMagirecoVoiceObjectKey(voiceId), {
      ...(safeRange
        ? { range: voiceRangeToR2Range(safeRange) }
        : {}),
    });
  } catch (error) {
    console.error('Magia Record voice R2 request failed', error);
    return Response.json(
      { error: '魔法纪录语音存储暂时不可用' },
      { status: 502, headers: ERROR_HEADERS },
    );
  }

  if (!object) {
    return Response.json(
      { error: '未找到该语音' },
      { status: 404, headers: ERROR_HEADERS },
    );
  }

  let metadata;
  try {
    metadata = getR2VoiceResponseMetadata(object);
  } catch (error) {
    void object.body.cancel('Invalid or oversized R2 voice object');
    if (error instanceof RangeError) {
      return Response.json(
        { error: '语音文件超过 8 MiB 安全上限' },
        { status: 413, headers: ERROR_HEADERS },
      );
    }
    console.error('Magia Record voice R2 metadata is invalid', error);
    return Response.json(
      { error: '魔法纪录语音存储返回异常' },
      { status: 502, headers: ERROR_HEADERS },
    );
  }

  const headers = new Headers(SUCCESS_HEADERS);
  headers.set('Content-Type', 'audio/x-hca');
  headers.set('Accept-Ranges', 'bytes');
  headers.set('Content-Length', String(metadata.contentLength));
  headers.set('ETag', metadata.etag);
  if (metadata.contentRange) {
    headers.set('Content-Range', metadata.contentRange);
  }

  return new Response(
    createBoundedVoiceStream(object.body, metadata.contentLength, {
      readTimeoutMs: UPSTREAM_TIMEOUT_MS,
    }),
    {
      status: metadata.status,
      headers,
    },
  );
}

async function getFromPublicOrigin(
  voiceId: string,
  safeRange: string | null,
): Promise<Response> {
  const upstreamHeaders = new Headers({
    Accept: 'application/octet-stream',
  });
  if (safeRange) upstreamHeaders.set('Range', safeRange);

  let upstream: Response;
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(new Error('Magia Record voice upstream timed out')),
    UPSTREAM_TIMEOUT_MS,
  );
  try {
    upstream = await fetch(getMagirecoVoiceUpstreamUrl(voiceId), {
      cache: 'no-store',
      headers: upstreamHeaders,
      redirect: 'error',
      signal: controller.signal,
    });
  } catch (error) {
    clearTimeout(timeout);
    console.error('Magia Record voice upstream request failed', error);
    return Response.json(
      { error: '魔法纪录语音源暂时不可用' },
      { status: 502, headers: ERROR_HEADERS },
    );
  }
  clearTimeout(timeout);

  if (upstream.status !== 200 && upstream.status !== 206) {
    await cancelResponseBody(upstream, `Voice upstream HTTP ${upstream.status}`);
    return Response.json(
      {
        error:
          upstream.status === 404
            ? '未找到该语音'
            : '魔法纪录语音源返回异常',
      },
      {
        status: upstream.status === 404 ? 404 : 502,
        headers: ERROR_HEADERS,
      },
    );
  }
  if (!upstream.body) {
    return Response.json(
      { error: '魔法纪录语音源没有返回正文' },
      { status: 502, headers: ERROR_HEADERS },
    );
  }

  const contentLength = parseBoundedContentLength(
    upstream.headers.get('content-length'),
  );
  if (
    (contentLength !== null && contentLength > MAX_VOICE_BYTES) ||
    contentRangeTotalExceedsLimit(upstream.headers.get('content-range'))
  ) {
    await cancelResponseBody(upstream, 'Voice object exceeds size limit');
    return Response.json(
      { error: '语音文件超过 8 MiB 安全上限' },
      { status: 413, headers: ERROR_HEADERS },
    );
  }

  const headers = new Headers(SUCCESS_HEADERS);
  headers.set('Content-Type', 'audio/x-hca');
  headers.set('Accept-Ranges', 'bytes');
  if (contentLength !== null) {
    headers.set('Content-Length', String(contentLength));
  }
  const contentRange = upstream.headers.get('content-range');
  if (contentRange) headers.set('Content-Range', contentRange);
  const etag = upstream.headers.get('etag');
  if (etag) headers.set('ETag', etag);

  return new Response(createBoundedVoiceStream(upstream.body, MAX_VOICE_BYTES, {
    readTimeoutMs: UPSTREAM_TIMEOUT_MS,
    onTimeout: () => controller.abort(
      new Error('Magia Record voice upstream body timed out'),
    ),
  }), {
    status: upstream.status,
    headers,
  });
}

export async function GET(
  request: Request,
  context: { params: Promise<{ voiceId: string }> },
) {
  const { voiceId } = await context.params;
  if (!isMagirecoVoiceId(voiceId)) {
    return Response.json(
      { error: '无效的魔法纪录语音编号' },
      { status: 400, headers: ERROR_HEADERS },
    );
  }

  const requestRange = request.headers.get('range');
  const safeRange = normalizeVoiceRange(requestRange);
  if (requestRange !== null && safeRange === null) {
    return Response.json(
      { error: '无效或过大的 Range 请求' },
      { status: 416, headers: ERROR_HEADERS },
    );
  }

  const { env } = await getCloudflareContext({ async: true });
  if (env.MAGIRECO_VOICE_R2) {
    return getFromR2(env.MAGIRECO_VOICE_R2, voiceId, safeRange);
  }
  return getFromPublicOrigin(voiceId, safeRange);
}
