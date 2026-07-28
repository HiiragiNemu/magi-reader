export const MIN_ADMIN_TOKEN_LENGTH = 32;

const MAX_HEADER_COMPONENT_LENGTH = 256;

const normalizedHeaderValue = (
  headers: Headers,
  name: string,
): string | null => {
  const value = headers.get(name)?.trim();
  if (!value) return null;
  return value.slice(0, MAX_HEADER_COMPONENT_LENGTH);
};

export const getUsableAdminToken = (
  token: string | undefined,
): string | null => {
  const normalized = token?.trim();
  return normalized && normalized.length >= MIN_ADMIN_TOKEN_LENGTH
    ? normalized
    : null;
};

export const getAdminAccessConfiguration = (
  hasSubmissionsKv: boolean,
  token: string | undefined,
):
  | { ok: true; token: string }
  | { ok: false; status: 503 } => {
  const usableToken = getUsableAdminToken(token);
  return hasSubmissionsKv && usableToken
    ? { ok: true, token: usableToken }
    : { ok: false, status: 503 };
};

export const getRateLimitIdentity = (
  headers: Headers,
  createNonce: () => string = () => crypto.randomUUID(),
): string => {
  const cloudflareIp = normalizedHeaderValue(headers, 'cf-connecting-ip');
  if (cloudflareIp) return `cloudflare-ip:${cloudflareIp}`;

  const realIp = normalizedHeaderValue(headers, 'x-real-ip');
  if (realIp) return `proxy-ip:${realIp}`;

  const forwardedFor = normalizedHeaderValue(headers, 'x-forwarded-for')
    ?.split(',', 1)[0]
    ?.trim();
  if (forwardedFor) return `forwarded-ip:${forwardedFor}`;

  const clientHints = [
    normalizedHeaderValue(headers, 'user-agent'),
    normalizedHeaderValue(headers, 'accept-language'),
    normalizedHeaderValue(headers, 'accept-encoding'),
  ].filter((value): value is string => value !== null);

  if (clientHints.length > 0) {
    return `client-hints:${clientHints.join('|')}`;
  }

  return `request:${createNonce()}`;
};
