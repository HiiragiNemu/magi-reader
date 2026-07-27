import magirecoManifestJson from '@/public/data/machine_translation_manifest.generated.json';
import exedraManifestJson from '@/public/data/exedra_machine_translation_manifest.generated.json';

export type MachineTranslationSystem = 'magireco' | 'exedra';

export type MachineTranslationEntry = {
  story_id: string;
  category: string;
  folder: string;
  title: string;
  source_identity: string;
  repository_path_cn: string;
  path_cn: string;
  path_jp: string;
  provenance?: 'added_after_trusted_main' | 'machine_translation' | string;
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
  provenance_counts?: Record<string, number>;
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
const statePrefix = (system: MachineTranslationSystem): string =>
  `proofreading:machine-review:${system}:`;

const normalizeManifest = (
  value: unknown,
  system: MachineTranslationSystem,
): MachineTranslationManifest => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${system} machine translation manifest is invalid`);
  }
  const record = value as Partial<MachineTranslationManifest>;
  if (!Array.isArray(record.entries) || !Number.isSafeInteger(record.total) ||
      record.total !== record.entries.length) {
    throw new Error(`${system} machine translation manifest is inconsistent`);
  }
  return { ...record, system } as MachineTranslationManifest;
};

export const MACHINE_TRANSLATION_MANIFESTS: Record<
  MachineTranslationSystem,
  MachineTranslationManifest
> = {
  magireco: normalizeManifest(magirecoManifestJson, 'magireco'),
  exedra: normalizeManifest(exedraManifestJson, 'exedra'),
};

export const MACHINE_TRANSLATION_ID_SETS: Record<
  MachineTranslationSystem,
  Set<string>
> = {
  magireco: new Set(
    MACHINE_TRANSLATION_MANIFESTS.magireco.entries.map(entry => entry.story_id),
  ),
  exedra: new Set(
    MACHINE_TRANSLATION_MANIFESTS.exedra.entries.map(entry => entry.story_id),
  ),
};

// Backward-compatible exports used by existing submission routes. They represent the
// union of both systems; callers that mutate state should pass an explicit system.
export const MACHINE_TRANSLATION_MANIFEST = MACHINE_TRANSLATION_MANIFESTS.magireco;
export const MACHINE_TRANSLATION_ID_SET = new Set([
  ...MACHINE_TRANSLATION_ID_SETS.magireco,
  ...MACHINE_TRANSLATION_ID_SETS.exedra,
]);

export const machineTranslationSystemForStory = (
  storyId: string,
): MachineTranslationSystem | null => {
  if (MACHINE_TRANSLATION_ID_SETS.magireco.has(storyId)) return 'magireco';
  if (MACHINE_TRANSLATION_ID_SETS.exedra.has(storyId)) return 'exedra';
  return null;
};

export const machineTranslationStateKey = (
  storyId: string,
  system: MachineTranslationSystem = 'magireco',
): string => `${statePrefix(system)}${storyId}`;

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
        typeof value.submission_id === 'string' ? value.submission_id : undefined,
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
  system: MachineTranslationSystem = 'magireco',
): Promise<MachineTranslationReviewState | null> => {
  const current = parseMachineTranslationReviewState(
    await kv.get(machineTranslationStateKey(storyId, system)),
  );
  if (current || system !== 'magireco') return current;
  // Read legacy Magia Record keys created before system separation.
  return parseMachineTranslationReviewState(
    await kv.get(`${LEGACY_STATE_PREFIX}${storyId}`),
  );
};

export const setMachineTranslationReviewState = async (
  kv: SubmissionKvNamespace,
  storyId: string,
  state: MachineTranslationReviewState,
  system?: MachineTranslationSystem,
): Promise<void> => {
  const resolved = system ?? machineTranslationSystemForStory(storyId);
  if (!resolved || !MACHINE_TRANSLATION_ID_SETS[resolved].has(storyId)) {
    throw new Error('STORY_NOT_IN_MACHINE_TRANSLATION_MANIFEST');
  }
  await kv.put(machineTranslationStateKey(storyId, resolved), JSON.stringify(state));
};

export const listMachineTranslationReviewStates = async (
  kv: SubmissionKvNamespace,
  system: MachineTranslationSystem = 'magireco',
): Promise<Record<string, MachineTranslationReviewState>> => {
  const result: Record<string, MachineTranslationReviewState> = {};
  const allowed = MACHINE_TRANSLATION_ID_SETS[system];
  let cursor: string | undefined;
  const prefix = statePrefix(system);
  do {
    const listed = await kv.list({ prefix, limit: 1000, cursor });
    for (const item of listed.keys) {
      const storyId = item.name.slice(prefix.length);
      if (!allowed.has(storyId)) continue;
      const state = parseMachineTranslationReviewState(await kv.get(item.name));
      if (state) result[storyId] = state;
    }
    cursor = listed.list_complete ? undefined : listed.cursor;
  } while (cursor);

  if (system === 'magireco') {
    // Merge legacy entries only when no system-specific value exists.
    cursor = undefined;
    do {
      const listed = await kv.list({ prefix: LEGACY_STATE_PREFIX, limit: 1000, cursor });
      for (const item of listed.keys) {
        const suffix = item.name.slice(LEGACY_STATE_PREFIX.length);
        if (suffix.startsWith('magireco:') || suffix.startsWith('exedra:')) continue;
        if (!allowed.has(suffix) || result[suffix]) continue;
        const state = parseMachineTranslationReviewState(await kv.get(item.name));
        if (state) result[suffix] = state;
      }
      cursor = listed.list_complete ? undefined : listed.cursor;
    } while (cursor);
  }
  return result;
};

export const machineTranslationSystemSummary = async (
  kv: SubmissionKvNamespace | undefined,
  system: MachineTranslationSystem,
) => {
  const manifest = MACHINE_TRANSLATION_MANIFESTS[system];
  const states = kv ? await listMachineTranslationReviewStates(kv, system) : {};
  const verifiedIds = manifest.entries
    .filter(entry => states[entry.story_id]?.verified === true)
    .map(entry => entry.story_id);
  return {
    system,
    definition: manifest.definition,
    total: manifest.total,
    verified: verifiedIds.length,
    remaining: Math.max(0, manifest.total - verifiedIds.length),
    machine_translation_ids: manifest.entries.map(entry => entry.story_id),
    verified_ids: verifiedIds,
  };
};
