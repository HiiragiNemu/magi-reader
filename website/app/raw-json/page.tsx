'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { Database, Download, Search } from 'lucide-react';

type RawJsonEntry = {
  game: 'magireco' | 'exedra';
  language: 'cn' | 'jp';
  category: string;
  folder: string;
  name: string;
  stem: string;
  path: string;
  bytes: number;
  sha256: string;
  storyIds: string[];
};

type RawJsonManifest = {
  schemaVersion: number;
  generatedAt: string;
  entries: number;
  bytes: number;
  counts: Record<string, number>;
  associatedStories: number;
  associatedFiles: number;
  unassociatedFiles: number;
  files: RawJsonEntry[];
};

const PAGE_SIZE = 100;

const formatBytes = (value: number) => {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 ** 2).toFixed(1)} MiB`;
};

export default function RawJsonPage() {
  const [manifest, setManifest] = useState<RawJsonManifest | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [game, setGame] = useState<'all' | 'magireco' | 'exedra'>('all');
  const [language, setLanguage] = useState<'all' | 'cn' | 'jp'>('all');
  const [category, setCategory] = useState('all');
  const [page, setPage] = useState(1);

  useEffect(() => {
    const controller = new AbortController();
    void fetch('/raw_story_json_manifest.json', {
      cache: 'force-cache',
      signal: controller.signal,
    })
      .then(async response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<RawJsonManifest>;
      })
      .then(value => setManifest(value))
      .catch(reason => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return;
        setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => controller.abort();
  }, []);

  const categories = useMemo(
    () => [...new Set((manifest?.files ?? []).map(item => item.category))].sort(),
    [manifest],
  );

  const filtered = useMemo(() => {
    const terms = query.trim().toLocaleLowerCase('zh-CN').split(/\s+/).filter(Boolean);
    return (manifest?.files ?? []).filter(item => {
      if (game !== 'all' && item.game !== game) return false;
      if (language !== 'all' && item.language !== language) return false;
      if (category !== 'all' && item.category !== category) return false;
      if (!terms.length) return true;
      const text = [item.name, item.folder, item.category, item.stem, item.path, ...item.storyIds]
        .join(' ')
        .toLocaleLowerCase('zh-CN');
      return terms.every(term => text.includes(term));
    });
  }, [manifest, query, game, language, category]);

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages);
  const shown = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const changeFilter = (callback: () => void) => {
    callback();
    setPage(1);
  };

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur md:px-8">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-purple-100 text-purple-700"><Database size={20} /></span>
            <div><h1 className="font-black">原始剧情 JSON</h1><p className="text-xs text-slate-500">魔法纪录 · Magia Exedra</p></div>
          </div>
          <Link href="/" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold hover:bg-slate-50">返回剧情阅读器</Link>
        </div>
      </header>

      <div className="mx-auto max-w-[1600px] px-4 py-6 md:px-8">
        {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 p-4 text-red-800">读取JSON清单失败：{error}</div>}
        {!manifest && !error && <div className="rounded-xl border border-slate-200 bg-white p-8 text-center">正在读取原始JSON清单……</div>}
        {manifest && (
          <>
            <section className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl border border-slate-200 bg-white p-4"><strong className="text-2xl">{manifest.entries.toLocaleString('zh-CN')}</strong><span className="mt-1 block text-xs text-slate-500">原始JSON文件</span></div>
              <div className="rounded-xl border border-slate-200 bg-white p-4"><strong className="text-2xl">{formatBytes(manifest.bytes)}</strong><span className="mt-1 block text-xs text-slate-500">文件总量</span></div>
              <div className="rounded-xl border border-slate-200 bg-white p-4"><strong className="text-2xl">{manifest.associatedStories.toLocaleString('zh-CN')}</strong><span className="mt-1 block text-xs text-slate-500">已回链剧情单元</span></div>
              <div className="rounded-xl border border-slate-200 bg-white p-4"><strong className="text-2xl">{manifest.associatedFiles.toLocaleString('zh-CN')}</strong><span className="mt-1 block text-xs text-slate-500">已匹配JSON</span></div>
            </section>

            <section className="mb-5 grid gap-2 rounded-xl border border-slate-200 bg-white p-3 lg:grid-cols-[minmax(260px,1fr)_auto_auto_minmax(170px,auto)]">
              <label className="relative"><Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} /><input type="search" value={query} onChange={event => changeFilter(() => setQuery(event.target.value))} placeholder="搜索文件名、目录、剧情ID或SHA路径" className="w-full rounded-lg border border-slate-300 py-2.5 pl-10 pr-3 outline-none focus:border-purple-500" /></label>
              <select value={game} onChange={event => changeFilter(() => setGame(event.target.value as typeof game))} className="rounded-lg border border-slate-300 px-3 py-2"><option value="all">两个游戏</option><option value="magireco">魔法纪录</option><option value="exedra">Magia Exedra</option></select>
              <select value={language} onChange={event => changeFilter(() => setLanguage(event.target.value as typeof language))} className="rounded-lg border border-slate-300 px-3 py-2"><option value="all">中日来源</option><option value="cn">中文源</option><option value="jp">日文源</option></select>
              <select value={category} onChange={event => changeFilter(() => setCategory(event.target.value))} className="rounded-lg border border-slate-300 px-3 py-2"><option value="all">全部分类</option>{categories.map(value => <option key={value} value={value}>{value}</option>)}</select>
            </section>

            <div className="mb-3 flex items-center justify-between text-sm text-slate-500"><span>{filtered.length.toLocaleString('zh-CN')} 个匹配文件</span><span>第 {currentPage} / {pages} 页</span></div>
            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
              {shown.map(item => (
                <article key={item.path} className="grid gap-2 border-b border-slate-100 p-3 last:border-b-0 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                  <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><strong className="break-all text-sm">{item.name}</strong><span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase">{item.game}</span><span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase">{item.language}</span><span className="text-[10px] text-slate-500">{item.category}</span></div><p className="mt-1 break-all text-xs text-slate-500">{item.folder} · {formatBytes(item.bytes)} · SHA-256 {item.sha256.slice(0, 16)}…</p>{item.storyIds.length > 0 && <p className="mt-1 break-all text-[10px] text-purple-700">剧情：{item.storyIds.slice(0, 8).join(' · ')}{item.storyIds.length > 8 ? ` 等${item.storyIds.length}项` : ''}</p>}</div>
                  <a href={item.path} target="_blank" rel="noreferrer" download className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-purple-700"><Download size={14} />打开 / 下载</a>
                </article>
              ))}
            </section>

            <div className="mt-5 flex items-center justify-center gap-3"><button type="button" disabled={currentPage <= 1} onClick={() => setPage(value => Math.max(1, value - 1))} className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm disabled:opacity-30">上一页</button><span className="text-sm">{currentPage} / {pages}</span><button type="button" disabled={currentPage >= pages} onClick={() => setPage(value => Math.min(pages, value + 1))} className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm disabled:opacity-30">下一页</button></div>
          </>
        )}
      </div>
    </main>
  );
}
