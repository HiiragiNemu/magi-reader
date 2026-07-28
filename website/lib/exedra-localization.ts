import storyIndexJson from '@/public/story_index.json';

export const EXEDRA_CACHE_PREFIX = 'exedra-localization:v1:';
const MAX_SOURCE_BYTES = 8 * 1024 * 1024;
const MAX_BLOCKS_PER_SECTION = 4_000;
const MAX_TEXT_LENGTH = 20_000;
const EXEDRA_ID_RE = /^[A-Za-z0-9_.:-]{1,256}$/u;
const SECTION_RE = /^---\s*\[Section\s+(\d+)\]\s*\(Source:\s*([^()\r\n]+\.json)\s*\)\s*---$/iu;

export type ExedraProvenance =
  | 'local_human'
  | 'official_tw_human'
  | 'exedra_wiki_human';

export type ExedraStoryEntry = {
  id: string;
  category: string;
  folder: string;
  title: string;
  game?: string;
  path_cn: string;
  path_jp: string;
  source_identity: string;
};

export type ParsedBlock = {
  speaker: string;
  text: string;
  kind: 'dialogue' | 'narration';
};

export type ParsedSection = {
  number: number;
  source: string;
  blocks: ParsedBlock[];
};

export type CachedExedraLocalization = {
  version: 1;
  story_id: string;
  source_identity: string;
  provenance: ExedraProvenance;
  source_url: string;
  generated_at: string;
  jp_sha256: string;
  cn_sha256: string;
  text: string;
};

const entries = (Array.isArray(storyIndexJson) ? storyIndexJson : [])
  .filter((value): value is ExedraStoryEntry => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    const item = value as Partial<ExedraStoryEntry>;
    return item.game === 'exedra' &&
      typeof item.id === 'string' &&
      typeof item.category === 'string' &&
      typeof item.folder === 'string' &&
      typeof item.title === 'string' &&
      typeof item.path_cn === 'string' &&
      typeof item.path_jp === 'string' &&
      typeof item.source_identity === 'string';
  });

const entryMap = new Map(entries.map(entry => [entry.id, entry]));

export const EXEDRA_STORIES = entries;

export const findExedraStory = (storyId: string): ExedraStoryEntry | null =>
  EXEDRA_ID_RE.test(storyId) ? entryMap.get(storyId) ?? null : null;

const normalize = (value: string): string =>
  value.replace(/^\uFEFF/u, '').replace(/\r\n?/gu, '\n').replace(/\u0000/gu, '');

const clean = (value: unknown, maxLength = MAX_TEXT_LENGTH): string =>
  typeof value === 'string'
    ? normalize(value)
      .replace(/[\u0001-\u0008\u000b\u000c\u000e-\u001f\u007f]/gu, '')
      .trim()
      .slice(0, maxLength)
    : '';

const narrationSpeaker = (speaker: string): boolean =>
  /^(?:旁白|ナレーション|Narration|Narrator|心声|モノローグ)$/iu.test(speaker.trim());

const splitDialogue = (line: string): [string, string] => {
  const positions = [line.indexOf(':'), line.indexOf('：')].filter(index => index > 0);
  if (positions.length === 0) return ['旁白', line.trim()];
  const separator = Math.min(...positions);
  return [line.slice(0, separator).trim(), line.slice(separator + 1).trim()];
};

export const parseExedraTxt = (raw: string): ParsedSection[] => {
  const sections: ParsedSection[] = [];
  let current: ParsedSection | null = null;
  for (const original of normalize(raw).split('\n')) {
    const line = original.trim();
    if (!line) continue;
    if (line.startsWith('---')) {
      const match = line.match(SECTION_RE);
      if (!match) throw new Error(`Exedra Section 头无效：${line.slice(0, 160)}`);
      if (current) sections.push(current);
      const number = Number(match[1]);
      if (number !== sections.length + 1) throw new Error('Exedra Section 编号不连续');
      current = { number, source: match[2].trim(), blocks: [] };
      continue;
    }
    if (!current) throw new Error('Exedra 正文出现在首个 Section 之前');
    const [speaker, text] = splitDialogue(line);
    if (!speaker || !text) throw new Error('Exedra 含空说话人或空正文');
    current.blocks.push({
      speaker: clean(speaker, 160),
      text: clean(text),
      kind: narrationSpeaker(speaker) ? 'narration' : 'dialogue',
    });
    if (current.blocks.length > MAX_BLOCKS_PER_SECTION) {
      throw new Error('Exedra 单节事件数量超过安全上限');
    }
  }
  if (current) sections.push(current);
  if (!sections.length) throw new Error('Exedra TXT 不含 Section');
  return sections;
};

export const serializeExedraSections = (sections: ParsedSection[]): string => {
  const lines: string[] = [];
  for (const section of sections) {
    lines.push(`--- [Section ${section.number}] (Source: ${section.source}) ---`);
    for (const block of section.blocks) lines.push(`${block.speaker}：${block.text}`);
    lines.push('');
  }
  return `${lines.join('\n').trim()}\n`;
};

export const sha256ExedraText = async (value: string): Promise<string> => {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(normalize(value)),
  );
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
};

const readBoundedUtf8 = async (response: Response, label: string): Promise<string> => {
  if (!response.ok) throw new Error(`${label}读取失败（HTTP ${response.status}）`);
  const declared = Number(response.headers.get('content-length'));
  if (Number.isSafeInteger(declared) && declared > MAX_SOURCE_BYTES) {
    await response.body?.cancel(`${label}过大`);
    throw new Error(`${label}超过 8 MiB`);
  }
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength > MAX_SOURCE_BYTES) throw new Error(`${label}超过 8 MiB`);
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    throw new Error(`${label}不是有效 UTF-8`);
  }
};

export const readExedraJapaneseText = async ({
  request,
  env,
  entry,
}: {
  request: Request;
  env: CloudflareEnv;
  entry: ExedraStoryEntry;
}): Promise<string> => {
  if (!entry.path_jp) throw new Error('Exedra 条目缺少日文路径');
  const sourceRequest = new Request(new URL(entry.path_jp, request.url), {
    headers: { Accept: 'text/plain' },
  });
  const response = env.ASSETS
    ? await env.ASSETS.fetch(sourceRequest)
    : await fetch(sourceRequest);
  return readBoundedUtf8(response, 'Exedra 日文剧情');
};

export const exedraCacheKey = (storyId: string): string =>
  `${EXEDRA_CACHE_PREFIX}${storyId}`;

export const parseCachedExedraLocalization = (
  raw: string | null,
): CachedExedraLocalization | null => {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<CachedExedraLocalization> & {
      provenance?: unknown;
    };
    if (
      value.version !== 1 ||
      typeof value.story_id !== 'string' ||
      typeof value.source_identity !== 'string' ||
      !['local_human', 'official_tw_human', 'exedra_wiki_human']
        .includes(String(value.provenance)) ||
      typeof value.source_url !== 'string' ||
      typeof value.generated_at !== 'string' ||
      !/^[a-f0-9]{64}$/u.test(String(value.jp_sha256)) ||
      !/^[a-f0-9]{64}$/u.test(String(value.cn_sha256)) ||
      typeof value.text !== 'string' ||
      !value.text.trim()
    ) {
      return null;
    }
    return value as CachedExedraLocalization;
  } catch {
    return null;
  }
};

export const getTrustedCachedExedraLocalization = async ({
  kv,
  entry,
  jpSha256,
}: {
  kv: SubmissionKvNamespace | undefined;
  entry: ExedraStoryEntry;
  jpSha256: string;
}): Promise<CachedExedraLocalization | null> => {
  if (!kv) return null;
  const record = parseCachedExedraLocalization(
    await kv.get(exedraCacheKey(entry.id)),
  );
  return record &&
    record.story_id === entry.id &&
    record.source_identity === entry.source_identity &&
    record.jp_sha256 === jpSha256
    ? record
    : null;
};

export const listCachedExedraLocalizations = async (
  kv: SubmissionKvNamespace,
): Promise<Array<Omit<CachedExedraLocalization, 'text'>>> => {
  const records: Array<Omit<CachedExedraLocalization, 'text'>> = [];
  let cursor: string | undefined;
  do {
    const page = await kv.list({ prefix: EXEDRA_CACHE_PREFIX, limit: 1000, cursor });
    for (const key of page.keys) {
      const record = parseCachedExedraLocalization(await kv.get(key.name));
      if (!record) continue;
      const { text: _text, ...metadata } = record;
      records.push(metadata);
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return records.sort((left, right) =>
    left.source_identity.localeCompare(right.source_identity, 'en', { numeric: true }),
  );
};
