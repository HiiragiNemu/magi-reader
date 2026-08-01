type TurnstileResponse = {
  success?: boolean;
  action?: string;
  hostname?: string;
  'error-codes'?: string[];
};

export type TurnstileVerification =
  | { ok: true; hostname: string }
  | { ok: false; status: 400 | 503; error: string };

const SITEVERIFY_URL =
  'https://challenges.cloudflare.com/turnstile/v0/siteverify';

export const verifyTurnstileToken = async (
  options: {
    token: string;
    secret: string | undefined;
    remoteIp?: string;
    expectedAction?: string;
    allowedHostnames?: string;
  },
  fetcher: typeof fetch = fetch,
): Promise<TurnstileVerification> => {
  const secret = options.secret?.trim();
  if (!secret) {
    return { ok: false, status: 503, error: '人机验证尚未配置' };
  }
  const token = options.token.trim();
  if (!token || token.length > 2_048) {
    return { ok: false, status: 400, error: '请完成人机验证' };
  }

  const body = new URLSearchParams({
    secret,
    response: token,
    idempotency_key: crypto.randomUUID(),
  });
  if (options.remoteIp) body.set('remoteip', options.remoteIp);

  let response: Response;
  try {
    response = await fetcher(SITEVERIFY_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });
  } catch {
    return { ok: false, status: 503, error: '人机验证服务暂不可用' };
  }
  if (!response.ok) {
    return { ok: false, status: 503, error: '人机验证服务暂不可用' };
  }

  let result: TurnstileResponse;
  try {
    result = (await response.json()) as TurnstileResponse;
  } catch {
    return { ok: false, status: 503, error: '人机验证响应无效' };
  }
  if (!result.success) {
    return {
      ok: false,
      status: 400,
      error: result['error-codes']?.includes('timeout-or-duplicate')
        ? '人机验证已过期，请重新验证'
        : '人机验证失败，请重试',
    };
  }
  if (
    options.expectedAction &&
    result.action &&
    result.action !== options.expectedAction
  ) {
    return { ok: false, status: 400, error: '人机验证用途不匹配' };
  }

  const allowed = (options.allowedHostnames ?? '')
    .split(',')
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
  const hostname = (result.hostname ?? '').toLowerCase();
  if (allowed.length > 0 && !allowed.includes(hostname)) {
    return { ok: false, status: 400, error: '人机验证来源不匹配' };
  }
  return { ok: true, hostname };
};
