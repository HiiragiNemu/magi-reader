"use client";

import { use, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  BookOpen,
  Download,
  Leaf,
  Menu,
  Moon,
  Search,
  Settings,
  Sun,
  X,
} from 'lucide-react';

import AboutModal from '@/components/AboutModal';
import Sidebar, { type Story } from '@/components/Sidebar';
import StoryText from '@/components/StoryText';
import {
  speakerColorFor,
  translateSpeakerName,
} from '@/app/config/dictionary';
import { useGlobal } from '@/app/providers';
import { readLocalStoryPayload, readScenarioFile } from '@/lib/local-story';
import { normalizeSearchText } from '@/lib/search';
import { loadStoryIndex } from '@/lib/story-index';
import { useDialog } from '@/lib/use-dialog';
import {
  alignStoryLines,
  makeSectionAnchorId,
  parseStoryContent,
  serializeStoryLine,
  type AlignedStoryLine,
  type StoryFormat,
  type StoryLine,
} from '@/lib/story-parser';

type ReaderMode = 'cn' | 'split' | 'jp';
type EditSeed = 'empty' | 'jp' | 'current';

type LoadedSource = {
  name: string;
  raw: string;
  format: StoryFormat;
};

const THEME_STYLES: Record<string, string> = {
  light: 'bg-transparent text-gray-900',
  dark: 'bg-transparent text-gray-200',
  paper: 'bg-transparent text-[#4a4036]',
  green: 'bg-transparent text-[#003300]',
};

const HEADER_STYLES: Record<string, string> = {
  light: 'border-gray-200 bg-white/80 backdrop-blur-md',
  dark: 'border-gray-800 bg-[#0f172a]/80 backdrop-blur-md',
  paper: 'border-[#e6dfc5] bg-[#f0e6d2]/60 backdrop-blur-md',
  green: 'border-[#A8D8B9] bg-[#C7EDCC]/80 backdrop-blur-md',
};

const FORMAT_LABELS: Record<StoryFormat, string> = {
  'plain-text': 'TXT',
  'scene0-text': 'Scene0 TXT',
  'magireco-json': 'Magia Record JSON',
  'exedra-json': 'Magia Exedra JSON',
  'generic-json': '通用 JSON',
};

const safeDownloadName = (value: string): string =>
  value.replace(/[<>:"/\\|?*\u0000-\u001F]/g, '-').replace(/\s+/g, ' ').trim() || 'story';

const filenameFromPath = (path: string, fallback: string): string => {
  try {
    const pathname = new URL(path, window.location.origin).pathname;
    return decodeURIComponent(pathname.split('/').filter(Boolean).at(-1) || fallback);
  } catch {
    return fallback;
  }
};

const downloadContent = (content: string, filename: string, addBom = false) => {
  const blob = new Blob([addBom ? `\uFEFF${content}` : content], {
    type: filename.toLowerCase().endsWith('.json')
      ? 'application/json;charset=utf-8'
      : 'text/plain;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = safeDownloadName(filename);
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 100);
};

const sourceDownloadName = (id: string, language: 'cn' | 'jp', source: LoadedSource): string => {
  const extension = source.name.toLowerCase().endsWith('.json') ? 'json' : 'txt';
  return `${id}_${language}.${extension}`;
};

const translatedSpeaker = (speaker: string): string =>
  translateSpeakerName(speaker);

const seedEditableLines = (
  cnLines: StoryLine[],
  jpLines: StoryLine[],
  seed: EditSeed,
): StoryLine[] => {
  const rows = alignStoryLines(cnLines, jpLines);
  return rows.flatMap(({ cn, jp }) => {
    const basis = cn ?? jp;
    if (!basis) return [];

    if (seed === 'current' && cn) return [{ ...cn }];

    const structural = Boolean(basis.isHeader || basis.isChoice);
    const text =
      structural
        ? basis.text
        : seed === 'jp'
          ? (jp ?? basis).text
          : seed === 'current' && cn
            ? cn.text
            : '';

    return [{
      ...basis,
      speaker: cn?.speaker || translatedSpeaker((jp ?? basis).speaker),
      text,
    }];
  });
};

const lineTextAlignClass = (line?: StoryLine): string => {
  if (line?.position === 'right') return 'text-right';
  if (line?.position === 'center') return 'text-center';
  return 'text-left';
};

const lineKindClass = (line?: StoryLine): string => {
  if (line?.kind === 'fnarration') return 'italic opacity-80';
  if (line?.kind === 'narration') return 'opacity-90';
  return '';
};

const speakerColor = (speaker: string): string | undefined =>
  speakerColorFor(speaker);

const parseLoadedSource = (name: string, raw: string): {
  source: LoadedSource;
  lines: StoryLine[];
  title?: string;
  warnings: string[];
} => {
  const parsed = parseStoryContent(raw, {
    filename: name,
    mergeConsecutiveTextLines: true,
  });
  return {
    source: { name, raw, format: parsed.format },
    lines: parsed.lines,
    title: parsed.title,
    warnings: parsed.warnings,
  };
};

export default function ReaderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const searchParams = useSearchParams();
  const isLocal = searchParams.get('local') === '1';
  const { theme, setTheme } = useGlobal();

  const [cnLines, setCnLines] = useState<StoryLine[]>([]);
  const [jpLines, setJpLines] = useState<StoryLine[]>([]);
  const [cnSource, setCnSource] = useState<LoadedSource | null>(null);
  const [jpSource, setJpSource] = useState<LoadedSource | null>(null);
  const [storyTitle, setStoryTitle] = useState('');
  const [loadError, setLoadError] = useState('');
  const [parseWarnings, setParseWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<ReaderMode>('cn');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [fontSize, setFontSize] = useState(15);
  const [lineHeight, setLineHeight] = useState(1.1);
  const [allStories, setAllStories] = useState<Story[]>([]);
  const [storyIndexReady, setStoryIndexReady] = useState(false);
  const [storyIndexError, setStoryIndexError] = useState('');
  const [isEditMode, setIsEditMode] = useState(false);
  const [editedCnLines, setEditedCnLines] = useState<StoryLine[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentMatchIndex, setCurrentMatchIndex] = useState(-1);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [editMessage, setEditMessage] = useState('');
  const settingsDialogRef = useDialog<HTMLElement>(
    showSettings,
    () => setShowSettings(false),
  );

  useEffect(() => {
    const controller = new AbortController();
    loadStoryIndex(controller.signal)
      .then(({ stories }) => {
        setAllStories(stories);
      })
      .catch(error => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        console.error('剧情索引加载失败：', error);
        setStoryIndexError('剧情目录读取失败。');
      })
      .finally(() => {
        if (!controller.signal.aborted) setStoryIndexReady(true);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!isLocal && !storyIndexReady) return;

    const controller = new AbortController();
    let active = true;

    setLoading(true);
    setLoadError('');
    setParseWarnings([]);
    setCnLines([]);
    setJpLines([]);
    setCnSource(null);
    setJpSource(null);
    setStoryTitle('');
    setEditedCnLines([]);
    setIsEditMode(false);
    setEditMessage('');
    setSearchQuery('');
    setCurrentMatchIndex(-1);

    const fetchSource = async (
      path: string,
      fallbackName: string,
    ): Promise<ReturnType<typeof parseLoadedSource> | null> => {
      if (!path) return null;
      const response = await fetch(path, { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`${fallbackName}读取失败（HTTP ${response.status}）`);
      }
      const raw = await response.text();
      return parseLoadedSource(filenameFromPath(path, fallbackName), raw);
    };

    const load = async () => {
      try {
        let parsedCn: ReturnType<typeof parseLoadedSource> | null = null;
        let parsedJp: ReturnType<typeof parseLoadedSource> | null = null;
        let localTitle = '';

        if (isLocal) {
          const payload = readLocalStoryPayload();
          if (!payload || payload.id !== id) {
            throw new Error('本地剧情已失效，请返回首页重新选择文件。');
          }
          localTitle = payload.title;
          if (payload.cn) parsedCn = parseLoadedSource(payload.cn.name, payload.cn.raw);
          if (payload.jp) parsedJp = parseLoadedSource(payload.jp.name, payload.jp.raw);
        } else {
          if (storyIndexError) throw new Error(storyIndexError);
          const manifestStory = allStories.find(story => story.id === id);
          if (!manifestStory) {
            throw new Error('剧情编号不存在，或剧情目录尚未包含该文件。');
          }
          [parsedCn, parsedJp] = await Promise.all([
            fetchSource(manifestStory.path_cn || '', `${id}_cn.txt`),
            fetchSource(manifestStory.path_jp || '', `${id}_jp.txt`),
          ]);
        }

        if (!active) return;
        const nextCnLines = parsedCn?.lines ?? [];
        const nextJpLines = parsedJp?.lines ?? [];
        if (nextCnLines.length === 0 && nextJpLines.length === 0) {
          throw new Error('文件中没有找到可显示的剧情文本。');
        }

        setCnLines(nextCnLines);
        setJpLines(nextJpLines);
        setCnSource(parsedCn?.source ?? null);
        setJpSource(parsedJp?.source ?? null);
        setParseWarnings([...(parsedCn?.warnings ?? []), ...(parsedJp?.warnings ?? [])]);
        setStoryTitle(localTitle || parsedCn?.title || parsedJp?.title || '');
        setMode(
          nextCnLines.length > 0 && nextJpLines.length > 0
            ? 'split'
            : nextCnLines.length > 0
              ? 'cn'
              : 'jp',
        );
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (!active) return;
        setLoadError(error instanceof Error ? error.message : '剧情加载失败。');
      } finally {
        if (active) setLoading(false);
      }
    };

    void load();
    return () => {
      active = false;
      controller.abort();
    };
  }, [allStories, id, isLocal, storyIndexError, storyIndexReady]);

  const currentStory = useMemo(
    () => allStories.find(story => story.id === id),
    [allStories, id],
  );

  const displayedCnLines =
    isEditMode && editedCnLines.length > 0 ? editedCnLines : cnLines;
  const renderList = useMemo(
    () => alignStoryLines(displayedCnLines, jpLines),
    [displayedCnLines, jpLines],
  );
  const editedLineIndices = useMemo(
    () => new Map(editedCnLines.map((line, index) => [line, index])),
    [editedCnLines],
  );

  const normalizedQuery = useMemo(
    () => normalizeSearchText(searchQuery),
    [searchQuery],
  );

  const matchedIndices = useMemo(() => {
    if (!normalizedQuery) return [];
    const matches: number[] = [];
    renderList.forEach((row, index) => {
      const header = row.cn?.isHeader ? row.cn : row.jp?.isHeader ? row.jp : undefined;
      const choice = row.cn?.isChoice ? row.cn : row.jp?.isChoice ? row.jp : undefined;
      const searchable = [
        row.cn?.speaker,
        row.cn?.text,
        row.jp?.speaker,
        row.jp?.text,
        header?.headerSection ? `第${header.headerSection}节 节${header.headerSection}` : '',
        header?.headerBranch ? `分支${header.headerBranch} 路线${header.headerBranch}` : '',
        choice?.choiceLabel ? `${choice.choiceLabel} 选项 分支` : '',
      ].filter(Boolean).join(' ');
      if (normalizeSearchText(searchable).includes(normalizedQuery)) matches.push(index);
    });
    return matches;
  }, [normalizedQuery, renderList]);

  const jumpToNextMatch = useCallback(() => {
    if (matchedIndices.length === 0) return;
    const next = currentMatchIndex < 0
      ? 0
      : (currentMatchIndex + 1) % matchedIndices.length;
    setCurrentMatchIndex(next);
    document.getElementById(`line-${matchedIndices[next]}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [currentMatchIndex, matchedIndices]);

  const changeSearch = (value: string) => {
    setSearchQuery(value);
    setCurrentMatchIndex(-1);
  };

  const initializeEditing = (seed: EditSeed) => {
    const next = seedEditableLines(cnLines, jpLines, seed);
    if (next.length === 0) {
      setEditMessage('当前剧情没有可编辑的文本。');
      return;
    }
    setEditedCnLines(next);
    setMode(jpLines.length > 0 ? 'split' : 'cn');
    setEditMessage('');
  };

  const toggleEditMode = () => {
    if (isEditMode) {
      setIsEditMode(false);
      return;
    }
    if (editedCnLines.length === 0) initializeEditing('current');
    setIsEditMode(true);
  };

  const downloadTranslation = () => {
    const lines = editedCnLines.length > 0 ? editedCnLines : cnLines;
    if (lines.length === 0) {
      setEditMessage('当前没有可下载的中文内容。');
      return;
    }
    downloadContent(
      lines.map(serializeStoryLine).join('\n'),
      `${id}_translated.txt`,
      true,
    );
  };

  const uploadTranslation = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    try {
      const source = await readScenarioFile(file);
      const parsed = parseStoryContent(source.raw, {
        filename: source.name,
        mergeConsecutiveTextLines: true,
      });
      if (parsed.lines.length === 0) throw new Error('文件中没有可编辑的剧情文本。');
      const normalized = seedEditableLines(parsed.lines, jpLines, 'current');
      setEditedCnLines(normalized.length > 0 ? normalized : parsed.lines);
      setParseWarnings(previous => [...previous, ...parsed.warnings]);
      setEditMessage(`已载入 ${file.name}（${FORMAT_LABELS[parsed.format]}）。`);
    } catch (error) {
      setEditMessage(error instanceof Error ? error.message : '文件读取失败。');
    }
  };

  const submitToCloud = async () => {
    if (editedCnLines.length === 0) {
      setEditMessage('请先初始化或上传翻译内容。');
      return;
    }
    const content = editedCnLines.map(serializeStoryLine).join('\n');
    if (content.trim().length < 10) {
      setEditMessage('内容过短，请编辑后再提交。');
      return;
    }

    try {
      const response = await fetch('/api/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ story_id: id, content, author: 'Anonymous' }),
      });
      const responseText = await response.text();
      let data: { success?: boolean; key?: string; error?: string } = {};
      try {
        data = JSON.parse(responseText) as typeof data;
      } catch {
        // The generic message below intentionally avoids exposing server internals.
      }
      if (!response.ok || !data.success) {
        throw new Error(data.error || `提交服务暂不可用（HTTP ${response.status}）`);
      }
      setEditMessage(`提交成功，审核编号：${data.key || '已接收'}`);
    } catch (error) {
      setEditMessage(
        `${error instanceof Error ? error.message : '在线提交失败'}；已自动下载备份文件。`,
      );
      downloadContent(content, `${id}_submit.txt`, true);
    }
  };

  const jumpToChoice = (rowIndex: number, choice: StoryLine) => {
    if (!choice.choiceTargetId) return;
    let source = choice.headerSourceId || '';
    let section = choice.headerSection || '';
    for (let index = rowIndex; index >= 0 && (!source || !section); index--) {
      const row = renderList[index];
      const header = row.cn?.isHeader ? row.cn : row.jp?.isHeader ? row.jp : undefined;
      source ||= header?.headerSourceId || '';
      section ||= header?.headerSection || '';
    }

    const exactId =
      source && section
        ? makeSectionAnchorId(source, section, choice.choiceTargetId)
        : '';
    let target = exactId ? document.getElementById(exactId) : null;
    if (!target) {
      const fallback = renderList.slice(rowIndex + 1).find(row => {
        const header = row.cn?.isHeader ? row.cn : row.jp?.isHeader ? row.jp : undefined;
        return header?.headerBranch === choice.choiceTargetId;
      });
      const header = fallback?.cn?.isHeader ? fallback.cn : fallback?.jp;
      target = header?.headerId ? document.getElementById(header.headerId) : null;
    }
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.add('ring-4', 'ring-amber-400');
    window.setTimeout(() => target?.classList.remove('ring-4', 'ring-amber-400'), 1500);
  };

  if (loading) {
    return (
      <div className="flex h-screen h-[100dvh] items-center justify-center opacity-60">
        正在读取剧情…
      </div>
    );
  }

  return (
    <div className={`flex h-screen h-[100dvh] overflow-hidden ${THEME_STYLES[theme]}`}>
      <Sidebar
        stories={allStories}
        currentId={id}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        className={sidebarOpen ? '' : 'hidden md:flex'}
      />

      <div className="relative flex min-w-0 flex-1 flex-col">
        <header className={`z-20 flex shrink-0 items-center justify-between border-b px-4 py-2 ${HEADER_STYLES[theme]}`}>
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              aria-label="打开剧情目录"
              onClick={() => setSidebarOpen(true)}
              className="rounded p-2 -ml-2 hover:bg-black/5 md:hidden"
            >
              <Menu size={20} />
            </button>
            <div className="flex min-w-0 flex-col">
              <span className="truncate text-[10px] opacity-50">
                {isLocal ? '本地文件' : currentStory?.folder || '剧情阅读器'}
                {storyTitle ? ` · ${storyTitle}` : ''}
              </span>
              <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm font-bold">
                <span className="truncate font-mono text-emerald-600">{id}</span>
                {cnSource && (
                  <button
                    type="button"
                    title={`下载原始文件（${FORMAT_LABELS[cnSource.format]}）`}
                    onClick={() => downloadContent(
                      cnSource.raw,
                      sourceDownloadName(id, 'cn', cnSource),
                      !cnSource.name.toLowerCase().endsWith('.json'),
                    )}
                    className="flex items-center gap-1 rounded px-1.5 py-0.5 opacity-50 transition hover:text-green-600 hover:opacity-100"
                  >
                    <Download size={14} /><span className="text-[10px]">CN</span>
                  </button>
                )}
                {jpSource && (
                  <button
                    type="button"
                    title={`下载原始文件（${FORMAT_LABELS[jpSource.format]}）`}
                    onClick={() => downloadContent(
                      jpSource.raw,
                      sourceDownloadName(id, 'jp', jpSource),
                      !jpSource.name.toLowerCase().endsWith('.json'),
                    )}
                    className="flex items-center gap-1 rounded px-1.5 py-0.5 opacity-50 transition hover:text-blue-600 hover:opacity-100"
                  >
                    <Download size={14} /><span className="text-[10px]">JP</span>
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="group relative mx-4 hidden max-w-md flex-1 md:flex">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="search"
              aria-label="在当前剧情中搜索"
              placeholder="页内搜索（Enter 跳转）"
              value={searchQuery}
              onChange={event => changeSearch(event.target.value)}
              onKeyDown={event => {
                if (event.key === 'Enter') jumpToNextMatch();
              }}
              className={`w-full rounded-full border py-1.5 pl-9 pr-14 text-sm outline-none transition ${
                theme === 'dark'
                  ? 'border-gray-700 bg-gray-800 text-gray-200 focus:border-blue-500'
                  : 'border-transparent bg-gray-100 focus:border-blue-400 focus:bg-white'
              }`}
            />
            {searchQuery && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-xs text-gray-400">
                {matchedIndices.length
                  ? `${currentMatchIndex >= 0 ? currentMatchIndex + 1 : 0}/${matchedIndices.length}`
                  : '0'}
              </span>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              aria-pressed={isEditMode}
              onClick={toggleEditMode}
              className={`z-30 flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-bold transition ${
                isEditMode
                  ? 'bg-emerald-600 text-white shadow-lg'
                  : 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200'
              }`}
            >
              <Leaf size={14} />
              <span className="hidden sm:inline">{isEditMode ? '返回阅读' : '协助汉化'}</span>
            </button>
            <div className={`flex rounded p-0.5 text-[10px] font-bold ${theme === 'dark' ? 'bg-white/10' : 'bg-black/5'}`}>
              {(['cn', 'split', 'jp'] as const).map(nextMode => (
                <button
                  type="button"
                  key={nextMode}
                  aria-label={
                    nextMode === 'cn'
                      ? '只显示中文'
                      : nextMode === 'jp'
                        ? '只显示日文'
                        : '显示中日双语'
                  }
                  aria-pressed={mode === nextMode}
                  onClick={() => setMode(nextMode)}
                  className={`rounded px-2 py-1 ${
                    mode === nextMode
                      ? theme === 'dark' ? 'bg-gray-700 text-white' : 'bg-white shadow'
                      : 'opacity-40'
                  }`}
                >
                  {nextMode === 'cn' ? '中' : nextMode === 'jp' ? '日' : '双'}
                </button>
              ))}
            </div>
            <button
              type="button"
              aria-label="打开阅读设置"
              onClick={() => setShowSettings(true)}
              className="rounded p-2 text-gray-500 hover:bg-black/5"
            >
              <Settings size={18} />
            </button>
          </div>
        </header>

        <main
          className="z-10 flex-1 overflow-y-auto scroll-smooth p-2 md:p-6"
          style={{ fontSize: `${fontSize}px`, lineHeight }}
        >
          <div className={`mx-auto min-h-screen max-w-3xl rounded-lg pb-32 transition ${
            theme === 'paper' || theme === 'green'
              ? 'md:bg-white/40 md:px-12 md:py-8 md:shadow-sm'
              : ''
          }`}>
            {loadError && (
              <div role="alert" className="mb-4 rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-800">
                <p className="font-bold">无法打开这段剧情</p>
                <p className="mt-1">{loadError}</p>
                <Link href="/" className="mt-3 inline-block underline">返回首页重新选择</Link>
              </div>
            )}

            {parseWarnings.length > 0 && !loadError && (
              <details className="mb-4 rounded-lg border border-amber-200 bg-amber-50/80 p-3 text-xs text-amber-900">
                <summary className="cursor-pointer font-bold">
                  已读取，但有 {parseWarnings.length} 条格式提示
                </summary>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {parseWarnings.slice(0, 20).map((warning, index) => (
                    <li key={`${warning}-${index}`}>{warning}</li>
                  ))}
                </ul>
              </details>
            )}

            {isEditMode && !loadError && (
              <section className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50/80 p-4 shadow-sm">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="mr-1 text-xs font-bold text-emerald-800 opacity-70">初始化：</span>
                  <button type="button" onClick={() => initializeEditing('empty')} className="rounded-lg border border-emerald-300 bg-white px-3 py-1.5 text-xs font-bold text-emerald-700 hover:bg-emerald-50">
                    仅填入译名
                  </button>
                  <button type="button" onClick={() => initializeEditing('jp')} className="rounded-lg border border-emerald-300 bg-white px-3 py-1.5 text-xs font-bold text-emerald-700 hover:bg-emerald-50">
                    填入日文原文
                  </button>
                  <label className="flex cursor-pointer items-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-bold text-blue-700 hover:bg-blue-100">
                    上传 JSON / TXT
                    <input type="file" accept=".json,.txt" className="hidden" onChange={uploadTranslation} />
                  </label>
                  <button type="button" onClick={downloadTranslation} className="ml-auto rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-bold text-white shadow hover:bg-blue-700">
                    下载当前进度
                  </button>
                  <button type="button" onClick={() => void submitToCloud()} className="rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-bold text-white shadow hover:bg-purple-700">
                    提交审核
                  </button>
                </div>
                <p className="mt-2 text-[10px] text-emerald-700/70">
                  标题、分支、位置与动作信息会在初始化时保留。请定期下载 TXT 备份。
                </p>
                {editMessage && (
                  <p role="status" className="mt-2 rounded bg-white/70 px-2 py-1 text-xs text-emerald-900">
                    {editMessage}
                  </p>
                )}
              </section>
            )}

            <div className="relative mb-4 px-1 md:hidden">
              <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="search"
                aria-label="在当前剧情中搜索"
                placeholder="搜索角色或对话…"
                value={searchQuery}
                onChange={event => changeSearch(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') jumpToNextMatch();
                }}
                className={`w-full rounded-lg border py-2.5 pl-10 pr-16 text-sm shadow-sm outline-none ${
                  theme === 'dark'
                    ? 'border-gray-700 bg-gray-800 text-gray-100'
                    : 'border-gray-200 bg-white text-gray-900'
                }`}
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={jumpToNextMatch}
                  className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md bg-blue-500 px-2 py-1 text-xs text-white"
                >
                  {matchedIndices.length
                    ? `${currentMatchIndex >= 0 ? currentMatchIndex + 1 : 0}/${matchedIndices.length} ↓`
                    : '0'}
                </button>
              )}
            </div>

            {!isEditMode && !loadError && (
              <div className={`mb-4 rounded-xl border p-4 text-center text-sm ${
                theme === 'dark' ? 'border-white/10 bg-white/5' : 'border-black/5 bg-black/[0.02]'
              }`}>
                <div className="flex flex-wrap items-center justify-center gap-2 text-xs font-bold">
                  <Link href="/" className="rounded-lg border border-current px-3 py-1.5 opacity-70 hover:opacity-100">
                    🏠 返回首页
                  </Link>
                  <button type="button" onClick={() => setAboutOpen(true)} className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-emerald-700">
                    🔗 我的工具与动态
                  </button>
                </div>
              </div>
            )}

            {!loadError && renderList.map((row, index) => (
              <StoryRow
                key={index}
                row={row}
                index={index}
                editIndex={row.cn ? (editedLineIndices.get(row.cn) ?? index) : index}
                mode={mode}
                theme={theme}
                isEditMode={isEditMode}
                editedLines={editedCnLines}
                setEditedLines={setEditedCnLines}
                query={searchQuery}
                normalizedQuery={normalizedQuery}
                focused={currentMatchIndex >= 0 && matchedIndices[currentMatchIndex] === index}
                onChoice={jumpToChoice}
              />
            ))}
          </div>
        </main>

        {showSettings && (
          <div
            role="presentation"
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
            onMouseDown={() => setShowSettings(false)}
          >
            <section
              ref={settingsDialogRef}
              role="dialog"
              aria-modal="true"
              aria-labelledby="reader-settings-title"
              tabIndex={-1}
              className={`w-full max-w-xs rounded-xl p-5 shadow-2xl ${
                theme === 'dark' ? 'border border-gray-700 bg-gray-800' : 'bg-white'
              }`}
              onMouseDown={event => event.stopPropagation()}
            >
              <div className="mb-4 flex items-center justify-between">
                <h2 id="reader-settings-title" className="font-bold">阅读设置</h2>
                <button type="button" aria-label="关闭阅读设置" onClick={() => setShowSettings(false)}>
                  <X size={18} />
                </button>
              </div>
              <div className="space-y-4 text-sm">
                <div>
                  <p className="mb-2 opacity-70">主题</p>
                  <div className="flex justify-center gap-2">
                    {([
                      { key: 'light', icon: Sun, label: '亮色' },
                      { key: 'paper', icon: BookOpen, label: '护眼' },
                      { key: 'dark', icon: Moon, label: '暗黑' },
                      { key: 'green', icon: Leaf, label: '绿色' },
                    ] as const).map(option => (
                      <button
                        type="button"
                        key={option.key}
                        aria-pressed={theme === option.key}
                        onClick={() => setTheme(option.key)}
                        className={`flex flex-1 flex-col items-center gap-1 rounded border py-2 ${
                          theme === option.key
                            ? 'border-blue-500 bg-blue-500/10 text-blue-500'
                            : 'border-transparent bg-black/5'
                        }`}
                      >
                        <option.icon size={16} />
                        <span className="text-[10px]">{option.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <label className="block">
                  <span className="mb-1 block opacity-70">字号（{fontSize}px）</span>
                  <input type="range" min="12" max="22" value={fontSize} onChange={event => setFontSize(Number(event.target.value))} className="w-full" />
                </label>
                <label className="block">
                  <span className="mb-1 block opacity-70">行高（{lineHeight}）</span>
                  <input type="range" min="1.1" max="2" step="0.1" value={lineHeight} onChange={event => setLineHeight(Number(event.target.value))} className="w-full" />
                </label>
              </div>
            </section>
          </div>
        )}
      </div>

      <AboutModal isOpen={aboutOpen} onClose={() => setAboutOpen(false)} theme={theme} />
    </div>
  );
}

type StoryRowProps = {
  row: AlignedStoryLine;
  index: number;
  editIndex: number;
  mode: ReaderMode;
  theme: string;
  isEditMode: boolean;
  editedLines: StoryLine[];
  setEditedLines: React.Dispatch<React.SetStateAction<StoryLine[]>>;
  query: string;
  normalizedQuery: string;
  focused: boolean;
  onChoice: (index: number, choice: StoryLine) => void;
};

function StoryRow({
  row,
  index,
  editIndex,
  mode,
  theme,
  isEditMode,
  editedLines,
  setEditedLines,
  query,
  normalizedQuery,
  focused,
  onChoice,
}: StoryRowProps) {
  const header = row.cn?.isHeader ? row.cn : row.jp?.isHeader ? row.jp : undefined;
  if (header) {
    const headerText = header.text.replace(/---/g, '').trim();
    const isBranch = Boolean(header.headerBranch);
    return (
      <div
        id={header.headerId}
        className={`mb-4 mt-6 border-t-2 pt-4 text-center ${
          isBranch
            ? 'rounded-lg border-amber-400/50 bg-amber-50/30 py-3'
            : 'border-dashed border-current opacity-50'
        }`}
      >
        {isBranch ? (
          <div className="flex flex-col items-center gap-1">
            <span className={`rounded-full border px-3 py-1.5 text-xs font-bold ${
              theme === 'dark'
                ? 'border-amber-700 bg-amber-900/40 text-amber-300'
                : 'border-amber-300 bg-amber-100 text-amber-800'
            }`}>
              🔀 {header.headerSection ? `第${header.headerSection}节 ` : ''}
              选项路线 {header.headerBranch}
            </span>
            {header.headerSourceId && (
              <span className="font-mono text-[10px] opacity-50">{header.headerSourceId}</span>
            )}
          </div>
        ) : (
          <span className="rounded-full border border-current px-3 py-1 font-mono text-xs opacity-70">
            {headerText}
          </span>
        )}
      </div>
    );
  }

  const choice = row.cn?.isChoice ? row.cn : row.jp?.isChoice ? row.jp : undefined;
  if (choice) {
    const editableChoice = editedLines[editIndex];
    return (
      <div id={`line-${index}`} className="my-3 flex justify-center">
        {isEditMode ? (
          <label className="flex w-full max-w-xl items-center gap-2 rounded-xl border-2 border-amber-300 bg-amber-50 p-2 text-xs font-bold text-amber-900">
            选项
            <input
              aria-label={`第 ${index + 1} 行选项文本`}
              className="min-w-0 flex-1 rounded border border-amber-200 bg-white px-2 py-1.5 font-normal text-black outline-none focus:ring-2 focus:ring-amber-400"
              value={editableChoice?.choiceLabel || editableChoice?.text || ''}
              onChange={event => {
                const value = event.target.value;
                setEditedLines(previous => {
                  const next = [...previous];
                  const basis = next[editIndex] || choice;
                  next[editIndex] = { ...basis, choiceLabel: value, text: `【${value}】` };
                  return next;
                });
              }}
            />
          </label>
        ) : (
          <button
            type="button"
            onClick={() => onChoice(index, choice)}
            className={`cursor-pointer rounded-xl border-2 px-5 py-2.5 text-sm font-bold transition hover:scale-105 active:scale-95 ${
              theme === 'dark'
                ? 'border-amber-700 bg-gradient-to-r from-amber-900/60 to-orange-900/60 text-amber-200'
                : 'border-amber-300 bg-gradient-to-r from-amber-50 to-orange-50 text-amber-800 shadow-sm'
            }`}
          >
            👆 {choice.choiceLabel || choice.text}
            <span className="ml-2 text-[10px] opacity-50">↓ 点击跳转</span>
          </button>
        )}
      </div>
    );
  }

  const cnSpeakerMatches =
    Boolean(normalizedQuery) &&
    normalizeSearchText(row.cn?.speaker || '').includes(normalizedQuery);
  const jpSpeakerMatches =
    Boolean(normalizedQuery) &&
    normalizeSearchText(row.jp?.speaker || '').includes(normalizedQuery);

  return (
    <div
      id={`line-${index}`}
      className={`group flex flex-col border-b border-transparent py-1 transition-colors md:flex-row md:gap-4 ${
        focused
          ? theme === 'dark'
            ? 'bg-blue-900/30 ring-1 ring-blue-500/50'
            : 'bg-yellow-50 ring-1 ring-yellow-400/50'
          : 'hover:border-current hover:border-opacity-10'
      }`}
    >
      {mode !== 'jp' && (
        <div className={`flex gap-3 ${mode === 'split' ? 'md:w-1/2' : 'w-full'}`}>
          {isEditMode ? (
            <>
              <input
                aria-label={`第 ${index + 1} 行角色名`}
                className={`w-20 flex-shrink-0 rounded border px-1 py-1 text-right text-[11px] font-bold leading-tight outline-none focus:ring-2 focus:ring-emerald-500 md:w-24 ${
                  theme === 'dark'
                    ? 'border-gray-700 bg-gray-800 text-white'
                    : 'border-gray-200 bg-white text-black'
                }`}
                value={editedLines[editIndex]?.speaker || row.jp?.speaker || '旁白'}
                onChange={event => {
                  const value = event.target.value;
                  setEditedLines(previous => {
                    const next = [...previous];
                    const basis = next[editIndex] || row.cn || row.jp || {
                      speaker: '旁白',
                      text: '',
                    };
                    next[editIndex] = { ...basis, speaker: value };
                    return next;
                  });
                }}
              />
              <textarea
                aria-label={`第 ${index + 1} 行翻译`}
                className={`flex-1 rounded border p-2 text-sm outline-none transition focus:ring-2 focus:ring-emerald-500 ${
                  theme === 'dark'
                    ? 'border-gray-700 bg-gray-800 text-white'
                    : 'border-gray-200 bg-white text-black'
                }`}
                value={editedLines[editIndex]?.text || ''}
                placeholder="在此输入翻译内容…"
                onChange={event => {
                  const value = event.target.value;
                  setEditedLines(previous => {
                    const next = [...previous];
                    const basis = next[editIndex] || row.cn || row.jp || {
                      speaker: '旁白',
                      text: '',
                    };
                    next[editIndex] = { ...basis, text: value };
                    return next;
                  });
                }}
                rows={Math.max(1, (editedLines[editIndex]?.text || '').split('\n').length)}
              />
            </>
          ) : row.cn ? (
            <>
              <SpeakerLabel line={row.cn} highlighted={cnSpeakerMatches} />
              <div className={`flex-1 whitespace-pre-wrap pt-0.5 ${lineTextAlignClass(row.cn)} ${lineKindClass(row.cn)}`}>
                <StoryText text={row.cn.text} query={query} theme={theme} />
              </div>
            </>
          ) : (
            <div className="flex-1 border-b border-dashed border-black/5 py-1 text-xs italic opacity-20">
              等待翻译…
            </div>
          )}
        </div>
      )}

      {mode !== 'cn' && (
        <div className={`flex gap-2 ${
          mode === 'split'
            ? 'mt-1 border-current border-opacity-10 md:mt-0 md:w-1/2 md:border-l md:pl-4'
            : 'w-full'
        }`}>
          {row.jp ? (
            <>
              <SpeakerLabel line={row.jp} highlighted={jpSpeakerMatches} faded />
              <div className={`flex-1 whitespace-pre-wrap font-sans text-sm opacity-70 ${lineTextAlignClass(row.jp)} ${lineKindClass(row.jp)}`}>
                <StoryText text={row.jp.text} query={query} theme={theme} />
              </div>
            </>
          ) : (
            <div className="flex-1 py-1 text-xs italic opacity-20">…</div>
          )}
        </div>
      )}
    </div>
  );
}

function SpeakerLabel({
  line,
  highlighted,
  faded = false,
}: {
  line: StoryLine;
  highlighted: boolean;
  faded?: boolean;
}) {
  return (
    <div
      className={`h-fit w-20 flex-shrink-0 break-words rounded px-1 pt-1 text-right text-[11px] font-bold leading-tight md:w-24 ${
        highlighted ? 'ring-2 ring-yellow-400' : faded ? 'opacity-50' : ''
      }`}
      style={{ color: speakerColor(line.speaker) }}
    >
      {line.speaker}
    </div>
  );
}
