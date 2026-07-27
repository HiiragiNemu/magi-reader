import {
  normalizeProofreadingText,
  sha256Text,
  type ProofreadingPullRequest,
  type ProofreadingSubmission,
} from '@/lib/proofreading';

const GITHUB_API = 'https://api.github.com';
const HEADER_RE = /^---\s*\[Section\s+\d+(?:\s+-\s+Branch\s+\d+)?\]\s*\(Source:\s*[^()\r\n]+\.json\s*\)\s*---$/iu;

export class ProofreadingPullRequestError extends Error {
  readonly code: 'stale' | 'invalid' | 'github';

  constructor(
    message: string,
    code: 'stale' | 'invalid' | 'github' = 'github',
  ) {
    super(message);
    this.name = 'ProofreadingPullRequestError';
    this.code = code;
  }
}

type GitHubRequestOptions = {
  method?: string;
  body?: unknown;
};

const githubRequest = async <T,>(
  token: string,
  path: string,
  options: GitHubRequestOptions = {},
  fetcher: typeof fetch = fetch,
): Promise<T> => {
  const response = await fetcher(`${GITHUB_API}${path}`, {
    method: options.method ?? 'GET',
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'magi-reader-proofreading-pr',
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: 'no-store',
  });
  const text = await response.text();
  let payload: unknown = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    // The error below deliberately avoids echoing arbitrary upstream HTML.
  }
  if (!response.ok) {
    const message =
      payload && typeof payload === 'object' && 'message' in payload &&
      typeof (payload as { message?: unknown }).message === 'string'
        ? (payload as { message: string }).message
        : `HTTP ${response.status}`;
    throw new ProofreadingPullRequestError(
      `GitHub API 请求失败：${message}`,
      response.status === 409 || response.status === 422 ? 'invalid' : 'github',
    );
  }
  return payload as T;
};

const encodeBase64 = (value: string): string => {
  const bytes = new TextEncoder().encode(value);
  let binary = '';
  const chunk = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunk) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunk));
  }
  return btoa(binary);
};

const decodeBase64 = (value: string): string => {
  const binary = atob(value.replace(/\s+/gu, ''));
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
};

const safePath = (value: string): string => {
  if (
    !value ||
    value.length > 2_048 ||
    value.startsWith('/') ||
    value.includes('\\') ||
    /[\u0000-\u001f\u007f]/u.test(value)
  ) {
    throw new ProofreadingPullRequestError('计算出的仓库源路径无效', 'invalid');
  }
  const parts = value.split('/');
  if (parts.some((part) => !part || part === '.' || part === '..')) {
    throw new ProofreadingPullRequestError('计算出的仓库源路径无效', 'invalid');
  }
  return parts.join('/');
};

export const proofreadingRepositoryPath = (
  record: ProofreadingSubmission,
): string => {
  const exedra = record.source_identity.match(
    /^exedra:([A-Za-z0-9_.-]{1,128}):([A-Za-z0-9_.-]{1,96})$/u,
  );
  if (exedra) {
    const [, rawCategory, group] = exedra;
    return safePath(
      `magiraexedra-translate-data-master/Scenarios_full/${rawCategory}/${group}/${group}_cn.txt`,
    );
  }
  if (record.source_identity.includes(':')) {
    throw new ProofreadingPullRequestError('剧情来源身份格式无效', 'invalid');
  }
  return safePath(
    `magireco-translate-data-master/Scenarios_full/${record.source_identity}.txt`,
  );
};

const sectionHeaders = (value: string): string[] => {
  const headers: string[] = [];
  for (const rawLine of normalizeProofreadingText(value).split('\n')) {
    const line = rawLine.trim();
    if (!line.startsWith('---')) continue;
    if (!HEADER_RE.test(line)) {
      throw new ProofreadingPullRequestError(
        `发现无法识别的 Section 标题：${line.slice(0, 120)}`,
        'invalid',
      );
    }
    headers.push(line);
  }
  if (headers.length === 0) {
    throw new ProofreadingPullRequestError('投稿文本缺少 Section 结构', 'invalid');
  }
  return headers;
};

const slug = (value: string): string =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9_.-]+/gu, '-')
    .replace(/^-+|-+$/gu, '')
    .slice(0, 72) || 'story';

type GitReference = { object?: { sha?: string } };
type GitHubContent = {
  type?: string;
  sha?: string;
  encoding?: string;
  content?: string;
};
type GitHubPull = {
  number?: number;
  html_url?: string;
  created_at?: string;
};

export const createProofreadingPullRequest = async (
  options: {
    token: string;
    repository: string;
    record: ProofreadingSubmission;
  },
  fetcher: typeof fetch = fetch,
): Promise<ProofreadingPullRequest> => {
  const { token, repository, record } = options;
  if (!/^[^/\s]+\/[^/\s]+$/u.test(repository)) {
    throw new ProofreadingPullRequestError('GitHub 仓库配置无效', 'invalid');
  }
  if (!token || token.length > 1_024) {
    throw new ProofreadingPullRequestError('缺少可创建 PR 的 GitHub 凭据');
  }

  const targetBranch = record.target_branch || 'EXEDRA-TEST';
  if (targetBranch !== 'EXEDRA-TEST') {
    throw new ProofreadingPullRequestError('投稿目标分支不是 EXEDRA-TEST', 'invalid');
  }
  const path = proofreadingRepositoryPath(record);
  const encodedPath = path.split('/').map(encodeURIComponent).join('/');
  const encodedBranch = encodeURIComponent(targetBranch);
  const reference = await githubRequest<GitReference>(
    token,
    `/repos/${repository}/git/ref/heads/${encodedBranch}`,
    {},
    fetcher,
  );
  const baseSha = reference.object?.sha;
  if (!baseSha || !/^[a-f0-9]{40}$/iu.test(baseSha)) {
    throw new ProofreadingPullRequestError('无法解析目标分支提交');
  }

  const currentFile = await githubRequest<GitHubContent>(
    token,
    `/repos/${repository}/contents/${encodedPath}?ref=${encodeURIComponent(baseSha)}`,
    {},
    fetcher,
  );
  if (
    currentFile.type !== 'file' ||
    !currentFile.sha ||
    currentFile.encoding !== 'base64' ||
    typeof currentFile.content !== 'string'
  ) {
    throw new ProofreadingPullRequestError('中文源文件无法通过 GitHub Contents API 读取');
  }

  let currentText: string;
  try {
    currentText = decodeBase64(currentFile.content);
  } catch {
    throw new ProofreadingPullRequestError('GitHub 中的中文源文件不是有效 UTF-8', 'invalid');
  }
  const currentHash = await sha256Text(currentText);
  if (currentHash !== record.base_sha256) {
    throw new ProofreadingPullRequestError(
      '中文源文件已更新，投稿基准已过期',
      'stale',
    );
  }
  if (await sha256Text(record.content) !== record.content_sha256) {
    throw new ProofreadingPullRequestError('投稿正文哈希不一致', 'invalid');
  }
  if (record.content_sha256 === record.base_content_sha256) {
    throw new ProofreadingPullRequestError('投稿没有实际文本变化', 'invalid');
  }
  const currentHeaders = sectionHeaders(currentText);
  const submittedHeaders = sectionHeaders(record.content);
  if (
    currentHeaders.length !== submittedHeaders.length ||
    currentHeaders.some((header, index) => header !== submittedHeaders[index])
  ) {
    throw new ProofreadingPullRequestError(
      'Section/Branch 结构发生变化，拒绝自动创建 PR',
      'invalid',
    );
  }

  const branch = `community-proofreading/${slug(record.story_id)}-${slug(record.id).slice(-24)}`;
  const encodedNewBranch = branch.split('/').map(encodeURIComponent).join('/');
  let branchCreated = false;
  try {
    await githubRequest(
      token,
      `/repos/${repository}/git/refs`,
      {
        method: 'POST',
        body: { ref: `refs/heads/${branch}`, sha: baseSha },
      },
      fetcher,
    );
    branchCreated = true;

    const output = normalizeProofreadingText(record.content).replace(/\n*$/u, '\n');
    await githubRequest(
      token,
      `/repos/${repository}/contents/${encodedPath}`,
      {
        method: 'PUT',
        body: {
          message: `Apply community proofreading for ${record.story_id}`,
          content: encodeBase64(output),
          branch,
          sha: currentFile.sha,
          committer: {
            name: 'MagiReader Proofreading Bot',
            email: '41898282+github-actions[bot]@users.noreply.github.com',
          },
        },
      },
      fetcher,
    );

    const note = record.note ? `\n\n投稿说明：\n${record.note}` : '';
    const pull = await githubRequest<GitHubPull>(
      token,
      `/repos/${repository}/pulls`,
      {
        method: 'POST',
        body: {
          title: `校对 ${record.story_id} · ${record.nickname}`,
          head: branch,
          base: targetBranch,
          body:
            `社区校对投稿 \`${record.id}\`。\n\n` +
            `- 剧情：\`${record.story_id}\`\n` +
            `- 校对者：${record.nickname}\n` +
            `- 源文件：\`${path}\`\n` +
            `- 编辑基准：\`${record.base_sha256}\`\n` +
            `- 修订哈希：\`${record.content_sha256}\`${note}\n\n` +
            '该 PR 由审阅后台在人工批准后创建。合并前仍需通过完整数据管线与网站构建检查。',
          maintainer_can_modify: true,
        },
      },
      fetcher,
    );
    if (!pull.number || !pull.html_url) {
      throw new ProofreadingPullRequestError('GitHub 未返回有效的 PR 信息');
    }
    return {
      number: pull.number,
      url: pull.html_url,
      branch,
      created_at: pull.created_at || new Date().toISOString(),
    };
  } catch (error) {
    if (branchCreated) {
      try {
        await githubRequest(
          token,
          `/repos/${repository}/git/refs/heads/${encodedNewBranch}`,
          { method: 'DELETE' },
          fetcher,
        );
      } catch {
        // A branch containing a successfully created PR must not be deleted.
        // Other cleanup failures can be handled manually without hiding the root error.
      }
    }
    throw error;
  }
};

export const readProofreadingPullRequestState = async (
  options: {
    token: string;
    repository: string;
    pullRequest: ProofreadingPullRequest;
  },
  fetcher: typeof fetch = fetch,
): Promise<{
  status: 'pr_created' | 'merged' | 'closed';
  pullRequest: ProofreadingPullRequest;
}> => {
  const remote = await githubRequest<{
    state?: string;
    merged_at?: string | null;
    closed_at?: string | null;
  }>(
    options.token,
    `/repos/${options.repository}/pulls/${options.pullRequest.number}`,
    {},
    fetcher,
  );
  if (remote.merged_at) {
    return {
      status: 'merged',
      pullRequest: {
        ...options.pullRequest,
        merged_at: remote.merged_at,
      },
    };
  }
  if (remote.state === 'closed') {
    return {
      status: 'closed',
      pullRequest: {
        ...options.pullRequest,
        closed_at: remote.closed_at || new Date().toISOString(),
      },
    };
  }
  return { status: 'pr_created', pullRequest: options.pullRequest };
};
