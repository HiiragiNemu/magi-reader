export type StoryIndexEntry = {
  id: string;
  category: string;
  folder: string;
  percent: number;
  has_cn: boolean;
  has_jp?: boolean;
  filename_cn?: string;
  filename_jp?: string;
  path_cn?: string;
  path_jp?: string;
  json_paths_cn?: string[];
  json_sources_jp?: string[];
  json_sources_cn?: string[];
  title?: string;
  sections?: string[];
  game?: string;
  source_format?: string;
  source_count?: number;
  source_identity?: string;
  legacy_ids?: string[];
  translated_units_cn?: number;
  translation_units_total?: number;
  raw_voice_references?: number;
  groups_without_voice?: number;
  model_id?: string;
  character_group_id?: string;
  component_model_ids?: string[];
};

export type LoadedStoryIndex = {
  stories: StoryIndexEntry[];
  sha256: string;
};

const MAX_STORY_INDEX_BYTES = 32 * 1024 * 1024;
const MAX_STORY_INDEX_ENTRIES = 100_000;
const MAX_EXEDRA_LOCALIZATION_STATUS_BYTES = 2 * 1024 * 1024;
const MAX_EXEDRA_LOCALIZATION_STATUS_ENTRIES = 10_000;
const MAX_LEGACY_IDS_PER_STORY = 16;
const MAX_LEGACY_ROUTE_ALIASES = 10_000;
const SAFE_IDENTIFIER_RE = /^[A-Za-z0-9_.:-]+$/;
const ENCODED_PATH_CONTROL_RE = /%(?:25|2e|2f|5c)/i;
const EXEDRA_ROUTE_CATEGORIES = [
  'exedra_main',
  'exedra_sub',
  'exedra_character',
  'exedra_portrait',
  'exedra_reaction',
  'exedra_namae',
  'exedra_dungeon',
  'exedra_battle',
] as const;
type ExedraRouteCategory = (typeof EXEDRA_ROUTE_CATEGORIES)[number];
const EXEDRA_RAW_CATEGORIES: Record<ExedraRouteCategory, string> = {
  exedra_main: '1_Main',
  exedra_sub: '2_Sub',
  exedra_character: '3_Character',
  exedra_portrait: '4_Portrait',
  exedra_reaction: '6_Reaction',
  exedra_namae: '7_Namae',
  exedra_dungeon: '8_Dungeon',
  exedra_battle: '10_Battle',
};
const EXEDRA_GROUP_KEY_RE = /^[A-Za-z0-9_.-]{1,96}$/;
const EXEDRA_ROUTE_HASH_RE = /^(.+)_([a-f0-9]{10})$/;
const STORY_SOURCE_EXTENSION_RE = /\.(?:json|txt)$/i;
const MAX_REPOSITORY_JSON_SOURCES = 10_000;
const REPOSITORY_JSON_ROOTS = {
  jp: [
    'magireco-source-master/Scenarios_full',
    'magiraexedra-source-master/Scenarios_full',
  ],
  cn: [
    'magireco-translate-data-master/Scenarios_full',
    'magiraexedra-translate-data-master/Scenarios_full',
    'magireco-voice-translate-data-master/Scenarios_full/general_voice',
  ],
} as const;

export type StoryJsonLanguage = keyof typeof REPOSITORY_JSON_ROOTS;

export type DirectStorySources = {
  pathCn: string;
  pathJp: string;
  optionalCn: boolean;
  kind: 'exedra-trusted-runtime' | 'query';
};

export type TrustedExedraLocalizationStatusEntry = {
  story_id: string;
  source_identity: string;
};

export type TrustedExedraLocalizationStatus = {
  version: 1;
  total: number;
  entries: TrustedExedraLocalizationStatusEntry[];
  database_configured: boolean;
};

const isOptionalString = (value: unknown): value is string | undefined =>
  value === undefined || typeof value === 'string';

export const isSafeDataPath = (value: string): boolean => {
  if (
    value.length === 0 ||
    value.length > 4096 ||
    !value.startsWith('/data/') ||
    value.includes('\\') ||
    value.includes('?') ||
    value.includes('#') ||
    ENCODED_PATH_CONTROL_RE.test(value)
  ) {
    return false;
  }

  let decoded = value;
  try {
    for (let iteration = 0; iteration < 4; iteration += 1) {
      if (ENCODED_PATH_CONTROL_RE.test(decoded)) return false;
      const next = decodeURIComponent(decoded);
      if (next === decoded) break;
      decoded = next;
    }
  } catch {
    return false;
  }
  if (
    !decoded.startsWith('/data/') ||
    decoded.includes('\\') ||
    decoded.includes('?') ||
    decoded.includes('#') ||
    ENCODED_PATH_CONTROL_RE.test(decoded) ||
    /[\u0000-\u001f\u007f]/.test(decoded)
  ) {
    return false;
  }
  const segments = decoded.split('/');
  if (segments.some((segment) => segment === '.' || segment === '..')) {
    return false;
  }

  try {
    const parsed = new URL(decoded, 'https://magi-reader.invalid');
    return (
      parsed.origin === 'https://magi-reader.invalid' &&
      parsed.pathname.startsWith('/data/') &&
      parsed.search === '' &&
      parsed.hash === ''
    );
  } catch {
    return false;
  }
};

const parseExedraRoute = (
  id: string,
): {
  category: ExedraRouteCategory;
  groupKey: string;
  routeHash: string;
} | null => {
  for (const category of EXEDRA_ROUTE_CATEGORIES) {
    const prefix = `${category}_`;
    if (!id.startsWith(prefix)) continue;
    const match = id.slice(prefix.length).match(EXEDRA_ROUTE_HASH_RE);
    const groupKey = match?.[1] ?? '';
    if (!EXEDRA_GROUP_KEY_RE.test(groupKey)) {
      throw new Error('Exedra 剧情编号格式无效。');
    }
    return { category, groupKey, routeHash: match?.[2] ?? '' };
  }
  return null;
};

export const verifyExedraStoryId = async (id: string): Promise<boolean> => {
  const route = parseExedraRoute(id);
  if (!route) return true;
  const rawCategory = EXEDRA_RAW_CATEGORIES[route.category];
  const relativeSource =
    `${rawCategory}/${route.groupKey}/${route.groupKey}_jp.txt`;
  const identity = `exedra/${route.category}/${relativeSource}`;
  const digest = await crypto.subtle.digest(
    'SHA-1',
    new TextEncoder().encode(identity),
  );
  return toHex(digest).slice(0, 10) === route.routeHash;
};

export const resolveDirectStorySources = (
  id: string,
  queryCn: string | null,
  queryJp: string | null,
): DirectStorySources | null => {
  if (
    id.length === 0 ||
    id.length > 256 ||
    !SAFE_IDENTIFIER_RE.test(id)
  ) {
    throw new Error('剧情编号格式无效。');
  }

  const exedraRoute = parseExedraRoute(id);
  if (exedraRoute) {
    const { category, groupKey } = exedraRoute;
    const basePath = `/data/${category}/${groupKey}/${groupKey}`;
    const pathCn = `/api/exedra/localized/${encodeURIComponent(id)}`;
    const pathJp = `${basePath}_jp.txt`;
    if (!isSafeDataPath(pathJp)) {
      throw new Error('Exedra 剧情编号无法生成安全路径。');
    }
    return {
      pathCn,
      pathJp,
      optionalCn: true,
      kind: 'exedra-trusted-runtime',
    };
  }

  const hasQueryPaths = queryCn !== null || queryJp !== null;
  if (hasQueryPaths) {
    const pathCn = queryCn ?? '';
    const pathJp = queryJp ?? '';
    if (
      (pathCn && (
        !isSafeDataPath(pathCn) ||
        !STORY_SOURCE_EXTENSION_RE.test(pathCn)
      )) ||
      (pathJp && (
        !isSafeDataPath(pathJp) ||
        !STORY_SOURCE_EXTENSION_RE.test(pathJp)
      ))
    ) {
      throw new Error('剧情链接包含不安全的文件路径。');
    }
    if (pathCn || pathJp) {
      return {
        pathCn,
        pathJp,
        optionalCn: false,
        kind: 'query',
      };
    }
  }

  return null;
};

export const isSafeRepositoryStoryJsonPath = (
  value: string,
  language: StoryJsonLanguage,
): boolean => {
  if (
    value.length === 0 ||
    value.length > 4096 ||
    value.startsWith('/') ||
    value.includes('\\') ||
    value.includes('%') ||
    value.includes('?') ||
    value.includes('#') ||
    /[\u0000-\u001f\u007f]/u.test(value) ||
    !/\.json$/iu.test(value)
  ) {
    return false;
  }
  const segments = value.split('/');
  if (
    segments.some(
      segment => segment.length === 0 || segment === '.' || segment === '..',
    )
  ) {
    return false;
  }
  return REPOSITORY_JSON_ROOTS[language].some(
    root => value.startsWith(`${root}/`) && value.length > root.length + 1,
  );
};

export const isOptionalStorySourceUnavailable = (status: number): boolean =>
  status === 404 || status === 502 || status === 503;

const parseStory = (value: unknown, index: number): StoryIndexEntry => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`剧情目录第 ${index + 1} 项不是对象`);
  }
  const story = value as Record<string, unknown>;
  if (
    typeof story.id !== 'string' ||
    story.id.length === 0 ||
    story.id.length > 256 ||
    !SAFE_IDENTIFIER_RE.test(story.id)
  ) {
    throw new Error(`剧情目录第 ${index + 1} 项 id 无效`);
  }
  if (
    typeof story.category !== 'string' ||
    story.category.length === 0 ||
    story.category.length > 128 ||
    !SAFE_IDENTIFIER_RE.test(story.category)
  ) {
    throw new Error(`${story.id}: category 无效`);
  }
  if (
    typeof story.folder !== 'string' ||
    story.folder.length === 0 ||
    story.folder.length > 512 ||
    /[\u0000-\u001f\u007f]/.test(story.folder)
  ) {
    throw new Error(`${story.id}: folder 无效`);
  }
  if (
    !Number.isFinite(story.percent) ||
    !Number.isInteger(story.percent) ||
    Number(story.percent) < 0 ||
    Number(story.percent) > 100
  ) {
    throw new Error(`${story.id}: percent 无效`);
  }
  if (
    typeof story.has_cn !== 'boolean' ||
    (story.has_jp !== undefined && typeof story.has_jp !== 'boolean')
  ) {
    throw new Error(`${story.id}: 语言标记无效`);
  }

  for (const field of [
    'filename_cn',
    'filename_jp',
    'path_cn',
    'path_jp',
    'title',
    'game',
    'source_format',
    'source_identity',
  ] as const) {
    if (!isOptionalString(story[field])) {
      throw new Error(`${story.id}: ${field} 必须是字符串`);
    }
  }
  if (
    typeof story.source_identity === 'string' &&
    (
      story.source_identity.length === 0 ||
      story.source_identity.length > 1_024 ||
      /[\u0000-\u001f\u007f]/u.test(story.source_identity) ||
      story.source_identity.includes('\\') ||
      story.source_identity.split('/').some((part) => part === '.' || part === '..')
    )
  ) {
    throw new Error(`${story.id}: source_identity 无效`);
  }
  if (
    story.sections !== undefined &&
    (
      !Array.isArray(story.sections) ||
      story.sections.length > 10_000 ||
      story.sections.some(
        (section) => typeof section !== 'string' || section.length > 1024,
      )
    )
  ) {
    throw new Error(`${story.id}: sections 无效`);
  }
  if (
    story.json_paths_cn !== undefined &&
    (
      !Array.isArray(story.json_paths_cn) ||
      story.json_paths_cn.length === 0 ||
      story.json_paths_cn.length > 10_000 ||
      story.json_paths_cn.some(
        (path) =>
          typeof path !== 'string' ||
          !isSafeDataPath(path) ||
          !/\.json$/iu.test(path),
      ) ||
      new Set(story.json_paths_cn.map(path => path.toLowerCase())).size
        !== story.json_paths_cn.length
    )
  ) {
    throw new Error(`${story.id}: json_paths_cn 无效`);
  }
  for (const language of ['jp', 'cn'] as const) {
    const field = `json_sources_${language}` as const;
    const sources = story[field];
    if (sources === undefined) continue;
    if (
      !Array.isArray(sources) ||
      sources.length === 0 ||
      sources.length > MAX_REPOSITORY_JSON_SOURCES ||
      sources.some(
        path =>
          typeof path !== 'string' ||
          !isSafeRepositoryStoryJsonPath(path, language),
      ) ||
      new Set(sources.map(path => path.toLowerCase())).size !== sources.length ||
      story[`has_${language}`] !== true
    ) {
      throw new Error(`${story.id}: ${field} 无效`);
    }
    if (
      (story.source_format === 'organized_txt' ||
        story.source_format === 'general_voice_json') &&
      Number.isSafeInteger(story.source_count) &&
      sources.length !== story.source_count
    ) {
      throw new Error(`${story.id}: ${field} 与 source_count 数量不同`);
    }
  }
  if (
    story.source_count !== undefined &&
    (
      !Number.isSafeInteger(story.source_count) ||
      Number(story.source_count) <= 0 ||
      Number(story.source_count) > MAX_REPOSITORY_JSON_SOURCES
    )
  ) {
    throw new Error(`${story.id}: source_count 无效`);
  }
  if (story.source_format === 'general_voice_json') {
    const translated = story.translated_units_cn;
    const total = story.translation_units_total;
    const rawReferences = story.raw_voice_references;
    const groupsWithoutVoice = story.groups_without_voice;
    if (
      !Number.isSafeInteger(translated) ||
      !Number.isSafeInteger(total) ||
      !Number.isSafeInteger(rawReferences) ||
      !Number.isSafeInteger(groupsWithoutVoice) ||
      Number(translated) < 0 ||
      Number(total) < 0 ||
      Number(translated) > Number(total) ||
      Number(rawReferences) < Number(total) ||
      Number(groupsWithoutVoice) < 0 ||
      story.percent !== (
        Number(total) > 0
          ? Math.round(Number(translated) * 100 / Number(total))
          : 0
      ) ||
      typeof story.model_id !== 'string' ||
      !/^\d{6}$/u.test(story.model_id) ||
      typeof story.character_group_id !== 'string' ||
      !/^\d{4}$/u.test(story.character_group_id) ||
      story.character_group_id !== story.model_id.slice(0, 4)
    ) {
      throw new Error(`${story.id}: general_voice_json 汉化统计无效`);
    }
    if (
      story.component_model_ids !== undefined &&
      (
        !Array.isArray(story.component_model_ids) ||
        story.component_model_ids.length === 0 ||
        story.component_model_ids.length > 8 ||
        story.component_model_ids.some(
          modelId =>
            typeof modelId !== 'string' ||
            !/^\d{6}$/u.test(modelId) ||
            modelId.slice(0, 4) !== story.character_group_id ||
            modelId === story.model_id,
        ) ||
        new Set(story.component_model_ids).size !== story.component_model_ids.length
      )
    ) {
      throw new Error(`${story.id}: component_model_ids 无效`);
    }
  }
  if (
    story.legacy_ids !== undefined &&
    (
      story.game !== 'magireco' ||
      !Array.isArray(story.legacy_ids) ||
      story.legacy_ids.length === 0 ||
      story.legacy_ids.length > MAX_LEGACY_IDS_PER_STORY ||
      story.legacy_ids.some(
        (legacyId) =>
          typeof legacyId !== 'string' ||
          legacyId.length === 0 ||
          legacyId.length > 256 ||
          !SAFE_IDENTIFIER_RE.test(legacyId),
      )
    )
  ) {
    throw new Error(`${story.id}: legacy_ids 无效`);
  }

  const hasCn = story.has_cn;
  const hasJp = story.has_jp === true;
  const cnPath = typeof story.path_cn === 'string' ? story.path_cn : '';
  const jpPath = typeof story.path_jp === 'string' ? story.path_jp : '';
  if (hasCn !== Boolean(cnPath) || hasJp !== Boolean(jpPath)) {
    throw new Error(`${story.id}: 语言标记与 path 路径不一致`);
  }
  if ((cnPath && !isSafeDataPath(cnPath)) || (jpPath && !isSafeDataPath(jpPath))) {
    throw new Error(`${story.id}: path 必须是安全的同源 /data/ 路径`);
  }

  return value as StoryIndexEntry;
};

export const parseStoryIndex = (value: unknown): StoryIndexEntry[] => {
  if (
    !Array.isArray(value) ||
    value.length === 0 ||
    value.length > MAX_STORY_INDEX_ENTRIES
  ) {
    throw new Error('剧情目录格式或条目数无效');
  }
  const stories = value.map(parseStory);
  const routeOwners = new Map<string, string>();
  for (const story of stories) {
    const key = story.id.toLowerCase();
    const previous = routeOwners.get(key);
    if (previous) {
      throw new Error(`剧情目录 id 重复: ${previous}, ${story.id}`);
    }
    routeOwners.set(key, story.id);
  }
  let legacyAliasCount = 0;
  for (const story of stories) {
    for (const legacyId of story.legacy_ids ?? []) {
      const key = legacyId.toLowerCase();
      const previous = routeOwners.get(key);
      if (previous) {
        throw new Error(`旧剧情编号冲突: ${legacyId}: ${previous}`);
      }
      routeOwners.set(key, story.id);
      legacyAliasCount += 1;
      if (legacyAliasCount > MAX_LEGACY_ROUTE_ALIASES) {
        throw new Error('旧剧情编号总数超过安全限制');
      }
    }
  }
  return stories;
};

const isSafeSourceIdentity = (value: string): boolean =>
  value.length > 0 &&
  value.length <= 1_024 &&
  !/[\u0000-\u001f\u007f]/u.test(value) &&
  !value.includes('\\') &&
  !value.split('/').some((part) => part === '.' || part === '..');

export const parseTrustedExedraLocalizationStatus = (
  value: unknown,
): TrustedExedraLocalizationStatus => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Exedra 可信中文状态格式无效');
  }
  const record = value as Record<string, unknown>;
  if (
    record.version !== 1 ||
    typeof record.database_configured !== 'boolean' ||
    !Number.isSafeInteger(record.total) ||
    Number(record.total) < 0 ||
    !Array.isArray(record.entries) ||
    record.entries.length > MAX_EXEDRA_LOCALIZATION_STATUS_ENTRIES ||
    Number(record.total) !== record.entries.length
  ) {
    throw new Error('Exedra 可信中文状态版本或条目数无效');
  }

  const seen = new Set<string>();
  const entries = record.entries.map((value, index) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error(`Exedra 可信中文状态第 ${index + 1} 项无效`);
    }
    const entry = value as Record<string, unknown>;
    const storyId = typeof entry.story_id === 'string' ? entry.story_id : '';
    const sourceIdentity =
      typeof entry.source_identity === 'string' ? entry.source_identity : '';
    if (
      storyId.length === 0 ||
      storyId.length > 256 ||
      !SAFE_IDENTIFIER_RE.test(storyId) ||
      !sourceIdentity.startsWith('exedra:') ||
      !isSafeSourceIdentity(sourceIdentity) ||
      seen.has(storyId)
    ) {
      throw new Error(`Exedra 可信中文状态第 ${index + 1} 项身份无效`);
    }
    seen.add(storyId);
    return {
      story_id: storyId,
      source_identity: sourceIdentity,
    };
  });

  return {
    version: 1,
    total: entries.length,
    entries,
    database_configured: record.database_configured,
  };
};

export const mergeTrustedExedraLocalizations = (
  stories: readonly StoryIndexEntry[],
  status: TrustedExedraLocalizationStatus,
): StoryIndexEntry[] => {
  if (!status.database_configured || status.entries.length === 0) {
    return [...stories];
  }
  const entriesByStoryId = new Map(
    status.entries.map((entry) => [entry.story_id, entry]),
  );
  return stories.map((story) => {
    const trusted = entriesByStoryId.get(story.id);
    if (
      !trusted ||
      story.game !== 'exedra' ||
      story.has_cn ||
      story.path_cn ||
      !story.source_identity ||
      story.source_identity !== trusted.source_identity
    ) {
      return story;
    }
    return {
      ...story,
      percent: 100,
      has_cn: true,
      path_cn: `/api/exedra/localized/${encodeURIComponent(story.id)}`,
    };
  });
};

export const applyTrustedExedraLocalizationStatus = async (
  stories: readonly StoryIndexEntry[],
  fetchStatus: typeof fetch = fetch,
): Promise<StoryIndexEntry[]> => {
  try {
    const statusResponse = await fetchStatus(
      '/api/exedra/localization-status',
      {
        cache: 'no-store',
        credentials: 'same-origin',
      },
    );
    if (!statusResponse.ok) {
      throw new Error(`HTTP ${statusResponse.status}`);
    }
    const statusPayload = await readBoundedResponseBody(
      statusResponse,
      MAX_EXEDRA_LOCALIZATION_STATUS_BYTES,
      'Exedra 可信中文状态',
    );
    let statusRaw: unknown;
    try {
      statusRaw = JSON.parse(
        new TextDecoder('utf-8', { fatal: true }).decode(statusPayload),
      ) as unknown;
    } catch (error) {
      throw new Error(
        `Exedra 可信中文状态不是有效的 UTF-8 JSON: ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    }
    return mergeTrustedExedraLocalizations(
      stories,
      parseTrustedExedraLocalizationStatus(statusRaw),
    );
  } catch (error) {
    console.warn(
      'Exedra 可信中文状态暂时不可用；继续使用静态剧情目录。',
      error,
    );
    return stories.slice();
  }
};

export const findStoryByRouteId = (
  stories: readonly StoryIndexEntry[],
  routeId: string,
): StoryIndexEntry | undefined => {
  const key = routeId.toLowerCase();
  return stories.find(
    (story) =>
      story.id.toLowerCase() === key ||
      story.legacy_ids?.some(
        (legacyId) => legacyId.toLowerCase() === key,
      ),
  );
};

export const readBoundedResponseBody = async (
  response: Response,
  maxBytes: number,
  label: string,
): Promise<Uint8Array> => {
  if (!Number.isSafeInteger(maxBytes) || maxBytes <= 0) {
    throw new Error(`${label}大小限制无效`);
  }
  const tooLargeMessage = `${label}超过大小限制`;
  const declaredLengthRaw = response.headers.get('content-length');
  if (declaredLengthRaw !== null) {
    const declaredLength = Number(declaredLengthRaw);
    if (
      Number.isSafeInteger(declaredLength) &&
      declaredLength > maxBytes
    ) {
      await response.body?.cancel(tooLargeMessage);
      throw new Error(tooLargeMessage);
    }
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error(`${label}响应无法安全读取`);

  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel(tooLargeMessage);
        throw new Error(tooLargeMessage);
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const payload = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    payload.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return payload;
};

const toHex = (buffer: ArrayBuffer): string =>
  Array.from(
    new Uint8Array(buffer),
    (byte) => byte.toString(16).padStart(2, '0'),
  ).join('');

let cachedStoryIndex: LoadedStoryIndex | null = null;
let pendingStoryIndex: Promise<LoadedStoryIndex> | null = null;

const fetchStoryIndex = async (): Promise<LoadedStoryIndex> => {
  const response = await fetch('/story_index.json', {
    cache: 'no-store',
    credentials: 'same-origin',
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const payload = await readBoundedResponseBody(
    response,
    MAX_STORY_INDEX_BYTES,
    '剧情目录',
  );
  const sha256 = toHex(
    await crypto.subtle.digest('SHA-256', payload.buffer as ArrayBuffer),
  );
  let raw: unknown;
  try {
    raw = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(payload));
  } catch (error) {
    throw new Error(
      `剧情目录不是有效的 UTF-8 JSON: ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }
  const stories = parseStoryIndex(raw);
  return {
    stories: await applyTrustedExedraLocalizationStatus(stories),
    sha256,
  };
};

const waitWithAbort = <T>(promise: Promise<T>, signal: AbortSignal): Promise<T> =>
  new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('The operation was aborted.', 'AbortError'));
      return;
    }
    const onAbort = () => {
      reject(new DOMException('The operation was aborted.', 'AbortError'));
    };
    signal.addEventListener('abort', onAbort, { once: true });
    promise.then(
      value => {
        signal.removeEventListener('abort', onAbort);
        resolve(value);
      },
      error => {
        signal.removeEventListener('abort', onAbort);
        reject(error);
      },
    );
  });

export const loadStoryIndex = (
  signal: AbortSignal,
): Promise<LoadedStoryIndex> => {
  if (cachedStoryIndex) {
    return waitWithAbort(Promise.resolve(cachedStoryIndex), signal);
  }
  if (!pendingStoryIndex) {
    pendingStoryIndex = fetchStoryIndex()
      .then(result => {
        cachedStoryIndex = result;
        return result;
      })
      .finally(() => {
        pendingStoryIndex = null;
      });
  }
  return waitWithAbort(pendingStoryIndex, signal);
};
