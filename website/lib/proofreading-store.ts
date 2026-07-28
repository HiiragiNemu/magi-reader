import {
  PROOFREADING_SCHEMA_VERSION,
  isProofreadingStatus,
  type ProofreadingStatus,
  type ProofreadingSubmission,
} from '@/lib/proofreading';

const RECORD_PREFIX = 'proofreading:record:';
const INDEX_PREFIX = 'proofreading:index:';
const DEDUPE_PREFIX = 'proofreading:dedupe:';
const MAX_TIMESTAMP = 9_999_999_999_999;
const DEDUPE_TTL_SECONDS = 30 * 24 * 60 * 60;

const statusTransitionMap: Record<ProofreadingStatus, ReadonlySet<ProofreadingStatus>> = {
  pending: new Set(['held', 'approved', 'rejected']),
  held: new Set(['pending', 'approved', 'rejected']),
  approved: new Set(['held', 'processing', 'stale']),
  processing: new Set(['held', 'stale', 'pr_created']),
  stale: new Set(['held', 'rejected']),
  rejected: new Set(),
  pr_created: new Set(['merged', 'closed']),
  merged: new Set(),
  closed: new Set(),
};

export const proofreadingRecordKey = (id: string): string =>
  `${RECORD_PREFIX}${id}`;

const reverseTimestamp = (date: string): string => {
  const parsed = Date.parse(date);
  const safe = Number.isFinite(parsed) ? parsed : Date.now();
  return String(MAX_TIMESTAMP - Math.min(MAX_TIMESTAMP, Math.max(0, safe))).padStart(13, '0');
};

export const proofreadingIndexKey = (
  status: ProofreadingStatus,
  date: string,
  id: string,
): string => `${INDEX_PREFIX}${status}:${reverseTimestamp(date)}:${id}`;

export const proofreadingIndexPrefix = (status: ProofreadingStatus): string =>
  `${INDEX_PREFIX}${status}:`;

export const proofreadingDedupeKey = (
  storyId: string,
  contentSha256: string,
): string => `${DEDUPE_PREFIX}${storyId}:${contentSha256}`;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export const parseProofreadingSubmission = (
  raw: string,
): ProofreadingSubmission | null => {
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value)) return null;
    if (value.schema_version !== PROOFREADING_SCHEMA_VERSION) return null;
    if (!isProofreadingStatus(value.status)) return null;
    const requiredStrings = [
      'id',
      'story_id',
      'nickname',
      'note',
      'content',
      'content_sha256',
      'base_sha256',
      'base_content_sha256',
      'catalog_sha256',
      'source_path_cn',
      'source_path_jp',
      'source_identity',
      'source_revision',
      'target_branch',
      'submitted_at',
      'updated_at',
      'receipt_sha256',
      'index_key',
    ];
    if (requiredStrings.some((key) => typeof value[key] !== 'string')) return null;
    return value as ProofreadingSubmission;
  } catch {
    return null;
  }
};

export const getProofreadingSubmission = async (
  kv: SubmissionKvNamespace,
  id: string,
): Promise<ProofreadingSubmission | null> => {
  const raw = await kv.get(proofreadingRecordKey(id));
  return raw ? parseProofreadingSubmission(raw) : null;
};

export const createProofreadingSubmission = async (
  kv: SubmissionKvNamespace,
  record: ProofreadingSubmission,
): Promise<void> => {
  const recordKey = proofreadingRecordKey(record.id);
  const duplicateKey = proofreadingDedupeKey(
    record.story_id,
    record.content_sha256,
  );
  if (await kv.get(duplicateKey)) {
    throw new Error('DUPLICATE_SUBMISSION');
  }
  await kv.put(recordKey, JSON.stringify(record));
  await kv.put(record.index_key, recordKey);
  await kv.put(duplicateKey, record.id, {
    expirationTtl: DEDUPE_TTL_SECONDS,
  });
};

export const listProofreadingSubmissions = async (
  kv: SubmissionKvNamespace,
  status: ProofreadingStatus,
  options: { limit: number; cursor?: string },
): Promise<{
  records: ProofreadingSubmission[];
  cursor: string | null;
  listComplete: boolean;
}> => {
  const listed = await kv.list({
    prefix: proofreadingIndexPrefix(status),
    limit: options.limit,
    cursor: options.cursor,
  });
  const records: ProofreadingSubmission[] = [];
  const seen = new Set<string>();
  for (const { name } of listed.keys) {
    const recordKey = await kv.get(name);
    if (!recordKey || !recordKey.startsWith(RECORD_PREFIX)) continue;
    const raw = await kv.get(recordKey);
    if (!raw) continue;
    const record = parseProofreadingSubmission(raw);
    if (!record || record.status !== status || seen.has(record.id)) continue;
    seen.add(record.id);
    records.push(record);
  }
  return {
    records,
    cursor: listed.list_complete ? null : listed.cursor ?? null,
    listComplete: listed.list_complete,
  };
};

export const transitionProofreadingSubmission = async (
  kv: SubmissionKvNamespace,
  record: ProofreadingSubmission,
  nextStatus: ProofreadingStatus,
  patch: Partial<ProofreadingSubmission>,
): Promise<ProofreadingSubmission> => {
  if (
    record.status !== nextStatus &&
    !statusTransitionMap[record.status].has(nextStatus)
  ) {
    throw new Error(`INVALID_STATUS_TRANSITION:${record.status}:${nextStatus}`);
  }
  const now = new Date().toISOString();
  const nextIndexKey = proofreadingIndexKey(nextStatus, now, record.id);
  const next: ProofreadingSubmission = {
    ...record,
    ...patch,
    status: nextStatus,
    updated_at: now,
    index_key: nextIndexKey,
  };
  await kv.put(proofreadingRecordKey(record.id), JSON.stringify(next));
  await kv.put(nextIndexKey, proofreadingRecordKey(record.id));
  if (record.index_key && record.index_key !== nextIndexKey) {
    await kv.delete(record.index_key);
  }
  return next;
};
