import { NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';
import {
  MACHINE_TRANSLATION_MANIFEST,
  listMachineTranslationReviewStates,
} from '@/lib/machine-translation-review';

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };

export async function GET() {
  const { env } = await getCloudflareContext({ async: true });
  const states = env.SUBMISSIONS_KV
    ? await listMachineTranslationReviewStates(env.SUBMISSIONS_KV)
    : {};
  const machineIds = MACHINE_TRANSLATION_MANIFEST.entries.map(entry => entry.story_id);
  const verifiedIds = machineIds.filter(storyId => states[storyId]?.verified === true);
  return NextResponse.json(
    {
      version: 1,
      definition: MACHINE_TRANSLATION_MANIFEST.definition,
      translation_commit: MACHINE_TRANSLATION_MANIFEST.translation_commit,
      total: machineIds.length,
      verified: verifiedIds.length,
      remaining: Math.max(0, machineIds.length - verifiedIds.length),
      machine_translation_ids: machineIds,
      verified_ids: verifiedIds,
      states,
    },
    { headers: NO_STORE_HEADERS },
  );
}
