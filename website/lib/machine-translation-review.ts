import manifestJson from '@/public/data/machine_translation_manifest.generated.json';

export type MachineTranslationSystem = 'magireco';

export type MachineTranslationEntry = {
  story_id: string;
  category: string;
  folder: string;
  title: string;
  source_identity: string;
  repository_path_cn: string;
  path_cn: string;
  path_jp: string;
  provenance?: 'added_after_trusted_main' | string;
  machine_source_json_count?: number;
  direct_txt_changed?: boolean;
};

export type MachineTranslationManifest = {
  version: number;
  definition: string;
  system?: MachineTranslationSystem;
  trusted_baseline?: string;
  source_commit?: string;
  translation_base?: string;
  translation_commit?: string;
  trusted_baseline_file_total?: number;
  current_file_total?: number;
  added_file_total?: number;
  changed_json_total?: number;
  changed_txt_total?: number;
  referenced_changed_json_total?: number;
  protected_human_overwrite_count?: number;
  protected_human_deletion_count?: number;
  total: number;
  entries: MachineTranslationEntry[];
  unreferenced_changed_json_count?: number;
  unreferenced_changed_json_paths?: string[];
  unmatched_changed_txt_identities?: string[];
  missing_repository_txt_paths?: string[];
  unmatched_source_identities?: string[];
  legacy_translation_commit_not_used_for_classification?: string;
};

export type MachineTranslationReviewState = {
  verified: boolean;
  reviewer: string;
  reviewed_at: string;
  note: string;
  submission_id?: string;
  pull_request_url?: string;
};

const LEGACY_STATE_PREFIX = 'proofreading:machine-review:';
const STATE_PREFIX = 'proofreading:machine-review:magireco:';

const normalizeManifest = (value: unknown): MachineTranslationManifest => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Magia Record machine translation manifest is invalid');
  }
  const record = value as Partial<MachineTranslationManifest>;
  if (
    !Array.isArray(record.entries) ||
    !Number.isSafeInteger(record.total) ||
    record.total !== record.entries.length
  ) {
    throw new Error('Magia Record machine translation manifest is inconsistent');
  }
  return { ...record, system: 'magireco' } as MachineTranslationManifest;
};

export const MACHINE_TRANSLATION_MANIFEST = normalizeManifest(manifestJson);
export const MACHINE_TRANSLATION_ID_SET = new Set(
  MACHINE_TRANSLATION_MANIFEST.entries.map(entry => entry.story_id),
);

// Compatibility aliases retained for existing Magia Record-only callers.
export const MACHINE_TRANSLATION_MANIFESTS = {
  magireco: MACHINE_TRANSLATION_MANIFEST,
} as const;
export const MACHINE_TRANSLATION_ID_SETS = {
  magireco: MACHINE_TRANSLATION_ID_SET,
} as const;

export const machineTranslationSystemForStory = (
  storyId: string,
): MachineTranslationSystem | null =>
  MACHINE_TRANSLATION_ID_SET.has(storyId) ? 'magireco' : null;

export const machineTranslationStateKey = (
  storyId: string,
  _system: MachineTranslationSystem = 'magireco',
): string => {
  void _system;
  return `${STATE_PREFIX}${storyId}`;
};

export const parseMachineTranslationReviewState = (
  raw: string | null,
): MachineTranslationReviewState | null => {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<MachineTranslationReviewState>;
    if (
      typeof value.verified !== 'boolean' ||
      typeof value.reviewer !== 'string' ||
      typeof value.reviewed_at !== 'string' ||
      typeof value.note !== 'string'
    ) {
      return null;
    }
    return {
      verified: value.verified,
      reviewer: value.reviewer,
      reviewed_at: value.reviewed_at,
      note: value.note,
      submission_id:
        typeof value.submission_id === 'string'
          ? value.submission_id
          : undefined,
      pull_request_url:
        typeof value.pull_request_url === 'string'
          ? value.pull_request_url
          : undefined,
    };
  } catch {
    return null;
  }
};

export const getMachineTranslationReviewState = async (
  kv: SubmissionKvNamespace,
  storyId: string,
  _system: MachineTranslationSystem = 'magireco',
): Promise<MachineTranslationReviewState | null> => {
  void _system;
  const current = parseMachineTranslationReviewState(
    await kv.get(machineTranslationStateKey(storyId)),
  );
  if (current) return current;
  return parseMachineTranslationReviewState(
    await kv.get(`${LEGACY_STATE_PREFIX}${storyId}`),
  );
};

export const setMachineTranslationReviewState = async (
  kv: SubmissionKvNamespace,
  storyId: string,
  state: MachineTranslationReviewState,
  _system: MachineTranslationSystem = 'magireco',
): Promise<void> => {
  void _system;
  if (!MACHINE_TRANSLATION_ID_SET.has(storyId)) {
    throw new Error('STORY_NOT_IN_MACHINE_TRANSLATION_MANIFEST');
  }
  await kv.put(machineTranslationStateKey(storyId), JSON.stringify(state));
};

export const listMachineTranslationReviewStates = async (
  kv: SubmissionKvNamespace,
  _system: MachineTranslationSystem = 'magireco',
): Promise<Record<string, MachineTranslationReviewState>> => {
  void _system;
  const result: Record<string, MachineTranslationReviewState> = {};
  let cursor: string | undefined;
  do {
    const listed = await kv.list({ prefix: STATE_PREFIX, limit: 1000, cursor });
    for (const item of listed.keys) {
      const storyId = item.name.slice(STATE_PREFIX.length);
      if (!MACHINE_TRANSLATION_ID_SET.has(storyId)) continue;
      const state = parseMachineTranslationReviewState(await kv.get(item.name));
      if (state) result[storyId] = state;
    }
    cursor = listed.list_complete ? undefined : listed.cursor;
  } while (cursor);

  // Merge legacy Magia Record entries only when no namespaced value exists.
  cursor = undefined;
  do {
    const listed = await kv.list({
      prefix: LEGACY_STATE_PREFIX,
      limit: 1000,
      cursor,
    });
    for (const item of listed.keys) {
      const suffix = item.name.slice(LEGACY_STATE_PREFIX.length);
      if (suffix.startsWith('magireco:') || suffix.startsWith('exedra:')) continue;
      if (!MACHINE_TRANSLATION_ID_SET.has(suffix) || result[suffix]) continue;
      const state = parseMachineTranslationReviewState(await kv.get(item.name));
      if (state) result[suffix] = state;
    }
    cursor = listed.list_complete ? undefined : listed.cursor;
  } while (cursor);
  return result;
};

export const machineTranslationSystemSummary = async (
  kv: SubmissionKvNamespace | undefined,
  _system: MachineTranslationSystem = 'magireco',
) => {
  void _system;
  const states = kv ? await listMachineTranslationReviewStates(kv) : {};
  const verifiedIds = MACHINE_TRANSLATION_MANIFEST.entries
    .filter(entry => states[entry.story_id]?.verified === true)
    .map(entry => entry.story_id);
  return {
    system: 'magireco' as const,
    definition: MACHINE_TRANSLATION_MANIFEST.definition,
    total: MACHINE_TRANSLATION_MANIFEST.total,
    verified: verifiedIds.length,
    remaining: Math.max(0, MACHINE_TRANSLATION_MANIFEST.total - verifiedIds.length),
    machine_translation_ids: MACHINE_TRANSLATION_MANIFEST.entries.map(
      entry => entry.story_id,
    ),
    verified_ids: verifiedIds,
  };
};
