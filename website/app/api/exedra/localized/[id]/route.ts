import { NextRequest } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import {
  findExedraStory,
  getTrustedCachedExedraLocalization,
  readExedraJapaneseText,
  sha256ExedraText,
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

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const entry = findExedraStory(decodeURIComponent(id));
    if (!entry) {
      return new Response('没有找到该 Exedra 剧情。', {
        status: 404,
        headers: TEXT_HEADERS,
      });
    }
    if (entry.path_cn) {
      return Response.redirect(new URL(entry.path_cn, request.url), 307);
    }

    const { env } = await getCloudflareContext({ async: true });
    const jpText = await readExedraJapaneseText({ request, env, entry });
    const jpSha256 = await sha256ExedraText(jpText);
    const cached = await getTrustedCachedExedraLocalization({
      kv: env.SUBMISSIONS_KV,
      entry,
      jpSha256,
    });
    const initial = cached ?? await tryExactWikiLocalization({ env, entry, jpText });
    if (!initial) {
      return new Response(
        '该剧情目前没有本地人工中文、官方台服中文或已验证的 Exedra Wiki 中文。',
        { status: 404, headers: TEXT_HEADERS },
      );
    }

    const text = canonicalizeLocalizedSpeakers(jpText, initial.text);
    const cnSha256 = await sha256Text(text);
    return new Response(text, {
      status: 200,
      headers: {
        ...TEXT_HEADERS,
        'X-MagiReader-Translation-Provenance': initial.provenance,
        'X-MagiReader-Translation-Sha256': cnSha256,
        ...(initial.source_url
          ? { 'X-MagiReader-Translation-Source': initial.source_url }
          : {}),
      },
    });
  } catch (error) {
    console.error('Trusted Exedra localization failed', error);
    const message = error instanceof Error
      ? error.message
      : 'Exedra 中文读取失败';
    return new Response(message, { status: 502, headers: TEXT_HEADERS });
  }
}
