"use client";

import {
  use,
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
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
} from 'lucide-react';

import AboutModal from '@/components/AboutModal';
import FloatingWindow from '@/components/FloatingWindow';
import ReaderFontSettings from '@/components/ReaderFontSettings';
import TurnstileWidget from '@/components/TurnstileWidget';
import Sidebar, { type Story } from '@/components/Sidebar';
import StoryText, { LineBreakMarkerText } from '@/components/StoryText';
import { VoicePlayButton } from '@/components/voice/VoicePlayButton';
import {
  speakerColorFor,
  translateSpeakerName,
} from '@/app/config/dictionary';
import { useGlobal } from '@/app/providers';
import { readLocalStoryPayload, readScenarioFile } from '@/lib/local-story';
import { normalizeSearchText } from '@/lib/search';
import {
  normalizeProofreadingText,
  sha256Text,
} from '@/lib/proofreading';
import { saveProofreadingReceipt } from '@/lib/proofreading-client';
import { voicePlaybackController } from '@/lib/audio/voice-player';
import {
  findStoryByRouteId,
  isOptionalStorySourceUnavailable,
  loadStoryIndex,
  readBoundedResponseBody,
  resolveDirectStorySources,
  verifyExedraStoryId,
} from '@/lib/story-index';
import { triggerUtf8Download } from '@/lib/browser-download';
import { initializeExedraFonts } from '@/lib/exedra-fonts';
import {
  bilingualLanguagePaneClass,
  bilingualStoryPairClass,
} from '@/lib/bilingual-layout';
import { resolveOfficialSectionTitle } from '@/lib/official-tw-titles';
import { initializeReaderFonts } from '@/lib/reader-fonts';
import {
  READER_TEXT_WIDTH_MAX,
  READER_TEXT_WIDTH_MIN,
  READER_TEXT_WIDTH_STEP,
  getReaderDisplayPreferencesServerSnapshot,
  getReaderDisplayPreferencesSnapshot,
  parseReaderDisplayPreferences,
  subscribeReaderDisplayPreferences,
  updateReaderDisplayPreferences,
} from '@/lib/reader-display-preferences';
import {
  createEditedScenarioJsonDownload,
  createOriginalScenarioJsonDownload,
  triggerScenarioJsonDownload,
} from '@/lib/scenario-json-download';
import {
  applyScenarioJsonUploadToAggregate,
  buildScenarioJsonSourceOptions,
  mapAggregateEditsToScenarioJson,
} from '@/lib/scenario-json-selection';
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
type BilingualLayout = 'side-by-side' | 'stacked';
type JsonDownloadBusy = 'jp' | 'cn' | 'edited' | null;

type LoadedSource = {
  name: string;
  raw: string;
  format: StoryFormat;
};

type ProofreadingConfig = {
  submissions_enabled: boolean;
  turnstile_site_key: string;
  target_branch: string;
  source_revision: string;
  github_admin_auth: boolean;
  turnstile_test_mode: boolean;
};

const MAX_STORY_SOURCE_BYTES = 8 * 1024 * 1024;
const BILINGUAL_LAYOUT_STORAGE_KEY = 'magi-reader-bilingual-layout-v1';
const STORY_ROWS_PER_PAGE = 200;

const countLineBreaks = (text: string): number => {
  let count = 0;
  let cursor = 0;
  while (cursor < text.length) {
    const next = text.indexOf('\n', cursor);
    if (next < 0) break;
    count += 1;
    cursor = next + 1;
  }
  return count;
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

const filenameFromPath = (path: string, fallback: string): string => {
  try {
    const pathname = new URL(path, window.location.origin).pathname;
    return decodeURIComponent(pathname.split('/').filter(Boolean).at(-1) || fallback);
  } catch {
    return fallback;
  }
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
  eventLines: StoryLine[];
  title?: string;
  warnings: string[];
} => {
  const eventParsed = parseStoryContent(raw, {
    filename: name,
    mergeConsecutiveTextLines: false,
  });
  const displayParsed = parseStoryContent(raw, {
    filename: name,
    mergeConsecutiveTextLines: true,
  });
  return {
    source: { name, raw, format: eventParsed.format },
    lines: displayParsed.lines,
    eventLines: eventParsed.lines,
    title: displayParsed.title || eventParsed.title,
    warnings: [...new Set([
      ...eventParsed.warnings,
      ...displayParsed.warnings,
    ])],
  };
};

export default function ReaderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const searchParams = useSearchParams();
  const isLocal = searchParams.get('local') === '1';
  const queryCnPath = searchParams.get('cn');
  const queryJpPath = searchParams.get('jp');
  const { theme, setTheme } = useGlobal();

  const [cnLines, setCnLines] = useState<StoryLine[]>([]);
  const [jpLines, setJpLines] = useState<StoryLine[]>([]);
  const [cnEventLines, setCnEventLines] = useState<StoryLine[]>([]);
  const [jpEventLines, setJpEventLines] = useState<StoryLine[]>([]);
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
  const [bilingualLayout, setBilingualLayout] =
    useState<BilingualLayout>('side-by-side');
  const readerDisplayPreferencesSnapshot = useSyncExternalStore(
    subscribeReaderDisplayPreferences,
    getReaderDisplayPreferencesSnapshot,
    getReaderDisplayPreferencesServerSnapshot,
  );
  const readerDisplayPreferences = useMemo(
    () =>
      parseReaderDisplayPreferences(readerDisplayPreferencesSnapshot),
    [readerDisplayPreferencesSnapshot],
  );
  const [allStories, setAllStories] = useState<Story[]>([]);
  const [storyIndexReady, setStoryIndexReady] = useState(false);
  const [storyIndexError, setStoryIndexError] = useState('');
  const [storyIndexSha256, setStoryIndexSha256] = useState('');
  const [isEditMode, setIsEditMode] = useState(false);
  const [proofreadingConfig, setProofreadingConfig] =
    useState<ProofreadingConfig | null>(null);
  const [proofreadingConfigLoading, setProofreadingConfigLoading] =
    useState(false);
  const [proofreadingNickname, setProofreadingNickname] = useState('');
  const [proofreadingNote, setProofreadingNote] = useState('');
  const [turnstileToken, setTurnstileToken] = useState('');
  const [turnstileResetKey, setTurnstileResetKey] = useState(0);
  const [submittingProofreading, setSubmittingProofreading] = useState(false);
  const [lastSubmissionId, setLastSubmissionId] = useState('');
  const [editedCnLines, setEditedCnLines] = useState<StoryLine[]>([]);
  const [selectedJsonSourceKey, setSelectedJsonSourceKey] = useState('');
  const [jsonDownloadBusy, setJsonDownloadBusy] =
    useState<JsonDownloadBusy>(null);
  const jsonDownloadBusyRef = useRef<JsonDownloadBusy>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentMatchIndex, setCurrentMatchIndex] = useState(-1);
  const [visiblePage, setVisiblePage] = useState(0);
  const [pendingRowScroll, setPendingRowScroll] = useState<{
    rowIndex: number;
    highlight: boolean;
  } | null>(null);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [editMessage, setEditMessage] = useState('');

  useEffect(() => {
    const stored = window.localStorage.getItem(BILINGUAL_LAYOUT_STORAGE_KEY);
    if (stored === 'side-by-side' || stored === 'stacked') {
      setBilingualLayout(stored);
    }
  }, []);

  const changeBilingualLayout = (layout: BilingualLayout) => {
    setBilingualLayout(layout);
    window.localStorage.setItem(BILINGUAL_LAYOUT_STORAGE_KEY, layout);
  };

  const directSourceResolution = useMemo(() => {
    try {
      return {
        error: '',
        sources: resolveDirectStorySources(id, queryCnPath, queryJpPath),
      };
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : '剧情链接中的文件路径无效。',
        sources: null,
      };
    }
  }, [id, queryCnPath, queryJpPath]);
  const deferStoryIndexUntilContent =
    isLocal || directSourceResolution.sources !== null;

  useEffect(() => {
    if (deferStoryIndexUntilContent && loading) {
      return;
    }
    const controller = new AbortController();
    loadStoryIndex(controller.signal)
      .then(({ stories, sha256 }) => {
        setAllStories(stories);
        setStoryIndexSha256(sha256);
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
  }, [deferStoryIndexUntilContent, loading]);

  useEffect(() => {
    if (!isEditMode || isLocal) return;
    const controller = new AbortController();
    setProofreadingConfigLoading(true);
    setTurnstileToken('');
    void fetch('/api/proofreading/config', {
      cache: 'no-store',
      credentials: 'same-origin',
      signal: controller.signal,
    })
      .then(async (response) => {
        const payload = await response.json() as ProofreadingConfig & {
          error?: string;
        };
        if (!response.ok) {
          throw new Error(payload.error || `HTTP ${response.status}`);
        }
        setProofreadingConfig(payload);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setProofreadingConfig(null);
        setEditMessage('无法读取投稿服务配置；仍可下载 TXT 备份。');
      })
      .finally(() => {
        if (!controller.signal.aborted) setProofreadingConfigLoading(false);
      });
    return () => controller.abort();
  }, [isEditMode, isLocal]);

  const currentStory = useMemo(
    () => findStoryByRouteId(allStories, id),
    [allStories, id],
  );
  const isExedraStory =
    currentStory?.game === 'exedra' ||
    currentStory?.category.startsWith('exedra_') === true ||
    directSourceResolution.sources?.kind === 'exedra-trusted-runtime';
  const jsonSourceOptionsState = useMemo(() => {
    if (!currentStory) return { options: [], error: '' };
    try {
      return {
        options: buildScenarioJsonSourceOptions({
          story: currentStory,
          cnLines: cnEventLines,
          jpLines: jpEventLines,
        }),
        error: '',
      };
    } catch (error) {
      return {
        options: [],
        error:
          error instanceof Error
            ? error.message
            : '剧情 JSON 来源清单无法读取。',
      };
    }
  }, [cnEventLines, currentStory, jpEventLines]);
  const selectedJsonSource = useMemo(
    () =>
      jsonSourceOptionsState.options.find(
        option => option.key === selectedJsonSourceKey,
      ) ?? jsonSourceOptionsState.options[0],
    [jsonSourceOptionsState.options, selectedJsonSourceKey],
  );

  useEffect(() => {
    if (
      jsonSourceOptionsState.options.length === 0 ||
      jsonSourceOptionsState.options.some(
        option => option.key === selectedJsonSourceKey,
      )
    ) {
      return;
    }
    setSelectedJsonSourceKey(jsonSourceOptionsState.options[0].key);
  }, [jsonSourceOptionsState.options, selectedJsonSourceKey]);

  const sourceReady =
    isLocal ||
    Boolean(directSourceResolution.error) ||
    directSourceResolution.sources !== null ||
    storyIndexReady;
  const sourceError =
    directSourceResolution.error ||
    (
      !isLocal &&
      storyIndexReady
        ? directSourceResolution.sources === null
          ? storyIndexError ||
            (currentStory ? '' : '剧情编号不存在，或剧情目录尚未包含该文件。')
          : !storyIndexError && !currentStory
            ? '剧情编号不存在，或剧情目录尚未包含该文件。'
            : ''
        : ''
    );
  const useManifestSources =
    storyIndexReady &&
    currentStory !== undefined &&
    (
      directSourceResolution.sources?.kind === 'query' ||
      Boolean(currentStory.path_cn)
    );
  const sourcePathCn =
    useManifestSources
      ? currentStory.path_cn ?? ''
      : directSourceResolution.sources?.pathCn ?? currentStory?.path_cn ?? '';
  const sourcePathJp =
    useManifestSources
      ? currentStory.path_jp ?? ''
      : directSourceResolution.sources?.pathJp ?? currentStory?.path_jp ?? '';
  const sourceCnOptional =
    useManifestSources
      ? false
      : directSourceResolution.sources?.optionalCn ?? false;

  useEffect(() => {
    if (!sourceReady) return;

    const controller = new AbortController();
    let active = true;

    setLoading(true);
    setLoadError('');
    setParseWarnings([]);
    setCnLines([]);
    setJpLines([]);
    setCnEventLines([]);
    setJpEventLines([]);
    setCnSource(null);
    setJpSource(null);
    setStoryTitle('');
    setEditedCnLines([]);
    setSelectedJsonSourceKey('');
    setJsonDownloadBusy(null);
    jsonDownloadBusyRef.current = null;
    setIsEditMode(false);
    setEditMessage('');
    setLastSubmissionId('');
    setTurnstileToken('');
    setTurnstileResetKey((value) => value + 1);
    setSearchQuery('');
    setCurrentMatchIndex(-1);

    const fetchSource = async (
      path: string,
      fallbackName: string,
      optional = false,
    ): Promise<ReturnType<typeof parseLoadedSource> | null> => {
      if (!path) return null;
      const response = await fetch(path, { signal: controller.signal });
      if (!response.ok) {
        if (
          optional &&
          isOptionalStorySourceUnavailable(response.status)
        ) {
          return null;
        }
        throw new Error(`${fallbackName}读取失败（HTTP ${response.status}）`);
      }
      const declaredLength = Number(response.headers.get('content-length'));
      if (
        Number.isFinite(declaredLength) &&
        declaredLength > MAX_STORY_SOURCE_BYTES
      ) {
        await response.body?.cancel('剧情文件超过大小限制');
        throw new Error(`${fallbackName}超过 8 MB 大小限制。`);
      }
      const payload = await readBoundedResponseBody(
        response,
        MAX_STORY_SOURCE_BYTES,
        fallbackName,
      );
      let raw: string;
      try {
        raw = new TextDecoder('utf-8', { fatal: true }).decode(payload);
      } catch {
        throw new Error(`${fallbackName}不是有效的 UTF-8 文本。`);
      }
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
          if (sourceError) throw new Error(sourceError);
          if (
            directSourceResolution.sources?.kind === 'exedra-trusted-runtime' &&
            !(await verifyExedraStoryId(id))
          ) {
            throw new Error('Exedra 剧情编号校验失败。');
          }
          [parsedCn, parsedJp] = await Promise.all([
            fetchSource(sourcePathCn, `${id}_cn.txt`, sourceCnOptional),
            fetchSource(sourcePathJp, `${id}_jp.txt`),
          ]);
        }

        if (!active) return;
        const nextCnLines = parsedCn?.lines ?? [];
        const nextJpLines = parsedJp?.lines ?? [];
        const nextCnEventLines = parsedCn?.eventLines ?? [];
        const nextJpEventLines = parsedJp?.eventLines ?? [];
        if (nextCnLines.length === 0 && nextJpLines.length === 0) {
          throw new Error('文件中没有找到可显示的剧情文本。');
        }

        setCnLines(nextCnLines);
        setJpLines(nextJpLines);
        setCnEventLines(nextCnEventLines);
        setJpEventLines(nextJpEventLines);
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
  }, [
    id,
    isLocal,
    directSourceResolution.sources?.kind,
    sourceCnOptional,
    sourceError,
    sourcePathCn,
    sourcePathJp,
    sourceReady,
  ]);

  const displayedCnLines =
    isEditMode && editedCnLines.length > 0 ? editedCnLines : cnLines;
  const displayedJpLines =
    isEditMode && jpEventLines.length > 0 ? jpEventLines : jpLines;
  const renderList = useMemo(
    () => alignStoryLines(displayedCnLines, displayedJpLines),
    [displayedCnLines, displayedJpLines],
  );
  const pageCount = Math.max(1, Math.ceil(renderList.length / STORY_ROWS_PER_PAGE));
  const pageStart = visiblePage * STORY_ROWS_PER_PAGE;
  const visibleRenderList = renderList.slice(
    pageStart,
    pageStart + STORY_ROWS_PER_PAGE,
  );
  const editedLineIndices = useMemo(
    () => new Map(editedCnLines.map((line, index) => [line, index])),
    [editedCnLines],
  );

  useEffect(() => {
    setVisiblePage(current => Math.min(current, pageCount - 1));
  }, [pageCount]);

  useEffect(() => {
    setVisiblePage(0);
    setPendingRowScroll(null);
  }, [id]);

  const revealRow = useCallback((rowIndex: number, highlight = false) => {
    if (rowIndex < 0) return;
    voicePlaybackController.stop();
    setVisiblePage(Math.floor(rowIndex / STORY_ROWS_PER_PAGE));
    setPendingRowScroll({ rowIndex, highlight });
  }, []);

  useEffect(() => {
    void initializeReaderFonts();
    if (isExedraStory) void initializeExedraFonts();
  }, [isExedraStory]);

  useEffect(() => {
    const stopForHiddenPage = () => {
      if (document.visibilityState === 'hidden') {
        voicePlaybackController.stop();
      }
    };
    window.addEventListener('pagehide', voicePlaybackController.stop);
    document.addEventListener('visibilitychange', stopForHiddenPage);
    return () => {
      window.removeEventListener('pagehide', voicePlaybackController.stop);
      document.removeEventListener('visibilitychange', stopForHiddenPage);
      voicePlaybackController.stop();
    };
  }, [id]);

  const changeVisiblePage = useCallback((page: number) => {
    const nextPage = Math.max(0, page);
    voicePlaybackController.stop();
    setVisiblePage(nextPage);
    setPendingRowScroll({
      rowIndex: nextPage * STORY_ROWS_PER_PAGE,
      highlight: false,
    });
  }, []);

  useEffect(() => {
    if (!pendingRowScroll) return;
    const targetPage = Math.floor(
      pendingRowScroll.rowIndex / STORY_ROWS_PER_PAGE,
    );
    if (targetPage !== visiblePage) return;

    const frame = window.requestAnimationFrame(() => {
      const pendingRow = renderList[pendingRowScroll.rowIndex];
      const header = pendingRow?.cn?.isHeader
        ? pendingRow.cn
        : pendingRow?.jp?.isHeader
          ? pendingRow.jp
          : undefined;
      const target = document.getElementById(
        header?.headerId || `line-${pendingRowScroll.rowIndex}`,
      );
      if (!target) {
        setPendingRowScroll(null);
        return;
      }
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      if (pendingRowScroll.highlight) {
        target.classList.add('ring-4', 'ring-amber-400');
        window.setTimeout(
          () => target.classList.remove('ring-4', 'ring-amber-400'),
          1500,
        );
      }
      setPendingRowScroll(null);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pendingRowScroll, renderList, visiblePage]);

  const deferredSearchQuery = useDeferredValue(searchQuery);
  const normalizedQuery = useMemo(
    () => normalizeSearchText(deferredSearchQuery),
    [deferredSearchQuery],
  );

  const findMatchedIndices = useCallback((query: string): number[] => {
    if (!query) return [];
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
      if (normalizeSearchText(searchable).includes(query)) matches.push(index);
    });
    return matches;
  }, [renderList]);
  const matchedIndices = useMemo(
    () => findMatchedIndices(normalizedQuery),
    [findMatchedIndices, normalizedQuery],
  );

  const jumpToNextMatch = useCallback(() => {
    const immediateQuery = normalizeSearchText(searchQuery);
    const currentMatches =
      immediateQuery === normalizedQuery
        ? matchedIndices
        : findMatchedIndices(immediateQuery);
    if (currentMatches.length === 0) return;
    const next = currentMatchIndex < 0
      ? 0
      : (currentMatchIndex + 1) % currentMatches.length;
    setCurrentMatchIndex(next);
    revealRow(currentMatches[next]);
  }, [
    currentMatchIndex,
    findMatchedIndices,
    matchedIndices,
    normalizedQuery,
    revealRow,
    searchQuery,
  ]);

  const changeSearch = (value: string) => {
    setSearchQuery(value);
    setCurrentMatchIndex(-1);
  };

  const initializeEditing = (seed: EditSeed) => {
    const next = seedEditableLines(cnEventLines, jpEventLines, seed);
    if (next.length === 0) {
      setEditMessage('当前剧情没有可编辑的文本。');
      return;
    }
    setEditedCnLines(next);
    setMode(jpEventLines.length > 0 ? 'split' : 'cn');
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
    triggerUtf8Download(
      lines.map(serializeStoryLine).join('\n'),
      `${id}_translated.txt`,
    );
  };

  const fetchScenarioJson = async (
    language: 'jp' | 'cn',
    index: number,
  ): Promise<string> => {
    if (!currentStory || !selectedJsonSource) {
      throw new Error('当前剧情没有可用的 JSON 来源。');
    }
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20_000);
    try {
      const response = await fetch(
        `/api/story-json/${encodeURIComponent(currentStory.id)}/`
        + `${language}/${index}`,
        {
          cache: 'no-store',
          credentials: 'same-origin',
          signal: controller.signal,
        },
      );
      if (!response.ok) {
        await response.body?.cancel('剧情 JSON 请求失败');
        throw new Error(
          `来源 JSON 读取失败（HTTP ${response.status}）。`,
        );
      }
      const contentType = (
        response.headers.get('content-type') || ''
      ).split(';', 1)[0]?.trim().toLowerCase();
      if (contentType !== 'application/json') {
        await response.body?.cancel('剧情 JSON 类型异常');
        throw new Error('来源 JSON 返回了非 JSON 内容。');
      }
      const payload = await readBoundedResponseBody(
        response,
        MAX_STORY_SOURCE_BYTES,
        '来源 JSON',
      );
      try {
        return new TextDecoder('utf-8', { fatal: true }).decode(payload);
      } catch {
        throw new Error('来源 JSON 不是有效的 UTF-8 文本。');
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new Error('来源 JSON 读取超时。');
      }
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  };

  const runJsonDownload = async (
    kind: Exclude<JsonDownloadBusy, null>,
    operation: () => Promise<string>,
  ) => {
    if (jsonDownloadBusyRef.current) return;
    jsonDownloadBusyRef.current = kind;
    setJsonDownloadBusy(kind);
    setEditMessage('');
    try {
      setEditMessage(await operation());
    } catch (error) {
      setEditMessage(
        error instanceof Error ? error.message : '剧情 JSON 下载失败。',
      );
    } finally {
      jsonDownloadBusyRef.current = null;
      setJsonDownloadBusy(null);
    }
  };

  const downloadOriginalJson = async (language: 'jp' | 'cn') => {
    const sourceIndex = selectedJsonSource?.[
      language === 'jp' ? 'jpIndex' : 'cnIndex'
    ];
    if (
      !selectedJsonSource ||
      sourceIndex === undefined ||
      !currentStory
    ) {
      setEditMessage(
        language === 'jp'
          ? '选中的 Section 没有日文原始 JSON。'
          : '选中的 Section 没有中文原始 JSON。',
      );
      return;
    }
    await runJsonDownload(language, async () => {
      const sourceJson = await fetchScenarioJson(language, sourceIndex);
      const download = createOriginalScenarioJsonDownload({
        sourceJson,
        sourceFilename: selectedJsonSource.filename,
        storyId:
          `${currentStory.id}_`
          + selectedJsonSource.filename.replace(/\.json$/iu, ''),
        language,
      });
      triggerScenarioJsonDownload(download);
      return `已生成 ${selectedJsonSource.filename} 的`
        + `${language === 'jp' ? '日文' : '中文'}原始 JSON。`;
    });
  };

  const downloadEditedJson = async () => {
    if (!selectedJsonSource || !currentStory) {
      setEditMessage('当前剧情没有可生成的 JSON 来源。');
      return;
    }
    if (editedCnLines.length === 0) {
      setEditMessage('请先初始化或上传中文编辑内容。');
      return;
    }
    const sourceLanguage: 'cn' | 'jp' | null =
      selectedJsonSource.cnIndex !== undefined
        ? 'cn'
        : selectedJsonSource.jpIndex !== undefined
          ? 'jp'
          : null;
    if (!sourceLanguage) {
      setEditMessage('选中的 Section 没有日文或中文结构 JSON。');
      return;
    }
    const sourceIndex =
      sourceLanguage === 'cn'
        ? selectedJsonSource.cnIndex
        : selectedJsonSource.jpIndex;
    if (sourceIndex === undefined) return;

    await runJsonDownload('edited', async () => {
      const sourceJson = await fetchScenarioJson(
        sourceLanguage,
        sourceIndex,
      );
      const generalVoice =
        currentStory.source_format === 'general_voice_json';
      let download;
      if (generalVoice) {
        download = createEditedScenarioJsonDownload({
          sourceJson,
          sourceFilename: selectedJsonSource.filename,
          storyId:
            `${currentStory.id}_`
            + selectedJsonSource.filename.replace(/\.json$/iu, ''),
          baselineLines: cnEventLines,
          editedLines: editedCnLines,
        });
      } else {
        const editingBaselineLines =
          cnEventLines.length > 0 ? cnEventLines : jpEventLines;
        const sourceBaselineLines =
          sourceLanguage === 'cn' ? cnEventLines : jpEventLines;
        if (
          editingBaselineLines.length === 0 ||
          sourceBaselineLines.length === 0
        ) {
          throw new Error('当前缺少可验证的逐事件 TXT 基准。');
        }
        const mapped = mapAggregateEditsToScenarioJson({
          sourceJson,
          sourceFilename: selectedJsonSource.filename,
          aggregateSourceBaselineLines: sourceBaselineLines,
          aggregateEditingBaselineLines: editingBaselineLines,
          aggregateEditedLines: editedCnLines,
        });
        download = createEditedScenarioJsonDownload({
          sourceJson,
          sourceFilename: selectedJsonSource.filename,
          storyId:
            `${currentStory.id}_`
            + selectedJsonSource.filename.replace(/\.json$/iu, ''),
          editedLines: mapped.editedLines,
        });
      }
      triggerScenarioJsonDownload(download);
      return sourceLanguage === 'cn'
        ? `已按中文结构生成可播放编辑 JSON；仅改动 ${download.changedTextFields} 个文本字段。`
        : `该 Section 没有中文 JSON；已明确使用日文 JSON 作为结构模板，`
          + `并用当前中文编辑行生成可播放 JSON。仅改动 `
          + `${download.changedTextFields} 个文本字段。`;
    });
  };

  const uploadTranslation = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    try {
      const source = await readScenarioFile(file);
      const parsed = parseStoryContent(source.raw, {
        filename: source.name,
        mergeConsecutiveTextLines: false,
      });
      if (parsed.lines.length === 0) throw new Error('文件中没有可编辑的剧情文本。');
      if (
        !isLocal &&
        (parsed.format === 'magireco-json' ||
          parsed.format === 'exedra-json')
      ) {
        if (!selectedJsonSource || !currentStory) {
          throw new Error(
            '请先在“来源 JSON”中选择该文件对应的 Section。',
          );
        }
        const sourceLanguage: 'cn' | 'jp' | null =
          selectedJsonSource.cnIndex !== undefined
            ? 'cn'
            : selectedJsonSource.jpIndex !== undefined
              ? 'jp'
              : null;
        const sourceIndex =
          sourceLanguage === 'cn'
            ? selectedJsonSource.cnIndex
            : selectedJsonSource.jpIndex;
        if (!sourceLanguage || sourceIndex === undefined) {
          throw new Error('选中的 Section 没有结构 JSON。');
        }
        const sourceJson = await fetchScenarioJson(
          sourceLanguage,
          sourceIndex,
        );
        const editingBaselineLines =
          cnEventLines.length > 0 ? cnEventLines : jpEventLines;
        const next = applyScenarioJsonUploadToAggregate({
          sourceJson,
          uploadedJson: source.raw,
          sourceFilename: selectedJsonSource.filename,
          aggregateEditingBaselineLines: editingBaselineLines,
          aggregateCurrentEditedLines: editedCnLines,
        });
        setEditedCnLines(next);
        setMode(jpEventLines.length > 0 ? 'split' : 'cn');
        setEditMessage(
          `已从 ${file.name} 导入 ${selectedJsonSource.label} 的逐事件文本；`
          + '上传文件的动作、资源和其他播放字段不会直接写入。',
        );
        return;
      }
      const normalized = seedEditableLines(
        parsed.lines,
        jpEventLines,
        'current',
      );
      setEditedCnLines(normalized.length > 0 ? normalized : parsed.lines);
      setParseWarnings(previous => [...previous, ...parsed.warnings]);
      setEditMessage(`已载入 ${file.name}（${FORMAT_LABELS[parsed.format]}）。`);
    } catch (error) {
      setEditMessage(error instanceof Error ? error.message : '文件读取失败。');
    }
  };

  const handleTurnstileToken = useCallback((token: string) => {
    setTurnstileToken(token);
    if (token) setEditMessage('');
  }, []);

  const handleTurnstileError = useCallback((message: string) => {
    setTurnstileToken('');
    setEditMessage(message);
  }, []);

  const submitToCloud = async () => {
    if (!currentStory) {
      setEditMessage('剧情目录尚未确认当前编号，暂不能在线提交。');
      return;
    }
    if (editedCnLines.length === 0) {
      setEditMessage('请先初始化或上传翻译内容。');
      return;
    }
    if (!proofreadingConfig?.submissions_enabled) {
      setEditMessage('投稿服务尚未启用；请先下载当前进度作为备份。');
      return;
    }
    if (!storyIndexSha256 || !currentStory.source_identity) {
      setEditMessage('剧情版本信息尚未准备完成，请稍后重试。');
      return;
    }
    if (!turnstileToken) {
      setEditMessage('请先完成人机验证。');
      return;
    }

    const content = normalizeProofreadingText(
      editedCnLines.map(serializeStoryLine).join('\n'),
    );
    if (content.trim().length < 10) {
      setEditMessage('内容过短，请编辑后再提交。');
      return;
    }

    setSubmittingProofreading(true);
    setLastSubmissionId('');
    try {
      const [baseSha256, baseContentSha256] = await Promise.all([
        sha256Text(cnSource?.raw ?? ''),
        sha256Text(normalizeProofreadingText(
          cnLines.map(serializeStoryLine).join('\n'),
        )),
      ]);
      const response = await fetch('/api/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          story_id: currentStory.id,
          content,
          nickname: proofreadingNickname,
          note: proofreadingNote,
          base_sha256: baseSha256,
          base_content_sha256: baseContentSha256,
          catalog_sha256: storyIndexSha256,
          source_path_cn: currentStory.path_cn || '',
          source_path_jp: currentStory.path_jp || '',
          source_identity: currentStory.source_identity,
          turnstile_token: turnstileToken,
        }),
      });
      const responseText = await response.text();
      let data: {
        success?: boolean;
        id?: string;
        receipt?: string;
        status?: string;
        error?: string;
      } = {};
      try {
        data = JSON.parse(responseText) as typeof data;
      } catch {
        // Keep a generic error without exposing server internals.
      }
      if (!response.ok || !data.success || !data.id || !data.receipt) {
        throw new Error(data.error || `提交服务暂不可用（HTTP ${response.status}）`);
      }
      const nickname = proofreadingNickname.trim() || '匿名校对者';
      saveProofreadingReceipt({
        id: data.id,
        receipt: data.receipt,
        storyId: currentStory.id,
        nickname,
        submittedAt: new Date().toISOString(),
      });
      setLastSubmissionId(data.id);
      setEditMessage(`提交成功，审核编号：${data.id}`);
      setTurnstileToken('');
      setTurnstileResetKey((value) => value + 1);
    } catch (error) {
      setEditMessage(
        `${error instanceof Error ? error.message : '在线提交失败'}；已自动下载备份文件。`,
      );
      triggerUtf8Download(content, `${currentStory.id}_submit.txt`);
      setTurnstileToken('');
      setTurnstileResetKey((value) => value + 1);
    } finally {
      setSubmittingProofreading(false);
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
    let targetIndex = exactId
      ? renderList.findIndex(row => {
          const header = row.cn?.isHeader ? row.cn : row.jp?.isHeader ? row.jp : undefined;
          return header?.headerId === exactId;
        })
      : -1;
    if (targetIndex < 0) {
      const fallbackOffset = renderList.slice(rowIndex + 1).findIndex(row => {
        const header = row.cn?.isHeader ? row.cn : row.jp?.isHeader ? row.jp : undefined;
        return header?.headerBranch === choice.choiceTargetId;
      });
      if (fallbackOffset >= 0) targetIndex = rowIndex + 1 + fallbackOffset;
    }
    revealRow(targetIndex, true);
  };

  if (loading) {
    return (
      <div className="flex h-screen h-[100dvh] items-center justify-center opacity-60">
        正在读取剧情…
      </div>
    );
  }

  const hasChineseDisplay =
    cnLines.length > 0 || (isEditMode && editedCnLines.length > 0);
  const hasJapaneseDisplay = jpLines.length > 0;
  const modeAvailability: Record<ReaderMode, boolean> = {
    cn: hasChineseDisplay,
    split: hasChineseDisplay && hasJapaneseDisplay,
    jp: hasJapaneseDisplay,
  };
  const generalVoiceHasNoTrustedJapaneseColumn =
    currentStory?.category === 'general_voice' &&
    hasChineseDisplay &&
    !hasJapaneseDisplay &&
    !loadError;

  return (
    <div className={`flex h-screen h-[100dvh] overflow-hidden ${THEME_STYLES[theme]}`}>
      <Sidebar
        stories={allStories}
        currentId={currentStory?.id ?? id}
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
              <span
                lang={isExedraStory && mode === 'jp' ? 'ja' : undefined}
                className={`${isExedraStory && mode === 'jp' ? 'exedra-page ' : ''}truncate text-[10px] opacity-50 ${
                mode === 'jp' && hasJapaneseDisplay
                  ? 'reader-font-jp-title'
                  : 'reader-font-cn-title'
              }`}
              >
                {isLocal ? '本地文件' : currentStory?.folder || '剧情阅读器'}
                {storyTitle ? ` · ${storyTitle}` : ''}
              </span>
              <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm font-bold">
                <span className="truncate font-mono text-emerald-600">{id}</span>
                {currentStory?.official_tw && (
                  <span
                    className="rounded-full border border-stone-400/35 bg-stone-200/35 px-2 py-0.5 text-[10px] font-medium tracking-wide text-stone-600 dark:border-stone-500/40 dark:bg-stone-700/35 dark:text-stone-300"
                    title="中文正文来自 Magia Exedra 台服官方文本，并已转换为简体中文"
                  >
                    {currentStory.official_tw_label || '台服'}
                  </span>
                )}
                {cnSource && (
                  <button
                    type="button"
                    title={`下载原始文件（${FORMAT_LABELS[cnSource.format]}）`}
                    onClick={() => triggerUtf8Download(
                      cnSource.raw,
                      sourceDownloadName(id, 'cn', cnSource),
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
                    onClick={() => triggerUtf8Download(
                      jpSource.raw,
                      sourceDownloadName(id, 'jp', jpSource),
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
                  disabled={!modeAvailability[nextMode]}
                  title={
                    modeAvailability[nextMode]
                      ? undefined
                      : nextMode === 'cn'
                        ? '当前没有可显示的中文文本'
                        : '当前没有可逐行证明的日文文本'
                  }
                  aria-label={
                    nextMode === 'cn'
                      ? '只显示中文'
                      : nextMode === 'jp'
                        ? '只显示日文'
                        : '显示中日双语'
                  }
                  aria-pressed={mode === nextMode}
                  onClick={() => {
                    if (modeAvailability[nextMode]) setMode(nextMode);
                  }}
                  className={`rounded px-2 py-1 ${
                    mode === nextMode
                      ? theme === 'dark' ? 'bg-gray-700 text-white' : 'bg-white shadow'
                      : 'opacity-40'
                  } ${
                    modeAvailability[nextMode]
                      ? ''
                      : 'cursor-not-allowed opacity-20'
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
          <div
            className={`mx-auto min-h-screen w-full min-w-0 rounded-lg pb-32 transition-all duration-500 ease-in-out ${
            theme === 'paper' || theme === 'green'
              ? 'md:bg-white/40 md:px-12 md:py-8 md:shadow-sm md:backdrop-blur-[2px]'
              : ''
            }`}
            style={{ maxWidth: `${readerDisplayPreferences.textWidthPx}px` }}
          >
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

            {generalVoiceHasNoTrustedJapaneseColumn && (
              <div className="mb-4 rounded-lg border border-sky-200 bg-sky-50/80 p-3 text-xs text-sky-900">
                这是魔法纪录语音资料。现有上游没有独立且完整、可逐行证明的日文字幕列，
                因此本站保留人工中文和语音编号，但不会伪造日文对照。Exedra 语音在存在
                可信中文时仍使用真实的中日对照。
              </div>
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
                    下载当前进度（UTF-8）
                  </button>
                </div>

                <div
                  data-scenario-json-tools="true"
                  className="mt-4 rounded-xl border border-sky-200 bg-sky-50/80 p-3 text-sky-950"
                >
                  <div className="flex flex-col gap-3">
                    <label className="text-xs font-bold">
                      来源 JSON（按 Section）
                      <select
                        aria-label="选择要下载或生成的来源 JSON"
                        value={selectedJsonSource?.key ?? ''}
                        onChange={event =>
                          setSelectedJsonSourceKey(event.target.value)
                        }
                        disabled={
                          jsonSourceOptionsState.options.length === 0 ||
                          jsonDownloadBusy !== null
                        }
                        className="mt-1 min-h-11 w-full rounded-lg border border-sky-200 bg-white px-3 py-2 font-normal text-gray-900 outline-none focus:border-sky-500 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {jsonSourceOptionsState.options.length === 0 ? (
                          <option value="">当前剧情没有 JSON 来源清单</option>
                        ) : (
                          jsonSourceOptionsState.options.map(option => (
                            <option key={option.key} value={option.key}>
                              {option.label}
                            </option>
                          ))
                        )}
                      </select>
                    </label>

                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                      <button
                        type="button"
                        onClick={() => void downloadOriginalJson('jp')}
                        disabled={
                          jsonDownloadBusy !== null ||
                          selectedJsonSource?.jpIndex === undefined
                        }
                        className="min-h-11 rounded-lg border border-blue-300 bg-white px-3 py-2 text-xs font-bold text-blue-700 shadow-sm hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {jsonDownloadBusy === 'jp'
                          ? '读取日文 JSON…'
                          : '下载日文原始 JSON'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void downloadOriginalJson('cn')}
                        disabled={
                          jsonDownloadBusy !== null ||
                          selectedJsonSource?.cnIndex === undefined
                        }
                        className="min-h-11 rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-bold text-emerald-700 shadow-sm hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {jsonDownloadBusy === 'cn'
                          ? '读取中文 JSON…'
                          : '下载中文原始 JSON'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void downloadEditedJson()}
                        disabled={
                          jsonDownloadBusy !== null ||
                          !selectedJsonSource ||
                          (
                            selectedJsonSource.cnIndex === undefined &&
                            selectedJsonSource.jpIndex === undefined
                          ) ||
                          editedCnLines.length === 0
                        }
                        className="min-h-11 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-bold text-white shadow hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {jsonDownloadBusy === 'edited'
                          ? '校验并生成 JSON…'
                          : '下载本次编辑 JSON'}
                      </button>
                    </div>
                  </div>

                  {jsonSourceOptionsState.error ? (
                    <p className="mt-2 text-xs font-bold text-red-700">
                      {jsonSourceOptionsState.error}
                    </p>
                  ) : selectedJsonSource?.cnIndex === undefined &&
                    selectedJsonSource?.jpIndex !== undefined ? (
                      <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-900">
                        此 Section 没有中文源 JSON。生成编辑 JSON 时会明确使用日文
                        JSON 作为结构模板，只把当前中文逐事件写入允许的文本字段；
                        事件数量、动作、分支或位置不一致时会停止。
                      </p>
                    ) : (
                      <p className="mt-2 text-[11px] text-sky-800/80">
                        编辑 JSON 优先使用中文结构源；生成前会逐事件校验，且不会改动
                        动作、资源、分支、位置或其他播放字段。
                      </p>
                    )}
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <label className="text-xs font-bold text-emerald-900">
                    昵称（可选）
                    <input
                      type="text"
                      maxLength={40}
                      value={proofreadingNickname}
                      onChange={(event) => setProofreadingNickname(event.target.value)}
                      placeholder="匿名校对者"
                      className="mt-1 w-full rounded-lg border border-emerald-200 bg-white px-3 py-2 font-normal outline-none focus:border-emerald-500"
                    />
                  </label>
                  <label className="text-xs font-bold text-emerald-900">
                    修改说明（可选）
                    <textarea
                      maxLength={1_000}
                      rows={2}
                      value={proofreadingNote}
                      onChange={(event) => setProofreadingNote(event.target.value)}
                      placeholder="例如：修正角色口吻、专有名词或错字"
                      className="mt-1 w-full resize-y rounded-lg border border-emerald-200 bg-white px-3 py-2 font-normal outline-none focus:border-emerald-500"
                    />
                  </label>
                </div>

                <div className="mt-3 rounded-lg border border-emerald-200 bg-white/70 p-3">
                  {proofreadingConfigLoading ? (
                    <p className="text-xs text-emerald-800">正在连接投稿服务…</p>
                  ) : proofreadingConfig?.submissions_enabled && proofreadingConfig.turnstile_site_key ? (
                    <>
                      {proofreadingConfig.turnstile_test_mode && (
                        <p className="mb-2 rounded bg-amber-50 px-2 py-1 text-[10px] text-amber-800">
                          当前检查站使用 Cloudflare 测试验证密钥，仅用于功能验收；正式开放前必须换成真实 Turnstile 密钥。
                        </p>
                      )}
                      <TurnstileWidget
                        siteKey={proofreadingConfig.turnstile_site_key}
                        theme={theme}
                        resetKey={turnstileResetKey}
                        onToken={handleTurnstileToken}
                        onError={handleTurnstileError}
                      />
                      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                        <p className="text-[10px] text-emerald-700/70">
                          投稿会记录当前剧情目录哈希和中文源文件哈希；源文本更新后，旧投稿不会被自动覆盖。
                        </p>
                        <button
                          type="button"
                          onClick={() => void submitToCloud()}
                          disabled={!turnstileToken || submittingProofreading}
                          className="rounded-lg bg-purple-600 px-4 py-2 text-xs font-bold text-white shadow hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          {submittingProofreading ? '正在提交…' : '提交审核'}
                        </button>
                      </div>
                    </>
                  ) : (
                    <p className="text-xs text-amber-800">
                      投稿服务尚未配置。你仍可下载 TXT，并将文件交给项目维护者。
                    </p>
                  )}
                </div>

                <p className="mt-2 text-[10px] text-emerald-700/70">
                  编辑模式保留未合并的逐事件行；标题、分支、位置与动作信息不会被
                  TXT 或 JSON 下载改写。请定期下载 TXT 备份。
                </p>
                {editMessage && (
                  <p role="status" className="mt-2 rounded bg-white/70 px-2 py-1 text-xs text-emerald-900">
                    {editMessage}
                    {lastSubmissionId && (
                      <>
                        {' '}
                        <Link href="/proofreading/status" className="font-bold text-blue-700 underline">
                          查看审核状态
                        </Link>
                      </>
                    )}
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

            {!loadError && renderList.length > 0 && (
              <StoryPagination
                page={visiblePage}
                pageCount={pageCount}
                start={pageStart}
                end={Math.min(pageStart + visibleRenderList.length, renderList.length)}
                total={renderList.length}
                onPage={changeVisiblePage}
              />
            )}

            {!loadError && visibleRenderList.map((row, offset) => {
              const index = pageStart + offset;
              return (
                <StoryRow
                  key={index}
                  row={row}
                  index={index}
                  editIndex={row.cn ? (editedLineIndices.get(row.cn) ?? index) : index}
                  mode={mode}
                  bilingualLayout={bilingualLayout}
                  showLineBreaks={readerDisplayPreferences.showLineBreaks}
                  theme={theme}
                   isExedra={isExedraStory}
                   officialSectionTitles={currentStory?.official_tw_section_titles}
                  isEditMode={isEditMode}
                  editedLines={editedCnLines}
                  setEditedLines={setEditedCnLines}
                  query={deferredSearchQuery}
                  normalizedQuery={normalizedQuery}
                  focused={currentMatchIndex >= 0 && matchedIndices[currentMatchIndex] === index}
                  onChoice={jumpToChoice}
                />
              );
            })}

            {!loadError && renderList.length > STORY_ROWS_PER_PAGE && (
              <StoryPagination
                page={visiblePage}
                pageCount={pageCount}
                start={pageStart}
                end={Math.min(pageStart + visibleRenderList.length, renderList.length)}
                total={renderList.length}
                onPage={changeVisiblePage}
              />
            )}
          </div>
        </main>

        <FloatingWindow
          isOpen={showSettings}
          onClose={() => setShowSettings(false)}
          theme={theme}
          title="阅读设置"
          titleId="reader-settings-title"
          systemLabel="SYS://READER.CONFIG"
          initialOffset={{ x: 38, y: 28 }}
          className="magi-settings-window"
          bodyClassName="p-5"
        >
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
                  <span className="mb-1 block opacity-70">
                    正文横向宽度（{readerDisplayPreferences.textWidthPx}px）
                  </span>
                  <input
                    type="range"
                    min={READER_TEXT_WIDTH_MIN}
                    max={READER_TEXT_WIDTH_MAX}
                    step={READER_TEXT_WIDTH_STEP}
                    value={readerDisplayPreferences.textWidthPx}
                    aria-valuetext={`${readerDisplayPreferences.textWidthPx} 像素`}
                    onChange={event =>
                      updateReaderDisplayPreferences({
                        textWidthPx: Number(event.target.value),
                      })
                    }
                    className="w-full"
                  />
                  <span className="mt-1 block text-[11px] opacity-60">
                    同时作用于阅读和汉化输入；手机端自动限制为屏幕可用宽度。
                  </span>
                </label>
                <ReaderFontSettings theme={theme} isExedra={isExedraStory} />
                <div>
                  <p className="mb-2 opacity-70">中日对照排列</p>
                  <div className="grid grid-cols-2 gap-2">
                    {([
                      ['side-by-side', '左右排列'],
                      ['stacked', '上下排列'],
                    ] as const).map(([key, label]) => (
                      <button
                        type="button"
                        key={key}
                        aria-pressed={bilingualLayout === key}
                        onClick={() => changeBilingualLayout(key)}
                        className={`rounded border px-2 py-2 text-xs font-bold ${
                          bilingualLayout === key
                            ? 'border-blue-500 bg-blue-500/10 text-blue-600'
                            : 'border-current opacity-60'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <p className="mt-1 text-[11px] opacity-60">
                    手机端始终采用上下排列以避免挤压；此选项控制电脑端的左右或上下排列，
                    并同样适用于汉化输入框。
                  </p>
                </div>
                <label className="block">
                  <span className="mb-1 block opacity-70">行高（{lineHeight}）</span>
                  <input type="range" min="1.1" max="2" step="0.1" value={lineHeight} onChange={event => setLineHeight(Number(event.target.value))} className="w-full" />
                </label>
                <label className={`flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-lg border px-3 py-2 ${
                  theme === 'dark'
                    ? 'border-gray-700 bg-white/5'
                    : 'border-gray-200 bg-black/[0.02]'
                }`}>
                  <span>
                    <span className="block font-bold">
                      显示换行符 <span aria-hidden="true" className="text-fuchsia-500">↵</span>
                    </span>
                    <span className="block text-[11px] opacity-60">
                      仅作视觉提示，不会写入翻译或下载文件。
                    </span>
                  </span>
                  <input
                    type="checkbox"
                    checked={readerDisplayPreferences.showLineBreaks}
                    onChange={event =>
                      updateReaderDisplayPreferences({
                        showLineBreaks: event.target.checked,
                      })
                    }
                    className="h-5 w-5 shrink-0 accent-fuchsia-600"
                  />
                </label>
              </div>
        </FloatingWindow>
      </div>

      <AboutModal isOpen={aboutOpen} onClose={() => setAboutOpen(false)} theme={theme} />
    </div>
  );
}

type StoryPaginationProps = {
  page: number;
  pageCount: number;
  start: number;
  end: number;
  total: number;
  onPage: (page: number) => void;
};

function StoryPagination({
  page,
  pageCount,
  start,
  end,
  total,
  onPage,
}: StoryPaginationProps) {
  if (pageCount <= 1) return null;

  return (
    <nav
      aria-label="剧情分页"
      className="my-4 flex flex-wrap items-center justify-center gap-3 rounded-xl border border-black/10 bg-white/50 px-3 py-2 text-xs shadow-sm"
    >
      <button
        type="button"
        disabled={page <= 0}
        onClick={() => onPage(Math.max(0, page - 1))}
        className="rounded-lg border border-current px-3 py-1.5 font-bold disabled:cursor-not-allowed disabled:opacity-30"
      >
        ← 上一页
      </button>
      <span aria-live="polite" className="tabular-nums opacity-75">
        第 {page + 1} / {pageCount} 页 · 第 {start + 1}–{end} 行，共 {total} 行
      </span>
      <button
        type="button"
        disabled={page >= pageCount - 1}
        onClick={() => onPage(Math.min(pageCount - 1, page + 1))}
        className="rounded-lg border border-current px-3 py-1.5 font-bold disabled:cursor-not-allowed disabled:opacity-30"
      >
        下一页 →
      </button>
    </nav>
  );
}

type StoryRowProps = {
  row: AlignedStoryLine;
  index: number;
  editIndex: number;
  mode: ReaderMode;
  bilingualLayout: BilingualLayout;
  showLineBreaks: boolean;
  theme: string;
  isExedra: boolean;
  officialSectionTitles?: string[];
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
  bilingualLayout,
  showLineBreaks,
  theme,
  isExedra,
  officialSectionTitles,
  isEditMode,
  editedLines,
  setEditedLines,
  query,
  normalizedQuery,
  focused,
  onChoice,
}: StoryRowProps) {
  const header = mode === 'jp'
    ? row.jp?.isHeader
      ? row.jp
      : row.cn?.isHeader
        ? row.cn
        : undefined
    : row.cn?.isHeader
      ? row.cn
      : row.jp?.isHeader
        ? row.jp
        : undefined;
  if (header) {
    const headerText = header.text.replace(/---/g, '').trim();
    const isBranch = Boolean(header.headerBranch);
    const displayedHeaderText = isBranch
      ? headerText
      : resolveOfficialSectionTitle(
          officialSectionTitles,
          header.headerSection,
          headerText,
        );
    return (
      <div
        id={header.headerId}
        lang={isExedra ? (header === row.jp ? 'ja' : 'zh-Hans') : undefined}
        className={`mb-4 mt-6 border-t-2 pt-4 text-center ${
          isExedra ? 'exedra-page ' : ''
        }${
          header === row.jp
            ? 'reader-font-jp-title'
            : 'reader-font-cn-title'
        } ${
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
            {displayedHeaderText}
          </span>
        )}
      </div>
    );
  }

  const choice = mode === 'jp'
    ? row.jp?.isChoice
      ? row.jp
      : row.cn?.isChoice
        ? row.cn
        : undefined
    : row.cn?.isChoice
      ? row.cn
      : row.jp?.isChoice
        ? row.jp
        : undefined;
  if (choice) {
    const editableChoice = editedLines[editIndex];
    return (
      <div id={`line-${index}`} className="my-3 flex justify-center">
        {isEditMode ? (
          <label className="reader-font-cn-title flex w-full max-w-xl items-center gap-2 rounded-xl border-2 border-amber-300 bg-amber-50 p-2 text-xs font-bold text-amber-900">
            选项
            <input
              aria-label={`第 ${index + 1} 行选项文本`}
              className="reader-font-cn-title min-w-0 flex-1 rounded border border-amber-200 bg-white px-2 py-1.5 font-normal text-black outline-none focus:ring-2 focus:ring-amber-400"
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
            lang={isExedra && choice === row.jp ? 'ja' : undefined}
            onClick={() => onChoice(index, choice)}
            className={`${isExedra && choice === row.jp ? 'exedra-page ' : ''}${choice === row.jp ? 'reader-font-jp-title' : 'reader-font-cn-title'} cursor-pointer rounded-xl border-2 px-5 py-2.5 text-sm font-bold transition hover:scale-105 active:scale-95 ${
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
  const audioCueId = row.cn?.audioCueId || row.jp?.audioCueId;
  const editedText = editedLines[editIndex]?.text || '';
  const editedLineBreakCount = showLineBreaks
    ? countLineBreaks(editedText)
    : 0;
  const lineBreakDescriptionId = `line-${index}-line-break-description`;

  return (
    <div
      id={`line-${index}`}
      className={`group flex transition-colors ${bilingualStoryPairClass(
        mode,
        bilingualLayout,
      )} ${
        focused
          ? theme === 'dark'
            ? 'bg-blue-900/30 ring-1 ring-blue-500/50'
            : 'bg-yellow-50 ring-1 ring-yellow-400/50'
          : 'hover:border-current hover:border-opacity-10'
      }`}
    >
      {mode !== 'jp' && (
        <div
          lang={isExedra ? 'zh-Hans' : undefined}
          className={`reader-font-cn-body ${isExedra ? 'exedra-page ' : ''}flex min-w-0 gap-3 ${
            mode === 'split' && bilingualLayout === 'side-by-side'
              ? 'md:w-1/2'
              : 'w-full'
          }`}
        >
          {audioCueId && (
            <VoicePlayButton
              cueId={audioCueId}
              label="播放"
              className="shrink-0 px-2"
            />
          )}
          {isEditMode ? (
            <>
              <input
                aria-label={`第 ${index + 1} 行角色名`}
                className={`reader-font-cn-title w-20 flex-shrink-0 rounded border px-1 py-1 text-right text-[11px] font-bold leading-tight outline-none focus:ring-2 focus:ring-emerald-500 md:w-24 ${
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
              <div className="relative min-w-0 flex-1">
                <textarea
                  aria-label={`第 ${index + 1} 行翻译`}
                  aria-describedby={
                    editedLineBreakCount > 0
                      ? lineBreakDescriptionId
                      : undefined
                  }
                  className={`reader-font-cn-body relative z-0 block w-full rounded border p-2 font-sans text-sm outline-none transition focus:ring-2 focus:ring-emerald-500 ${
                    theme === 'dark'
                      ? 'border-gray-700 bg-gray-800 text-white'
                      : 'border-gray-200 bg-white text-black'
                  }`}
                  value={editedText}
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
                  onScroll={event => {
                    const overlay = event.currentTarget.nextElementSibling;
                    if (
                      overlay instanceof HTMLElement &&
                      overlay.dataset.lineBreakOverlay === 'true'
                    ) {
                      overlay.scrollTop = event.currentTarget.scrollTop;
                      overlay.scrollLeft = event.currentTarget.scrollLeft;
                    }
                  }}
                  rows={Math.max(1, editedText.split('\n').length)}
                />
                {editedLineBreakCount > 0 && (
                  <>
                    <div
                      aria-hidden="true"
                      data-line-break-overlay="true"
                      className="reader-font-cn-body pointer-events-none absolute inset-0 z-10 select-none overflow-hidden whitespace-pre-wrap break-words rounded border border-transparent p-2 font-sans text-sm"
                    >
                      <LineBreakMarkerText text={editedText} markerOnly />
                    </div>
                    <span id={lineBreakDescriptionId} className="sr-only">
                      此输入框含 {editedLineBreakCount} 个手动换行符，视觉上以箭头标记。
                    </span>
                  </>
                )}
              </div>
            </>
          ) : row.cn ? (
            <>
              <SpeakerLabel line={row.cn} highlighted={cnSpeakerMatches} language="cn" />
              <div className={`min-w-0 flex-1 break-words whitespace-pre-wrap pt-0.5 ${lineTextAlignClass(row.cn)} ${lineKindClass(row.cn)}`}>
                <StoryText
                  text={row.cn.text}
                  query={query}
                  theme={theme}
                  showLineBreaks={showLineBreaks}
                />
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
        <div
          lang={isExedra ? 'ja' : undefined}
          className={`reader-font-jp-body ${isExedra ? 'exedra-page ' : ''}flex min-w-0 gap-2 ${bilingualLanguagePaneClass(
            mode,
            bilingualLayout,
            'jp',
          )}`}
        >
          {mode === 'jp' && audioCueId && (
            <VoicePlayButton
              cueId={audioCueId}
              label="播放"
              className="shrink-0 px-2"
            />
          )}
          {row.jp ? (
            <>
              <SpeakerLabel line={row.jp} highlighted={jpSpeakerMatches} faded language="jp" />
              <div className={`exedra-jp-story-text min-w-0 flex-1 break-words whitespace-pre-wrap font-sans text-sm opacity-70 ${lineTextAlignClass(row.jp)} ${lineKindClass(row.jp)}`}>
                <StoryText
                  text={row.jp.text}
                  query={query}
                  theme={theme}
                  showLineBreaks={showLineBreaks}
                />
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
  language,
}: {
  line: StoryLine;
  highlighted: boolean;
  faded?: boolean;
  language: 'cn' | 'jp';
}) {
  return (
    <div
      className={`${language === 'cn' ? 'reader-font-cn-title' : 'reader-font-jp-title'} h-fit w-20 flex-shrink-0 break-words rounded px-1 pt-1 text-right text-[11px] font-bold leading-tight md:w-24 ${
        highlighted ? 'ring-2 ring-yellow-400' : faded ? 'opacity-50' : ''
      }`}
      style={{ color: speakerColor(line.speaker) }}
    >
      {line.speaker}
    </div>
  );
}
