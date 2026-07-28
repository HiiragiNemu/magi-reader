'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  MACHINE_TRANSLATION_MANIFEST,
  type MachineTranslationEntry,
  type MachineTranslationReviewState,
} from '@/lib/machine-translation-review';

type MachineStatus = {
  total: number;
  verified: number;
  remaining: number;
  states: Record<string, MachineTranslationReviewState>;
  entries?: MachineTranslationEntry[];
};

const requestAdmin = async <T,>(
  token: string,
  input: string,
  init?: RequestInit,
): Promise<T> => {
  const response = await fetch(input, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  });
  const payload = await response.json() as T & { error?: string };
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
};

export default function MachineTranslationReviewPage() {
  const [token, setToken] = useState('');
  const [status, setStatus] = useState<MachineStatus | null>(null);
  const [query, setQuery] = useState('');
  const [showVerified, setShowVerified] = useState(false);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const sourceEntries = status?.entries ?? MACHINE_TRANSLATION_MANIFEST.entries;

  useEffect(() => {
    setToken(sessionStorage.getItem('magi-reader-proofreading-admin-token') || '');
  }, []);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setMessage('');
    try {
      const result = await requestAdmin<MachineStatus>(
        token,
        '/api/admin/machine-review',
      );
      sessionStorage.setItem('magi-reader-proofreading-admin-token', token);
      setStatus(result);
    } catch (error) {
      setStatus(null);
      setMessage(
        error instanceof Error ? error.message : '读取人工校验状态失败',
      );
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (token) void refresh();
  }, [refresh, token]);

  const toggle = async (storyId: string, verified: boolean) => {
    if (!token) return;
    setLoading(true);
    setMessage('');
    try {
      await requestAdmin(token, '/api/admin/machine-review', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          story_id: storyId,
          verified,
          note: verified
            ? '管理员确认已完成魔法纪录人工校验'
            : '管理员恢复魔法纪录机器翻译待校标记',
        }),
      });
      setMessage(
        verified
          ? `${storyId} 已取消待校高亮。`
          : `${storyId} 已恢复待校高亮。`,
      );
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '更新标记失败');
    } finally {
      setLoading(false);
    }
  };

  const entries = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return sourceEntries.filter(entry => {
      const verified = status?.states?.[entry.story_id]?.verified === true;
      if (!showVerified && verified) return false;
      if (!normalized) return true;
      return [entry.story_id, entry.folder, entry.title, entry.source_identity]
        .join(' ')
        .toLowerCase()
        .includes(normalized);
    });
  }, [query, showVerified, sourceEntries, status]);

  return (
    <main className="min-h-screen bg-gray-100 p-4 text-gray-900 md:p-8">
      <div className="mx-auto max-w-6xl space-y-5">
        <header className="rounded-2xl border bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="flex gap-3 text-sm font-bold">
                <Link href="/" className="text-emerald-700">← 返回目录</Link>
                <Link href="/review/submissions" className="text-purple-700">投稿审核台</Link>
                <Link href="/review/exedra-localization" className="text-violet-700">Exedra 可信中文</Link>
              </div>
              <h1 className="mt-3 text-2xl font-black">魔法纪录机器翻译人工校验清单</h1>
              <p className="mt-1 text-sm text-gray-500">
                Exedra 自动机翻计划已经取消；本页只管理魔法纪录既有机翻基线。
              </p>
            </div>
            <div className="flex min-w-0 flex-1 gap-2 lg:max-w-xl">
              <input
                type="password"
                value={token}
                onChange={event => setToken(event.target.value.trim())}
                className="min-w-0 flex-1 rounded-lg border px-3 py-2 font-mono text-sm"
                placeholder="管理员令牌或具有仓库写权限的 GitHub PAT"
              />
              <button
                type="button"
                disabled={!token || loading}
                onClick={() => void refresh()}
                className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-bold text-white disabled:opacity-40"
              >
                登录/刷新
              </button>
            </div>
          </div>
        </header>

        {status && (
          <section className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">
              <p className="text-xs font-bold text-amber-700">机器翻译总数</p>
              <p className="text-3xl font-black">{status.total}</p>
            </div>
            <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-4">
              <p className="text-xs font-bold text-emerald-700">已人工校验</p>
              <p className="text-3xl font-black">{status.verified}</p>
            </div>
            <div className="rounded-xl border border-red-300 bg-red-50 p-4">
              <p className="text-xs font-bold text-red-700">剩余待校</p>
              <p className="text-3xl font-black">{status.remaining}</p>
            </div>
          </section>
        )}

        {message && (
          <div role="status" className="rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
            {message}
          </div>
        )}

        <section className="rounded-xl border bg-white p-4 shadow-sm">
          <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <input
              value={query}
              onChange={event => setQuery(event.target.value)}
              className="rounded-lg border px-3 py-2 text-sm md:w-96"
              placeholder="搜索编号、标题或目录"
            />
            <label className="flex items-center gap-2 text-sm font-bold">
              <input
                type="checkbox"
                checked={showVerified}
                onChange={event => setShowVerified(event.target.checked)}
              />
              显示已经人工校验的剧情
            </label>
          </div>
          <div className="max-h-[72vh] overflow-auto rounded-lg border">
            {entries.map(entry => {
              const state = status?.states?.[entry.story_id];
              const verified = state?.verified === true;
              return (
                <article
                  key={entry.story_id}
                  className={`grid gap-3 border-b p-3 md:grid-cols-[9rem_minmax(0,1fr)_10rem] md:items-center ${verified ? 'bg-emerald-50' : 'bg-amber-50'}`}
                >
                  <strong className="font-mono text-sm">{entry.story_id}</strong>
                  <div className="min-w-0">
                    <p className="truncate font-bold">{entry.title || entry.source_identity}</p>
                    <p className="truncate text-xs text-gray-500">{entry.folder}</p>
                    {state && (
                      <p className="mt-1 text-[10px] text-gray-400">
                        {state.reviewer} · {new Date(state.reviewed_at).toLocaleString('zh-CN')} · {state.note}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    disabled={!token || loading}
                    onClick={() => void toggle(entry.story_id, !verified)}
                    className={`rounded-lg px-3 py-2 text-xs font-black text-white disabled:opacity-40 ${verified ? 'bg-amber-600' : 'bg-emerald-600'}`}
                  >
                    {verified ? '恢复待校标记' : '标记为人工已校'}
                  </button>
                </article>
              );
            })}
            {!entries.length && (
              <p className="p-8 text-center text-gray-400">没有符合筛选条件的魔法纪录机翻剧情。</p>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
