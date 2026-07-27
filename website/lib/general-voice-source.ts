export const GENERAL_VOICE_SOURCE_COMMIT =
  '196f4bfcfa28c446539b4611e4cce7992b0c40d1';

export const GENERAL_VOICE_UPSTREAM_BASES = [
  'https://566b00b8.magiaexedralive2dviewer.pages.dev/story/general',
  'https://feature-story-playback-local.magiaexedralive2dviewer.pages.dev/story/general',
] as const;

const MAX_MANIFEST_BYTES = 2 * 1024 * 1024;
const MAX_SCRIPT_BYTES = 2 * 1024 * 1024;
const MAX_MODELS = 2_000;
const MODEL_ID_RE = /^\d{6}$/u;

export type GeneralVoiceLanguage = 'cn' | 'en';

export type GeneralVoiceManifestEntry = {
  id: string;
  charId: string | null;
  char: { jp: string; cn: string; en: string } | null;
  costume: { jp: string; cn: string; en: string } | null;
  langs: Partial<Record<GeneralVoiceLanguage, { groups: number; voices: number }>>;
};

export type GeneralVoiceManifest = {
  version: 1;
  languages: GeneralVoiceLanguage[];
  models: GeneralVoiceManifestEntry[];
};

type GeneralVoiceChara = {
  id?: unknown;
  voice?: unknown;
  textHome?: unknown;
  motion?: unknown;
  face?: unknown;
};

type GeneralVoiceTurn = {
  autoTurnFirst?: unknown;
  autoTurnLast?: unknown;
  chara?: unknown;
};

export type GeneralVoiceScript = {
  story: Record<string, GeneralVoiceTurn[]>;
};

const cleanText = (value: unknown, maxLength: number): string =>
  typeof value === 'string'
    ? value.replace(/[\u0000-\u001f\u007f]/gu, ' ').trim().slice(0, maxLength)
    : '';

const boundedJson = async (response: Response, maxBytes: number, label: string) => {
  if (!response.ok) throw new Error(`${label}读取失败（HTTP ${response.status}）`);
  const declared = Number(response.headers.get('content-length'));
  if (Number.isSafeInteger(declared) && declared > maxBytes) {
    await response.body?.cancel(`${label}超过大小限制`);
    throw new Error(`${label}超过大小限制`);
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength > maxBytes) throw new Error(`${label}超过大小限制`);
  try {
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(buffer)) as unknown;
  } catch {
    throw new Error(`${label}不是有效的 UTF-8 JSON`);
  }
};

const fetchFromUpstreams = async (
  relativePath: string,
  maxBytes: number,
  label: string,
): Promise<unknown> => {
  let lastError: unknown;
  for (const base of GENERAL_VOICE_UPSTREAM_BASES) {
    try {
      const response = await fetch(`${base}/${relativePath}`, {
        headers: { Accept: 'application/json' },
        redirect: 'follow',
      });
      return await boundedJson(response, maxBytes, label);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError instanceof Error ? lastError : new Error(`${label}读取失败`);
};

const isLanguageMeta = (value: unknown): value is { groups: number; voices: number } => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return Number.isSafeInteger(record.groups) && Number(record.groups) >= 0 &&
    Number.isSafeInteger(record.voices) && Number(record.voices) >= 0;
};

const parseNameSet = (
  value: unknown,
): { jp: string; cn: string; en: string } | null => {
  if (value === null) return null;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  return {
    jp: cleanText(record.jp, 160),
    cn: cleanText(record.cn, 160),
    en: cleanText(record.en, 160),
  };
};

export const parseGeneralVoiceManifest = (value: unknown): GeneralVoiceManifest => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('语音清单顶层格式错误');
  }
  const record = value as Record<string, unknown>;
  if (record.version !== 1 || !Array.isArray(record.models) ||
      record.models.length === 0 || record.models.length > MAX_MODELS) {
    throw new Error('语音清单版本或模型数量无效');
  }
  const seen = new Set<string>();
  const models = record.models.map((item, index): GeneralVoiceManifestEntry => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      throw new Error(`语音清单第 ${index + 1} 项格式错误`);
    }
    const model = item as Record<string, unknown>;
    const id = typeof model.id === 'string' ? model.id : '';
    if (!MODEL_ID_RE.test(id) || seen.has(id)) {
      throw new Error(`语音清单模型 ID 无效或重复：${id}`);
    }
    seen.add(id);
    const langsRaw = model.langs;
    if (!langsRaw || typeof langsRaw !== 'object' || Array.isArray(langsRaw)) {
      throw new Error(`${id}: langs 无效`);
    }
    const langsRecord = langsRaw as Record<string, unknown>;
    const cn = isLanguageMeta(langsRecord.cn) ? langsRecord.cn : undefined;
    const en = isLanguageMeta(langsRecord.en) ? langsRecord.en : undefined;
    if (!cn && !en) throw new Error(`${id}: 不含可用语音脚本`);
    return {
      id,
      charId: typeof model.charId === 'string' && /^\d{4}$/u.test(model.charId)
        ? model.charId
        : null,
      char: parseNameSet(model.char),
      costume: parseNameSet(model.costume),
      langs: { ...(cn ? { cn } : {}), ...(en ? { en } : {}) },
    };
  });
  return {
    version: 1,
    languages: ['cn', 'en'],
    models,
  };
};

export const loadGeneralVoiceManifest = async (): Promise<GeneralVoiceManifest> =>
  parseGeneralVoiceManifest(
    await fetchFromUpstreams('manifest.json', MAX_MANIFEST_BYTES, '语音清单'),
  );

export const parseGeneralVoiceScript = (value: unknown): GeneralVoiceScript => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('语音脚本顶层格式错误');
  }
  const story = (value as Record<string, unknown>).story;
  if (!story || typeof story !== 'object' || Array.isArray(story)) {
    throw new Error('语音脚本缺少 story');
  }
  const result: Record<string, GeneralVoiceTurn[]> = {};
  for (const [key, turns] of Object.entries(story as Record<string, unknown>)) {
    if (!/^group_\d+$/u.test(key) || !Array.isArray(turns) || turns.length > 1_000) {
      throw new Error(`语音分组无效：${key}`);
    }
    result[key] = turns as GeneralVoiceTurn[];
  }
  if (Object.keys(result).length === 0) throw new Error('语音脚本没有分组');
  return { story: result };
};

export const loadGeneralVoiceScript = async (
  modelId: string,
  language: GeneralVoiceLanguage = 'cn',
): Promise<GeneralVoiceScript> => {
  if (!MODEL_ID_RE.test(modelId)) throw new Error('语音模型 ID 无效');
  return parseGeneralVoiceScript(
    await fetchFromUpstreams(`${language}/${modelId}.json`, MAX_SCRIPT_BYTES, '语音脚本'),
  );
};

const groupNumber = (key: string): number => Number(key.replace(/^group_/u, ''));

const numberValue = (value: unknown): number =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 0;

export const generalVoiceScriptToTxt = (
  script: GeneralVoiceScript,
  model: GeneralVoiceManifestEntry,
): string => {
  const speaker = model.char?.cn || model.costume?.cn || `模型${model.id}`;
  const lines: string[] = [];
  const groups = Object.entries(script.story)
    .sort(([left], [right]) => groupNumber(left) - groupNumber(right));
  groups.forEach(([groupKey, turns], sectionIndex) => {
    lines.push(`--- [Section ${sectionIndex + 1}] (Source: ${model.id}.json) ---`);
    const voices: string[] = [];
    const texts: string[] = [];
    let duration = 0;
    for (const rawTurn of turns) {
      if (!rawTurn || typeof rawTurn !== 'object' || Array.isArray(rawTurn)) continue;
      const turn = rawTurn as GeneralVoiceTurn;
      duration += numberValue(turn.autoTurnFirst) || numberValue(turn.autoTurnLast);
      if (!Array.isArray(turn.chara)) continue;
      for (const rawChara of turn.chara) {
        if (!rawChara || typeof rawChara !== 'object' || Array.isArray(rawChara)) continue;
        const chara = rawChara as GeneralVoiceChara;
        const voice = cleanText(chara.voice, 256);
        const text = cleanText(chara.textHome, 20_000).replace(/@+/gu, '／');
        if (voice) voices.push(voice);
        if (text) texts.push(text);
      }
    }
    const voiceLabel = [...new Set(voices)].join(', ') || groupKey;
    const body = texts.join(' ').trim() || `语音资源：${voiceLabel}`;
    lines.push(`${speaker}：【${voiceLabel}｜${Math.round(duration * 10) / 10}秒】${body}`);
    lines.push('');
  });
  return `${lines.join('\n').trim()}\n`;
};

export const generalVoiceCatalogEntries = (manifest: GeneralVoiceManifest) =>
  manifest.models
    .filter(model => model.langs.cn)
    .map(model => {
      const characterName = model.char?.cn || model.char?.jp || `角色${model.charId ?? model.id}`;
      const japaneseName = model.char?.jp || '';
      const folder = model.charId
        ? `${model.charId} - ${characterName}${japaneseName ? `（${japaneseName}）` : ''}`
        : `${model.id} - ${characterName}`;
      const costume = model.costume?.cn || model.costume?.jp || model.id;
      const count = model.langs.cn?.voices ?? model.langs.cn?.groups ?? 0;
      return {
        id: `voice_${model.id}`,
        category: 'general_voice',
        folder,
        percent: 100,
        has_cn: true,
        has_jp: false,
        filename_cn: `${model.id}_cn.txt`,
        path_cn: `/data/general_voice/${model.id}/${model.id}_cn.txt`,
        title: `${costume} · ${count} 条语音`,
        game: 'magireco',
        source_identity: `general_voice/${model.id}`,
      };
    });
