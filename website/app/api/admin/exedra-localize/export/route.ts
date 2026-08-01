import { NextRequest, NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import { authenticateProofreadingAdmin } from '@/lib/admin-auth';
import {
  EXEDRA_CACHE_PREFIX,
  loadExedraStories,
  parseCachedExedraLocalization,
} from '@/lib/exedra-localization';

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

  const stories = await loadExedraStories({ request, env });
  const storiesById = new Map(stories.map(story => [story.id, story]));
  const records: Array<Record<string, unknown>> = [];
  let cursor: string | undefined;
  do {
    const page = await env.SUBMISSIONS_KV.list({
      prefix: EXEDRA_CACHE_PREFIX,
      limit: 1000,
      cursor,
    });
    for (const key of page.keys) {
      const value = parseCachedExedraLocalization(
        await env.SUBMISSIONS_KV.get(key.name),
      );
      if (!value) continue;
      const story = storiesById.get(value.story_id);
      if (!story || value.source_identity !== story.source_identity) continue;
      records.push({
        ...value,
        category: story.category,
        folder: story.folder,
        title: story.title,
        path_jp: story.path_jp,
      });
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);

  records.sort((left, right) =>
    String(left.source_identity).localeCompare(
      String(right.source_identity),
      'en',
      { numeric: true },
    ),
  );
  return NextResponse.json(
    {
      version: 1,
      policy: 'trusted_exedra_sources_only',
      exported_at: new Date().toISOString(),
      reviewer: authentication.identity.label,
      total: records.length,
      records,
    },
    { headers: NO_STORE_HEADERS },
  );
}
