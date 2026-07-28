import { NextRequest, NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import { authenticateProofreadingAdmin } from '@/lib/admin-auth';
import {
  EXEDRA_CACHE_PREFIX,
  getTrustedCachedExedraLocalization,
  listCachedExedraLocalizations,
  loadExedraStories,
  readExedraJapaneseText,
  sha256ExedraText,
  type ExedraStoryEntry,
} from '@/lib/exedra-localization';
import { tryExactWikiLocalization } from '@/lib/exedra-wiki-exact';

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };
const MAX_BODY = 16 * 1024;
const WIKI_MISS_PREFIX = 'exedra-wiki-miss:v1:';
const LEGACY_EXEDRA_REVIEW_PREFIX = 'proofreading:machine-review:exedra:';
const errorResponse = (error: string, status: number) =>
  NextResponse.json({ error }, { status, headers: NO_STORE_HEADERS });

const candidatesFor = (stories: ExedraStoryEntry[]) =>
  stories
    .filter(entry =>
      entry.category === 'exedra_character' && !entry.path_cn && entry.path_jp,
    )
    .sort((left, right) =>
      left.id.localeCompare(right.id, 'en', { numeric: true }),
    );

const listKeys = async (kv: SubmissionKvNamespace, prefix: string) => {
  const names: string[] = [];
  let cursor: string | undefined;
  do {
    const page = await kv.list({ prefix, limit: 1000, cursor });
    names.push(...page.keys.map(key => key.name));
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return names;
};

const legacyMachineCacheKeys = async (kv: SubmissionKvNamespace) => {
  const result: string[] = [];
  for (const key of await listKeys(kv, EXEDRA_CACHE_PREFIX)) {
    const raw = await kv.get(key);
    if (!raw) continue;
    try {
      const value = JSON.parse(raw) as { provenance?: unknown };
      if (value.provenance === 'machine_translation') result.push(key);
    } catch {
      // Malformed records are not deleted by this targeted cleanup.
    }
  }
  return result;
};

const summary = async (
  env: CloudflareEnv,
  stories: ExedraStoryEntry[],
) => {
  const candidates = candidatesFor(stories);
  const cached = env.SUBMISSIONS_KV
    ? await listCachedExedraLocalizations(env.SUBMISSIONS_KV)
    : [];
  const cachedIds = new Set(cached.map(record => record.story_id));
  const missKeys = env.SUBMISSIONS_KV
    ? await listKeys(env.SUBMISSIONS_KV, WIKI_MISS_PREFIX)
    : [];
  const missIds = new Set(
    missKeys.map(key => key.slice(WIKI_MISS_PREFIX.length)),
  );
  const counts = {
    local_human: stories.filter(entry => Boolean(entry.path_cn)).length,
    official_tw_human: cached.filter(
      record => record.provenance === 'official_tw_human',
    ).length,
    exedra_wiki_human: cached.filter(
      record => record.provenance === 'exedra_wiki_human',
    ).length,
  };
  const reviewed = candidates.filter(entry =>
    cachedIds.has(entry.id) || missIds.has(entry.id),
  ).length;
  const legacyMachine = env.SUBMISSIONS_KV
    ? (await legacyMachineCacheKeys(env.SUBMISSIONS_KV)).length
    : 0;
  return {
    total: stories.length,
    wiki_candidates: candidates.length,
    wiki_reviewed: reviewed,
    wiki_missing: missIds.size,
    remaining: Math.max(0, candidates.length - reviewed),
    counts,
    legacy_machine_cache: legacyMachine,
    records: cached,
  };
};

export async function GET(request: NextRequest) {
  const { env } = await getCloudflareContext({ async: true });
  const authentication = await authenticateProofreadingAdmin(request, env);
  if (!authentication.ok) {
    return errorResponse(authentication.error, authentication.status);
  }
  const stories = await loadExedraStories({ request, env });
  return NextResponse.json(
    { reviewer: authentication.identity.label, ...(await summary(env, stories)) },
    { headers: NO_STORE_HEADERS },
  );
}

export async function POST(request: NextRequest) {
  const { env } = await getCloudflareContext({ async: true });
  const authentication = await authenticateProofreadingAdmin(request, env);
  if (!authentication.ok) {
    return errorResponse(authentication.error, authentication.status);
  }
  if (!env.SUBMISSIONS_KV) {
    return errorResponse('Exedra 中文缓存 KV 尚未配置', 503);
  }
  const declared = Number(request.headers.get('content-length'));
  if (Number.isSafeInteger(declared) && declared > MAX_BODY) {
    return errorResponse('批处理请求过大', 413);
  }
  let body: unknown = {};
  try {
    body = await request.json();
  } catch {
    return errorResponse('批处理请求必须是 JSON', 400);
  }
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return errorResponse('批处理请求格式错误', 400);
  }

  const stories = await loadExedraStories({ request, env });
  const candidates = candidatesFor(stories);
  const record = body as Record<string, unknown>;
  const cursor = Number.isSafeInteger(record.cursor) && Number(record.cursor) >= 0
    ? Number(record.cursor)
    : 0;
  const limit = Number.isSafeInteger(record.limit)
    ? Math.min(3, Math.max(1, Number(record.limit)))
    : 1;
  const selected = candidates.slice(cursor, cursor + limit);
  const results: Array<Record<string, unknown>> = [];

  for (const entry of selected) {
    try {
      const jpText = await readExedraJapaneseText({ request, env, entry });
      const jpSha256 = await sha256ExedraText(jpText);
      const cached = await getTrustedCachedExedraLocalization({
        kv: env.SUBMISSIONS_KV,
        entry,
        jpSha256,
      });
      const localized = cached ?? await tryExactWikiLocalization({
        env,
        entry,
        jpText,
      });
      if (localized) {
        await env.SUBMISSIONS_KV.delete(`${WIKI_MISS_PREFIX}${entry.id}`);
        results.push({
          story_id: entry.id,
          source_identity: entry.source_identity,
          success: true,
          outcome: cached ? 'cached' : 'wiki_found',
          provenance: localized.provenance,
          source_url: localized.source_url,
          cn_sha256: localized.cn_sha256,
        });
      } else {
        await env.SUBMISSIONS_KV.put(
          `${WIKI_MISS_PREFIX}${entry.id}`,
          JSON.stringify({ checked_at: new Date().toISOString() }),
          { expirationTtl: 7 * 24 * 60 * 60 },
        );
        results.push({
          story_id: entry.id,
          source_identity: entry.source_identity,
          success: true,
          outcome: 'wiki_not_found',
        });
      }
    } catch (error) {
      results.push({
        story_id: entry.id,
        source_identity: entry.source_identity,
        success: false,
        outcome: 'error',
        error: error instanceof Error
          ? error.message.slice(0, 1000)
          : '未知错误',
      });
    }
  }

  const nextCursor = cursor + selected.length;
  return NextResponse.json(
    {
      success: results.every(item => item.success === true),
      cursor,
      next_cursor: nextCursor < candidates.length ? nextCursor : null,
      complete: nextCursor >= candidates.length,
      processed: results,
      summary: await summary(env, stories),
    },
    { headers: NO_STORE_HEADERS },
  );
}

export async function DELETE(request: NextRequest) {
  const { env } = await getCloudflareContext({ async: true });
  const authentication = await authenticateProofreadingAdmin(request, env);
  if (!authentication.ok) {
    return errorResponse(authentication.error, authentication.status);
  }
  if (!env.SUBMISSIONS_KV) {
    return errorResponse('Exedra 中文缓存 KV 尚未配置', 503);
  }
  const stories = await loadExedraStories({ request, env });
  const scope = request.nextUrl.searchParams.get('scope');
  let keys: string[];
  if (scope === 'legacy-machine') {
    keys = [
      ...await legacyMachineCacheKeys(env.SUBMISSIONS_KV),
      ...await listKeys(env.SUBMISSIONS_KV, LEGACY_EXEDRA_REVIEW_PREFIX),
    ];
  } else if (scope === 'wiki-misses') {
    keys = await listKeys(env.SUBMISSIONS_KV, WIKI_MISS_PREFIX);
  } else {
    return errorResponse('不支持的清理范围', 400);
  }
  const uniqueKeys = [...new Set(keys)];
  for (const key of uniqueKeys) await env.SUBMISSIONS_KV.delete(key);
  return NextResponse.json(
    {
      success: true,
      scope,
      deleted: uniqueKeys.length,
      summary: await summary(env, stories),
    },
    { headers: NO_STORE_HEADERS },
  );
}
