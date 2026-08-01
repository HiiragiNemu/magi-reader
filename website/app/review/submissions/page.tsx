'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Check,
  Clock3,
  Download,
  ExternalLink,
  FileWarning,
  LogOut,
  RefreshCw,
  X,
} from 'lucide-react';

import { triggerUtf8Download } from '@/lib/browser-download';
import {
  PROOFREADING_STATUSES,
  PROOFREADING_STATUS_LABELS,
  normalizeProofreadingText,
  sha256Text,
  type ProofreadingListItem,
  type ProofreadingAdminDetail,
  type ProofreadingStatus,
} from '@/lib/proofreading';
import {
  parseStoryContent,
  serializeStoryLine,
  type StoryLine,
} from '@/lib/story-parser';

const ADMIN_TOKEN_KEY = 'magi-reader-proofreading-admin-token';
const LIST_STATUSES = PROOFREADING_STATUSES;

type ListResponse = {
  submissions?: ProofreadingListItem[];
  cursor?: string | null;
  list_complete?: boolean;
  reviewer?: string;
  error?: string;
};

type DetailResponse = {
  submission?: ProofreadingAdminDetail;
  reviewer?: string;
  error?: string;
};

type CompareRow = {
  current?: StoryLine;
  submitted?: StoryLine;
  jp?: StoryLine;
  changed: boolean;
};

const sourceLabel = (line?: StoryLine): string =>
  line ? serializeStoryLine(line) : '';

const parseLines = (raw: string, filename: string): StoryLine[] => {
  if (!raw) return [];
  return parseStoryContent(raw, {
    filename,
    mergeConsecutiveTextLines: true,
  }).lines;
};

const makeRows = (
  currentRaw: string,
  submittedRaw: string,
  jpRaw: string,
): CompareRow[] => {
  const current = parseLines(currentRaw, 'current_cn.txt');
  const submitted = parseLines(submittedRaw, 'submitted_cn.txt');
  const jp = parseLines(jpRaw, 'source_jp.txt');
  const length = Math.max(current.length, submitted.length, jp.length);
  return Array.from({ length }, (_, index) => {
    const currentLine = current[index];
    const submittedLine = submitted[index];
    return {
      current: currentLine,
      submitted: submittedLine,
      jp: jp[index],
      changed: sourceLabel(currentLine) !== sourceLabel(submittedLine),
    };
  });
};

const responseJson = async <T,>(response: Response): Promise<T> => {
  const text = await response.text();
  try {
    return JSON.parse(text) as T;
  } catch {
    return {} as T;
  }
};

const lineCard = (line: StoryLine | undefined, emptyText: string) => {
  if (!line) return <span className="text-gray-300">{emptyText}</span>;
  if (line.isHeader) {
    return <strong className="text-xs text-gray-500">{line.text}</strong>;
  }
  return (
    <>
      <span className="mr-2 font-bold text-emerald-700">{line.speaker || '旁白'}</span>
      <span className="whitespace-pre-wrap break-words">{line.text}</span>
    </>
  );
};

export default function ProofreadingReviewPage() {
  const [token, setToken] = useState('');
  const [tokenInput, setTokenInput] = useState('');
  const [authConfig, setAuthConfig] = useState<{
    shared_admin_auth?: boolean;
    server_pr_creation?: boolean;
    github_admin_auth?: boolean;
  } | null>(null);
  const [status, setStatus] = useState<ProofreadingStatus>('pending');
  const [items, setItems] = useState<ProofreadingListItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [listComplete, setListComplete] = useState(true);
  const [reviewer, setReviewer] = useState('');
  const [selected, setSelected] = useState<ProofreadingAdminDetail | null>(null);
  const [currentCn, setCurrentCn] = useState('');
  const [currentJp, setCurrentJp] = useState('');
  const [currentHash, setCurrentHash] = useState('');
  const [publicMessage, setPublicMessage] = useState('');
  const [internalNote, setInternalNote] = useState('');
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const stored = sessionStorage.getItem(ADMIN_TOKEN_KEY) || '';
    setToken(stored);
    setTokenInput(stored);
    void fetch('/api/proofreading/config', {
      cache: 'no-store',
    })
      .then(response => response.json())
      .then(payload => setAuthConfig(payload))
      .catch(() => setAuthConfig(null));
  }, []);

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}` }),
    [token],
  );

  const loadList = useCallback(async (
    requestedStatus: ProofreadingStatus,
    nextCursor?: string,
    append = false,
  ) => {
    if (!token) return;
    setLoadingList(true);
    setError('');
    try {
      const params = new URLSearchParams({
        status: requestedStatus,
        limit: '30',
      });
      if (nextCursor) params.set('cursor', nextCursor);
      const response = await fetch(`/api/admin/submissions?${params}`, {
        headers,
        cache: 'no-store',
      });
      const payload = await responseJson<ListResponse>(response);
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      setItems((current) => append
        ? [...current, ...(payload.submissions || [])]
        : payload.submissions || []);
      setCursor(payload.cursor || null);
      setListComplete(Boolean(payload.list_complete));
      setReviewer(payload.reviewer || '');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '读取投稿列表失败');
    } finally {
      setLoadingList(false);
    }
  }, [headers, token]);

  useEffect(() => {
    if (token) void loadList(status);
  }, [loadList, status, token]);

  const openSubmission = async (id: string) => {
    setLoadingDetail(true);
    setError('');
    try {
      const response = await fetch(`/api/admin/submissions/${encodeURIComponent(id)}`, {
        headers,
        cache: 'no-store',
      });
      const payload = await responseJson<DetailResponse>(response);
      if (!response.ok || !payload.submission) {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      const submission = payload.submission;
      const [cnResponse, jpResponse] = await Promise.all([
        submission.source_path_cn
          ? fetch(submission.source_path_cn, { cache: 'no-store' })
          : Promise.resolve(null),
        submission.source_path_jp
          ? fetch(submission.source_path_jp, { cache: 'no-store' })
          : Promise.resolve(null),
      ]);
      const cnText = cnResponse?.ok ? await cnResponse.text() : '';
      const jpText = jpResponse?.ok ? await jpResponse.text() : '';
      setSelected(submission);
      setCurrentCn(normalizeProofreadingText(cnText));
      setCurrentJp(normalizeProofreadingText(jpText));
      setCurrentHash(await sha256Text(cnText));
      setPublicMessage(submission.review?.public_message || '');
      setInternalNote(submission.review?.internal_note || '');
      setReviewer(payload.reviewer || reviewer);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '读取投稿详情失败');
    } finally {
      setLoadingDetail(false);
    }
  };

  const submitReview = async (nextStatus: ProofreadingStatus) => {
    if (!selected) return;
    setActionLoading(true);
    setError('');
    try {
      const response = await fetch(
        `/api/admin/submissions/${encodeURIComponent(selected.id)}`,
        {
          method: 'PATCH',
          headers: {
            ...headers,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            status: nextStatus,
            public_message: publicMessage,
            internal_note: internalNote,
          }),
        },
      );
      const payload = await responseJson<{
        submission?: ProofreadingAdminDetail;
        error?: string;
      }>(response);
      if (payload.submission) {
        setSelected(payload.submission);
        setPublicMessage(payload.submission.review?.public_message || '');
        setInternalNote(payload.submission.review?.internal_note || '');
      }
      if (!response.ok || !payload.submission) {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      await loadList(status);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '更新审核状态失败');
    } finally {
      setActionLoading(false);
    }
  };

  const login = () => {
    const normalized = tokenInput.trim();
    if (!normalized) return;
    sessionStorage.setItem(ADMIN_TOKEN_KEY, normalized);
    setToken(normalized);
    setSelected(null);
  };

  const logout = () => {
    sessionStorage.removeItem(ADMIN_TOKEN_KEY);
    setToken('');
    setTokenInput('');
    setItems([]);
    setSelected(null);
    setReviewer('');
  };

  const rows = useMemo(
    () => selected
      ? makeRows(currentCn, selected.content, currentJp)
      : [],
    [currentCn, currentJp, selected],
  );
  const changedCount = rows.filter((row) => row.changed).length;
  const stale = Boolean(selected && currentHash && currentHash !== selected.base_sha256);
  const noChanges = Boolean(
    selected && selected.content_sha256 === selected.base_content_sha256,
  );

  const downloadReviewText = (
    content: string,
    suffix: 'current_cn' | 'submitted_cn' | 'source_jp',
  ) => {
    if (!selected || !content) return;
    triggerUtf8Download(
      content,
      `${selected.story_id}_${suffix}.txt`,
    );
  };

  if (!token) {
    return (
      <main className="mx-auto flex min-h-screen max-w-xl items-center px-4 py-12">
        <section className="w-full rounded-2xl border bg-white p-6 shadow-lg">
          <h1 className="text-xl font-bold">中文校对审阅后台</h1>
          <p className="mt-2 text-sm leading-6 text-gray-500">
            向项目负责人领取团队审核口令，输入一次即可查看投稿、审核并自动建立 PR，
            普通审核员无需创建 GitHub 令牌。口令只保存在当前浏览器标签页中。
          </p>
          {authConfig && (!authConfig.shared_admin_auth || !authConfig.server_pr_creation) && (
            <p
              role="status"
              className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm leading-6 text-amber-900"
            >
              团队审核口令尚未完整启用。项目负责人需要配置固定审核口令和服务器
              GitHub 写入令牌后重新部署。
            </p>
          )}
          <input
            type="password"
            autoComplete="off"
            value={tokenInput}
            onChange={(event) => setTokenInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') login();
            }}
            placeholder="团队审核口令"
            className="mt-5 w-full rounded-lg border px-3 py-2 outline-none focus:border-emerald-500"
          />
          <button
            type="button"
            onClick={login}
            className="mt-3 w-full rounded-lg bg-emerald-600 px-4 py-2 font-bold text-white"
          >
            进入审阅后台
          </button>
          {authConfig?.github_admin_auth && (
            <details className="mt-4 rounded-lg bg-gray-50 p-3 text-xs leading-5 text-gray-600">
              <summary className="cursor-pointer font-bold text-gray-700">
                仓库维护者高级登录
              </summary>
              <p className="mt-2">
                仅在团队口令暂不可用时，仓库维护者才需要在上方输入自己的 GitHub
                PAT。个人令牌不要共享给其他审核员，也不要写入网页或仓库。
              </p>
            </details>
          )}
          <Link href="/" className="mt-4 block text-center text-sm text-gray-500 underline">
            返回剧情目录
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50 text-gray-900">
      <header className="sticky top-0 z-20 border-b bg-white/95 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="font-bold">中文校对审阅后台</h1>
            <p className="text-xs text-gray-500">当前审核者：{reviewer || '正在验证'}</p>
          </div>
          <div className="flex gap-2">
            <Link href="/" className="rounded-lg border px-3 py-2 text-xs hover:bg-gray-50">
              剧情目录
            </Link>
            <button type="button" onClick={logout} className="flex items-center gap-1 rounded-lg border px-3 py-2 text-xs text-red-600">
              <LogOut size={14} />退出
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1600px] gap-4 p-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="rounded-xl border bg-white p-3 shadow-sm">
          <div className="flex gap-2 overflow-x-auto pb-3">
            {LIST_STATUSES.map((value) => (
              <button
                type="button"
                key={value}
                onClick={() => {
                  setStatus(value);
                  setSelected(null);
                }}
                className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-bold ${
                  status === value
                    ? 'bg-emerald-600 text-white'
                    : 'bg-gray-100 text-gray-600'
                }`}
              >
                {PROOFREADING_STATUS_LABELS[value]}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => void loadList(status)}
            disabled={loadingList}
            className="mb-3 flex w-full items-center justify-center gap-1 rounded-lg border px-3 py-2 text-xs disabled:opacity-50"
          >
            <RefreshCw size={14} />刷新
          </button>

          <div className="max-h-[calc(100vh-190px)] space-y-2 overflow-y-auto pr-1">
            {items.map((item) => (
              <button
                type="button"
                key={item.id}
                onClick={() => void openSubmission(item.id)}
                className={`w-full rounded-lg border p-3 text-left transition ${
                  selected?.id === item.id
                    ? 'border-emerald-500 bg-emerald-50'
                    : 'hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs font-bold text-emerald-700">
                    {item.story_id}
                  </span>
                  <span className="text-[10px] text-gray-400">
                    {item.content_length.toLocaleString('zh-CN')} 字符
                  </span>
                </div>
                <p className="mt-1 truncate text-sm font-bold">{item.nickname}</p>
                <p className="mt-1 line-clamp-2 text-xs text-gray-500">
                  {item.note || '未填写修改说明'}
                </p>
                <p className="mt-2 text-[10px] text-gray-400">
                  {new Date(item.submitted_at).toLocaleString('zh-CN')}
                </p>
              </button>
            ))}
            {!loadingList && items.length === 0 && (
              <p className="py-8 text-center text-sm text-gray-400">此状态下没有投稿。</p>
            )}
          </div>
          {!listComplete && cursor && (
            <button
              type="button"
              onClick={() => void loadList(status, cursor, true)}
              className="mt-3 w-full rounded-lg bg-gray-100 px-3 py-2 text-xs font-bold"
            >
              加载更多
            </button>
          )}
        </aside>

        <section className="min-w-0 rounded-xl border bg-white p-4 shadow-sm">
          {error && (
            <div role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}
          {loadingDetail ? (
            <p className="py-20 text-center text-gray-400">正在读取投稿详情…</p>
          ) : !selected ? (
            <p className="py-20 text-center text-gray-400">从左侧选择一条投稿。</p>
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-3 border-b pb-4">
                <div>
                  <div className="font-mono text-lg font-bold text-emerald-700">
                    {selected.story_id}
                  </div>
                  <div className="mt-1 text-sm text-gray-500">
                    {selected.nickname} · {new Date(selected.submitted_at).toLocaleString('zh-CN')}
                  </div>
                  <div className="mt-1 break-all font-mono text-[10px] text-gray-400">
                    {selected.id}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-bold">
                    {PROOFREADING_STATUS_LABELS[selected.status]}
                  </span>
                  <button
                    type="button"
                    onClick={() => downloadReviewText(selected.content, 'submitted_cn')}
                    className="flex items-center gap-1 rounded-lg border px-3 py-1 text-xs"
                  >
                    <Download size={13} />下载投稿 TXT
                  </button>
                  <Link
                    href={`/reader/${encodeURIComponent(selected.story_id)}?cn=${encodeURIComponent(selected.source_path_cn)}&jp=${encodeURIComponent(selected.source_path_jp)}`}
                    target="_blank"
                    className="flex items-center gap-1 rounded-lg border px-3 py-1 text-xs"
                  >
                    打开剧情<ExternalLink size={13} />
                  </Link>
                </div>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <div className="rounded-lg bg-gray-50 p-3 text-xs">
                  <div className="font-bold text-gray-500">源版本</div>
                  <div className="mt-1 break-all font-mono">{selected.source_revision}</div>
                </div>
                <div className={`rounded-lg p-3 text-xs ${stale ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-700'}`}>
                  <div className="font-bold">源文本校验</div>
                  <div className="mt-1">{stale ? '当前文本已变化，禁止直接批准' : '基准哈希一致'}</div>
                </div>
                <div className="rounded-lg bg-blue-50 p-3 text-xs text-blue-800">
                  <div className="font-bold">差异统计</div>
                  <div className="mt-1">{changedCount} / {rows.length} 行发生变化</div>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                <span className="self-center text-gray-500">
                  下载文件统一为 UTF-8 BOM 与 CRLF，兼容手机编辑器并可重新上传：
                </span>
                <button
                  type="button"
                  disabled={!currentCn}
                  onClick={() => downloadReviewText(currentCn, 'current_cn')}
                  className="rounded-lg border px-3 py-1.5 disabled:opacity-40"
                >
                  当前中文
                </button>
                <button
                  type="button"
                  onClick={() => downloadReviewText(selected.content, 'submitted_cn')}
                  className="rounded-lg border px-3 py-1.5"
                >
                  投稿修订
                </button>
                <button
                  type="button"
                  disabled={!currentJp}
                  onClick={() => downloadReviewText(currentJp, 'source_jp')}
                  className="rounded-lg border px-3 py-1.5 disabled:opacity-40"
                >
                  日文原文
                </button>
              </div>

              {selected.note && (
                <div className="mt-4 rounded-lg border-l-4 border-blue-400 bg-blue-50 p-3 text-sm">
                  <strong>投稿说明：</strong>{selected.note}
                </div>
              )}
              {selected.processing_error && (
                <div className="mt-4 rounded-lg border-l-4 border-red-400 bg-red-50 p-3 text-sm text-red-800">
                  <strong>处理错误：</strong>{selected.processing_error}
                </div>
              )}
              {selected.pull_request?.url && (
                <a
                  href={selected.pull_request.url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-4 inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-2 text-sm font-bold text-white"
                >
                  查看 GitHub PR #{selected.pull_request.number}<ExternalLink size={14} />
                </a>
              )}
              {stale && (
                <div className="mt-4 flex gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
                  <FileWarning className="shrink-0" size={18} />
                  投稿基于旧中文文本。请暂缓并要求投稿者基于最新版重新提交，自动 PR 流程也会拒绝过期基准。
                </div>
              )}
              {noChanges && (
                <div className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                  投稿内容与当前文本相同，不需要建立 PR。
                </div>
              )}

              <div className="mt-5 overflow-x-auto rounded-xl border">
                <div className="grid min-w-[1050px] grid-cols-3 bg-gray-100 text-xs font-bold text-gray-600">
                  <div className="border-r p-3">当前中文</div>
                  <div className="border-r p-3">投稿修订</div>
                  <div className="p-3">日文原文</div>
                </div>
                <div className="max-h-[62vh] min-w-[1050px] overflow-y-auto">
                  {rows.map((row, index) => (
                    <div
                      key={index}
                      className={`grid grid-cols-3 border-t text-sm ${row.changed ? 'bg-amber-50/70' : ''}`}
                    >
                      <div className="border-r p-3">{lineCard(row.current, '无当前中文')}</div>
                      <div className={`border-r p-3 ${row.changed ? 'font-medium text-purple-900' : ''}`}>
                        {lineCard(row.submitted, '投稿中缺失')}
                      </div>
                      <div className="p-3 text-gray-600">{lineCard(row.jp, '无日文')}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <label className="text-sm font-bold">
                  给投稿者的公开回复
                  <textarea
                    value={publicMessage}
                    onChange={(event) => setPublicMessage(event.target.value)}
                    maxLength={1_000}
                    rows={4}
                    className="mt-2 w-full rounded-lg border p-3 font-normal outline-none focus:border-emerald-500"
                    placeholder="驳回或暂缓时说明需要修改的内容；该消息可由投稿者查询。"
                  />
                </label>
                <label className="text-sm font-bold">
                  内部审核备注
                  <textarea
                    value={internalNote}
                    onChange={(event) => setInternalNote(event.target.value)}
                    maxLength={4_000}
                    rows={4}
                    className="mt-2 w-full rounded-lg border p-3 font-normal outline-none focus:border-emerald-500"
                    placeholder="只在管理员后台显示。"
                  />
                </label>
              </div>

              <div className="mt-5 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void submitReview('approved')}
                  disabled={actionLoading || stale || noChanges || !['pending', 'held', 'approved'].includes(selected.status)}
                  className="flex items-center gap-1 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Check size={16} />批准并进入自动 PR 队列
                </button>
                <button
                  type="button"
                  onClick={() => void submitReview('held')}
                  disabled={actionLoading || !['pending', 'held', 'approved', 'stale'].includes(selected.status)}
                  className="flex items-center gap-1 rounded-lg bg-amber-500 px-4 py-2 text-sm font-bold text-white disabled:opacity-40"
                >
                  <Clock3 size={16} />暂缓
                </button>
                <button
                  type="button"
                  onClick={() => void submitReview('rejected')}
                  disabled={actionLoading || !['pending', 'held', 'stale'].includes(selected.status)}
                  className="flex items-center gap-1 rounded-lg bg-red-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-40"
                >
                  <X size={16} />驳回
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
