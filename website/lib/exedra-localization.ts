import storyIndexJson from '@/public/story_index.json';

const CACHE_PREFIX = 'exedra-localization:v1:';
const MAX_JP_BYTES = 8 * 1024 * 1024;
const MAX_BLOCKS = 4_000;
const MAX_TEXT_LENGTH = 20_000;
const AI_CHUNK_SIZE = 28;
const EXEDRA_ID_RE = /^[A-Za-z0-9_.:-]{1,256}$/u;
const SECTION_RE = /^---\s*\[Section\s+(\d+)\]\s*\(Source:\s*([^()\r\n]+\.json)\s*\)\s*---$/iu;
const WIKI_STORY_SUFFIX_RE = /\/Story\/Chinese\s*$/iu;

export type ExedraProvenance =
  | 'local_human'
  | 'official_tw_human'
  | 'exedra_wiki_human'
  | 'machine_translation';

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

type ParsedBlock = {
  speaker: string;
  text: string;
  kind: 'dialogue' | 'narration';
};

type ParsedSection = {
  number: number;
  source: string;
  blocks: ParsedBlock[];
};

type CachedLocalization = {
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

export const exedraDynamicCnPath = (storyId: string): string =>
  `/api/exedra/localized/${encodeURIComponent(storyId)}`;

export const augmentExedraCnPaths = <T extends Record<string, unknown>>(items: T[]): T[] =>
  items.map(item => {
    if (item.game !== 'exedra' || typeof item.id !== 'string' ||
        typeof item.path_jp !== 'string' || !item.path_jp ||
        (typeof item.path_cn === 'string' && item.path_cn)) {
      return item;
    }
    return {
      ...item,
      path_cn: exedraDynamicCnPath(item.id),
      has_cn: true,
      percent: 100,
      localization_dynamic: true,
    };
  });

const normalize = (value: string): string =>
  value.replace(/^\uFEFF/u, '').replace(/\r\n?/gu, '\n').replace(/\u0000/gu, '');

const clean = (value: unknown, maxLength = MAX_TEXT_LENGTH): string =>
  typeof value === 'string'
    ? normalize(value).replace(/[\u0001-\u0008\u000b\u000c\u000e-\u001f\u007f]/gu, '')
      .trim().slice(0, maxLength)
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
    if (current.blocks.length > MAX_BLOCKS) throw new Error('Exedra 单节事件数量超过安全上限');
  }
  if (current) sections.push(current);
  if (!sections.length) throw new Error('Exedra TXT 不含 Section');
  return sections;
};

const serializeSections = (sections: ParsedSection[]): string => {
  const lines: string[] = [];
  for (const section of sections) {
    lines.push(`--- [Section ${section.number}] (Source: ${section.source}) ---`);
    for (const block of section.blocks) lines.push(`${block.speaker}：${block.text}`);
    lines.push('');
  }
  return `${lines.join('\n').trim()}\n`;
};

const sha256 = async (value: string): Promise<string> => {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(normalize(value)));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
};

const readBoundedText = async (response: Response, label: string): Promise<string> => {
  if (!response.ok) throw new Error(`${label}读取失败（HTTP ${response.status}）`);
  const declared = Number(response.headers.get('content-length'));
  if (Number.isSafeInteger(declared) && declared > MAX_JP_BYTES) {
    await response.body?.cancel(`${label}过大`);
    throw new Error(`${label}超过 8 MiB`);
  }
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength > MAX_JP_BYTES) throw new Error(`${label}超过 8 MiB`);
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    throw new Error(`${label}不是有效 UTF-8`);
  }
};

const cacheKey = (storyId: string): string => `${CACHE_PREFIX}${storyId}`;

const parseCache = (raw: string | null): CachedLocalization | null => {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<CachedLocalization>;
    if (value.version !== 1 || typeof value.story_id !== 'string' ||
        typeof value.source_identity !== 'string' ||
        !['local_human', 'official_tw_human', 'exedra_wiki_human', 'machine_translation']
          .includes(String(value.provenance)) ||
        typeof value.source_url !== 'string' || typeof value.generated_at !== 'string' ||
        !/^[a-f0-9]{64}$/u.test(String(value.jp_sha256)) ||
        !/^[a-f0-9]{64}$/u.test(String(value.cn_sha256)) ||
        typeof value.text !== 'string') return null;
    return value as CachedLocalization;
  } catch {
    return null;
  }
};

const htmlEntities = (value: string): string => value
  .replace(/&nbsp;/giu, ' ')
  .replace(/&amp;/giu, '&')
  .replace(/&lt;/giu, '<')
  .replace(/&gt;/giu, '>')
  .replace(/&quot;/giu, '"')
  .replace(/&#39;|&apos;/giu, "'")
  .replace(/&#(\d+);/gu, (_, code: string) => String.fromCodePoint(Number(code)))
  .replace(/&#x([a-f0-9]+);/giu, (_, code: string) => String.fromCodePoint(Number.parseInt(code, 16)));

const visibleWikiLines = (html: string): ParsedBlock[] => {
  const text = htmlEntities(html
    .replace(/<br\s*\/?\s*>/giu, '\n')
    .replace(/<\/p>|<\/li>|<\/tr>|<\/div>|<\/h\d>/giu, '\n')
    .replace(/<style[\s\S]*?<\/style>|<script[\s\S]*?<\/script>/giu, '')
    .replace(/<[^>]+>/gu, ''));
  const blocks: ParsedBlock[] = [];
  for (const rawLine of text.split('\n')) {
    const line = rawLine.replace(/\s+/gu, ' ').trim();
    if (!line || line.length > MAX_TEXT_LENGTH) continue;
    const positions = [line.indexOf(':'), line.indexOf('：')].filter(index => index > 0 && index < 160);
    if (!positions.length) continue;
    const separator = Math.min(...positions);
    const speaker = clean(line.slice(0, separator), 160);
    const body = clean(line.slice(separator + 1));
    if (!speaker || !body) continue;
    blocks.push({ speaker, text: body, kind: narrationSpeaker(speaker) ? 'narration' : 'dialogue' });
  }
  return blocks;
};

const wikiSearchTerms = (entry: ExedraStoryEntry, sections: ParsedSection[]): string[] => {
  const firstSpeaker = sections.flatMap(section => section.blocks)
    .find(block => block.kind === 'dialogue')?.speaker ?? '';
  return [
    `${entry.folder} Story Chinese`,
    `${entry.title} Story Chinese`,
    `${firstSpeaker} Story Chinese`,
  ].map(value => value.trim()).filter(Boolean);
};

const tryWiki = async (
  baseUrl: string,
  entry: ExedraStoryEntry,
  jpSections: ParsedSection[],
): Promise<{ text: string; sourceUrl: string } | null> => {
  if (entry.category !== 'exedra_character') return null;
  const api = `${baseUrl.replace(/\/$/u, '')}/api.php`;
  const expected = jpSections.flatMap(section => section.blocks);
  for (const term of wikiSearchTerms(entry, jpSections)) {
    try {
      const searchUrl = new URL(api);
      searchUrl.search = new URLSearchParams({
        action: 'query', list: 'search', srsearch: term, srlimit: '10', format: 'json', origin: '*',
      }).toString();
      const searchResponse = await fetch(searchUrl, { headers: { Accept: 'application/json' } });
      if (!searchResponse.ok) continue;
      const searchPayload = await searchResponse.json() as {
        query?: { search?: Array<{ title?: unknown }> };
      };
      const titles = (searchPayload.query?.search ?? [])
        .map(item => typeof item.title === 'string' ? item.title : '')
        .filter(title => WIKI_STORY_SUFFIX_RE.test(title));
      for (const title of titles) {
        const parseUrl = new URL(api);
        parseUrl.search = new URLSearchParams({
          action: 'parse', page: title, prop: 'text', format: 'json', origin: '*',
        }).toString();
        const parsedResponse = await fetch(parseUrl, { headers: { Accept: 'application/json' } });
        if (!parsedResponse.ok) continue;
        const parsedPayload = await parsedResponse.json() as { parse?: { text?: unknown } };
        const html = typeof parsedPayload.parse?.text === 'string' ? parsedPayload.parse.text : '';
        const wikiBlocks = visibleWikiLines(html);
        if (wikiBlocks.length !== expected.length) continue;
        const kindMatches = wikiBlocks.every((block, index) => block.kind === expected[index].kind);
        if (!kindMatches) continue;
        let offset = 0;
        const cnSections = jpSections.map(section => ({
          ...section,
          blocks: section.blocks.map(() => wikiBlocks[offset++]),
        }));
        return {
          text: serializeSections(cnSections),
          sourceUrl: `${baseUrl.replace(/\/$/u, '')}/wiki/${encodeURIComponent(title.replace(/ /gu, '_'))}`,
        };
      }
    } catch (error) {
      console.warn('Exedra Wiki lookup failed', term, error);
    }
  }
  return null;
};

type AiItem = { speaker?: unknown; text?: unknown };

const extractAiItems = (value: unknown): AiItem[] | null => {
  const response = value as { response?: unknown; result?: unknown };
  const candidate = typeof response?.response === 'string'
    ? response.response
    : typeof response?.result === 'string'
      ? response.result
      : typeof value === 'string' ? value : '';
  if (!candidate) return null;
  const start = candidate.indexOf('{');
  const end = candidate.lastIndexOf('}');
  if (start < 0 || end <= start) return null;
  try {
    const parsed = JSON.parse(candidate.slice(start, end + 1)) as { items?: unknown };
    return Array.isArray(parsed.items) ? parsed.items as AiItem[] : null;
  } catch {
    return null;
  }
};

const translateChunk = async (
  ai: CloudflareAiBinding,
  model: string,
  blocks: ParsedBlock[],
): Promise<ParsedBlock[]> => {
  const input = blocks.map((block, index) => ({
    index,
    speaker: block.speaker,
    text: block.text,
    kind: block.kind,
  }));
  const prompt = [
    '你是《魔法少女小圆》系列剧情的简体中文本地化编辑。',
    '把输入的日文剧情逐项译成自然、克制、角色口吻一致的简体中文。',
    '不得增删、合并、拆分或重排条目。角色名也翻译为常用简体中文名。',
    '保留专有符号、数字和占位符。旁白 speaker 使用“旁白”。',
    '只输出严格 JSON：{"items":[{"speaker":"...","text":"..."}]}。',
    `输入：${JSON.stringify(input)}`,
  ].join('\n');
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const result = await ai.run(model, {
      messages: [
        { role: 'system', content: 'Return JSON only. Never use Markdown fences.' },
        { role: 'user', content: prompt },
      ],
      temperature: 0.15,
      max_tokens: 6_000,
    });
    const items = extractAiItems(result);
    if (!items || items.length !== blocks.length) continue;
    const translated = items.map((item, index): ParsedBlock => {
      const speaker = clean(item.speaker, 160);
      const text = clean(item.text);
      if (!speaker || !text) throw new Error(`AI 翻译第 ${index + 1} 项为空`);
      return { speaker, text, kind: blocks[index].kind };
    });
    return translated;
  }
  throw new Error('AI 未返回与输入等长的严格 JSON');
};

const machineTranslate = async (
  ai: CloudflareAiBinding,
  model: string,
  sections: ParsedSection[],
): Promise<string> => {
  const translatedSections: ParsedSection[] = [];
  for (const section of sections) {
    const translated: ParsedBlock[] = [];
    for (let start = 0; start < section.blocks.length; start += AI_CHUNK_SIZE) {
      translated.push(...await translateChunk(ai, model, section.blocks.slice(start, start + AI_CHUNK_SIZE)));
    }
    translatedSections.push({ ...section, blocks: translated });
  }
  return serializeSections(translatedSections);
};

export const loadOrCreateExedraLocalization = async ({
  request,
  env,
  entry,
}: {
  request: Request;
  env: CloudflareEnv;
  entry: ExedraStoryEntry;
}): Promise<CachedLocalization> => {
  if (entry.path_cn) throw new Error('本地已有中文的 Exedra 条目不应进入动态翻译');
  if (!entry.path_jp) throw new Error('Exedra 条目缺少日文路径');
  const sourceRequest = new Request(new URL(entry.path_jp, request.url), {
    headers: { Accept: 'text/plain' },
  });
  const jpResponse = env.ASSETS
    ? await env.ASSETS.fetch(sourceRequest)
    : await fetch(sourceRequest);
  const jpText = await readBoundedText(jpResponse, 'Exedra 日文剧情');
  const jpSha256 = await sha256(jpText);
  const existing = env.SUBMISSIONS_KV
    ? parseCache(await env.SUBMISSIONS_KV.get(cacheKey(entry.id)))
    : null;
  if (existing && existing.jp_sha256 === jpSha256 && existing.source_identity === entry.source_identity) {
    return existing;
  }

  const sections = parseExedraTxt(jpText);
  const wiki = await tryWiki(env.EXEDRA_WIKI_BASE_URL || 'https://exedra.wiki', entry, sections);
  let text: string;
  let provenance: ExedraProvenance;
  let sourceUrl = '';
  if (wiki) {
    text = wiki.text;
    provenance = 'exedra_wiki_human';
    sourceUrl = wiki.sourceUrl;
  } else {
    if (!env.AI) throw new Error('Exedra 缺少可信中文，且 Workers AI 尚未绑定');
    text = await machineTranslate(
      env.AI,
      env.EXEDRA_TRANSLATION_MODEL || '@cf/meta/llama-3.1-8b-instruct-fast',
      sections,
    );
    provenance = 'machine_translation';
  }
  const record: CachedLocalization = {
    version: 1,
    story_id: entry.id,
    source_identity: entry.source_identity,
    provenance,
    source_url: sourceUrl,
    generated_at: new Date().toISOString(),
    jp_sha256: jpSha256,
    cn_sha256: await sha256(text),
    text,
  };
  if (env.SUBMISSIONS_KV) await env.SUBMISSIONS_KV.put(cacheKey(entry.id), JSON.stringify(record));
  return record;
};

export const listCachedExedraLocalizations = async (
  kv: SubmissionKvNamespace,
): Promise<Array<Omit<CachedLocalization, 'text'>>> => {
  const records: Array<Omit<CachedLocalization, 'text'>> = [];
  let cursor: string | undefined;
  do {
    const page = await kv.list({ prefix: CACHE_PREFIX, limit: 1000, cursor });
    for (const key of page.keys) {
      const record = parseCache(await kv.get(key.name));
      if (!record) continue;
      const { text: _text, ...metadata } = record;
      records.push(metadata);
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return records;
};
