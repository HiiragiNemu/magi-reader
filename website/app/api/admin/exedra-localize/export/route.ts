import { NextRequest, NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import { authenticateProofreadingAdmin } from '@/lib/admin-auth';
import { findExedraStory } from '@/lib/exedra-localization';

const PREFIX = 'exedra-localization:v1:';
const NO_STORE_HEADERS = {
  'Cache-Control': 'no-store',
  'Content-Disposition': 'attachment; filename="exedra-localization-cache-v1.json"',
};

export async function GET(request: NextRequest) {
  const { env } = await getCloudflareContext({ async: true });
  const authentication = await authenticateProofreadingAdmin(request, env);
  if (!authentication.ok) {
    return NextResponse.json(
      { error: authentication.error },
      { status: authentication.status, headers: { 'Cache-Control': 'no-store' } },
    );
  }
  if (!env.SUBMISSIONS_KV) {
    return NextResponse.json(
      { error: 'Exedra 中文缓存 KV 尚未配置' },
      { status: 503, headers: { 'Cache-Control': 'no-store' } },
    );
  }

  const records: Array<Record<string, unknown>> = [];
  let cursor: string | undefined;
  do {
    const page = await env.SUBMISSIONS_KV.list({ prefix: PREFIX, limit: 1000, cursor });
    for (const key of page.keys) {
      const raw = await env.SUBMISSIONS_KV.get(key.name);
      if (!raw) continue;
      try {
        const value = JSON.parse(raw) as Record<string, unknown>;
        const storyId = typeof value.story_id === 'string' ? value.story_id : '';
        const story = findExedraStory(storyId);
        if (
          value.version !== 1 || !story ||
          typeof value.source_identity !== 'string' ||
          value.source_identity !== story.source_identity ||
          typeof value.text !== 'string' || !value.text.trim() ||
          typeof value.jp_sha256 !== 'string' || !/^[a-f0-9]{64}$/u.test(value.jp_sha256) ||
          typeof value.cn_sha256 !== 'string' || !/^[a-f0-9]{64}$/u.test(value.cn_sha256)
        ) {
          continue;
        }
        records.push({
          ...value,
          category: story.category,
          folder: story.folder,
          title: story.title,
          path_jp: story.path_jp,
        });
      } catch {
        // Skip malformed cache records; never export an unbound payload.
      }
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);

  records.sort((left, right) =>
    String(left.source_identity).localeCompare(String(right.source_identity), 'en', { numeric: true }),
  );
  return NextResponse.json(
    {
      version: 1,
      exported_at: new Date().toISOString(),
      reviewer: authentication.identity.label,
      total: records.length,
      records,
    },
    { headers: NO_STORE_HEADERS },
  );
}
