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
  title?: string;
  sections?: string[];
  game?: string;
};

export type LoadedStoryIndex = {
  stories: StoryIndexEntry[];
  sha256: string;
};

const MAX_STORY_INDEX_BYTES = 32 * 1024 * 1024;
const MAX_STORY_INDEX_ENTRIES = 100_000;
const SAFE_IDENTIFIER_RE = /^[A-Za-z0-9_.:-]+$/;
const ENCODED_PATH_CONTROL_RE = /%(?:2e|2f|5c)/i;

const isOptionalString = (value: unknown): value is string | undefined =>
  value === undefined || typeof value === 'string';

const isSafeDataPath = (value: string): boolean => {
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

  let decoded: string;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    return false;
  }
  if (
    !decoded.startsWith('/data/') ||
    decoded.includes('\\') ||
    /[\u0000-\u001f\u007f]/.test(decoded)
  ) {
    return false;
  }
  const segments = decoded.split('/');
  if (segments.some((segment) => segment === '.' || segment === '..')) {
    return false;
  }

  try {
    const parsed = new URL(value, 'https://magi-reader.invalid');
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
  ] as const) {
    if (!isOptionalString(story[field])) {
      throw new Error(`${story.id}: ${field} 必须是字符串`);
    }
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
  const seen = new Set<string>();
  for (const story of stories) {
    const key = story.id.toLocaleLowerCase();
    if (seen.has(key)) throw new Error(`剧情目录 id 重复: ${story.id}`);
    seen.add(key);
  }
  return stories;
};

const readBoundedBody = async (response: Response): Promise<Uint8Array> => {
  const declaredLengthRaw = response.headers.get('content-length');
  if (declaredLengthRaw !== null) {
    const declaredLength = Number(declaredLengthRaw);
    if (
      Number.isSafeInteger(declaredLength) &&
      declaredLength > MAX_STORY_INDEX_BYTES
    ) {
      await response.body?.cancel('剧情目录超过大小限制');
      throw new Error('剧情目录超过大小限制');
    }
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error('剧情目录响应无法安全读取');

  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_STORY_INDEX_BYTES) {
        await reader.cancel('剧情目录超过大小限制');
        throw new Error('剧情目录超过大小限制');
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

export const loadStoryIndex = async (
  signal: AbortSignal,
): Promise<LoadedStoryIndex> => {
  const response = await fetch('/story_index.json', {
    cache: 'no-store',
    credentials: 'same-origin',
    signal,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const payload = await readBoundedBody(response);
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
  return { stories: parseStoryIndex(raw), sha256 };
};
