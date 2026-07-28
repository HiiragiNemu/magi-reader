import { getUsableAdminToken } from '@/lib/submission-security';

export type ProofreadingAdminIdentity = {
  kind: 'shared-secret' | 'github';
  label: string;
  githubLogin?: string;
};

export type ProofreadingAdminAuthentication =
  | {
      ok: true;
      identity: ProofreadingAdminIdentity;
      githubToken?: string;
    }
  | { ok: false; status: 401 | 503; error: string };

const constantTimeEquals = async (
  left: string,
  right: string,
): Promise<boolean> => {
  const [leftHash, rightHash] = await Promise.all([
    crypto.subtle.digest('SHA-256', new TextEncoder().encode(left)),
    crypto.subtle.digest('SHA-256', new TextEncoder().encode(right)),
  ]);
  const leftBytes = new Uint8Array(leftHash);
  const rightBytes = new Uint8Array(rightHash);
  let difference = leftBytes.length ^ rightBytes.length;
  for (let index = 0; index < leftBytes.length; index += 1) {
    difference |= leftBytes[index] ^ (rightBytes[index] ?? 0);
  }
  return difference === 0;
};

const bearerToken = (request: Request): string => {
  const match = request.headers.get('authorization')?.match(/^Bearer\s+(.+)$/iu);
  return match?.[1]?.trim().slice(0, 1_024) ?? '';
};

const githubAuthentication = async (
  token: string,
  repository: string,
  fetcher: typeof fetch,
): Promise<ProofreadingAdminAuthentication> => {
  const headers = {
    Accept: 'application/vnd.github+json',
    Authorization: `Bearer ${token}`,
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'magi-reader-proofreading-admin',
  };
  const [userResponse, repoResponse] = await Promise.all([
    fetcher('https://api.github.com/user', { headers, cache: 'no-store' }),
    fetcher(`https://api.github.com/repos/${repository}`, {
      headers,
      cache: 'no-store',
    }),
  ]);
  if (!userResponse.ok || !repoResponse.ok) {
    return { ok: false, status: 401, error: 'GitHub 令牌无效或无权访问仓库' };
  }
  const user = (await userResponse.json()) as { login?: unknown };
  const repo = (await repoResponse.json()) as {
    permissions?: { admin?: boolean; maintain?: boolean; push?: boolean };
  };
  const permissions = repo.permissions;
  if (!permissions?.admin && !permissions?.maintain && !permissions?.push) {
    return { ok: false, status: 401, error: '该 GitHub 账户没有仓库写入权限' };
  }
  const login = typeof user.login === 'string' ? user.login : 'GitHub reviewer';
  return {
    ok: true,
    identity: {
      kind: 'github',
      label: `GitHub:${login}`,
      githubLogin: login,
    },
    githubToken: token,
  };
};

export const authenticateProofreadingAdmin = async (
  request: Request,
  env: CloudflareEnv,
  fetcher: typeof fetch = fetch,
): Promise<ProofreadingAdminAuthentication> => {
  const token = bearerToken(request);
  if (!token) {
    return { ok: false, status: 401, error: '需要管理员凭据' };
  }

  const sharedSecret = getUsableAdminToken(env.SUBMISSIONS_ADMIN_TOKEN);
  if (sharedSecret && await constantTimeEquals(token, sharedSecret)) {
    return {
      ok: true,
      identity: { kind: 'shared-secret', label: 'Shared admin token' },
      githubToken: env.PROOFREADING_GITHUB_TOKEN?.trim() || undefined,
    };
  }

  const repository = env.PROOFREADING_GITHUB_REPO?.trim();
  const githubAllowed =
    env.PROOFREADING_ALLOW_GITHUB_ADMIN?.trim().toLowerCase() === 'true';
  if (githubAllowed && repository && /^[^/\s]+\/[^/\s]+$/u.test(repository)) {
    return githubAuthentication(token, repository, fetcher);
  }

  return {
    ok: false,
    status: sharedSecret || githubAllowed ? 401 : 503,
    error: sharedSecret || githubAllowed ? '管理员凭据无效' : '管理员认证尚未配置',
  };
};
