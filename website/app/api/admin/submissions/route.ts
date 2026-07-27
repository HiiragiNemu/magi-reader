import { NextRequest, NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import { authenticateProofreadingAdmin } from '@/lib/admin-auth';
import {
  isProofreadingStatus,
  toProofreadingListItem,
  type ProofreadingStatus,
} from '@/lib/proofreading';
import { listProofreadingSubmissions } from '@/lib/proofreading-store';

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };
const ALLOWED_LIST_STATUSES = new Set<ProofreadingStatus>([
  'pending',
  'held',
  'approved',
  'processing',
  'stale',
  'rejected',
  'pr_created',
  'merged',
  'closed',
]);

const errorResponse = (error: string, status: number) =>
  NextResponse.json({ error }, { status, headers: NO_STORE_HEADERS });

export async function GET(request: NextRequest) {
  try {
    const { env } = await getCloudflareContext({ async: true });
    const authentication = await authenticateProofreadingAdmin(request, env);
    if (!authentication.ok) {
      return errorResponse(authentication.error, authentication.status);
    }
    const kv = env.SUBMISSIONS_KV;
    if (!kv) return errorResponse('投稿数据库尚未配置', 503);

    const rawStatus = request.nextUrl.searchParams.get('status') || 'pending';
    if (!isProofreadingStatus(rawStatus) || !ALLOWED_LIST_STATUSES.has(rawStatus)) {
      return errorResponse('状态筛选无效', 400);
    }
    const parsedLimit = Number.parseInt(
      request.nextUrl.searchParams.get('limit') || '20',
      10,
    );
    const limit = Number.isFinite(parsedLimit)
      ? Math.min(50, Math.max(1, parsedLimit))
      : 20;
    const cursor = request.nextUrl.searchParams.get('cursor') || undefined;
    const listed = await listProofreadingSubmissions(kv, rawStatus, {
      limit,
      cursor,
    });
    return NextResponse.json(
      {
        submissions: listed.records.map(toProofreadingListItem),
        cursor: listed.cursor,
        list_complete: listed.listComplete,
        reviewer: authentication.identity.label,
      },
      { headers: NO_STORE_HEADERS },
    );
  } catch (error: unknown) {
    console.error('Failed to list proofreading submissions', error);
    return errorResponse('服务器暂时无法处理查询', 500);
  }
}
