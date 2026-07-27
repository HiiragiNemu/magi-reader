import { NextRequest, NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import { authenticateProofreadingAdmin } from '@/lib/admin-auth';
import {
  isProofreadingStatus,
  sanitizeMultiline,
  toProofreadingAdminDetail,
  type ProofreadingStatus,
  type ProofreadingReview,
  type ProofreadingSubmission,
} from '@/lib/proofreading';
import {
  createProofreadingPullRequest,
  ProofreadingPullRequestError,
  readProofreadingPullRequestState,
} from '@/lib/github-proofreading';
import {
  MACHINE_TRANSLATION_ID_SET,
  setMachineTranslationReviewState,
} from '@/lib/machine-translation-review';
import {
  getProofreadingSubmission,
  transitionProofreadingSubmission,
} from '@/lib/proofreading-store';

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };
const MAX_ADMIN_BODY_BYTES = 32 * 1024;
const MAX_PUBLIC_MESSAGE_LENGTH = 1_000;
const MAX_INTERNAL_NOTE_LENGTH = 4_000;
const ADMIN_STATUSES = new Set<ProofreadingStatus>([
  'pending',
  'held',
  'approved',
  'rejected',
]);

const errorResponse = (
  error: string,
  status: number,
  submission?: ProofreadingSubmission,
) =>
  NextResponse.json(
    {
      error,
      ...(submission
        ? { submission: toProofreadingAdminDetail(submission) }
        : {}),
    },
    { status, headers: NO_STORE_HEADERS },
  );

const isSubmissionId = (value: string): boolean =>
  /^ps_[A-Za-z0-9_-]{10,128}$/u.test(value);

const readPatchBody = async (
  request: NextRequest,
): Promise<Record<string, unknown> | null> => {
  const declared = Number(request.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > MAX_ADMIN_BODY_BYTES) return null;
  try {
    const value: unknown = await request.json();
    return typeof value === 'object' && value !== null && !Array.isArray(value)
      ? value as Record<string, unknown>
      : null;
  } catch {
    return null;
  }
};

const contextFor = async (
  request: NextRequest,
  id: string,
) => {
  const { env } = await getCloudflareContext({ async: true });
  const authentication = await authenticateProofreadingAdmin(request, env);
  if (!authentication.ok) {
    return { response: errorResponse(authentication.error, authentication.status) };
  }
  const kv = env.SUBMISSIONS_KV;
  if (!kv) return { response: errorResponse('投稿数据库尚未配置', 503) };
  if (!isSubmissionId(id)) return { response: errorResponse('审核编号无效', 400) };
  const record = await getProofreadingSubmission(kv, id);
  if (!record) return { response: errorResponse('没有找到该投稿', 404) };
  return { env, kv, authentication, record };
};

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const context = await contextFor(request, id);
    if ('response' in context) return context.response;
    let record = context.record;
    if (
      record.status === 'pr_created' &&
      record.pull_request &&
      context.authentication.githubToken &&
      context.env.PROOFREADING_GITHUB_REPO?.trim()
    ) {
      try {
        const remote = await readProofreadingPullRequestState({
          token: context.authentication.githubToken,
          repository: context.env.PROOFREADING_GITHUB_REPO.trim(),
          pullRequest: record.pull_request,
        });
        if (remote.status !== 'pr_created') {
          record = await transitionProofreadingSubmission(
            context.kv,
            record,
            remote.status,
            { pull_request: remote.pullRequest },
          );
        }
      } catch (error) {
        console.error('Failed to synchronize proofreading PR state', error);
      }
    }
    return NextResponse.json(
      {
        submission: toProofreadingAdminDetail(record),
        reviewer: context.authentication.identity.label,
      },
      { headers: NO_STORE_HEADERS },
    );
  } catch (error: unknown) {
    console.error('Failed to read proofreading submission', error);
    return errorResponse('服务器暂时无法处理查询', 500);
  }
}

const transitionOrConflict = async (
  kv: SubmissionKvNamespace,
  record: ProofreadingSubmission,
  status: ProofreadingStatus,
  patch: Partial<ProofreadingSubmission>,
): Promise<ProofreadingSubmission> => {
  try {
    return await transitionProofreadingSubmission(kv, record, status, patch);
  } catch (error) {
    if (
      error instanceof Error &&
      error.message.startsWith('INVALID_STATUS_TRANSITION:')
    ) {
      throw new ProofreadingPullRequestError(
        '当前状态不允许执行该操作，请刷新后重试',
        'invalid',
      );
    }
    throw error;
  }
};

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const context = await contextFor(request, id);
    if ('response' in context) return context.response;
    const body = await readPatchBody(request);
    if (!body) return errorResponse('审核请求格式错误或过大', 400);
    const allowedFields = new Set(['status', 'public_message', 'internal_note']);
    if (Object.keys(body).some((key) => !allowedFields.has(key))) {
      return errorResponse('审核请求包含不支持的字段', 400);
    }
    if (!isProofreadingStatus(body.status) || !ADMIN_STATUSES.has(body.status)) {
      return errorResponse('目标审核状态无效', 400);
    }

    const publicMessage = sanitizeMultiline(
      body.public_message,
      MAX_PUBLIC_MESSAGE_LENGTH,
    );
    const internalNote = sanitizeMultiline(
      body.internal_note,
      MAX_INTERNAL_NOTE_LENGTH,
    );
    const review: ProofreadingReview = {
      reviewer: context.authentication.identity.label,
      reviewed_at: new Date().toISOString(),
      public_message: publicMessage,
      internal_note: internalNote,
    };

    if (body.status !== 'approved') {
      const updated = await transitionOrConflict(
        context.kv,
        context.record,
        body.status,
        { review, processing_error: '' },
      );
      return NextResponse.json(
        { success: true, submission: toProofreadingAdminDetail(updated) },
        { headers: NO_STORE_HEADERS },
      );
    }

    const githubToken = context.authentication.githubToken;
    const repository = context.env.PROOFREADING_GITHUB_REPO?.trim();
    if (!githubToken || !repository) {
      return errorResponse(
        '批准并创建 PR 需要具有仓库写入权限的 GitHub PAT，或服务器端 PROOFREADING_GITHUB_TOKEN',
        503,
        context.record,
      );
    }

    let processing = await transitionOrConflict(
      context.kv,
      context.record,
      'approved',
      { review, processing_error: '' },
    );
    processing = await transitionOrConflict(
      context.kv,
      processing,
      'processing',
      { review, processing_error: '' },
    );

    try {
      const pullRequest = await createProofreadingPullRequest({
        token: githubToken,
        repository,
        record: processing,
      });
      const completed = await transitionOrConflict(
        context.kv,
        processing,
        'pr_created',
        {
          review,
          pull_request: pullRequest,
          processing_error: '',
        },
      );
      if (MACHINE_TRANSLATION_ID_SET.has(completed.story_id)) {
        await setMachineTranslationReviewState(
          context.kv,
          completed.story_id,
          {
            verified: true,
            reviewer: context.authentication.identity.label,
            reviewed_at: review.reviewed_at,
            note: review.public_message || '社区校对投稿已批准并建立 PR',
            submission_id: completed.id,
            pull_request_url: pullRequest.url,
          },
        );
      }
      return NextResponse.json(
        { success: true, submission: toProofreadingAdminDetail(completed) },
        { headers: NO_STORE_HEADERS },
      );
    } catch (error) {
      const message =
        error instanceof Error ? error.message : '无法创建 GitHub 校对 PR';
      const stale =
        error instanceof ProofreadingPullRequestError && error.code === 'stale';
      const publicFailureMessage = stale
        ? '源中文文本已更新，请基于最新版重新校对并提交。'
        : publicMessage;
      const failedReview: ProofreadingReview = {
        ...review,
        public_message: publicFailureMessage,
      };
      const failed = await transitionOrConflict(
        context.kv,
        processing,
        stale ? 'stale' : 'held',
        {
          review: failedReview,
          processing_error: message.slice(0, 4_000),
        },
      );
      return errorResponse(
        stale ? publicFailureMessage : `PR 创建失败：${message}`,
        stale ? 409 : 502,
        failed,
      );
    }
  } catch (error: unknown) {
    if (error instanceof ProofreadingPullRequestError) {
      return errorResponse(error.message, 409);
    }
    console.error('Failed to update proofreading submission', error);
    return errorResponse('服务器暂时无法处理审核', 500);
  }
}
