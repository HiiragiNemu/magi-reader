'use client';

import { useMemo, useSyncExternalStore } from 'react';
import {
  CheckCircle2,
  Download,
  LoaderCircle,
  RotateCcw,
  Trash2,
  TriangleAlert,
} from 'lucide-react';

import {
  EXEDRA_FONT_DEFINITIONS,
  disableExedraFont,
  enableExedraFont,
  formatExedraFontBytes,
  getExedraFontRuntimeServerSnapshot,
  getExedraFontRuntimeSnapshot,
  parseExedraFontRuntimeSnapshot,
  removeExedraFontCache,
  restoreSystemExedraFonts,
  subscribeExedraFontRuntime,
  type ExedraFontId,
  type ExedraFontRuntime,
} from '@/lib/exedra-fonts';

const BUSY = new Set(['checking', 'downloading', 'loading']);
const FONT_IDS = [
  'tangyuan',
  'tsuku-old-gothic',
  'new-cinema-a',
] as const;

const statusText = (
  id: ExedraFontId,
  runtime: ExedraFontRuntime,
): string => {
  const definition = EXEDRA_FONT_DEFINITIONS[id];
  if (runtime.status === 'checking') return '正在检查本地缓存…';
  if (runtime.status === 'downloading') return '正在按需下载并校验…';
  if (runtime.status === 'loading') return '校验通过，正在载入浏览器…';
  if (runtime.status === 'ready') {
    return `${runtime.source === 'cache' ? '已从本地缓存启用' : '已下载并启用'}。${runtime.validation}`;
  }
  if (runtime.status === 'error' || runtime.status === 'unsupported') {
    return runtime.error;
  }
  if (runtime.cached) return '已下载到当前浏览器，但尚未启用。';
  return `尚未下载；当前使用默认字体（${formatExedraFontBytes(definition.bytes)}）。`;
};

const statusIcon = (runtime: ExedraFontRuntime) => {
  if (BUSY.has(runtime.status)) {
    return <LoaderCircle className="mt-0.5 shrink-0 animate-spin" size={12} />;
  }
  if (runtime.status === 'error' || runtime.status === 'unsupported') {
    return <TriangleAlert className="mt-0.5 shrink-0" size={12} />;
  }
  if (runtime.status === 'ready') {
    return <CheckCircle2 className="mt-0.5 shrink-0" size={12} />;
  }
  return null;
};

export default function ExedraFontSettings({ theme }: { theme: string }) {
  const snapshot = useSyncExternalStore(
    subscribeExedraFontRuntime,
    getExedraFontRuntimeSnapshot,
    getExedraFontRuntimeServerSnapshot,
  );
  const state = useMemo(
    () => parseExedraFontRuntimeSnapshot(snapshot),
    [snapshot],
  );
  const anyReady = Object.values(state.fonts).some(font => font.status === 'ready');

  const renderCard = (id: ExedraFontId) => {
    const definition = EXEDRA_FONT_DEFINITIONS[id];
    const runtime = state.fonts[id];
    const busy = BUSY.has(runtime.status);
    const failed = runtime.status === 'error' || runtime.status === 'unsupported';
    return (
      <section
        key={id}
        data-exedra-font={id}
        className={`rounded-lg border p-3 ${
          theme === 'dark'
            ? 'border-gray-600 bg-black/10'
            : 'border-stone-300 bg-white/70'
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <h4 className="font-bold">{definition.label}</h4>
            <p className="mt-0.5 text-[10px] leading-relaxed opacity-65">
              {definition.description}
            </p>
          </div>
          <span className="shrink-0 rounded-full border border-current px-2 py-0.5 font-mono text-[10px] opacity-60">
            {formatExedraFontBytes(definition.bytes)}
          </span>
        </div>

        <p
          role="status"
          aria-live="polite"
          className={`mt-2 flex items-start gap-1.5 text-[11px] ${
            failed
              ? 'text-red-600'
              : runtime.status === 'ready'
                ? 'text-emerald-700'
                : 'opacity-65'
          }`}
        >
          {statusIcon(runtime)}
          <span>{statusText(id, runtime)}</span>
        </p>

        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              if (runtime.status === 'ready') disableExedraFont(id);
              else void enableExedraFont(id);
            }}
            className={`flex min-h-10 flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold text-white transition disabled:cursor-wait disabled:opacity-50 ${
              runtime.status === 'ready'
                ? 'bg-gray-600 hover:bg-gray-700'
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {runtime.status === 'ready' ? (
              <RotateCcw size={13} />
            ) : (
              <Download size={13} />
            )}
            {runtime.status === 'ready'
              ? '关闭并恢复默认字体'
              : runtime.cached
                ? '启用已下载字体'
                : '下载并启用'}
          </button>
          {runtime.cached && !busy && (
            <button
              type="button"
              onClick={() => void removeExedraFontCache(id)}
              className="flex min-h-10 items-center gap-1 rounded-lg border border-red-300 px-2 py-2 text-[10px] font-bold text-red-600 hover:bg-red-50"
            >
              <Trash2 size={12} />
              清除下载缓存
            </button>
          )}
        </div>
      </section>
    );
  };

  return (
    <details
      data-exedra-font-settings="true"
      className={`rounded-lg border p-3 ${
        theme === 'dark'
          ? 'border-gray-700 bg-white/5'
          : 'border-stone-300 bg-amber-50/30'
      }`}
    >
      <summary className="cursor-pointer select-none font-bold">
        Magia Exedra 字体（按需下载）
      </summary>
      <p className="mt-2 text-[11px] leading-relaxed opacity-70">
        默认不请求、不启用这些字体。猫啃网糖圆体覆盖 Exedra 全部 UI 与简体中文正文；
        日文剧情仍使用独立日文字体，魔法纪录页面保持原样。
      </p>

      <div className="mt-3 space-y-3">
        <div>
          <p className="mb-1 text-[11px] font-bold opacity-75">简体中文 zh-Hans</p>
          {renderCard('tangyuan')}
        </div>
        <div>
          <p className="mb-1 text-[11px] font-bold opacity-75">日文 ja</p>
          <div className="space-y-2">
            {FONT_IDS.slice(1).map(renderCard)}
          </div>
        </div>
      </div>

      <button
        type="button"
        disabled={!anyReady}
        onClick={restoreSystemExedraFonts}
        className="mt-3 flex min-h-10 w-full items-center justify-center gap-1.5 rounded-lg border border-current px-3 py-2 text-xs font-bold opacity-70 transition hover:opacity-100 disabled:cursor-not-allowed disabled:opacity-30"
      >
        <RotateCcw size={13} />
        全部关闭并恢复 Exedra 默认字体
      </button>
    </details>
  );
}
