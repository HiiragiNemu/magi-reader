'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';

type Provenance = 'local_human' | 'official_tw_human' | 'exedra_wiki_human' | 'machine_translation';
type Status = {
  reviewer?: string;
  total: number;
  candidates: number;
  cached: number;
  remaining: number;
  counts: Record<Provenance, number>;
  records?: Array<{
    story_id: string;
    source_identity: string;
    provenance: Provenance;
    source_url: string;
    generated_at: string;
  }>;
  error?: string;
};
type BatchResult = {
  next_cursor: number | null;
  complete: boolean;
  processed: Array<{
    story_id: string;
    success: boolean;
    provenance?: Provenance;
    error?: string;
  }>;
  summary: Status;
  error?: string;
};

const TOKEN_KEY = 'magi-reader-proofreading-admin-token';

const json = async <T,>(response: Response): Promise<T> => {
  const text = await response.text();
  try { return JSON.parse(text) as T; } catch { return {} as T; }
};

export default function ExedraLocalizationPage() {
  const [token, setToken] = useState('');
  const [status, setStatus] = useState<Status | null>(null);
  const [cursor, setCursor] = useState(0);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('');
  const [log, setLog] = useState<string[]>([]);
  const stopRef = useRef(false);

  useEffect(() => setToken(sessionStorage.getItem(TOKEN_KEY) || ''), []);

  const headers = useCallback(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const refresh = useCallback(async () => {
    if (!token) return;
    setMessage('');
    const response = await fetch('/api/admin/exedra-localize', {
      headers: headers(), cache: 'no-store',
    });
    const payload = await json<Status>(response);
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    sessionStorage.setItem(TOKEN_KEY, token);
    setStatus(payload);
    setCursor(Math.min(cursor, payload.candidates));
  }, [cursor, headers, token]);

  useEffect(() => {
    if (token) void refresh().catch(error => setMessage(error instanceof Error ? error.message : '读取失败'));
  }, [token]);

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
          ...payload.processed.map(item => item.success
            ? `${item.story_id}: ${item.provenance}`
            : `${item.story_id}: 失败 - ${item.error}`),
          ...previous,
        ].slice(0, 200));
        next = payload.next_cursor;
        setCursor(next ?? payload.summary.candidates);
        if (payload.processed.some(item => !item.success)) {
          setMessage('遇到失败项，已停止。检查日志后可从当前游标继续。');
          break;
        }
        await new Promise(resolve => window.setTimeout(resolve, 500));
      }
      if (next === null) setMessage('Exedra 全部缺失中文组已处理完成。');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '批处理失败');
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
                <Link href="/review/machine-translations?system=exedra" className="text-violet-700">Exedra 机翻清单</Link>
              </div>
              <h1 className="mt-3 text-2xl font-black">Exedra 中文来源与批量生成</h1>
              <p className="mt-1 text-sm text-gray-500">优先级：本地人工 → 官方繁中 → Exedra Wiki 中文 → Workers AI。只有最后一类标记机翻。</p>
            </div>
            <div className="flex min-w-72 gap-2">
              <input type="password" value={token} onChange={event => setToken(event.target.value.trim())} placeholder="管理员令牌或 GitHub PAT" className="min-w-0 flex-1 rounded-lg border px-3 py-2 font-mono text-sm" />
              <button type="button" onClick={() => void refresh().catch(error => setMessage(String(error)))} className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-bold text-white">刷新</button>
            </div>
          </div>
        </header>

        {status && (
          <section className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {[
              ['总组数', status.total], ['已有本地中文', status.counts.local_human],
              ['官方繁中', status.counts.official_tw_human], ['Wiki 人工', status.counts.exedra_wiki_human],
              ['机器翻译', status.counts.machine_translation], ['仍未处理', status.remaining],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-xl border bg-white p-4 shadow-sm"><p className="text-xs font-bold text-gray-500">{label}</p><p className="mt-1 text-2xl font-black">{value}</p></div>
            ))}
          </section>
        )}

        <section className="rounded-2xl border bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-sm font-bold">处理游标
              <input type="number" min={0} max={status?.candidates ?? 0} value={cursor} disabled={running} onChange={event => setCursor(Math.max(0, Number(event.target.value) || 0))} className="ml-2 w-28 rounded border px-2 py-1 font-mono" />
            </label>
            <button type="button" disabled={!token || running || status?.remaining === 0} onClick={() => void run()} className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-black text-white disabled:opacity-40">{running ? '正在持续处理…' : '从游标开始批量生成'}</button>
            <button type="button" disabled={!running} onClick={() => { stopRef.current = true; }} className="rounded-lg border border-red-300 px-4 py-2 text-sm font-bold text-red-700 disabled:opacity-40">安全停止</button>
          </div>
          <p className="mt-3 text-xs text-gray-500">每次只处理一个逻辑组，成功后立即写入 KV；关闭页面前可点击安全停止。重新打开后已缓存组不会重复翻译。</p>
          {message && <p role="status" className="mt-4 rounded-lg bg-blue-50 p-3 text-sm text-blue-900">{message}</p>}
          <div className="mt-4 max-h-96 overflow-auto rounded-lg bg-gray-950 p-3 font-mono text-xs text-gray-100">
            {log.length ? log.map((line, index) => <div key={`${line}-${index}`}>{line}</div>) : <div className="text-gray-500">尚无本次处理日志。</div>}
          </div>
        </section>
      </div>
    </main>
  );
}
