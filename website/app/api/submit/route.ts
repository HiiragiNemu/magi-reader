import { NextRequest, NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import { getRateLimitIdentity } from '@/lib/submission-security';
import { createKnownStoryIds } from '@/lib/story-id-membership';
import {
  PROOFREADING_SCHEMA_VERSION,
  isSafeSourceIdentity,
  isSafeStoryWebPath,
  isSha256,
  normalizeProofreadingText,
  sanitizeMultiline,
  sanitizeSingleLine,
  sha256Text,
  type ProofreadingPublicStatus,
  type ProofreadingSubmission,
} from '@/lib/proofreading';
import {
  createProofreadingSubmission,
  getProofreadingSubmission,
  proofreadingIndexKey,
  transitionProofreadingSubmission,
} from '@/lib/proofreading-store';
import { verifyTurnstileToken } from '@/lib/turnstile-server';
import { readProofreadingPullRequestState } from '@/lib/github-proofreading';
import storyIds from '../../../public/data/story_ids.generated.json';

const RATE_LIMIT_PREFIX = 'proofreading:ratelimit:';
const RATE_LIMIT_WINDOW_SECONDS = 10 * 60;
const RATE_LIMIT_MAX_SUBMISSIONS = 5;
const MAX_REQUEST_BYTES = 2 * 1024 * 1024;
const MAX_STORY_ID_LENGTH = 256;
const MAX_CONTENT_LENGTH = 500_000;
const MIN_CONTENT_LENGTH = 10;
const MAX_NICKNAME_LENGTH = 40;
const MAX_NOTE_LENGTH = 1_000;
const MAX_SOURCE_IDENTITY_LENGTH = 1_024;
const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };
const KNOWN_STORY_IDS = createKnownStoryIds(storyIds);

const errorResponse = (error: string, status: number, headers?: HeadersInit) =>
  NextResponse.json(
    { error },
    {
      status,
      headers: {
        ...NO_STORE_HEADERS,
        ...headers,
      },
    },
  );

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

type BodyResult =
  | { ok: true; value: unknown }
  | { ok: false; status: 400 | 413; error: string };

const readBoundedJson = async (request: NextRequest): Promise<BodyResult> => {
  const declaredLength = request.headers.get('content-length');
  if (declaredLength) {
    const parsedLength = Number(declaredLength);
    if (Number.isFinite(parsedLength) && parsedLength > MAX_REQUEST_BYTES) {
      return { ok: false, status: 413, error: '提交内容过大' };
    }
  }
  if (!request.body) {
    return { ok: false, status: 400, error: '请求内容为空' };
  }

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    totalBytes += value.byteLength;
    if (totalBytes > MAX_REQUEST_BYTES) {
      await reader.cancel();
      return { ok: false, status: 413, error: '提交内容过大' };
    }
    chunks.push(value);
  }

  const bodyBytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bodyBytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bodyBytes);
    return { ok: true, value: JSON.parse(text) as unknown };
  } catch {
    return { ok: false, status: 400, error: '请求必须是有效的 JSON' };
  }
};

type ValidSubmission = {
  storyId: string;
  content: string;
  nickname: string;
  note: string;
  baseSha256: string;
  baseContentSha256: string;
  catalogSha256: string;
  sourcePathCn: string;
  sourcePathJp: string;
  sourceIdentity: string;
  turnstileToken: string;
};

type ValidationResult =
  | { ok: true; submission: ValidSubmission }
  | { ok: false; error: string };

const validateSubmission = (value: unknown): ValidationResult => {
  if (!isRecord(value)) {
    return { ok: false, error: '请求内容格式错误' };
  }
  const allowedFields = new Set([
    'story_id',
    'content',
    'nickname',
    'note',
    'base_sha256',
    'base_content_sha256',
    'catalog_sha256',
    'source_path_cn',
    'source_path_jp',
    'source_identity',
    'turnstile_token',
  ]);
  if (Object.keys(value).some((key) => !allowedFields.has(key))) {
    return { ok: false, error: '请求包含不支持的字段' };
  }
  if (typeof value.story_id !== 'string' || typeof value.content !== 'string') {
    return { ok: false, error: 'story_id 和 content 必须是字符串' };
  }

  const storyId = value.story_id.trim();
  const content = normalizeProofreadingText(value.content);
  const nickname = sanitizeSingleLine(value.nickname, MAX_NICKNAME_LENGTH) || '匿名校对者';
  const note = sanitizeMultiline(value.note, MAX_NOTE_LENGTH);
  const turnstileToken =
    typeof value.turnstile_token === 'string' ? value.turnstile_token.trim() : '';

  if (
    storyId.length === 0 ||
    storyId.length > MAX_STORY_ID_LENGTH ||
    /[\u0000-\u001f\u007f]/u.test(storyId)
  ) {
    return { ok: false, error: 'story_id 长度或格式不合法' };
  }
  if (
    content.length > MAX_CONTENT_LENGTH ||
    content.trim().length < MIN_CONTENT_LENGTH
  ) {
    return { ok: false, error: 'content 长度或格式不合法' };
  }
  if (
    !isSha256(value.base_sha256) ||
    !isSha256(value.base_content_sha256) ||
    !isSha256(value.catalog_sha256)
  ) {
    return { ok: false, error: '源文本或剧情目录哈希无效' };
  }
  if (!isSafeStoryWebPath(value.source_path_cn, true)) {
    return { ok: false, error: '中文源路径无效' };
  }
  if (!isSafeStoryWebPath(value.source_path_jp, true)) {
    return { ok: false, error: '日文源路径无效' };
  }
  if (
    !isSafeSourceIdentity(value.source_identity) ||
    value.source_identity.length > MAX_SOURCE_IDENTITY_LENGTH
  ) {
    return { ok: false, error: '剧情来源身份无效' };
  }

  return {
    ok: true,
    submission: {
      storyId,
      content,
      nickname,
      note,
      baseSha256: value.base_sha256.toLowerCase(),
      baseContentSha256: value.base_content_sha256.toLowerCase(),
      catalogSha256: value.catalog_sha256.toLowerCase(),
      sourcePathCn: value.source_path_cn,
      sourcePathJp: value.source_path_jp,
      sourceIdentity: value.source_identity,
      turnstileToken,
    },
  };
};

const getRuntimeEnv = async (): Promise<CloudflareEnv> => {
  const { env } = await getCloudflareContext({ async: true });
  return env;
};

const consumeRateLimit = async (
  kv: SubmissionKvNamespace,
  request: NextRequest,
): Promise<{ allowed: true } | { allowed: false; retryAfter: number }> => {
  const now = Math.floor(Date.now() / 1_000);
  const windowStart =
    Math.floor(now / RATE_LIMIT_WINDOW_SECONDS) * RATE_LIMIT_WINDOW_SECONDS;
  const clientIdentity = getRateLimitIdentity(request.headers);
  const clientHash = (await sha256Text(clientIdentity)).slice(0, 32);
  const key = `${RATE_LIMIT_PREFIX}${clientHash}:${windowStart}`;
  const storedCount = Number.parseInt((await kv.get(key)) || '0', 10);
  const count = Number.isFinite(storedCount) ? storedCount : 0;
  if (count >= RATE_LIMIT_MAX_SUBMISSIONS) {
    return {
      allowed: false,
      retryAfter: Math.max(
        1,
        windowStart + RATE_LIMIT_WINDOW_SECONDS - now,
      ),
    };
  }
  await kv.put(key, String(count + 1), {
    expirationTtl: RATE_LIMIT_WINDOW_SECONDS * 2,
  });
  return { allowed: true };
};

export async function POST(request: NextRequest) {
  try {
    const contentType = request.headers
      .get('content-type')
      ?.split(';', 1)[0]
      .trim()
      .toLowerCase();
    if (contentType !== 'application/json') {
      return errorResponse('Content-Type 必须是 application/json', 415);
    }

    const env = await getRuntimeEnv();
    const kv = env.SUBMISSIONS_KV;
    if (!kv) return errorResponse('投稿服务暂不可用', 503);

    const bodyResult = await readBoundedJson(request);
    if (!bodyResult.ok) {
      return errorResponse(bodyResult.error, bodyResult.status);
    }
    const validation = validateSubmission(bodyResult.value);
    if (!validation.ok) return errorResponse(validation.error, 400);
    if (!KNOWN_STORY_IDS.has(validation.submission.storyId)) {
      return errorResponse('story_id 不在当前剧情目录中', 400);
    }

    const remoteIp = request.headers.get('cf-connecting-ip')?.trim();
    const turnstile = await verifyTurnstileToken({
      token: validation.submission.turnstileToken,
      secret: env.TURNSTILE_SECRET_KEY,
      remoteIp: remoteIp || undefined,
      expectedAction: 'proofreading-submit',
      allowedHostnames: env.TURNSTILE_ALLOWED_HOSTNAMES,
    });
    if (!turnstile.ok) return errorResponse(turnstile.error, turnstile.status);

    const rateLimit = await consumeRateLimit(kv, request);
    if (!rateLimit.allowed) {
      return errorResponse('提交过于频繁，请稍后再试', 429, {
        'Retry-After': String(rateLimit.retryAfter),
      });
    }

    const contentSha256 = await sha256Text(validation.submission.content);
    if (contentSha256 === validation.submission.baseContentSha256) {
      return errorResponse('修订内容与当前中文文本没有变化', 400);
    }

    const now = new Date().toISOString();
    const id = `ps_${Date.now().toString(36)}_${crypto.randomUUID()}`;
    const receipt = `${crypto.randomUUID()}.${crypto.randomUUID()}`;
    const receiptSha256 = await sha256Text(receipt);
    const status = 'pending' as const;
    const record: ProofreadingSubmission = {
      schema_version: PROOFREADING_SCHEMA_VERSION,
      id,
      story_id: validation.submission.storyId,
      nickname: validation.submission.nickname,
      note: validation.submission.note,
      content: validation.submission.content,
      content_sha256: contentSha256,
      base_sha256: validation.submission.baseSha256,
      base_content_sha256: validation.submission.baseContentSha256,
      catalog_sha256: validation.submission.catalogSha256,
      source_path_cn: validation.submission.sourcePathCn,
      source_path_jp: validation.submission.sourcePathJp,
      source_identity: validation.submission.sourceIdentity,
      source_revision: env.PROOFREADING_SOURCE_COMMIT?.trim() || 'unknown',
      target_branch: env.PROOFREADING_TARGET_BRANCH?.trim() || 'main',
      submitted_at: now,
      updated_at: now,
      status,
      receipt_sha256: receiptSha256,
      index_key: proofreadingIndexKey(status, now, id),
    };

    try {
      await createProofreadingSubmission(kv, record);
    } catch (error) {
      if (error instanceof Error && error.message === 'DUPLICATE_SUBMISSION') {
        return errorResponse('相同修订已经提交，请勿重复投稿', 409);
      }
      throw error;
    }

    return NextResponse.json(
      {
        success: true,
        id,
        receipt,
        status,
      },
      { headers: NO_STORE_HEADERS },
    );
  } catch (error: unknown) {
    console.error('Failed to store proofreading submission', error);
    return errorResponse('服务器暂时无法处理提交', 500);
  }
}

export async function GET(request: NextRequest) {
  try {
    const id = request.nextUrl.searchParams.get('id')?.trim() || '';
    const receipt = request.nextUrl.searchParams.get('receipt')?.trim() || '';
    if (!/^ps_[A-Za-z0-9_-]{10,128}$/u.test(id) || receipt.length > 256) {
      return errorResponse('审核编号或回执无效', 400);
    }
    const env = await getRuntimeEnv();
    const kv = env.SUBMISSIONS_KV;
    if (!kv) return errorResponse('投稿服务暂不可用', 503);
    let record = await getProofreadingSubmission(kv, id);
    if (!record || await sha256Text(receipt) !== record.receipt_sha256) {
      return errorResponse('审核编号或回执无效', 404);
    }
    const githubToken = env.PROOFREADING_GITHUB_TOKEN?.trim();
    const repository = env.PROOFREADING_GITHUB_REPO?.trim();
    if (
      record.status === 'pr_created' &&
      record.pull_request &&
      githubToken &&
      repository
    ) {
      try {
        const remote = await readProofreadingPullRequestState({
          token: githubToken,
          repository,
          pullRequest: record.pull_request,
        });
        if (remote.status !== 'pr_created') {
          record = await transitionProofreadingSubmission(
            kv,
            record,
            remote.status,
            { pull_request: remote.pullRequest },
          );
        }
      } catch (error) {
        console.error('Failed to synchronize public proofreading PR status', error);
      }
    }
    const result: ProofreadingPublicStatus = {
      id: record.id,
      story_id: record.story_id,
      nickname: record.nickname,
      submitted_at: record.submitted_at,
      updated_at: record.updated_at,
      status: record.status,
      public_message: record.review?.public_message || '',
      pull_request: record.pull_request,
    };
    return NextResponse.json(result, { headers: NO_STORE_HEADERS });
  } catch (error: unknown) {
    console.error('Failed to read proofreading status', error);
    return errorResponse('服务器暂时无法处理查询', 500);
  }
}
