'use client';

import { useMemo, useSyncExternalStore } from 'react';
import {
  CheckCircle2,
  Download,
  ExternalLink,
  LoaderCircle,
  RotateCcw,
  Trash2,
  TriangleAlert,
  Upload,
} from 'lucide-react';

import {
  READER_FONT_BUNDLES,
  disableReaderFontBundle,
  enableReaderFontBundle,
  formatReaderFontBytes,
  getReaderFontRuntimeServerSnapshot,
  getReaderFontRuntimeSnapshot,
  importReaderFontBundleFiles,
  parseReaderFontRuntimeSnapshot,
  removeReaderFontBundleCache,
  restoreSystemReaderFonts,
  subscribeReaderFontRuntime,
  type ReaderFontBundleId,
  type ReaderFontBundleRuntime,
} from '@/lib/reader-fonts';

const BUSY_STATUSES = new Set(['checking', 'downloading', 'loading']);

const bundleStatusText = (
  bundleId: ReaderFontBundleId,
  runtime: ReaderFontBundleRuntime,
  totalBytes: number,
): string => {
  switch (runtime.status) {
    case 'checking':
      return '正在检查本地字体缓存…';
    case 'downloading':
      return `正在下载（总计 ${formatReaderFontBytes(totalBytes)}）…`;
    case 'loading':
      return runtime.loadedBytes > 0
        ? `正在校验并载入 ${formatReaderFontBytes(runtime.loadedBytes)} / ${formatReaderFontBytes(totalBytes)}…`
        : '正在从本地缓存载入…';
    case 'ready':
      return runtime.source === 'cache'
        ? '已从本地缓存启用。'
        : runtime.cached
          ? '已启用，并保存到本地字体缓存。'
          : '已启用；浏览器未授予持久缓存，刷新时可能重新下载。';
    case 'error':
    case 'unsupported':
      return runtime.error;
    default:
      if (
        READER_FONT_BUNDLES[bundleId].activation === 'local-import'
      ) {
        return runtime.cached
          ? '已在本机缓存；尚未启用。'
          : '尚未导入；当前使用系统字体。';
      }
      return runtime.cached
        ? '已下载但未启用；当前使用系统字体。'
        : '尚未下载；当前使用系统字体。';
  }
};

const actionLabel = (
  bundleId: ReaderFontBundleId,
  runtime: ReaderFontBundleRuntime,
): string => {
  const label = READER_FONT_BUNDLES[bundleId].label;
  if (BUSY_STATUSES.has(runtime.status)) return '正在处理…';
  if (runtime.status === 'ready') return '恢复系统字体';
  if (READER_FONT_BUNDLES[bundleId].activation === 'local-import') {
    return runtime.cached ? `启用已导入的${label}` : `导入并启用${label}`;
  }
  return runtime.cached ? `启用已下载的${label}` : `下载并启用${label}`;
};

export default function ReaderFontSettings({
  theme,
  isExedraStory,
}: {
  theme: string;
  isExedraStory: boolean;
}) {
  const snapshot = useSyncExternalStore(
    subscribeReaderFontRuntime,
    getReaderFontRuntimeSnapshot,
    getReaderFontRuntimeServerSnapshot,
  );
  const state = useMemo(
    () => parseReaderFontRuntimeSnapshot(snapshot),
    [snapshot],
  );
  const bundleIds: readonly ReaderFontBundleId[] = isExedraStory
    ? ['exedraChinese', 'exedraChineseFallback', 'exedraJapanese']
    : ['chinese', 'japanese'];
  const anyReady = bundleIds.some(
    bundleId => state.bundles[bundleId].status === 'ready',
  );

  return (
    <details
      data-reader-font-settings="true"
      className={`rounded-lg border p-3 ${
        theme === 'dark'
          ? 'border-gray-700 bg-white/5'
          : 'border-gray-200 bg-black/[0.02]'
      }`}
    >
      <summary className="cursor-pointer select-none font-bold">
        游戏字体（按需下载）
      </summary>
      <p className="mt-2 text-[11px] leading-relaxed opacity-65">
        默认不请求或读取字体文件，只有明确选择后才启用。字体只作用于当前游戏的
        对应语言；遇到缺字会继续使用声明的 CJK 回退字体。
      </p>

      {isExedraStory && (
        <p className="mt-2 rounded border border-amber-300/60 bg-amber-50/60 p-2 text-[10px] leading-relaxed text-amber-900">
          简中主包从作者的固定 OFL Release 下载并校验 SHA-256；可选 GBK
          回退包同样只在本机导入。JP 原生字体是 Fontworks 商业字体，本站不分发；
          只接受你从合法副本选择的两份文件，在浏览器本机校验、缓存和使用，
          文件不会上传。
        </p>
      )}

      <div className="mt-3 space-y-3">
        {bundleIds.map(bundleId => {
          const definition = READER_FONT_BUNDLES[bundleId];
          const runtime = state.bundles[bundleId];
          const busy = BUSY_STATUSES.has(runtime.status);
          const failed =
            runtime.status === 'error' || runtime.status === 'unsupported';
          return (
            <section
              key={bundleId}
              data-reader-font-bundle={bundleId}
              className={`rounded-lg border p-3 ${
                theme === 'dark'
                  ? 'border-gray-600 bg-black/10'
                  : 'border-gray-200 bg-white'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="font-bold">{definition.label}</h3>
                  <p className="mt-0.5 text-[10px] opacity-60">
                    {definition.description}
                  </p>
                </div>
                <span className="shrink-0 rounded-full border border-current px-2 py-0.5 font-mono text-[10px] opacity-60">
                  {formatReaderFontBytes(definition.totalBytes)}
                </span>
              </div>

              <p
                role="status"
                aria-live="polite"
                className={`mt-2 flex items-start gap-1.5 text-[11px] ${
                  failed
                    ? 'text-red-600'
                    : runtime.status === 'ready'
                      ? 'text-emerald-600'
                      : 'opacity-65'
                }`}
              >
                {busy ? (
                  <LoaderCircle className="mt-0.5 shrink-0 animate-spin" size={12} />
                ) : failed ? (
                  <TriangleAlert className="mt-0.5 shrink-0" size={12} />
                ) : runtime.status === 'ready' ? (
                  <CheckCircle2 className="mt-0.5 shrink-0" size={12} />
                ) : null}
                <span>
                  {bundleStatusText(bundleId, runtime, definition.totalBytes)}
                </span>
              </p>

              <div className="mt-2 flex flex-wrap gap-2">
                {definition.activation === 'local-import' &&
                !runtime.cached && runtime.status !== 'ready' ? (
                  <label
                    className={`flex min-h-10 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-center text-xs font-bold text-white transition hover:bg-blue-700 ${
                      busy ? 'pointer-events-none cursor-wait opacity-50' : ''
                    }`}
                  >
                    <Upload size={13} />
                    {actionLabel(bundleId, runtime)}
                    <input
                      type="file"
                      multiple
                      accept=".otf,.ttf,font/otf,font/ttf"
                      disabled={busy}
                      className="sr-only"
                      onChange={event => {
                        const files = [...(event.currentTarget.files ?? [])];
                        event.currentTarget.value = '';
                        void importReaderFontBundleFiles(bundleId, files);
                      }}
                    />
                  </label>
                ) : (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      if (runtime.status === 'ready') {
                        disableReaderFontBundle(bundleId);
                      } else {
                        void enableReaderFontBundle(bundleId);
                      }
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
                    {actionLabel(bundleId, runtime)}
                  </button>
                )}
                {runtime.cached && runtime.status !== 'ready' && !busy && (
                  <button
                    type="button"
                    onClick={() => void removeReaderFontBundleCache(bundleId)}
                    className="flex min-h-10 items-center gap-1 rounded-lg border border-red-300 px-2 py-2 text-[10px] font-bold text-red-600 hover:bg-red-50"
                  >
                    <Trash2 size={12} />
                    删除缓存
                  </button>
                )}
              </div>
              {(definition.sourceUrl || definition.licenseUrl) && (
                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px]">
                  {definition.sourceUrl && (
                    <a
                      href={definition.sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-blue-600 underline"
                    >
                      官方来源 <ExternalLink size={10} />
                    </a>
                  )}
                  {definition.licenseUrl && (
                    <a
                      href={definition.licenseUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-blue-600 underline"
                    >
                      授权说明 <ExternalLink size={10} />
                    </a>
                  )}
                </div>
              )}
            </section>
          );
        })}
      </div>

      <button
        type="button"
        disabled={!anyReady}
        onClick={restoreSystemReaderFonts}
        className="mt-3 flex min-h-10 w-full items-center justify-center gap-1.5 rounded-lg border border-current px-3 py-2 text-xs font-bold opacity-70 transition hover:opacity-100 disabled:cursor-not-allowed disabled:opacity-30"
      >
        <RotateCcw size={13} />
        全部恢复系统字体
      </button>
    </details>
  );
}
