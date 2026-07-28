'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';

type Provenance = 'local_human' | 'official_tw_human' | 'exedra_wiki_human';
type Status = {
  reviewer?: string;
  total: number;
  wiki_candidates: number;
  wiki_reviewed: number;
  wiki_missing: number;
  remaining: number;
  legacy_machine_cache: number;
  counts: Record<Provenance, number>;
  error?: string;
};
type BatchResult = {
  next_cursor: number | null;
  complete: boolean;
  processed: Array<{
    story_id: string;
    success: boolean;
    outcome?: 'cached' | 'wiki_found' | 'wiki_not_found' | 'error';
    provenance?: Provenance;
    error?: string;
  }>;
  summary: Status;
  error?: string;
};

const TOKEN_KEY = 'magi-reader-proofreading-admin-token';

const json = async <T,>(response: Response): Promise<T> => {
  const text = await response.text();
  try {
    return JSON.parse(text) as T;
  } catch {
    return {} as T;
  }
};

export default function ExedraLocalizationPage() {
  const [token, setToken] = useState('');
  const [status, setStatus] = useState<Status | null>(null);
  const [cursor, setCursor] = useState(0);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('');
  const [log, setLog] = useState<string[]>([]);
  const stopRef = useRef(false);

  useEffect(() => {
    setToken(sessionStorage.getItem(TOKEN_KEY) || '');
  }, []);

  const headers = useCallback(
    () => ({ Authorization: `Bearer ${token}` }),
    [token],
  );

  const refresh = useCallback(async () => {
    if (!token) return;
    setMessage('');
    const response = await fetch('/api/admin/exedra-localize', {
      headers: headers(),
      cache: 'no-store',
    });
    const payload = await json<Status>(response);
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    sessionStorage.setItem(TOKEN_KEY, token);
    setStatus(payload);
    setCursor(current => Math.min(current, payload.wiki_candidates));
  }, [headers, token]);

  useEffect(() => {
    if (token) {
      void refresh().catch(error =>
        setMessage(error instanceof Error ? error.message : '读取失败'),
      );
    }
  }, [refresh, token]);

  const run = async () => {
    if (!token || running) return;
    stopRef.current = false;
    setRunning(true);
    setMessage('');
    let next: number | null = cursor;
    try {
      while (next !== null && !stopRef.current) {
        const response = await fetch('/api/admin/exedra-localize', {
          method: 'POST',
          headers: { ...headers(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ cursor: next, limit: 1 }),
        });
        const payload = await json<BatchResult>(response);
        if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
        setStatus(payload.summary);
        setLog(previous => [
          ...payload.processed.map(item => {
            if (!item.success) return `${item.story_id}: 错误 - ${item.error}`;
            if (item.outcome === 'wiki_found') return `${item.story_id}: 找到 Wiki 人工中文`;
            if (item.outcome === 'cached') return `${item.story_id}: 已有可信缓存`;
            return `${item.story_id}: Wiki 无可用中文页`;
          }),
          ...previous,
        ].slice(0, 300));
        next = payload.next_cursor;
        setCursor(next ?? payload.summary.wiki_candidates);
        if (payload.processed.some(item => !item.success)) {
          setMessage('遇到读取错误，已停止。修复后可从当前游标继续。');
          break;
        }
        await new Promise(resolve => window.setTimeout(resolve, 500));
      }
      if (next === null) setMessage('Exedra 角色 Wiki 人工中文审查已完成。');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '批处理失败');
    } finally {
      setRunning(false);
    }
  };

  const cleanup = async (scope: 'legacy-machine' | 'wiki-misses') => {
    if (!token || running) return;
    setRunning(true);
    setMessage('');
    try {
      const response = await fetch(
        `/api/admin/exedra-localize?scope=${encodeURIComponent(scope)}`,
        { method: 'DELETE', headers: headers() },
      );
      const payload = await json<{ deleted?: number; summary?: Status; error?: string }>(response);
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      if (payload.summary) setStatus(payload.summary);
      setMessage(
        scope === 'legacy-machine'
          ? `已清除 ${payload.deleted ?? 0} 条旧 Exedra 机翻缓存/校验状态。`
          : `已清除 ${payload.deleted ?? 0} 条 Wiki 未命中记录，可重新检查。`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '清理失败');
    } finally {
      setRunning(false);
    }
  };

  const exportCache = async () => {
    if (!token || running) return;
    setRunning(true);
    setMessage('');
    try {
      const response = await fetch('/api/admin/exedra-localize/export', {
        headers: headers(),
        cache: 'no-store',
      });
      if (!response.ok) {
        const payload = await json<{ error?: string }>(response);
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'exedra-localization-cache-v1.json';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setMessage('可信 Exedra 中文缓存已导出。');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '导出失败');
    } finally {
      setRunning(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-100 p-4 text-gray-900 md:p-8">
      <div className="mx-auto max-w-6xl space-y-5">
        <header className="rounded-2xl border bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex gap-3 text-sm font-bold">
                <Link href="/" className="text-emerald-700">← 返回目录</Link>
                <Link href="/review/submissions" className="text-purple-700">投稿审核台</Link>
              </div>
              <h1 className="mt-3 text-2xl font-black">Exedra 可信中文来源</h1>
              <p className="mt-1 text-sm text-gray-500">
                仅接受仓库人工中文、官方台服中文和经过结构校验的 Exedra Wiki 中文。Exedra 自动机翻已取消。
              </p>
            </div>
            <div className="flex min-w-72 gap-2">
              <input
                type="password"
                value={token}
                onChange={event => setToken(event.target.value.trim())}
                placeholder="管理员令牌或 GitHub PAT"
                className="min-w-0 flex-1 rounded-lg border px-3 py-2 font-mono text-sm"
              />
              <button
                type="button"
                onClick={() => void refresh().catch(error => setMessage(String(error)))}
                className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-bold text-white"
              >
                刷新
              </button>
            </div>
          </div>
        </header>

        {status && (
          <section className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {[
              ['总组数', status.total],
              ['仓库中文', status.counts.local_human],
              ['官方台服', status.counts.official_tw_human],
              ['Wiki 人工', status.counts.exedra_wiki_human],
              ['Wiki 无页面', status.wiki_missing],
              ['角色待检查', status.remaining],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-xl border bg-white p-4 shadow-sm">
                <p className="text-xs font-bold text-gray-500">{label}</p>
                <p className="mt-1 text-2xl font-black">{value}</p>
              </div>
            ))}
          </section>
        )}

        <section className="rounded-2xl border bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-sm font-bold">
              角色 Wiki 游标
              <input
                type="number"
                min={0}
                max={status?.wiki_candidates ?? 0}
                value={cursor}
                disabled={running}
                onChange={event => setCursor(Math.max(0, Number(event.target.value) || 0))}
                className="ml-2 w-28 rounded border px-2 py-1 font-mono"
              />
            </label>
            <button
              type="button"
              disabled={!token || running || status?.remaining === 0}
              onClick={() => void run()}
              className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-black text-white disabled:opacity-40"
            >
              {running ? '正在检查…' : '继续检查 Wiki 人工中文'}
            </button>
            <button
              type="button"
              disabled={!running}
              onClick={() => { stopRef.current = true; }}
              className="rounded-lg border border-red-300 px-4 py-2 text-sm font-bold text-red-700 disabled:opacity-40"
            >
              安全停止
            </button>
            <button
              type="button"
              disabled={!token || running}
              onClick={() => void exportCache()}
              className="rounded-lg border border-emerald-300 px-4 py-2 text-sm font-bold text-emerald-700 disabled:opacity-40"
            >
              导出可信中文缓存
            </button>
            <button
              type="button"
              disabled={!token || running || (status?.legacy_machine_cache ?? 0) === 0}
              onClick={() => void cleanup('legacy-machine')}
              className="rounded-lg border border-amber-300 px-4 py-2 text-sm font-bold text-amber-800 disabled:opacity-40"
            >
              清除旧机翻缓存（{status?.legacy_machine_cache ?? 0}）
            </button>
            <button
              type="button"
              disabled={!token || running || (status?.wiki_missing ?? 0) === 0}
              onClick={() => void cleanup('wiki-misses')}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-bold text-gray-700 disabled:opacity-40"
            >
              重新检查未命中页面
            </button>
          </div>
          <p className="mt-3 text-xs text-gray-500">
            本页只检查角色 Wiki 人工中文。主线、活动、肖像、语音、Namae、过场动画字幕和战斗内容等待官方台服文本或人工翻译，不会自动生成机翻。
          </p>
          {message && (
            <p role="status" className="mt-4 rounded-lg bg-blue-50 p-3 text-sm text-blue-900">
              {message}
            </p>
          )}
          <div className="mt-4 max-h-96 overflow-auto rounded-lg bg-gray-950 p-3 font-mono text-xs text-gray-100">
            {log.length
              ? log.map((line, index) => <div key={`${line}-${index}`}>{line}</div>)
              : <div className="text-gray-500">尚无本次检查日志。</div>}
          </div>
        </section>
      </div>
    </main>
  );
}
