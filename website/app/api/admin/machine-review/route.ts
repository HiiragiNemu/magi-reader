import { NextRequest, NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';
import { authenticateProofreadingAdmin } from '@/lib/admin-auth';
import {
  MACHINE_TRANSLATION_ID_SET,
  MACHINE_TRANSLATION_MANIFEST,
  listMachineTranslationReviewStates,
  setMachineTranslationReviewState,
} from '@/lib/machine-translation-review';
import { sanitizeMultiline } from '@/lib/proofreading';

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };
const errorResponse = (error: string, status: number) =>
  NextResponse.json({ error }, { status, headers: NO_STORE_HEADERS });

export async function GET(request: NextRequest) {
  const { env } = await getCloudflareContext({ async: true });
  const authentication = await authenticateProofreadingAdmin(request, env);
  if (!authentication.ok) return errorResponse(authentication.error, authentication.status);
  if (!env.SUBMISSIONS_KV) return errorResponse('投稿数据库尚未配置', 503);
  const states = await listMachineTranslationReviewStates(env.SUBMISSIONS_KV);
  const verified = MACHINE_TRANSLATION_MANIFEST.entries.filter(
    entry => states[entry.story_id]?.verified === true,
  ).length;
  return NextResponse.json(
    {
      reviewer: authentication.identity.label,
      total: MACHINE_TRANSLATION_MANIFEST.total,
      verified,
      remaining: Math.max(0, MACHINE_TRANSLATION_MANIFEST.total - verified),
      states,
    },
    { headers: NO_STORE_HEADERS },
  );
}

export async function PATCH(request: NextRequest) {
  const { env } = await getCloudflareContext({ async: true });
  const authentication = await authenticateProofreadingAdmin(request, env);
  if (!authentication.ok) return errorResponse(authentication.error, authentication.status);
  if (!env.SUBMISSIONS_KV) return errorResponse('投稿数据库尚未配置', 503);
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return errorResponse('请求必须是有效 JSON', 400);
  }
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return errorResponse('请求格式错误', 400);
  }
  const record = body as Record<string, unknown>;
  const storyId = typeof record.story_id === 'string' ? record.story_id.trim() : '';
  if (!MACHINE_TRANSLATION_ID_SET.has(storyId)) {
    return errorResponse('该剧情不在机器翻译人工校验清单中', 400);
  }
  if (typeof record.verified !== 'boolean') {
    return errorResponse('verified 必须是布尔值', 400);
  }
  const note = sanitizeMultiline(record.note, 1000) ||
    (record.verified ? '管理员确认已完成人工校验' : '恢复机器翻译待校标记');
  const state = {
    verified: record.verified,
    reviewer: authentication.identity.label,
    reviewed_at: new Date().toISOString(),
    note,
  };
  await setMachineTranslationReviewState(env.SUBMISSIONS_KV, storyId, state);
  return NextResponse.json({ success: true, story_id: storyId, state }, { headers: NO_STORE_HEADERS });
}
