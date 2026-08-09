import {
  TANGYUAN_V012_SOURCE,
  extractPinnedTangYuanFont,
} from '@/lib/exedra-font-assets';

export const runtime = 'edge';
export const dynamic = 'force-dynamic';

export async function GET(): Promise<Response> {
  try {
    const upstream = await fetch(TANGYUAN_V012_SOURCE.assetUrl, {
      cache: 'force-cache',
      redirect: 'follow',
      signal: AbortSignal.timeout(45_000),
    });
    if (!upstream.ok) {
      await upstream.body?.cancel('上游字体请求失败');
      return new Response('Pinned font source is temporarily unavailable.', {
        status: 502,
      });
    }
    const declaredLength = Number(upstream.headers.get('content-length'));
    if (
      Number.isFinite(declaredLength) &&
      declaredLength !== TANGYUAN_V012_SOURCE.archiveBytes
    ) {
      await upstream.body?.cancel('上游字体大小不符');
      return new Response('Pinned font source failed integrity validation.', {
        status: 502,
      });
    }
    const archive = new Uint8Array(await upstream.arrayBuffer());
    const font = await extractPinnedTangYuanFont(archive);
    const responseBytes = new Uint8Array(font.byteLength);
    responseBytes.set(font);
    return new Response(responseBytes.buffer, {
      status: 200,
      headers: {
        'cache-control': 'public, max-age=31536000, immutable',
        'content-disposition':
          'inline; filename="MaoKenTangYuan-beta0.12-20210702.ttf"',
        'content-length': String(font.byteLength),
        'content-type': 'font/ttf',
        'x-content-type-options': 'nosniff',
        'x-font-sha256': TANGYUAN_V012_SOURCE.fontSha256,
        'x-font-source-license': 'SIL-OFL-1.1',
      },
    });
  } catch {
    return new Response('Pinned font source failed integrity validation.', {
      status: 502,
    });
  }
}
