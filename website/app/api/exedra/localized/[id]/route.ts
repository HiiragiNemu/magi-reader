import { NextRequest } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import {
  findExedraStory,
  loadOrCreateExedraLocalization,
} from '@/lib/exedra-localization';

const TEXT_HEADERS = {
  'Content-Type': 'text/plain; charset=utf-8',
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
};

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const entry = findExedraStory(decodeURIComponent(id));
    if (!entry) return new Response('没有找到该 Exedra 剧情。', { status: 404, headers: TEXT_HEADERS });
    if (entry.path_cn) {
      return Response.redirect(new URL(entry.path_cn, request.url), 307);
    }
    const { env } = await getCloudflareContext({ async: true });
    const record = await loadOrCreateExedraLocalization({ request, env, entry });
    return new Response(record.text, {
      status: 200,
      headers: {
        ...TEXT_HEADERS,
        'X-MagiReader-Translation-Provenance': record.provenance,
        'X-MagiReader-Translation-Sha256': record.cn_sha256,
        ...(record.source_url ? { 'X-MagiReader-Translation-Source': record.source_url } : {}),
      },
    });
  } catch (error) {
    console.error('Exedra localization failed', error);
    const message = error instanceof Error ? error.message : 'Exedra 中文生成失败';
    return new Response(message, { status: 502, headers: TEXT_HEADERS });
  }
}
