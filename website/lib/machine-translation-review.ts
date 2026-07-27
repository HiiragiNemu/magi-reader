import manifestJson from '@/public/data/machine_translation_manifest.generated.json';

export type MachineTranslationEntry = {
  story_id: string;
  category: string;
  folder: string;
  title: string;
  source_identity: string;
  repository_path_cn: string;
  path_cn: string;
  path_jp: string;
};

export type MachineTranslationManifest = {
  version: 1;
  definition: string;
  translation_commit: string;
  total: number;
  entries: MachineTranslationEntry[];
  unmatched_source_identities?: string[];
};

export type MachineTranslationReviewState = {
  verified: boolean;
  reviewer: string;
  reviewed_at: string;
  note: string;
  submission_id?: string;
  pull_request_url?: string;
};

const STATE_PREFIX = 'proofreading:machine-review:';

export const MACHINE_TRANSLATION_MANIFEST = manifestJson as MachineTranslationManifest;
export const MACHINE_TRANSLATION_ID_SET = new Set(
  MACHINE_TRANSLATION_MANIFEST.entries.map(entry => entry.story_id),
);

export const machineTranslationStateKey = (storyId: string): string =>
  `${STATE_PREFIX}${storyId}`;

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
): Promise<MachineTranslationReviewState | null> =>
  parseMachineTranslationReviewState(await kv.get(machineTranslationStateKey(storyId)));

export const setMachineTranslationReviewState = async (
  kv: SubmissionKvNamespace,
  storyId: string,
  state: MachineTranslationReviewState,
): Promise<void> => {
  if (!MACHINE_TRANSLATION_ID_SET.has(storyId)) {
    throw new Error('STORY_NOT_IN_MACHINE_TRANSLATION_MANIFEST');
  }
  await kv.put(machineTranslationStateKey(storyId), JSON.stringify(state));
};

export const listMachineTranslationReviewStates = async (
  kv: SubmissionKvNamespace,
): Promise<Record<string, MachineTranslationReviewState>> => {
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
  return result;
};
