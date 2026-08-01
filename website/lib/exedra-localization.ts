export const EXEDRA_CACHE_PREFIX = 'exedra-localization:v1:';
const MAX_SOURCE_BYTES = 8 * 1024 * 1024;
const MAX_CATALOG_BYTES = 32 * 1024 * 1024;
const MAX_CATALOG_ENTRIES = 100_000;
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
  game: 'exedra';
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

type ExedraCatalog = {
  stories: ExedraStoryEntry[];
  byId: Map<string, ExedraStoryEntry>;
};

let catalogPromise: Promise<ExedraCatalog> | null = null;

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

const readBoundedBytes = async (
  response: Response,
  label: string,
  maxBytes: number,
): Promise<ArrayBuffer> => {
  if (!response.ok) throw new Error(`${label}读取失败（HTTP ${response.status}）`);
  const declared = Number(response.headers.get('content-length'));
  if (Number.isSafeInteger(declared) && declared > maxBytes) {
    await response.body?.cancel(`${label}过大`);
    throw new Error(`${label}超过 ${Math.floor(maxBytes / 1024 / 1024)} MiB`);
  }
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength > maxBytes) {
    throw new Error(`${label}超过 ${Math.floor(maxBytes / 1024 / 1024)} MiB`);
  }
  return bytes;
};

const decodeUtf8 = (bytes: ArrayBuffer, label: string): string => {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    throw new Error(`${label}不是有效 UTF-8`);
  }
};

export const parseExedraStoryIndex = (value: unknown): ExedraStoryEntry[] => {
  if (!Array.isArray(value) || value.length > MAX_CATALOG_ENTRIES) {
    throw new Error('剧情目录不是数组或超过安全上限');
  }
  const stories: ExedraStoryEntry[] = [];
  const ids = new Set<string>();
  for (const raw of value) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue;
    const item = raw as Record<string, unknown>;
    if (item.game !== 'exedra') continue;
    const id = clean(item.id, 256);
    const category = clean(item.category, 128);
    const folder = clean(item.folder, 512);
    const title = clean(item.title, 2_000);
    const pathCn = clean(item.path_cn, 2_000);
    const pathJp = clean(item.path_jp, 2_000);
    const sourceIdentity = clean(item.source_identity, 1_000);
    if (
      !EXEDRA_ID_RE.test(id) ||
      !category.startsWith('exedra_') ||
      !folder ||
      !pathJp.startsWith('/data/') ||
      (pathCn && !pathCn.startsWith('/data/')) ||
      !sourceIdentity.startsWith('exedra:')
    ) {
      throw new Error(`Exedra 剧情目录条目无效：${id || '<empty>'}`);
    }
    const folded = id.toLowerCase();
    if (ids.has(folded)) throw new Error(`Exedra 剧情编号重复：${id}`);
    ids.add(folded);
    stories.push({
      id,
      category,
      folder,
      title,
      game: 'exedra',
      path_cn: pathCn,
      path_jp: pathJp,
      source_identity: sourceIdentity,
    });
  }
  if (!stories.length) throw new Error('剧情目录不含 Exedra 条目');
  return stories;
};

const loadCatalog = async ({
  request,
  env,
}: {
  request: Request;
  env: CloudflareEnv;
}): Promise<ExedraCatalog> => {
  if (!catalogPromise) {
    catalogPromise = (async () => {
      const catalogRequest = new Request(new URL('/story_index.json', request.url), {
        headers: { Accept: 'application/json' },
      });
      const response = env.ASSETS
        ? await env.ASSETS.fetch(catalogRequest)
        : await fetch(catalogRequest);
      const bytes = await readBoundedBytes(
        response,
        '剧情目录',
        MAX_CATALOG_BYTES,
      );
      let value: unknown;
      try {
        value = JSON.parse(decodeUtf8(bytes, '剧情目录')) as unknown;
      } catch (error) {
        if (error instanceof SyntaxError) throw new Error('剧情目录不是有效 JSON');
        throw error;
      }
      const stories = parseExedraStoryIndex(value);
      return {
        stories,
        byId: new Map(stories.map(story => [story.id, story])),
      };
    })().catch(error => {
      catalogPromise = null;
      throw error;
    });
  }
  return catalogPromise;
};

export const loadExedraStories = async (context: {
  request: Request;
  env: CloudflareEnv;
}): Promise<ExedraStoryEntry[]> =>
  (await loadCatalog(context)).stories;

export const findExedraStory = async (
  storyId: string,
  context: { request: Request; env: CloudflareEnv },
): Promise<ExedraStoryEntry | null> => {
  if (!EXEDRA_ID_RE.test(storyId)) return null;
  return (await loadCatalog(context)).byId.get(storyId) ?? null;
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

export const readExedraJapaneseText = async ({
  request,
  env,
  entry,
}: {
  request: Request;
  env: CloudflareEnv;
  entry: ExedraStoryEntry;
}): Promise<string> => {
  const sourceRequest = new Request(new URL(entry.path_jp, request.url), {
    headers: { Accept: 'text/plain' },
  });
  const response = env.ASSETS
    ? await env.ASSETS.fetch(sourceRequest)
    : await fetch(sourceRequest);
  return decodeUtf8(
    await readBoundedBytes(response, 'Exedra 日文剧情', MAX_SOURCE_BYTES),
    'Exedra 日文剧情',
  );
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
      const { text, ...metadata } = record;
      void text;
      records.push(metadata);
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return records.sort((left, right) =>
    left.source_identity.localeCompare(right.source_identity, 'en', { numeric: true }),
  );
};
