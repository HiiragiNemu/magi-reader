import { NextRequest } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import {
  findExedraStory,
  loadOrCreateExedraLocalization,
} from '@/lib/exedra-localization';
import {
  canonicalizeLocalizedSpeakers,
  sha256Text,
  tryExactWikiLocalization,
} from '@/lib/exedra-wiki-exact';

const TEXT_HEADERS = {
  'Content-Type': 'text/plain; charset=utf-8',
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
};
const MAX_SOURCE_BYTES = 8 * 1024 * 1024;
const CACHE_PREFIX = 'exedra-localization:v1:';

const readJpSource = async (
  request: NextRequest,
  env: CloudflareEnv,
  path: string,
): Promise<string> => {
  const source = new Request(new URL(path, request.url), {
    headers: { Accept: 'text/plain' },
  });
  const response = env.ASSETS ? await env.ASSETS.fetch(source) : await fetch(source);
  if (!response.ok) throw new Error(`Exedra 日文剧情读取失败（HTTP ${response.status}）`);
  const declared = Number(response.headers.get('content-length'));
  if (Number.isSafeInteger(declared) && declared > MAX_SOURCE_BYTES) {
    await response.body?.cancel('source too large');
    throw new Error('Exedra 日文剧情超过 8 MiB');
  }
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength > MAX_SOURCE_BYTES) throw new Error('Exedra 日文剧情超过 8 MiB');
  return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
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
    const jpText = await readJpSource(request, env, entry.path_jp);
    const exactWiki = await tryExactWikiLocalization({ env, entry, jpText });
    const initial = exactWiki ?? await loadOrCreateExedraLocalization({ request, env, entry });
    const text = canonicalizeLocalizedSpeakers(jpText, initial.text);
    const cnSha256 = await sha256Text(text);
    const record = {
      ...initial,
      text,
      cn_sha256: cnSha256,
    };
    if (env.SUBMISSIONS_KV && (initial.text !== text || initial.cn_sha256 !== cnSha256)) {
      await env.SUBMISSIONS_KV.put(`${CACHE_PREFIX}${entry.id}`, JSON.stringify(record));
    }
    return new Response(text, {
      status: 200,
      headers: {
        ...TEXT_HEADERS,
        'X-MagiReader-Translation-Provenance': record.provenance,
        'X-MagiReader-Translation-Sha256': cnSha256,
        ...(record.source_url ? { 'X-MagiReader-Translation-Source': record.source_url } : {}),
      },
    });
  } catch (error) {
    console.error('Exedra localization failed', error);
    const message = error instanceof Error ? error.message : 'Exedra 中文生成失败';
    return new Response(message, { status: 502, headers: TEXT_HEADERS });
  }
}
