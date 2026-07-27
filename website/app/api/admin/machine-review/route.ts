import { NextRequest, NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';
import { authenticateProofreadingAdmin } from '@/lib/admin-auth';
import {
  findExedraStory,
  listCachedExedraLocalizations,
} from '@/lib/exedra-localization';
import {
  MACHINE_TRANSLATION_ID_SETS,
  MACHINE_TRANSLATION_MANIFESTS,
  listMachineTranslationReviewStates,
  machineTranslationStateKey,
  parseMachineTranslationReviewState,
  setMachineTranslationReviewState,
  type MachineTranslationReviewState,
  type MachineTranslationSystem,
} from '@/lib/machine-translation-review';
import { sanitizeMultiline } from '@/lib/proofreading';

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };
const EXEDRA_REVIEW_PREFIX = 'proofreading:machine-review:exedra:';
const errorResponse = (error: string, status: number) =>
  NextResponse.json({ error }, { status, headers: NO_STORE_HEADERS });

const systemFrom = (value: unknown): MachineTranslationSystem | null =>
  value === 'magireco' || value === 'exedra' ? value : null;

const dynamicExedra = async (kv: SubmissionKvNamespace) => {
  const cached = await listCachedExedraLocalizations(kv);
  const machine = cached.filter(record => record.provenance === 'machine_translation');
  const allowed = new Set(machine.map(record => record.story_id));
  const states: Record<string, MachineTranslationReviewState> = {};
  let cursor: string | undefined;
  do {
    const page = await kv.list({ prefix: EXEDRA_REVIEW_PREFIX, limit: 1000, cursor });
    for (const key of page.keys) {
      const storyId = key.name.slice(EXEDRA_REVIEW_PREFIX.length);
      if (!allowed.has(storyId)) continue;
      const state = parseMachineTranslationReviewState(await kv.get(key.name));
      if (state) states[storyId] = state;
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  const entries = machine.flatMap(record => {
    const story = findExedraStory(record.story_id);
    return story ? [{
      story_id: story.id,
      category: story.category,
      folder: story.folder,
      title: story.title,
      source_identity: story.source_identity,
      repository_path_cn: '',
      path_cn: `/api/exedra/localized/${encodeURIComponent(story.id)}`,
      path_jp: story.path_jp,
      provenance: record.provenance,
    }] : [];
  });
  return { allowed, states, entries };
};

export async function GET(request: NextRequest) {
  const { env } = await getCloudflareContext({ async: true });
  const authentication = await authenticateProofreadingAdmin(request, env);
  if (!authentication.ok) return errorResponse(authentication.error, authentication.status);
  if (!env.SUBMISSIONS_KV) return errorResponse('投稿数据库尚未配置', 503);
  const system = systemFrom(request.nextUrl.searchParams.get('system')) ?? 'magireco';
  if (system === 'exedra') {
    const dynamic = await dynamicExedra(env.SUBMISSIONS_KV);
    const verified = dynamic.entries.filter(
      entry => dynamic.states[entry.story_id]?.verified === true,
    ).length;
    return NextResponse.json({
      reviewer: authentication.identity.label,
      system,
      definition: 'exedra_cached_provenance_machine_translation_only',
      total: dynamic.entries.length,
      verified,
      remaining: Math.max(0, dynamic.entries.length - verified),
      states: dynamic.states,
      entries: dynamic.entries,
    }, { headers: NO_STORE_HEADERS });
  }
  const manifest = MACHINE_TRANSLATION_MANIFESTS.magireco;
  const states = await listMachineTranslationReviewStates(env.SUBMISSIONS_KV, 'magireco');
  const verified = manifest.entries.filter(entry => states[entry.story_id]?.verified === true).length;
  return NextResponse.json({
    reviewer: authentication.identity.label,
    system,
    definition: manifest.definition,
    total: manifest.total,
    verified,
    remaining: Math.max(0, manifest.total - verified),
    states,
    entries: manifest.entries,
  }, { headers: NO_STORE_HEADERS });
}

export async function PATCH(request: NextRequest) {
  const { env } = await getCloudflareContext({ async: true });
  const authentication = await authenticateProofreadingAdmin(request, env);
  if (!authentication.ok) return errorResponse(authentication.error, authentication.status);
  if (!env.SUBMISSIONS_KV) return errorResponse('投稿数据库尚未配置', 503);
  let body: unknown;
  try { body = await request.json(); } catch { return errorResponse('请求必须是有效 JSON', 400); }
  if (!body || typeof body !== 'object' || Array.isArray(body)) return errorResponse('请求格式错误', 400);
  const record = body as Record<string, unknown>;
  const system = systemFrom(record.system) ?? 'magireco';
  const storyId = typeof record.story_id === 'string' ? record.story_id.trim() : '';
  if (typeof record.verified !== 'boolean') return errorResponse('verified 必须是布尔值', 400);
  const note = sanitizeMultiline(record.note, 1000) ||
    (record.verified ? '管理员确认已完成人工校验' : '恢复机器翻译待校标记');
  const state: MachineTranslationReviewState = {
    verified: record.verified,
    reviewer: authentication.identity.label,
    reviewed_at: new Date().toISOString(),
    note,
  };
  if (system === 'exedra') {
    const dynamic = await dynamicExedra(env.SUBMISSIONS_KV);
    if (!dynamic.allowed.has(storyId)) return errorResponse('该剧情不是已生成的 Exedra 机器翻译', 400);
    await env.SUBMISSIONS_KV.put(machineTranslationStateKey(storyId, 'exedra'), JSON.stringify(state));
  } else {
    if (!MACHINE_TRANSLATION_ID_SETS.magireco.has(storyId)) {
      return errorResponse('该剧情不在魔法纪录机器翻译清单中', 400);
    }
    await setMachineTranslationReviewState(env.SUBMISSIONS_KV, storyId, state, 'magireco');
  }
  return NextResponse.json(
    { success: true, system, story_id: storyId, state },
    { headers: NO_STORE_HEADERS },
  );
}
