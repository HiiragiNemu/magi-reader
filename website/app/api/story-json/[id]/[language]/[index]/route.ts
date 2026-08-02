import { getCloudflareContext } from '@opennextjs/cloudflare';

import {
  fetchPublishedStoryJsonSource,
  fetchStoryJsonSource,
  loadStoryJsonCatalog,
  parseStoryJsonLanguage,
  parseStoryJsonSourceIndex,
  selectPublishedStoryJsonPath,
  selectStoryJsonSource,
  StoryJsonSourceError,
} from '@/lib/story-json-source';

export const dynamic = 'force-dynamic';

const SECURITY_HEADERS = {
  'Cache-Control': 'private, no-store',
  'Cross-Origin-Resource-Policy': 'same-origin',
  'X-Content-Type-Options': 'nosniff',
};

export async function GET(
  request: Request,
  context: {
    params: Promise<{ id: string; language: string; index: string }>;
  },
) {
  try {
    const { id, language: rawLanguage, index: rawIndex } =
      await context.params;
    const language = parseStoryJsonLanguage(rawLanguage);
    const index = parseStoryJsonSourceIndex(rawIndex);
    const storyId = id;
    const { env } = await getCloudflareContext({ async: true });
    const stories = await loadStoryJsonCatalog({
      requestUrl: request.url,
      assets: env.ASSETS,
    });
    const repositoryPath = selectStoryJsonSource({
      stories,
      storyId,
      language,
      index,
    });
    const publishedPath = selectPublishedStoryJsonPath({
      stories,
      storyId,
      language,
      index,
    });
    const publishedBytes = publishedPath
      ? await fetchPublishedStoryJsonSource({
          requestUrl: request.url,
          publishedPath,
          assets: env.ASSETS,
        })
      : undefined;
    const bytes = publishedBytes ?? await fetchStoryJsonSource({
      repositoryPath,
      language,
      sourceCommit: env.PROOFREADING_SOURCE_COMMIT,
      // Public reads never reuse the PR-writing credential.  A separately
      // scoped read-only token is optional; anonymous access remains valid.
      githubToken: env.STORY_JSON_GITHUB_TOKEN,
    });
    const body = bytes.buffer.slice(
      bytes.byteOffset,
      bytes.byteOffset + bytes.byteLength,
    ) as ArrayBuffer;
    return new Response(body, {
      status: 200,
      headers: {
        ...SECURITY_HEADERS,
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Length': String(bytes.byteLength),
        'Content-Disposition':
          `attachment; filename="story-${language}-${index}.json"`,
      },
    });
  } catch (error) {
    if (error instanceof StoryJsonSourceError) {
      return Response.json(
        { error: error.message },
        { status: error.status, headers: SECURITY_HEADERS },
      );
    }
    return Response.json(
      { error: '剧情 JSON 读取失败' },
      { status: 502, headers: SECURITY_HEADERS },
    );
  }
}
