import {
  findStoryByRouteId,
  isSafeDataPath,
  isSafeRepositoryStoryJsonPath,
  parseStoryIndex,
  readBoundedResponseBody,
  type StoryIndexEntry,
  type StoryJsonLanguage,
} from './story-index.ts';

const FIXED_REPOSITORY = 'HiiragiNemu/magi-reader';
const GITHUB_API_ORIGIN = 'https://api.github.com';
const SOURCE_COMMIT_RE = /^[0-9a-f]{40}$/iu;
const SAFE_STORY_ID_RE = /^[A-Za-z0-9_.:-]{1,256}$/u;
const SAFE_TOKEN_RE = /^[A-Za-z0-9_]{20,512}$/u;
const SOURCE_INDEX_RE = /^(?:0|[1-9][0-9]{0,3})$/u;
const MAX_STORY_INDEX_BYTES = 32 * 1024 * 1024;
export const MAX_STORY_JSON_BYTES = 8 * 1024 * 1024;
const UPSTREAM_TIMEOUT_MS = 15_000;
const ACCEPTED_SOURCE_CONTENT_TYPES = new Set([
  'application/json',
  'application/octet-stream',
  'application/vnd.github.raw+json',
  'text/plain',
]);

export class StoryJsonSourceError extends Error {
  readonly status: 400 | 404 | 413 | 502 | 503;

  constructor(
    status: 400 | 404 | 413 | 502 | 503,
    message: string,
  ) {
    super(message);
    this.name = 'StoryJsonSourceError';
    this.status = status;
  }
}

export const parseStoryJsonLanguage = (
  value: string,
): StoryJsonLanguage => {
  if (value !== 'jp' && value !== 'cn') {
    throw new StoryJsonSourceError(400, 'JSON 语言参数无效');
  }
  return value;
};

export const parseStoryJsonSourceIndex = (value: string): number => {
  if (!SOURCE_INDEX_RE.test(value)) {
    throw new StoryJsonSourceError(400, 'JSON 来源序号无效');
  }
  return Number(value);
};

export const selectStoryJsonSource = ({
  stories,
  storyId,
  language,
  index,
}: {
  stories: readonly StoryIndexEntry[];
  storyId: string;
  language: StoryJsonLanguage;
  index: number;
}): string => {
  if (!SAFE_STORY_ID_RE.test(storyId)) {
    throw new StoryJsonSourceError(400, '剧情编号无效');
  }
  if (!Number.isSafeInteger(index) || index < 0 || index > 9_999) {
    throw new StoryJsonSourceError(400, 'JSON 来源序号无效');
  }
  const story = findStoryByRouteId(stories, storyId);
  if (!story) {
    throw new StoryJsonSourceError(404, '没有找到该剧情');
  }
  const sources = language === 'jp'
    ? story.json_sources_jp
    : story.json_sources_cn;
  const source = sources?.[index];
  if (
    typeof source !== 'string' ||
    !isSafeRepositoryStoryJsonPath(source, language)
  ) {
    throw new StoryJsonSourceError(404, '该剧情没有此 JSON 来源');
  }
  return source;
};

export const selectPublishedStoryJsonPath = ({
  stories,
  storyId,
  language,
  index,
}: {
  stories: readonly StoryIndexEntry[];
  storyId: string;
  language: StoryJsonLanguage;
  index: number;
}): string | undefined => {
  if (language !== 'cn') return undefined;
  if (!SAFE_STORY_ID_RE.test(storyId)) {
    throw new StoryJsonSourceError(400, '剧情编号无效');
  }
  if (!Number.isSafeInteger(index) || index < 0 || index > 9_999) {
    throw new StoryJsonSourceError(400, 'JSON 来源序号无效');
  }
  const story = findStoryByRouteId(stories, storyId);
  if (!story) {
    throw new StoryJsonSourceError(404, '没有找到该剧情');
  }
  const publishedPath = story.json_paths_cn?.[index];
  if (publishedPath === undefined) return undefined;
  if (!isSafeDataPath(publishedPath) || !/\.json$/iu.test(publishedPath)) {
    throw new StoryJsonSourceError(503, '已发布剧情 JSON 路径无效');
  }
  return publishedPath;
};

export const loadStoryJsonCatalog = async ({
  requestUrl,
  assets,
  fetcher = fetch,
}: {
  requestUrl: string;
  assets?: CloudflareAssetsBinding;
  fetcher?: typeof fetch;
}): Promise<StoryIndexEntry[]> => {
  const catalogRequest = new Request(
    new URL('/story_index.json', requestUrl),
    { headers: { Accept: 'application/json' } },
  );
  let response: Response;
  try {
    response = assets
      ? await assets.fetch(catalogRequest)
      : await fetcher(catalogRequest);
  } catch {
    throw new StoryJsonSourceError(503, '剧情目录暂时不可用');
  }
  if (!response.ok) {
    void response.body?.cancel('Story index unavailable');
    throw new StoryJsonSourceError(503, '剧情目录暂时不可用');
  }
  const contentType = (
    response.headers.get('content-type') ?? ''
  ).split(';', 1)[0]?.trim().toLowerCase();
  if (contentType !== 'application/json') {
    void response.body?.cancel('Unexpected story index content type');
    throw new StoryJsonSourceError(503, '剧情目录返回格式异常');
  }

  let payload: Uint8Array;
  try {
    payload = await readBoundedResponseBody(
      response,
      MAX_STORY_INDEX_BYTES,
      '剧情目录',
    );
  } catch {
    throw new StoryJsonSourceError(503, '剧情目录读取失败');
  }
  try {
    const raw = JSON.parse(
      new TextDecoder('utf-8', { fatal: true }).decode(payload),
    ) as unknown;
    return parseStoryIndex(raw);
  } catch {
    throw new StoryJsonSourceError(503, '剧情目录内容无效');
  }
};

const githubContentsUrl = (
  repositoryPath: string,
  sourceCommit: string,
): string => {
  const encodedPath = repositoryPath
    .split('/')
    .map(segment => encodeURIComponent(segment))
    .join('/');
  const url = new URL(
    `/repos/${FIXED_REPOSITORY}/contents/${encodedPath}`,
    GITHUB_API_ORIGIN,
  );
  url.searchParams.set('ref', sourceCommit);
  return url.toString();
};

const readAndValidateStoryJson = async (
  response: Response,
  sourceLabel: string,
): Promise<Uint8Array> => {
  const contentType = (
    response.headers.get('content-type') ?? ''
  ).split(';', 1)[0]?.trim().toLowerCase();
  if (!contentType || !ACCEPTED_SOURCE_CONTENT_TYPES.has(contentType)) {
    void response.body?.cancel('Unexpected source JSON content type');
    throw new StoryJsonSourceError(502, `${sourceLabel}类型异常`);
  }

  let payload: Uint8Array;
  try {
    payload = await readBoundedResponseBody(
      response,
      MAX_STORY_JSON_BYTES,
      '剧情 JSON',
    );
  } catch (error) {
    if (
      error instanceof Error &&
      error.message.includes('超过大小限制')
    ) {
      throw new StoryJsonSourceError(
        413,
        '剧情 JSON 超过 8 MiB 安全上限',
      );
    }
    throw new StoryJsonSourceError(502, `${sourceLabel}读取失败`);
  }
  try {
    const parsed = JSON.parse(
      new TextDecoder('utf-8', { fatal: true }).decode(payload),
    ) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('top level is not an object');
    }
  } catch {
    throw new StoryJsonSourceError(502, '剧情 JSON 内容无效');
  }
  return payload;
};

export const fetchPublishedStoryJsonSource = async ({
  requestUrl,
  publishedPath,
  assets,
  fetcher = fetch,
}: {
  requestUrl: string;
  publishedPath: string;
  assets?: CloudflareAssetsBinding;
  fetcher?: typeof fetch;
}): Promise<Uint8Array | undefined> => {
  if (!isSafeDataPath(publishedPath) || !/\.json$/iu.test(publishedPath)) {
    throw new StoryJsonSourceError(404, '该剧情没有已发布 JSON');
  }
  const assetUrl = new URL(publishedPath, requestUrl);
  if (assetUrl.origin !== new URL(requestUrl).origin) {
    throw new StoryJsonSourceError(404, '该剧情没有已发布 JSON');
  }
  const assetRequest = new Request(assetUrl, {
    cache: 'force-cache',
    headers: { Accept: 'application/json' },
  });
  let response: Response;
  try {
    response = assets
      ? await assets.fetch(assetRequest)
      : await fetcher(assetRequest);
  } catch {
    return undefined;
  }
  if (response.status === 404) {
    void response.body?.cancel('Published story JSON not found');
    return undefined;
  }
  if (!response.ok) {
    void response.body?.cancel('Published story JSON unavailable');
    throw new StoryJsonSourceError(502, '已发布剧情 JSON 返回异常');
  }
  return readAndValidateStoryJson(response, '已发布剧情 JSON ');
};

export const fetchStoryJsonSource = async ({
  repositoryPath,
  language,
  sourceCommit,
  githubToken,
  fetcher = fetch,
}: {
  repositoryPath: string;
  language: StoryJsonLanguage;
  sourceCommit: string | undefined;
  githubToken?: string;
  fetcher?: typeof fetch;
}): Promise<Uint8Array> => {
  if (!isSafeRepositoryStoryJsonPath(repositoryPath, language)) {
    throw new StoryJsonSourceError(404, '该剧情没有此 JSON 来源');
  }
  const commit = sourceCommit?.trim() ?? '';
  if (!SOURCE_COMMIT_RE.test(commit)) {
    throw new StoryJsonSourceError(503, '剧情 JSON 来源版本尚未配置');
  }
  const token = githubToken?.trim() ?? '';
  if (token && !SAFE_TOKEN_RE.test(token)) {
    throw new StoryJsonSourceError(503, '剧情 JSON 来源凭据配置无效');
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);
  let response: Response;
  try {
    const headers = new Headers({
      Accept: 'application/vnd.github.raw+json',
      'User-Agent': 'magi-reader-story-json-source',
      'X-GitHub-Api-Version': '2022-11-28',
    });
    if (token) headers.set('Authorization', `Bearer ${token}`);
    response = await fetcher(
      githubContentsUrl(repositoryPath, commit.toLowerCase()),
      {
        // The URL includes the immutable 40-character commit.  This allows
        // framework/edge caches to reuse public source bytes without ever
        // caching a moving branch ref.
        cache: 'force-cache',
        headers,
        redirect: 'error',
        signal: controller.signal,
      },
    );
  } catch {
    clearTimeout(timeout);
    throw new StoryJsonSourceError(502, '剧情 JSON 来源暂时不可用');
  }

  try {
    if (response.status === 404) {
      void response.body?.cancel('Source JSON not found');
      throw new StoryJsonSourceError(404, '没有找到该剧情 JSON');
    }
    if (!response.ok) {
      void response.body?.cancel('Source JSON upstream failure');
      throw new StoryJsonSourceError(502, '剧情 JSON 来源返回异常');
    }
    return await readAndValidateStoryJson(response, '剧情 JSON 来源');
  } finally {
    clearTimeout(timeout);
  }
};
