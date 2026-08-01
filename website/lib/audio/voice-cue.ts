export const MAGIRECO_VOICE_ID_PATTERN =
  /^vo_char_[0-9]{4}_[0-9]{2}_[0-9]{2}$/;

export const EXEDRA_VOICE_ID_PATTERN =
  /^cv_[0-9]{6}_[a-z0-9]+(?:_[a-z0-9]+)*$/;

const EXEDRA_LOCAL_SOURCE_TO_SOUND = {
  cv_113401_1: 'cv_namae_call_01',
  cv_113401_2: 'cv_namae_item_get_03',
  cv_113401_3: 'cv_namae_good_02',
  cv_113401_4: 'cv_namae_encount_01',
  cv_113401_5: 'cv_namae_encount_05',
  cv_113501_1: 'cv_aq_hello_01',
  cv_113501_2: 'cv_aq_item_get_02',
  cv_113501_3: 'cv_aq_good_02',
  cv_113501_4: 'cv_aq_good_01',
  cv_113501_5: 'cv_aq_surprise_01',
  cv_113601_1: 'cv_yodaka_visit_01',
  cv_113601_2: 'cv_yodaka_wow_happy_m',
  cv_113601_3: 'cv_yodaka_wow_angry_m',
  cv_113601_4: 'cv_yodaka_wow_sad_m',
  cv_113601_5: 'cv_yodaka_wow_surprise_m',
  cv_114801_1: 'cv_114801_sad_02',
  cv_114801_2: 'cv_114801_cheese_13',
  cv_114801_3: 'cv_114801_original_13',
  cv_114801_4: 'cv_114801_original_09',
} as const satisfies Record<string, string>;

export type VoiceSystem = 'magireco' | 'exedra';

export interface VoiceCue {
  id: string;
  system: VoiceSystem;
}

export function isMagirecoVoiceId(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.length <= 32 &&
    MAGIRECO_VOICE_ID_PATTERN.test(value)
  );
}

export function isExedraVoiceId(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.length <= 96 &&
    EXEDRA_VOICE_ID_PATTERN.test(value)
  );
}

/**
 * Extract a Magia Record cue from the visible voice marker, for example:
 * `【vo_char_3031_00_01｜19秒】`.
 */
export function extractMagirecoVoiceId(text: string): string | null {
  const match = text.match(
    /(?:^|[^A-Za-z0-9_])(vo_char_[0-9]{4}_[0-9]{2}_[0-9]{2})(?![A-Za-z0-9_])/,
  );
  return match?.[1] ?? null;
}

/**
 * Accept only a bare Exedra cue name or the exact JSON source filename.
 * Paths and URLs are deliberately rejected.
 */
export function extractExedraVoiceId(source: string): string | null {
  const trimmed = source.trim();
  const candidate = trimmed.endsWith('.json')
    ? trimmed.slice(0, -'.json'.length)
    : trimmed;
  return isExedraVoiceId(candidate) ? candidate : null;
}

export function parseVoiceCue(cueId: string): VoiceCue | null {
  if (isMagirecoVoiceId(cueId)) {
    return { id: cueId, system: 'magireco' };
  }
  if (isExedraVoiceId(cueId)) {
    return { id: cueId, system: 'exedra' };
  }
  return null;
}

export function getMagirecoVoiceProxyUrl(voiceId: string): string {
  if (!isMagirecoVoiceId(voiceId)) {
    throw new TypeError('Invalid Magia Record voice cue ID');
  }
  return `/api/audio/magireco-voice/${voiceId}`;
}

export function getExedraWikiVoiceUrl(voiceId: string): string {
  if (!isExedraVoiceId(voiceId)) {
    throw new TypeError('Invalid Magia Exedra voice cue ID');
  }
  const wikiVoiceId = voiceId.replace(/^cv_100803_/, 'cv_100805_');
  const filename = `${wikiVoiceId}.ogg`;
  return `https://exedra.wiki/wiki/Special:Redirect/file/${encodeURIComponent(filename)}`;
}

export function getExedraVoiceUrl(voiceId: string): string {
  if (!isExedraVoiceId(voiceId)) {
    throw new TypeError('Invalid Magia Exedra voice cue ID');
  }
  const soundName =
    EXEDRA_LOCAL_SOURCE_TO_SOUND[
      voiceId as keyof typeof EXEDRA_LOCAL_SOURCE_TO_SOUND
    ];
  return soundName
    ? `/audio/exedra-local/${soundName}.ogg`
    : getExedraWikiVoiceUrl(voiceId);
}
