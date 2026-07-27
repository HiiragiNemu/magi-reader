import { NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import { listCachedExedraLocalizations } from '@/lib/exedra-localization';
import {
  MACHINE_TRANSLATION_MANIFESTS,
  machineTranslationSystemSummary,
  parseMachineTranslationReviewState,
} from '@/lib/machine-translation-review';

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };
const EXEDRA_REVIEW_PREFIX = 'proofreading:machine-review:exedra:';

const exedraReviewStates = async (
  kv: SubmissionKvNamespace | undefined,
  allowed: Set<string>,
) => {
  const verified: string[] = [];
  if (!kv || allowed.size === 0) return verified;
  let cursor: string | undefined;
  do {
    const page = await kv.list({ prefix: EXEDRA_REVIEW_PREFIX, limit: 1000, cursor });
    for (const key of page.keys) {
      const storyId = key.name.slice(EXEDRA_REVIEW_PREFIX.length);
      if (!allowed.has(storyId)) continue;
      const state = parseMachineTranslationReviewState(await kv.get(key.name));
      if (state?.verified) verified.push(storyId);
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return verified.sort();
};

export async function GET() {
  try {
    const { env } = await getCloudflareContext({ async: true });
    const magireco = await machineTranslationSystemSummary(env.SUBMISSIONS_KV, 'magireco');
    const cached = env.SUBMISSIONS_KV
      ? await listCachedExedraLocalizations(env.SUBMISSIONS_KV)
      : [];
    const staticIds = MACHINE_TRANSLATION_MANIFESTS.exedra.entries
      .map(entry => entry.story_id);
    const cachedMachineIds = cached
      .filter(record => record.provenance === 'machine_translation')
      .map(record => record.story_id);
    const machineIds = [...new Set([...staticIds, ...cachedMachineIds])].sort();
    const verifiedIds = await exedraReviewStates(env.SUBMISSIONS_KV, new Set(machineIds));
    const staticCounts = MACHINE_TRANSLATION_MANIFESTS.exedra.provenance_counts ?? {};
    const persistedIds = new Set(
      MACHINE_TRANSLATION_MANIFESTS.exedra.entries.map(entry => entry.story_id),
    );
    const uncopiedCache = cached.filter(record => !persistedIds.has(record.story_id));
    const provenanceCounts = {
      local_human: Number(staticCounts.local_human ?? 0),
      official_tw_human:
        Number(staticCounts.official_tw_human ?? 0) +
        uncopiedCache.filter(record => record.provenance === 'official_tw_human').length,
      exedra_wiki_human:
        Number(staticCounts.exedra_wiki_human ?? 0) +
        uncopiedCache.filter(record => record.provenance === 'exedra_wiki_human').length,
      machine_translation: machineIds.length,
    };
    const exedra = {
      system: 'exedra' as const,
      definition: 'exedra_persisted_or_cached_provenance_machine_translation_only',
      total: machineIds.length,
      verified: verifiedIds.length,
      remaining: Math.max(0, machineIds.length - verifiedIds.length),
      machine_translation_ids: machineIds,
      verified_ids: verifiedIds,
      localization_cached: cached.length,
      provenance_counts: provenanceCounts,
    };
    return NextResponse.json(
      {
        version: 2,
        systems: { magireco, exedra },
        // Backward compatibility for clients deployed before game separation.
        ...magireco,
      },
      { headers: NO_STORE_HEADERS },
    );
  } catch (error) {
    console.error('Failed to read machine translation review state', error);
    return NextResponse.json(
      { error: '机器翻译人工校验状态暂时不可用' },
      { status: 500, headers: NO_STORE_HEADERS },
    );
  }
}
