import {
  contentRangeTotalExceedsLimit,
  createBoundedVoiceStream,
  getMagirecoVoiceUpstreamUrl,
  MAX_VOICE_BYTES,
  normalizeVoiceRange,
  parseBoundedContentLength,
} from '@/lib/audio/voice-proxy';
import { isMagirecoVoiceId } from '@/lib/audio/voice-cue';

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

  const upstreamHeaders = new Headers({
    Accept: 'application/octet-stream',
  });
  if (safeRange) upstreamHeaders.set('Range', safeRange);

  let upstream: Response;
  try {
    upstream = await fetch(getMagirecoVoiceUpstreamUrl(voiceId), {
      cache: 'no-store',
      headers: upstreamHeaders,
      redirect: 'error',
    });
  } catch (error) {
    console.error('Magia Record voice upstream request failed', error);
    return Response.json(
      { error: '魔法纪录语音源暂时不可用' },
      { status: 502, headers: ERROR_HEADERS },
    );
  }

  if (upstream.status !== 200 && upstream.status !== 206) {
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
    void upstream.body.cancel('Voice object exceeds size limit');
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

  return new Response(createBoundedVoiceStream(upstream.body), {
    status: upstream.status,
    headers,
  });
}
