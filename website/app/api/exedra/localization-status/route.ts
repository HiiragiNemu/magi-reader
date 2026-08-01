import { NextRequest, NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import {
  listCachedExedraLocalizations,
  loadExedraStories,
} from '@/lib/exedra-localization';

const NO_STORE_HEADERS = {
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
};

export async function GET(request: NextRequest) {
  try {
    const { env } = await getCloudflareContext({ async: true });
    if (!env.SUBMISSIONS_KV) {
      return NextResponse.json(
        {
          version: 1,
          total: 0,
          entries: [],
          database_configured: false,
        },
        { headers: NO_STORE_HEADERS },
      );
    }

    const stories = await loadExedraStories({ request, env });
    const storiesById = new Map(stories.map(story => [story.id, story]));
    const records = await listCachedExedraLocalizations(env.SUBMISSIONS_KV);
    const entries = records.flatMap(record => {
      const story = storiesById.get(record.story_id);
      if (
        !story ||
        story.path_cn ||
        story.source_identity !== record.source_identity
      ) {
        return [];
      }
      return [{
        story_id: story.id,
        source_identity: story.source_identity,
        provenance: record.provenance,
        source_url: record.source_url,
        jp_sha256: record.jp_sha256,
        cn_sha256: record.cn_sha256,
        generated_at: record.generated_at,
      }];
    });

    entries.sort((left, right) =>
      left.story_id.localeCompare(right.story_id, 'en', { numeric: true }),
    );
    return NextResponse.json(
      {
        version: 1,
        total: entries.length,
        entries,
        database_configured: true,
      },
      { headers: NO_STORE_HEADERS },
    );
  } catch (error) {
    console.error('Failed to read trusted Exedra localization status', error);
    return NextResponse.json(
      { error: 'Exedra 可信中文状态暂时不可用' },
      { status: 500, headers: NO_STORE_HEADERS },
    );
  }
}
