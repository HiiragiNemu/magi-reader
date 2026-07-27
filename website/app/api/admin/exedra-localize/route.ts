import { NextRequest, NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import { authenticateProofreadingAdmin } from '@/lib/admin-auth';
import {
  EXEDRA_STORIES,
  listCachedExedraLocalizations,
  loadOrCreateExedraLocalization,
} from '@/lib/exedra-localization';

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };
const MAX_BODY = 16 * 1024;
const errorResponse = (error: string, status: number) =>
  NextResponse.json({ error }, { status, headers: NO_STORE_HEADERS });

const candidates = EXEDRA_STORIES
  .filter(entry => !entry.path_cn && entry.path_jp)
  .sort((left, right) => left.id.localeCompare(right.id, 'en', { numeric: true }));

const summary = async (env: CloudflareEnv) => {
  const cached = env.SUBMISSIONS_KV
    ? await listCachedExedraLocalizations(env.SUBMISSIONS_KV)
    : [];
  const counts = {
    local_human: EXEDRA_STORIES.filter(entry => Boolean(entry.path_cn)).length,
    official_tw_human: 0,
    exedra_wiki_human: 0,
    machine_translation: 0,
  };
  for (const record of cached) counts[record.provenance] += 1;
  return {
    total: EXEDRA_STORIES.length,
    candidates: candidates.length,
    cached: cached.length,
    remaining: Math.max(0, candidates.length - cached.length),
    counts,
    records: cached,
  };
};

export async function GET(request: NextRequest) {
  const { env } = await getCloudflareContext({ async: true });
  const authentication = await authenticateProofreadingAdmin(request, env);
  if (!authentication.ok) return errorResponse(authentication.error, authentication.status);
  return NextResponse.json(
    { reviewer: authentication.identity.label, ...(await summary(env)) },
    { headers: NO_STORE_HEADERS },
  );
}

export async function POST(request: NextRequest) {
  const { env } = await getCloudflareContext({ async: true });
  const authentication = await authenticateProofreadingAdmin(request, env);
  if (!authentication.ok) return errorResponse(authentication.error, authentication.status);
  if (!env.SUBMISSIONS_KV) return errorResponse('Exedra 中文缓存 KV 尚未配置', 503);
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
      const localized = await loadOrCreateExedraLocalization({ request, env, entry });
      results.push({
        story_id: entry.id,
        source_identity: entry.source_identity,
        success: true,
        provenance: localized.provenance,
        source_url: localized.source_url,
        cn_sha256: localized.cn_sha256,
      });
    } catch (error) {
      results.push({
        story_id: entry.id,
        source_identity: entry.source_identity,
        success: false,
        error: error instanceof Error ? error.message.slice(0, 1000) : '未知错误',
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
      summary: await summary(env),
    },
    { headers: NO_STORE_HEADERS },
  );
}
