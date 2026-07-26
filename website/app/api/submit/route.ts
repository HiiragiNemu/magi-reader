import { NextRequest, NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';
import {
  getAdminAccessConfiguration,
  getRateLimitIdentity,
} from '@/lib/submission-security';

const SUBMISSION_PREFIX = 'submit_';
const RATE_LIMIT_PREFIX = 'ratelimit_submit_';
const RATE_LIMIT_WINDOW_SECONDS = 10 * 60;
const RATE_LIMIT_MAX_SUBMISSIONS = 5;
const MAX_REQUEST_BYTES = 2 * 1024 * 1024;
const MAX_STORY_ID_LENGTH = 256;
const MAX_CONTENT_LENGTH = 500_000;
const MAX_AUTHOR_LENGTH = 80;
const MIN_CONTENT_LENGTH = 10;
const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };

type ValidSubmission = {
  storyId: string;
  content: string;
  author: string;
};

type ValidationResult =
  | { ok: true; submission: ValidSubmission }
  | { ok: false; error: string };

type BodyResult =
  | { ok: true; value: unknown }
  | { ok: false; status: 400 | 413; error: string };

function errorResponse(error: string, status: number, headers?: HeadersInit) {
  return NextResponse.json(
    { error },
    {
      status,
      headers: {
        ...NO_STORE_HEADERS,
        ...headers,
      },
    },
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

async function readBoundedJson(request: NextRequest): Promise<BodyResult> {
  const declaredLength = request.headers.get('content-length');
  if (declaredLength) {
    const parsedLength = Number(declaredLength);
    if (Number.isFinite(parsedLength) && parsedLength > MAX_REQUEST_BYTES) {
      return { ok: false, status: 413, error: '提交内容过大' };
    }
  }

  if (!request.body) {
    return { ok: false, status: 400, error: '请求内容为空' };
  }

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    totalBytes += value.byteLength;
    if (totalBytes > MAX_REQUEST_BYTES) {
      await reader.cancel();
      return { ok: false, status: 413, error: '提交内容过大' };
    }
    chunks.push(value);
  }

  const bodyBytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bodyBytes.set(chunk, offset);
    offset += chunk.byteLength;
  }

  try {
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bodyBytes);
    return { ok: true, value: JSON.parse(text) as unknown };
  } catch {
    return { ok: false, status: 400, error: '请求必须是有效的 JSON' };
  }
}

function validateSubmission(value: unknown): ValidationResult {
  if (!isRecord(value)) {
    return { ok: false, error: '请求内容格式错误' };
  }

  const allowedFields = new Set(['story_id', 'content', 'author']);
  if (Object.keys(value).some((key) => !allowedFields.has(key))) {
    return { ok: false, error: '请求包含不支持的字段' };
  }

  if (typeof value.story_id !== 'string' || typeof value.content !== 'string') {
    return { ok: false, error: 'story_id 和 content 必须是字符串' };
  }
  if (value.author !== undefined && typeof value.author !== 'string') {
    return { ok: false, error: 'author 必须是字符串' };
  }

  const storyId = value.story_id.trim();
  const content = value.content;
  const author = value.author?.trim() || 'Anonymous';

  if (
    storyId.length === 0 ||
    storyId.length > MAX_STORY_ID_LENGTH ||
    /[\u0000-\u001f\u007f]/u.test(storyId)
  ) {
    return { ok: false, error: 'story_id 长度或格式不合法' };
  }
  if (
    author.length > MAX_AUTHOR_LENGTH ||
    /[\u0000-\u001f\u007f]/u.test(author)
  ) {
    return { ok: false, error: 'author 长度或格式不合法' };
  }
  if (
    content.length > MAX_CONTENT_LENGTH ||
    content.trim().length < MIN_CONTENT_LENGTH ||
    content.includes('\u0000')
  ) {
    return { ok: false, error: 'content 长度或格式不合法' };
  }

  return {
    ok: true,
    submission: {
      storyId,
      content,
      author,
    },
  };
}

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(value),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

async function consumeRateLimit(
  kv: SubmissionKvNamespace,
  request: NextRequest,
): Promise<{ allowed: true } | { allowed: false; retryAfter: number }> {
  const now = Math.floor(Date.now() / 1000);
  const windowStart =
    Math.floor(now / RATE_LIMIT_WINDOW_SECONDS) * RATE_LIMIT_WINDOW_SECONDS;
  const clientIdentity = getRateLimitIdentity(request.headers);
  const clientHash = (await sha256Hex(clientIdentity)).slice(0, 32);
  const key = `${RATE_LIMIT_PREFIX}${clientHash}_${windowStart}`;
  const storedCount = Number.parseInt((await kv.get(key)) || '0', 10);
  const count = Number.isFinite(storedCount) ? storedCount : 0;

  if (count >= RATE_LIMIT_MAX_SUBMISSIONS) {
    return {
      allowed: false,
      retryAfter: Math.max(
        1,
        windowStart + RATE_LIMIT_WINDOW_SECONDS - now,
      ),
    };
  }

  await kv.put(key, String(count + 1), {
    expirationTtl: RATE_LIMIT_WINDOW_SECONDS * 2,
  });
  return { allowed: true };
}

async function secureTokenEquals(
  providedToken: string,
  expectedToken: string,
): Promise<boolean> {
  const [providedHash, expectedHash] = await Promise.all([
    crypto.subtle.digest(
      'SHA-256',
      new TextEncoder().encode(providedToken),
    ),
    crypto.subtle.digest(
      'SHA-256',
      new TextEncoder().encode(expectedToken),
    ),
  ]);
  const providedBytes = new Uint8Array(providedHash);
  const expectedBytes = new Uint8Array(expectedHash);
  let difference = providedBytes.length ^ expectedBytes.length;

  for (let index = 0; index < providedBytes.length; index += 1) {
    difference |= providedBytes[index] ^ (expectedBytes[index] ?? 0);
  }
  return difference === 0;
}

async function getRuntimeEnv(): Promise<CloudflareEnv> {
  const { env } = await getCloudflareContext({ async: true });
  return env;
}

export async function POST(request: NextRequest) {
  try {
    const contentType = request.headers
      .get('content-type')
      ?.split(';', 1)[0]
      .trim()
      .toLowerCase();
    if (contentType !== 'application/json') {
      return errorResponse('Content-Type 必须是 application/json', 415);
    }

    const env = await getRuntimeEnv();
    const kv = env.SUBMISSIONS_KV;
    if (!kv) {
      return errorResponse('投稿服务暂不可用', 503);
    }

    const bodyResult = await readBoundedJson(request);
    if (!bodyResult.ok) {
      return errorResponse(bodyResult.error, bodyResult.status);
    }

    const validation = validateSubmission(bodyResult.value);
    if (!validation.ok) {
      return errorResponse(validation.error, 400);
    }

    // Only a structurally valid submission consumes the user's quota. This
    // prevents malformed requests from locking out other users behind a
    // shared IP address.
    const rateLimit = await consumeRateLimit(kv, request);
    if (!rateLimit.allowed) {
      return errorResponse('提交过于频繁，请稍后再试', 429, {
        'Retry-After': String(rateLimit.retryAfter),
      });
    }

    const submittedAt = new Date().toISOString();
    const key = `${SUBMISSION_PREFIX}${Date.now()}_${crypto.randomUUID()}`;
    await kv.put(
      key,
      JSON.stringify({
        story_id: validation.submission.storyId,
        content: validation.submission.content,
        author: validation.submission.author,
        submitted_at: submittedAt,
      }),
    );

    return NextResponse.json(
      { success: true, key },
      { headers: NO_STORE_HEADERS },
    );
  } catch (error: unknown) {
    console.error('Failed to store submission', error);
    return errorResponse('服务器暂时无法处理提交', 500);
  }
}

export async function GET(request: NextRequest) {
  try {
    const env = await getRuntimeEnv();
    const kv = env.SUBMISSIONS_KV;
    const adminConfiguration = getAdminAccessConfiguration(
      Boolean(kv),
      env.SUBMISSIONS_ADMIN_TOKEN,
    );
    if (!adminConfiguration.ok) {
      return errorResponse('管理员接口不可用', adminConfiguration.status);
    }
    if (!kv) return errorResponse('管理员接口不可用', 503);
    const adminToken = adminConfiguration.token;

    const authorization = request.headers.get('authorization');
    const bearerMatch = authorization?.match(/^Bearer\s+(.+)$/iu);
    const providedToken = bearerMatch?.[1]?.trim();
    if (
      !providedToken ||
      !(await secureTokenEquals(providedToken, adminToken))
    ) {
      return errorResponse('未授权', 401, {
        'WWW-Authenticate': 'Bearer realm="submissions-admin"',
      });
    }

    const url = new URL(request.url);
    const requestedLimit = Number.parseInt(url.searchParams.get('limit') || '50', 10);
    const limit = Number.isFinite(requestedLimit)
      ? Math.min(100, Math.max(1, requestedLimit))
      : 50;
    const cursor = url.searchParams.get('cursor') || undefined;
    const listed = await kv.list({
      prefix: SUBMISSION_PREFIX,
      limit,
      cursor,
    });

    const submissions = await Promise.all(
      listed.keys.map(async ({ name }) => {
        const value = await kv.get(name);
        if (!value) return null;

        try {
          const parsed = JSON.parse(value) as unknown;
          return isRecord(parsed)
            ? { ...parsed, key: name }
            : { key: name, invalid: true };
        } catch {
          return { key: name, invalid: true };
        }
      }),
    );

    return NextResponse.json(
      {
        submissions: submissions.filter(
          (submission) => submission !== null,
        ),
        cursor: listed.list_complete ? null : listed.cursor,
        list_complete: listed.list_complete,
      },
      { headers: NO_STORE_HEADERS },
    );
  } catch (error: unknown) {
    console.error('Failed to list submissions', error);
    return errorResponse('服务器暂时无法处理查询', 500);
  }
}
