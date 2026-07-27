export const PROOFREADING_SCHEMA_VERSION = 2 as const;

export const PROOFREADING_STATUSES = [
  'pending',
  'held',
  'approved',
  'processing',
  'stale',
  'rejected',
  'pr_created',
  'merged',
  'closed',
] as const;

export type ProofreadingStatus = (typeof PROOFREADING_STATUSES)[number];

export type ProofreadingReview = {
  reviewer: string;
  reviewed_at: string;
  public_message: string;
  internal_note: string;
};

export type ProofreadingPullRequest = {
  number: number;
  url: string;
  branch: string;
  created_at: string;
  merged_at?: string;
  closed_at?: string;
};

export type ProofreadingSubmission = {
  schema_version: typeof PROOFREADING_SCHEMA_VERSION;
  id: string;
  story_id: string;
  nickname: string;
  note: string;
  content: string;
  content_sha256: string;
  base_sha256: string;
  base_content_sha256: string;
  catalog_sha256: string;
  source_path_cn: string;
  source_path_jp: string;
  source_identity: string;
  source_revision: string;
  target_branch: string;
  submitted_at: string;
  updated_at: string;
  status: ProofreadingStatus;
  receipt_sha256: string;
  index_key: string;
  review?: ProofreadingReview;
  pull_request?: ProofreadingPullRequest;
  processing_error?: string;
};

export type ProofreadingListItem = Omit<
  ProofreadingSubmission,
  'content' | 'receipt_sha256' | 'index_key'
> & {
  content_length: number;
};

export type ProofreadingAdminDetail = Omit<
  ProofreadingSubmission,
  'receipt_sha256' | 'index_key'
>;

export type ProofreadingPublicStatus = {
  id: string;
  story_id: string;
  nickname: string;
  submitted_at: string;
  updated_at: string;
  status: ProofreadingStatus;
  public_message: string;
  pull_request?: ProofreadingPullRequest;
};

export const PROOFREADING_STATUS_LABELS: Record<ProofreadingStatus, string> = {
  pending: '待审核',
  held: '暂缓',
  approved: '已批准，等待生成 PR',
  processing: '正在生成 PR',
  stale: '源文本已更新，需要重新提交',
  rejected: '已驳回',
  pr_created: '校对 PR 已建立',
  merged: '已合并',
  closed: 'PR 已关闭',
};

export const isProofreadingStatus = (value: unknown): value is ProofreadingStatus =>
  typeof value === 'string' &&
  (PROOFREADING_STATUSES as readonly string[]).includes(value);

export const normalizeProofreadingText = (value: string): string =>
  value
    .replace(/^\uFEFF/u, '')
    .replace(/\r\n?/gu, '\n')
    .replace(/\u0000/gu, '');

export const sha256Text = async (value: string): Promise<string> => {
  const bytes = new TextEncoder().encode(normalizeProofreadingText(value));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
};

export const isSha256 = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f0-9]{64}$/iu.test(value);

export const sanitizeSingleLine = (
  value: unknown,
  maxLength: number,
): string => {
  if (typeof value !== 'string') return '';
  return value
    .replace(/[\u0000-\u001f\u007f]/gu, ' ')
    .replace(/\s+/gu, ' ')
    .trim()
    .slice(0, maxLength);
};

export const sanitizeMultiline = (
  value: unknown,
  maxLength: number,
): string => {
  if (typeof value !== 'string') return '';
  return normalizeProofreadingText(value)
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/gu, '')
    .trim()
    .slice(0, maxLength);
};

export const isSafeStoryWebPath = (value: unknown, allowEmpty = true): value is string => {
  if (typeof value !== 'string') return false;
  if (value === '') return allowEmpty;
  if (value.length > 1_024 || !value.startsWith('/data/')) return false;
  if (value.includes('\\') || value.includes('\u0000')) return false;
  const parts = value.split('/');
  if (parts.some((part) => part === '.' || part === '..')) return false;
  return /_(?:cn|jp)\.(?:txt|json)$/iu.test(value);
};

export const isSafeSourceIdentity = (value: unknown): value is string =>
  typeof value === 'string' &&
  value.length > 0 &&
  value.length <= 1_024 &&
  !/[\u0000-\u001f\u007f]/u.test(value) &&
  !value.includes('\\') &&
  !value.split('/').some((part) => part === '.' || part === '..');

export const toProofreadingListItem = (
  record: ProofreadingSubmission,
): ProofreadingListItem => {
  const {
    content,
    receipt_sha256: _receipt,
    index_key: _indexKey,
    ...rest
  } = record;
  return {
    ...rest,
    content_length: content.length,
  };
};

export const toProofreadingAdminDetail = (
  record: ProofreadingSubmission,
): ProofreadingAdminDetail => {
  const { receipt_sha256: _receipt, index_key: _indexKey, ...rest } = record;
  return rest;
};
