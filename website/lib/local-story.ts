import { parseStoryContent } from './story-parser.ts';

export const LOCAL_STORY_STORAGE_KEY = 'magi-reader-local-story-v1';
export const MAX_LOCAL_FILE_BYTES = 8 * 1024 * 1024;
export const MAX_LOCAL_STORY_BYTES = 12 * 1024 * 1024;

export type LocalStorySource = {
  name: string;
  raw: string;
};

export type LocalStoryPayload = {
  id: string;
  title: string;
  cn?: LocalStorySource;
  jp?: LocalStorySource;
};

type LocalLanguageHint = 'cn' | 'jp' | 'ambiguous' | null;

const languageFromFilename = (filename: string): LocalLanguageHint => {
  const stem = filename.replace(/\.[^.]+$/, '');
  const hasCn =
    /(?:^|[_\-.])(cn|zh|chs|cht|translated?)(?:[_\-.]|$)/i.test(stem);
  const hasJp =
    /(?:^|[_\-.])(jp|ja|jpn)(?:[_\-.]|$)/i.test(stem);
  if (hasCn && hasJp) return 'ambiguous';
  if (hasCn) return 'cn';
  if (hasJp) return 'jp';
  return null;
};

const inferBomlessUtf16 = (
  bytes: Uint8Array,
): 'utf-16le' | 'utf-16be' | null => {
  if (bytes.length < 4 || bytes.length % 2 !== 0) return null;

  const sampleLength = Math.min(bytes.length, 4096) & ~1;
  let evenNulls = 0;
  let oddNulls = 0;
  for (let index = 0; index < sampleLength; index += 2) {
    if (bytes[index] === 0) evenNulls += 1;
    if (bytes[index + 1] === 0) oddNulls += 1;
  }

  // A NUL byte is not part of ordinary UTF-8 or Shift-JIS prose. Even a
  // sparse but one-sided pattern is therefore meaningful for long CJK text,
  // where most UTF-16 code units do not contain a zero byte.
  if (oddNulls > 0 && evenNulls === 0) {
    return 'utf-16le';
  }
  if (evenNulls > 0 && oddNulls === 0) {
    return 'utf-16be';
  }
  if (oddNulls >= 2 && oddNulls >= evenNulls * 3) return 'utf-16le';
  if (evenNulls >= 2 && evenNulls >= oddNulls * 3) return 'utf-16be';
  return null;
};

export const decodeStoryBuffer = (buffer: ArrayBuffer): string => {
  const bytes = new Uint8Array(buffer);
  if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    return new TextDecoder('utf-8').decode(bytes.subarray(3));
  }
  if (bytes[0] === 0xff && bytes[1] === 0xfe) {
    return new TextDecoder('utf-16le').decode(bytes.subarray(2));
  }
  if (bytes[0] === 0xfe && bytes[1] === 0xff) {
    return new TextDecoder('utf-16be').decode(bytes.subarray(2));
  }

  const bomlessUtf16 = inferBomlessUtf16(bytes);
  if (bomlessUtf16) {
    return new TextDecoder(bomlessUtf16).decode(bytes);
  }

  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    return new TextDecoder('shift_jis').decode(bytes);
  }
};

export const readScenarioFile = async (file: File): Promise<LocalStorySource> => {
  if (!/\.(?:json|txt)$/i.test(file.name)) {
    throw new Error('目前可本地打开 .json 与 .txt 文件。');
  }
  if (file.size > MAX_LOCAL_FILE_BYTES) {
    throw new Error('单个文件不能超过 8 MB。');
  }
  return {
    name: file.name,
    raw: decodeStoryBuffer(await file.arrayBuffer()),
  };
};

const safeLocalId = (filename: string): string => {
  const stem = filename.replace(/\.[^.]+$/, '');
  const cleaned = stem.replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^-+|-+$/g, '');
  return `local-${cleaned || 'story'}`;
};

const isLocalSource = (value: unknown): value is LocalStorySource => {
  if (typeof value !== 'object' || value === null) return false;
  const source = value as Record<string, unknown>;
  return typeof source.name === 'string' && typeof source.raw === 'string';
};

export const isLocalStoryPayload = (value: unknown): value is LocalStoryPayload => {
  if (typeof value !== 'object' || value === null) return false;
  const payload = value as Record<string, unknown>;
  return (
    typeof payload.id === 'string' &&
    typeof payload.title === 'string' &&
    (payload.cn === undefined || isLocalSource(payload.cn)) &&
    (payload.jp === undefined || isLocalSource(payload.jp)) &&
    (isLocalSource(payload.cn) || isLocalSource(payload.jp))
  );
};

export const readLocalStoryPayload = (): LocalStoryPayload | null => {
  try {
    const stored = sessionStorage.getItem(LOCAL_STORY_STORAGE_KEY);
    if (!stored) return null;
    const parsed: unknown = JSON.parse(stored);
    return isLocalStoryPayload(parsed) ? parsed : null;
  } catch {
    return null;
  }
};

export const createLocalStoryPayload = async (files: File[]): Promise<LocalStoryPayload> => {
  if (files.length < 1 || files.length > 2) {
    throw new Error('请选择 1 个文件，或选择一对中日文文件。');
  }
  if (files.some(file => !/\.(?:json|txt)$/i.test(file.name))) {
    throw new Error('目前可本地打开 .json 与 .txt 文件。');
  }
  if (files.some(file => file.size > MAX_LOCAL_FILE_BYTES)) {
    throw new Error('单个文件不能超过 8 MB。');
  }
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
  if (totalBytes > MAX_LOCAL_STORY_BYTES) {
    throw new Error('所选文件总大小不能超过 12 MB。');
  }

  const sources = await Promise.all(files.map(async file => {
    const { raw } = await readScenarioFile(file);
    const parsed = parseStoryContent(raw, {
      filename: file.name,
      mergeConsecutiveTextLines: false,
    });
    if (parsed.lines.length === 0) {
      throw new Error(`${file.name} 中没有可显示的剧情文本。`);
    }
    return { name: file.name, raw };
  }));

  const sourcesWithLanguage = sources.map(source => ({
    source,
    language: languageFromFilename(source.name),
  }));
  const ambiguous = sourcesWithLanguage.find(
    ({ language }) => language === 'ambiguous',
  );
  if (ambiguous) {
    throw new Error(
      `${ambiguous.source.name} 的文件名同时包含中日文标记，无法判断语言。`,
    );
  }
  const declaredLanguages = sourcesWithLanguage
    .map(({ language }) => language)
    .filter((language): language is 'cn' | 'jp' => language !== null);
  if (
    files.length === 2 &&
    declaredLanguages.length === 2 &&
    declaredLanguages[0] === declaredLanguages[1]
  ) {
    throw new Error('两份文件标记为同一种语言；请选择一份中文和一份日文。');
  }
  if (files.length === 2 && declaredLanguages.length === 0) {
    throw new Error(
      '两份文件都没有语言标记；请在文件名中加入 _cn 与 _jp 后重试。',
    );
  }

  let cn: LocalStorySource | undefined;
  let jp: LocalStorySource | undefined;

  for (const { source, language } of sourcesWithLanguage) {
    if (language === 'cn') cn = source;
    if (language === 'jp') jp = source;
  }
  for (const { source, language } of sourcesWithLanguage) {
    if (language !== null) continue;
    if (!jp) jp = source;
    else if (!cn) cn = source;
  }

  const primary = jp ?? cn ?? sources[0];
  return {
    id: safeLocalId(primary.name),
    title: primary.name.replace(/\.[^.]+$/, ''),
    cn,
    jp,
  };
};

export const storeLocalStoryPayload = (payload: LocalStoryPayload): void => {
  try {
    sessionStorage.setItem(LOCAL_STORY_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    throw new Error('浏览器无法保存该本地文件；请尝试减小文件大小或关闭无痕模式。');
  }
};
