'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';

import Home from '../page';
import { useGlobal } from '@/app/providers';

type StorySystem = 'magireco' | 'exedra';
type SystemStatus = {
  system: StorySystem;
  definition: string;
  total: number;
  verified: number;
  remaining: number;
  machine_translation_ids: string[];
  verified_ids: string[];
};
type StatusResponse = {
  version: 2;
  systems: Record<StorySystem, SystemStatus>;
};

const replaceVoiceLabels = (root: ParentNode) => {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const replacements: Text[] = [];
  let node = walker.nextNode();
  while (node) {
    if (node instanceof Text && node.nodeValue?.trim() === 'general_voice') {
      replacements.push(node);
    }
    node = walker.nextNode();
  }
  for (const text of replacements) text.nodeValue = '语音';
};

const storyIdFromLink = (link: HTMLAnchorElement): string => {
  try {
    const parts = new URL(link.href, window.location.origin).pathname.split('/');
    const readerIndex = parts.indexOf('reader');
    return readerIndex >= 0 ? decodeURIComponent(parts[readerIndex + 1] || '') : '';
  } catch {
    return '';
  }
};

const clearExedraEnhancements = () => {
  document.querySelectorAll<HTMLElement>('[data-exedra-machine-enhanced]').forEach(element => {
    element.style.removeProperty('background-color');
    element.style.removeProperty('border-color');
    element.style.removeProperty('color');
    element.removeAttribute('data-exedra-machine-enhanced');
  });
  document.querySelectorAll('[data-exedra-machine-badge]').forEach(element => element.remove());
};

const badge = (text: string, verified: boolean): HTMLSpanElement => {
  const element = document.createElement('span');
  element.dataset.exedraMachineBadge = 'true';
  element.textContent = text;
  element.style.cssText = [
    'display:inline-flex',
    'align-items:center',
    'border-radius:0.25rem',
    'padding:0.125rem 0.375rem',
    'font-size:9px',
    'font-weight:900',
    'color:white',
    `background:${verified ? '#059669' : '#f59e0b'}`,
    'white-space:nowrap',
  ].join(';');
  return element;
};

const enhanceExedraCards = (status: SystemStatus | null) => {
  clearExedraEnhancements();
  replaceVoiceLabels(document.body);
  if (!status || status.total === 0) return;

  const machine = new Set(status.machine_translation_ids);
  const verified = new Set(status.verified_ids);
  const folderCounts = new Map<HTMLElement, { pending: number; verified: number }>();
  for (const link of document.querySelectorAll<HTMLAnchorElement>('a[href*="/reader/"]')) {
    const storyId = storyIdFromLink(link);
    if (!machine.has(storyId)) continue;
    const isVerified = verified.has(storyId);
    link.dataset.exedraMachineEnhanced = 'true';
    link.style.backgroundColor = isVerified ? '#ecfdf5' : '#fffbeb';
    link.style.borderColor = isVerified ? '#10b981' : '#f59e0b';
    link.style.color = isVerified ? '#064e3b' : '#451a03';
    const row = link.querySelector('div');
    if (row) row.appendChild(badge(isVerified ? '人工已校' : '机翻待校', isVerified));
    const folder = link.closest<HTMLElement>('.break-inside-avoid');
    if (folder) {
      const count = folderCounts.get(folder) ?? { pending: 0, verified: 0 };
      if (isVerified) count.verified += 1;
      else count.pending += 1;
      folderCounts.set(folder, count);
    }
  }

  for (const [folder, count] of folderCounts) {
    folder.dataset.exedraMachineEnhanced = 'true';
    folder.style.borderColor = count.pending ? '#f59e0b' : '#10b981';
    const header = folder.querySelector<HTMLElement>('button');
    const titleRow = header?.querySelector<HTMLElement>('div.flex.items-start');
    if (header) {
      header.dataset.exedraMachineEnhanced = 'true';
      header.style.backgroundColor = count.pending ? '#fef3c7' : '#d1fae5';
      header.style.color = count.pending ? '#451a03' : '#064e3b';
    }
    titleRow?.appendChild(
      badge(count.pending ? `待校 ${count.pending}` : `已校 ${count.verified}`, count.pending === 0),
    );
  }
};

function ExedraReviewPanel({ status }: { status: SystemStatus }) {
  const progress = status.total > 0
    ? Math.round((status.verified / status.total) * 100)
    : 0;
  return (
    <aside className="fixed bottom-4 right-4 z-50 w-[min(28rem,calc(100vw-2rem))] rounded-2xl border border-violet-300 bg-white/95 p-4 text-gray-900 shadow-2xl backdrop-blur dark:border-violet-700 dark:bg-gray-900/95 dark:text-gray-100">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <strong>Exedra 机器翻译人工校验</strong>
            <span className="rounded-full bg-violet-600 px-2 py-0.5 text-[10px] font-black text-white">独立动态</span>
          </div>
          <p className="mt-1 text-xs opacity-70">
            总计 {status.total} 部，已校 {status.verified} 部，剩余 {status.remaining} 部。
          </p>
        </div>
        <Link
          href="/review/machine-translations?system=exedra"
          className="rounded-lg bg-violet-600 px-3 py-2 text-xs font-black text-white"
        >
          管理 Exedra 标记
        </Link>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-black/10">
          <div className="h-full rounded-full bg-emerald-500" style={{ width: `${progress}%` }} />
        </div>
        <span className="font-mono text-xs font-bold">{progress}%</span>
      </div>
    </aside>
  );
}

export default function VoiceEnabledHome() {
  const { lastCategory } = useGlobal();
  const system: StorySystem = lastCategory.startsWith('exedra_') ? 'exedra' : 'magireco';
  const [statuses, setStatuses] = useState<Record<StorySystem, SystemStatus> | null>(null);
  const frame = useRef<number | null>(null);
  const currentStatus = useMemo(() => statuses?.[system] ?? null, [statuses, system]);

  useEffect(() => {
    const controller = new AbortController();
    void fetch('/api/proofreading/machine-status', { cache: 'no-store', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const value = await response.json() as Partial<StatusResponse>;
        if (!value.systems?.magireco || !value.systems?.exedra) {
          throw new Error('双游戏机翻状态格式无效');
        }
        setStatuses(value.systems);
      })
      .catch(error => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          console.error('双游戏机翻状态读取失败', error);
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    let observer: MutationObserver;
    const observe = () => observer.observe(document.body, { childList: true, subtree: true });
    const applyNow = () => {
      observer.disconnect();
      if (system === 'exedra') enhanceExedraCards(currentStatus);
      else {
        clearExedraEnhancements();
        replaceVoiceLabels(document.body);
      }
      observe();
    };
    const schedule = () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(applyNow);
    };
    observer = new MutationObserver(records => {
      const onlyOwnBadges = records.every(record =>
        [...record.addedNodes, ...record.removedNodes].every(node =>
          node instanceof Element && node.hasAttribute('data-exedra-machine-badge'),
        ),
      );
      if (!onlyOwnBadges) schedule();
    });
    observe();
    schedule();
    return () => {
      observer.disconnect();
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      clearExedraEnhancements();
    };
  }, [currentStatus, system]);

  return (
    <>
      <Home />
      {system === 'exedra' && currentStatus && <ExedraReviewPanel status={currentStatus} />}
    </>
  );
}
