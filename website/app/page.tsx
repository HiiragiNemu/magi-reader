"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useId,
  useState,
  useSyncExternalStore,
  type ComponentType,
} from 'react';
import Link from 'next/link';
import {
  Search,
  Book,
  Layers,
  User,
  Calendar,
  Folder,
  FileText,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Sun,
  Moon,
  BookOpen,
  Leaf,
} from 'lucide-react';
import { useGlobal } from '@/app/providers';
import { characterFolderColorFor } from '@/app/config/dictionary';
import { type Story } from '@/components/Sidebar';
import AboutModal from '@/components/AboutModal';
import LocalStoryPicker from '@/components/LocalStoryPicker';
import { normalizeSearchText } from '@/lib/search';
import { loadStoryIndex } from '@/lib/story-index';
import { categoryOrder } from '@/lib/category-order';
import {
  getMachineReviewPanelServerSnapshot,
  getMachineReviewPanelSnapshot,
  setMachineReviewPanelCollapsedPreference,
  subscribeMachineReviewPanel,
} from '@/lib/machine-review-panel';

type SearchMode = 'all' | 'title' | 'content';
type StorySystem = 'magireco' | 'exedra';

type StoryGroup = {
  key: string;
  category: string;
  folderName: string;
  items: Story[];
  totalCn: number;
  matchSnippets?: Record<string, string>;
};

type CategoryConfig = {
  label: string;
  icon: ComponentType<{ size?: number }>;
};

type SearchWorkerMessage =
  | { type: 'status'; status: 'loading' | 'ready' }
  | { type: 'results'; sequence: number; matches: Array<[string, string]>; truncated: boolean }
  | { type: 'error'; sequence: number; message: string };

type SearchIndexChunk = {
  bytes: number;
  sha256: string;
};

type SearchIndexManifestV1 = {
  version: 1;
  sha256: string;
  bytes: number;
  entries: number;
  object_key: string;
  story_index_sha256: string;
};

type SearchIndexManifestV2 = Omit<SearchIndexManifestV1, 'version'> & {
  version: 2;
  chunk_bytes: number;
  chunks: SearchIndexChunk[];
};

type SearchIndexManifest = SearchIndexManifestV1 | SearchIndexManifestV2;

type SearchIndexSource = Pick<
  SearchIndexManifestV1,
  'sha256' | 'bytes' | 'entries'
> & {
  url: string;
  version: 1 | 2;
  chunk_bytes?: number;
  chunks?: SearchIndexChunk[];
};

type ProofreadingStatus = {
  total: number;
  verified: number;
  remaining: number;
  machine_translation_ids: string[];
  verified_ids: string[];
};

const CATEGORY_CONFIG: Record<string, CategoryConfig> = {
  main_story: { label: '主线', icon: Book },
  event_story: { label: '活动', icon: Calendar },
  character_story: { label: '角色', icon: User },
  costume_story: { label: '服装', icon: Layers },
  login_story: { label: '登录', icon: FileText },
  mirror_story: { label: '镜层', icon: Folder },
  scene0_main: { label: 'S0主线', icon: Book },
  scene0_sub: { label: 'S0支线', icon: User },
  exedra_main: { label: '主线', icon: Book },
  exedra_sub: { label: '活动', icon: Layers },
  exedra_character: { label: '角色', icon: User },
  exedra_portrait: { label: '肖像', icon: User },
  exedra_reaction: { label: '语音', icon: FileText },
  exedra_namae: { label: 'Namae', icon: Folder },
  exedra_dungeon: { label: '过场动画字幕', icon: Layers },
  exedra_battle: { label: '战斗', icon: Folder },
  Unclassified: { label: '其他', icon: Folder },
};

const EXEDRA_CATEGORIES = [
  'exedra_main',
  'exedra_sub',
  'exedra_character',
  'exedra_portrait',
  'exedra_reaction',
  'exedra_namae',
  'exedra_dungeon',
  'exedra_battle',
] as const;
const EXEDRA_CATEGORY_SET = new Set<string>(EXEDRA_CATEGORIES);
const DEFAULT_CATEGORY: Record<StorySystem, string> = {
  magireco: 'main_story',
  exedra: 'exedra_main',
};
const NATURAL_COLLATOR = new Intl.Collator(['zh-CN', 'ja-JP'], {
  numeric: true,
  sensitivity: 'base',
});

const isExedraCategory = (category: string): boolean =>
  EXEDRA_CATEGORY_SET.has(category);

const SEARCH_INDEX_MANIFEST_URL = '/search_index_manifest.json';
const SEARCH_INDEX_LOCAL_FALLBACK_URL = '/search_content.json';
const SEARCH_INDEX_CLOUDFLARE_BASE_URL =
  'https://pub-23cae552ecf24722bf572b29fa8dd03f.r2.dev/';

const isSearchIndexManifest = (value: unknown): value is SearchIndexManifest => {
  if (!value || typeof value !== 'object') return false;
  const manifest = value as Record<string, unknown>;
  const sha256 =
    typeof manifest.sha256 === 'string' ? manifest.sha256.toLowerCase() : '';
  const commonValid =
    (manifest.version === 1 || manifest.version === 2) &&
    /^[a-f0-9]{64}$/.test(sha256) &&
    Number.isSafeInteger(manifest.bytes) &&
    Number(manifest.bytes) > 0 &&
    Number(manifest.bytes) <= 256 * 1024 * 1024 &&
    Number.isSafeInteger(manifest.entries) &&
    Number(manifest.entries) > 0 &&
    Number(manifest.entries) <= 1_000_000 &&
    typeof manifest.object_key === 'string' &&
    manifest.object_key === `search/${sha256}.json` &&
    typeof manifest.story_index_sha256 === 'string' &&
    /^[a-f0-9]{64}$/.test(manifest.story_index_sha256);
  if (!commonValid) return false;
  if (manifest.version === 1) return true;

  const chunkBytes = Number(manifest.chunk_bytes);
  const chunks = manifest.chunks;
  if (
    chunkBytes !== 1024 * 1024 ||
    !Array.isArray(chunks) ||
    chunks.length === 0 ||
    chunks.length > 4096 ||
    chunks.length !== Math.ceil(Number(manifest.bytes) / chunkBytes)
  ) {
    return false;
  }
  let total = 0;
  for (let index = 0; index < chunks.length; index += 1) {
    const chunk = chunks[index];
    if (!chunk || typeof chunk !== 'object') return false;
    const item = chunk as Record<string, unknown>;
    const itemBytes = Number(item.bytes);
    const finalChunk = index === chunks.length - 1;
    if (
      !Number.isSafeInteger(itemBytes) ||
      itemBytes <= 0 ||
      itemBytes > chunkBytes ||
      (!finalChunk && itemBytes !== chunkBytes) ||
      typeof item.sha256 !== 'string' ||
      !/^[a-f0-9]{64}$/.test(item.sha256)
    ) {
      return false;
    }
    total += itemBytes;
    if (!Number.isSafeInteger(total) || total > Number(manifest.bytes)) {
      return false;
    }
  }
  return total === Number(manifest.bytes);
};

const getSearchIndexSources = async (
  signal: AbortSignal,
  storyIndexSha256: string,
): Promise<SearchIndexSource[]> => {
  const localDevelopment =
    process.env.NODE_ENV === 'development' ||
    ['localhost', '127.0.0.1'].includes(window.location.hostname);

  const response = await fetch(SEARCH_INDEX_MANIFEST_URL, {
    cache: 'no-store',
    credentials: 'same-origin',
    signal,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const manifest: unknown = await response.json();
  if (!isSearchIndexManifest(manifest)) {
    throw new Error('搜索索引清单格式不正确');
  }
  if (manifest.story_index_sha256 !== storyIndexSha256) {
    throw new Error('搜索索引与当前剧情目录不匹配');
  }

  const sourceMetadata = {
    version: manifest.version,
    sha256: manifest.sha256,
    bytes: manifest.bytes,
    entries: manifest.entries,
    ...(manifest.version === 2
      ? {
          chunk_bytes: manifest.chunk_bytes,
          chunks: manifest.chunks,
        }
      : {}),
  };
  const addressedSource: SearchIndexSource = {
    url: `${SEARCH_INDEX_CLOUDFLARE_BASE_URL}${manifest.object_key}`,
    ...sourceMetadata,
  };
  return localDevelopment
    ? [
        addressedSource,
        { url: SEARCH_INDEX_LOCAL_FALLBACK_URL, ...sourceMetadata },
      ]
    : [addressedSource];
};

const getDisplayLabel = (story: Story): string => {
  const label = story.title || story.filename_cn || story.filename_jp || story.id;
  return label.replace(/(_cn|_jp)?\.txt$/i, '');
};

const storyProgress = (story: Story): number =>
  story.percent ?? (story.has_cn ? 100 : 0);

function FolderCard({ group, theme }: { group: StoryGroup; theme: string }) {
  const hasSearchMatches = Boolean(
    group.matchSnippets && Object.keys(group.matchSnippets).length > 0,
  );
  const [manuallyOpen, setManuallyOpen] = useState(hasSearchMatches);
  const contentId = useId();
  const machinePending = group.items.filter(
    story => story.machine_translation && !story.human_verified,
  ).length;
  const machineVerified = group.items.filter(
    story => story.machine_translation && story.human_verified,
  ).length;
  const isOpen = hasSearchMatches || manuallyOpen;
  const avgPercent = Math.round(
    group.items.reduce((sum, story) => sum + storyProgress(story), 0) /
      group.items.length,
  );

  const isDark = theme === 'dark';
  let headerClass = '';
  let progressClass = '';

  if (machinePending > 0) {
    headerClass = isDark
      ? 'bg-amber-950/70 border-amber-700 text-amber-100'
      : 'bg-amber-100 border-amber-400 text-amber-950';
    progressClass = isDark ? 'text-amber-300' : 'text-amber-800';
  } else if (isDark) {
    headerClass =
      avgPercent === 0
        ? 'bg-gray-800 border-gray-700 text-gray-400'
        : 'bg-emerald-900/40 border-emerald-800 text-emerald-100';
    progressClass = 'text-emerald-400';
  } else {
    if (avgPercent === 0) {
      headerClass = 'bg-black/5 border-black/10 text-black/50';
    } else if (avgPercent === 100) {
      headerClass = 'bg-emerald-600 border-emerald-700 text-white';
    } else {
      headerClass = 'bg-emerald-100 border-emerald-300 text-emerald-900';
    }
    progressClass = avgPercent === 100 ? 'text-emerald-100' : 'text-emerald-700';
  }

  const displayTitle = group.folderName
    .replace(/^\d+ - /, '')
    .replace(/^Event_\d+/, 'Event');
  const folderId = group.folderName.match(/^(\d+)/)?.[1] || '';

  return (
    <div
      className={`break-inside-avoid mb-3 rounded-lg border shadow-sm transition-all ${
        machinePending > 0
          ? isDark ? 'border-amber-700 ring-1 ring-amber-700/40' : 'border-amber-400 ring-1 ring-amber-300'
          : isDark ? 'border-gray-700' : 'border-black/10'
      } ${isOpen ? '' : 'magi-folder-card-collapsed'}`}
    >
      <button
        type="button"
        aria-controls={contentId}
        aria-expanded={isOpen}
        onClick={() => setManuallyOpen(open => !open)}
        className={`w-full flex items-start justify-between px-3 py-3 text-left transition-colors border-b ${
          isOpen ? 'border-inherit' : 'border-transparent'
        } ${headerClass}`}
      >
        <div className="flex items-start gap-2 overflow-hidden w-full">
          <div className="mt-0.5 flex-shrink-0">
            {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </div>
          {folderId && (
            <span className="font-mono text-xs opacity-70 bg-black/10 px-1 rounded flex-shrink-0 mt-0.5">
              {folderId}
            </span>
          )}
          <span
            className="font-bold text-sm whitespace-normal break-words leading-tight flex-1 mr-2"
            style={{ color: characterFolderColorFor(group.category, displayTitle) }}
          >
            {displayTitle}
          </span>
          {machinePending > 0 && (
            <span className="shrink-0 rounded-full bg-amber-500 px-2 py-0.5 text-[10px] font-black text-white">
              待校 {machinePending}
            </span>
          )}
          {machinePending === 0 && machineVerified > 0 && (
            <span className="shrink-0 rounded-full bg-emerald-500 px-2 py-0.5 text-[10px] font-black text-white">
              已校 {machineVerified}
            </span>
          )}
        </div>
        <span className={`text-[10px] font-mono mt-0.5 flex-shrink-0 ${progressClass}`}>
          {avgPercent}%
        </span>
      </button>

      {isOpen && (
        <div id={contentId} className={`p-2 ${isDark ? 'bg-gray-900' : 'bg-white/50'}`}>
          <div className="flex flex-wrap gap-2">
            {[...group.items]
              .sort((a, b) => NATURAL_COLLATOR.compare(a.id, b.id))
              .map(story => {
                const label = getDisplayLabel(story);
                const progress = storyProgress(story);
                const snippet = group.matchSnippets?.[story.id];
                const machinePendingStory =
                  story.machine_translation && !story.human_verified;
                const buttonClass = machinePendingStory
                  ? isDark
                    ? 'bg-amber-950/60 border-amber-600 text-amber-200'
                    : 'bg-amber-50 border-amber-400 text-amber-950'
                  : story.machine_translation && story.human_verified
                    ? isDark
                      ? 'bg-emerald-950/50 border-emerald-600 text-emerald-300'
                      : 'bg-emerald-50 border-emerald-400 text-emerald-900'
                    : isDark
                      ? progress > 0
                        ? 'bg-emerald-900/30 border-emerald-700 text-emerald-400'
                        : 'bg-gray-800 border-gray-700 text-gray-500'
                      : progress > 0
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                        : 'bg-white border-gray-200 text-gray-400';

                return (
                  <Link
                    key={`${story.id}:${story.path_cn ?? ''}:${story.path_jp ?? ''}`}
                    href={`/reader/${encodeURIComponent(story.id)}?cn=${encodeURIComponent(
                      story.path_cn || '',
                    )}&jp=${encodeURIComponent(story.path_jp || '')}`}
                    prefetch={false}
                    className={`rounded border transition-all hover:scale-[1.01] ${buttonClass} overflow-hidden ${
                      snippet ? 'w-full' : ''
                    }`}
                  >
                    <div className="px-2 py-1.5 flex justify-between items-center gap-2">
                      <span className="font-mono text-xs font-bold break-all">#{label}</span>
                      {machinePendingStory && (
                        <span className="rounded bg-amber-500 px-1.5 py-0.5 text-[9px] font-black text-white">
                          机翻待校
                        </span>
                      )}
                      {story.machine_translation && story.human_verified && (
                        <span className="rounded bg-emerald-600 px-1.5 py-0.5 text-[9px] font-black text-white">
                          人工已校
                        </span>
                      )}
                      {progress < 100 && progress > 0 && (
                        <span className="text-[10px] opacity-60">{progress}%</span>
                      )}
                    </div>
                    {snippet && (
                      <div
                        className={`px-2 py-1.5 text-xs font-serif border-t ${
                          isDark
                            ? 'border-white/10 text-gray-300'
                            : 'border-black/5 text-gray-600'
                        }`}
                      >
                        …{snippet}…
                      </div>
                    )}
                  </Link>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}

type CategoryNavProps = {
  categories: string[];
  activeCategory: string;
  searchActive: boolean;
  theme: string;
  mobile?: boolean;
  onSelect: (category: string) => void;
};

function CategoryNav({
  categories,
  activeCategory,
  searchActive,
  theme,
  mobile = false,
  onSelect,
}: CategoryNavProps) {
  return (
    <nav
      className={
        mobile
          ? 'flex overflow-x-auto p-2 gap-2 no-scrollbar bg-inherit border-b border-black/5'
          : 'flex-1 overflow-y-auto p-2 space-y-1'
      }
    >
      {categories.map((category) => {
        const config = CATEGORY_CONFIG[category] || { label: category, icon: Folder };
        const Icon = config.icon;
        const isActive = activeCategory === category && !searchActive;
        const activeClass =
          theme === 'dark'
            ? 'bg-emerald-900/50 text-emerald-400 border-emerald-500'
            : 'bg-emerald-50 text-emerald-700 border-emerald-500';

        return (
          <button
            type="button"
            key={category}
            onClick={() => onSelect(category)}
            className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-bold transition-all whitespace-nowrap ${
              mobile ? 'border-b-2 rounded-none' : 'border-l-4'
            } ${
              isActive
                ? activeClass
                : 'text-gray-500 hover:bg-black/5 border-transparent'
            }`}
          >
            <Icon size={16} />
            <span>{config.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

export default function Home() {
  const [stories, setStories] = useState<Story[]>([]);
  const [storyIndexSha256, setStoryIndexSha256] = useState('');
  const [loading, setLoading] = useState(true);
  const [storyError, setStoryError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [searchTruncated, setSearchTruncated] = useState(false);
  const [searchIndexBytes, setSearchIndexBytes] = useState(0);
  const [textMatches, setTextMatches] = useState<Record<string, string>>({});
  const [aboutOpen, setAboutOpen] = useState(false);
  const [searchJp, setSearchJp] = useState(false);
  const [searchMode, setSearchMode] = useState<SearchMode>('title');
  const [proofreadingStatus, setProofreadingStatus] = useState<ProofreadingStatus | null>(null);
  const [onlyNeedsReview, setOnlyNeedsReview] = useState(false);
  const machineReviewPanelCollapsed = useSyncExternalStore(
    subscribeMachineReviewPanel,
    getMachineReviewPanelSnapshot,
    getMachineReviewPanelServerSnapshot,
  );
  const machineReviewPanelContentId = useId();
  const workerRef = useRef<Worker | null>(null);
  const searchSequenceRef = useRef(0);

  const { theme, setTheme, lastCategory, setLastCategory } = useGlobal();
  const storySystem: StorySystem =
    lastCategory.startsWith('exedra_') ? 'exedra' : 'magireco';

  useEffect(() => {
    const controller = new AbortController();
    void loadStoryIndex(controller.signal)
      .then(({ stories: loadedStories, sha256 }) => {
        setStories(loadedStories);
        setStoryIndexSha256(sha256);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setStoryError('剧情目录加载失败，请检查网络后刷新页面。');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void fetch('/api/proofreading/machine-status', {
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(response => response.ok ? response.json() as Promise<ProofreadingStatus> : null)
      .then(status => {
        if (status) setProofreadingStatus(status);
      })
      .catch(error => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          console.error('人工校验清单读取失败：', error);
        }
      });
    return () => controller.abort();
  }, []);

  const enrichedStories = useMemo(() => {
    const machine = new Set(proofreadingStatus?.machine_translation_ids ?? []);
    const verified = new Set(proofreadingStatus?.verified_ids ?? []);
    return stories.map(story => ({
      ...story,
      machine_translation: machine.has(story.id),
      human_verified: verified.has(story.id),
    }));
  }, [proofreadingStatus, stories]);

  useEffect(() => {
    if (enrichedStories.length === 0) return;
    const categoriesForSystem = Array.from(
      new Set(
        enrichedStories
          .map((story) => story.category || 'Unclassified')
          .filter((category) =>
            storySystem === 'exedra'
              ? isExedraCategory(category)
              : !category.startsWith('exedra_'),
          ),
      ),
    );
    if (
      categoriesForSystem.length > 0 &&
      !categoriesForSystem.includes(lastCategory)
    ) {
      const fallback = categoriesForSystem.includes(DEFAULT_CATEGORY[storySystem])
        ? DEFAULT_CATEGORY[storySystem]
        : categoriesForSystem.sort(
            (left, right) =>
              categoryOrder(left) - categoryOrder(right) ||
              NATURAL_COLLATOR.compare(left, right),
          )[0];
      setLastCategory(fallback);
    }
  }, [enrichedStories, lastCategory, setLastCategory, storySystem]);

  useEffect(() => {
    if (!storyIndexSha256) return;
    const controller = new AbortController();
    const worker = new Worker('/search-worker.js?v=2');
    workerRef.current = worker;
    worker.onmessage = (event: MessageEvent<SearchWorkerMessage>) => {
      const message = event.data;
      if (message.type === 'results') {
        if (message.sequence !== searchSequenceRef.current) return;
        setTextMatches(Object.fromEntries(message.matches));
        setSearchTruncated(message.truncated);
        setSearchLoading(false);
        setSearchError('');
      } else if (message.type === 'error') {
        if (message.sequence !== searchSequenceRef.current) return;
        setTextMatches({});
        setSearchLoading(false);
        setSearchError('正文索引加载失败；标题搜索仍然可以使用。');
      }
    };
    worker.onerror = () => {
      setSearchLoading(false);
      setSearchError('正文搜索组件未能启动；标题搜索仍然可以使用。');
    };

    void getSearchIndexSources(controller.signal, storyIndexSha256)
      .then((sources) => {
        setSearchIndexBytes(sources[0]?.bytes ?? 0);
        worker.postMessage({ type: 'init', sources });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        worker.postMessage({ type: 'init', sources: [] });
      });

    return () => {
      controller.abort();
      worker.terminate();
      workerRef.current = null;
    };
  }, [storyIndexSha256]);

  const requestContentSearch = useCallback(
    (term: string, mode: SearchMode, includeJapanese: boolean) => {
      const sequence = searchSequenceRef.current + 1;
      searchSequenceRef.current = sequence;
      const query = normalizeSearchText(term);
      const contentEnabled = mode === 'all' || mode === 'content';

      setTextMatches({});
      setSearchTruncated(false);
      setSearchError('');

      if (!contentEnabled || query.length < 2) {
        setSearchLoading(false);
        workerRef.current?.postMessage({ type: 'cancel', sequence });
        return;
      }

      if (!workerRef.current) {
        setSearchLoading(false);
        setSearchError('正文索引尚未就绪；标题搜索仍然可以使用。');
        return;
      }
      setSearchLoading(true);
      workerRef.current.postMessage({
        type: 'search',
        sequence,
        query: term,
        includeJapanese,
      });
    },
    [],
  );

  const updateSearchTerm = (term: string) => {
    setSearchTerm(term);
    requestContentSearch(term, searchMode, searchJp);
  };

  const updateSearchMode = (mode: SearchMode) => {
    setSearchMode(mode);
    requestContentSearch(searchTerm, mode, searchJp);
  };

  const updateSearchLanguage = (includeJapanese: boolean) => {
    setSearchJp(includeJapanese);
    requestContentSearch(searchTerm, searchMode, includeJapanese);
  };

  const normalizedQuery = normalizeSearchText(searchTerm);
  const { categories, displayedGroups } = useMemo(() => {
    const foundCategories = new Set<string>();
    const groups: Record<string, StoryGroup> = {};

    for (const story of enrichedStories) {
      const category = story.category || 'Unclassified';
      const storyIsExedra = category.startsWith('exedra_');
      if (
        (storySystem === 'exedra' && (!storyIsExedra || !isExedraCategory(category))) ||
        (storySystem === 'magireco' && storyIsExedra)
      ) {
        continue;
      }
      foundCategories.add(category);
      if (onlyNeedsReview && (!story.machine_translation || story.human_verified)) {
        continue;
      }

      const titleText = [
        story.id,
        story.folder,
        story.title,
        story.filename_cn,
        story.filename_jp,
      ]
        .filter(Boolean)
        .join(' ');
      const titleMatch =
        normalizedQuery.length > 0 &&
        normalizeSearchText(titleText).includes(normalizedQuery);
      const contentMatch = Boolean(textMatches[story.id]);

      let matches = normalizedQuery.length === 0;
      if (normalizedQuery) {
        if (searchMode === 'title') matches = titleMatch;
        else if (searchMode === 'content') matches = contentMatch;
        else matches = titleMatch || contentMatch;
      }

      const shouldShow = normalizedQuery ? matches : category === lastCategory;
      if (!shouldShow) continue;

      const key = `${category}\u0000${story.folder}`;
      if (!groups[key]) {
        groups[key] = {
          key,
          category,
          folderName: story.folder,
          items: [],
          totalCn: 0,
          matchSnippets: {},
        };
      }
      groups[key].items.push(story);
      if (story.has_cn) groups[key].totalCn += 1;
      if (contentMatch) groups[key].matchSnippets![story.id] = textMatches[story.id];
    }

    const sortedGroups = Object.values(groups).sort(
      (a, b) =>
        categoryOrder(a.category) - categoryOrder(b.category) ||
        NATURAL_COLLATOR.compare(a.folderName, b.folderName),
    );

    return {
      categories: Array.from(foundCategories).sort(
        (a, b) =>
          categoryOrder(a) - categoryOrder(b) ||
          NATURAL_COLLATOR.compare(a, b),
      ),
      displayedGroups: sortedGroups,
    };
  }, [enrichedStories, storySystem, lastCategory, normalizedQuery, searchMode, textMatches, onlyNeedsReview]);

  const selectCategory = (category: string) => {
    setLastCategory(category);
    updateSearchTerm('');
  };

  const switchStorySystem = () => {
    const nextSystem: StorySystem =
      storySystem === 'magireco' ? 'exedra' : 'magireco';
    setLastCategory(DEFAULT_CATEGORY[nextSystem]);
    if (nextSystem === 'exedra') setOnlyNeedsReview(false);
    updateSearchTerm('');
  };

  if (loading) {
    return (
      <div className="flex h-screen h-[100dvh] items-center justify-center opacity-50">
        数据加载中…
      </div>
    );
  }

  return (
    <div className="flex h-screen h-[100dvh] overflow-hidden">
      <aside
        className={`hidden md:flex w-64 border-r flex-col z-20 flex-shrink-0 ${
          theme === 'dark'
            ? 'border-gray-800 bg-gray-900'
            : 'border-black/5 bg-inherit'
        }`}
      >
        <div className="p-5 border-b border-inherit">
          <h1 className="text-xl font-black bg-clip-text text-transparent bg-gradient-to-r from-emerald-600 to-teal-500">
            MagiReader
          </h1>
          <p className="text-xs opacity-50 mt-1">Archive v3.0</p>
        </div>
        <CategoryNav
          categories={categories}
          activeCategory={lastCategory}
          searchActive={Boolean(normalizedQuery)}
          theme={theme}
          onSelect={selectCategory}
        />
      </aside>

      <main className="flex-1 flex flex-col min-w-0 bg-transparent">
        <header
          className={`border-b p-3 backdrop-blur z-10 flex flex-col gap-3 ${
            theme === 'dark'
              ? 'border-gray-800 bg-gray-900/90'
              : 'border-black/5 bg-white/60'
          }`}
        >
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-4xl flex flex-wrap gap-2">
              <div className="relative flex-1 min-w-56">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none opacity-50">
                  <Search size={16} />
                </div>
                <input
                  type="search"
                  aria-label="搜索剧情标题或正文"
                  placeholder={searchLoading ? '正在准备正文搜索…' : '搜索标题或正文…'}
                  className={`block w-full pl-9 pr-3 py-2 border rounded-lg text-sm outline-none transition-all ${
                    theme === 'dark'
                      ? 'bg-gray-800 border-gray-700'
                      : 'bg-white/50 border-black/10'
                  }`}
                  value={searchTerm}
                  onChange={(event) => updateSearchTerm(event.target.value)}
                />
              </div>

              <div className="flex items-center bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5 border border-gray-200 dark:border-gray-700 shrink-0">
                {(
                  [
                    { id: 'all', label: '全部' },
                    { id: 'title', label: '标题' },
                    { id: 'content', label: '正文' },
                  ] as const
                ).map((option) => (
                  <button
                    type="button"
                    key={option.id}
                    aria-pressed={searchMode === option.id}
                    onClick={() => updateSearchMode(option.id)}
                    className={`px-2 py-1.5 text-xs font-bold rounded-md transition-all ${
                      searchMode === option.id
                        ? 'bg-white dark:bg-gray-600 text-blue-600 dark:text-blue-300 shadow-sm'
                        : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>

              <label
                className={`flex items-center gap-1 px-2 rounded cursor-pointer border ${
                  searchJp
                    ? theme === 'dark'
                      ? 'bg-blue-900/30 border-blue-800 text-blue-400'
                      : 'bg-blue-50 border-blue-200 text-blue-700'
                    : 'border-transparent opacity-60'
                }`}
              >
                <input
                  type="checkbox"
                  checked={searchJp}
                  onChange={(event) => updateSearchLanguage(event.target.checked)}
                  className="accent-blue-500 w-3 h-3"
                />
                <span className="text-xs font-bold whitespace-nowrap">JP</span>
              </label>

              <LocalStoryPicker theme={theme} />
              <button
                type="button"
                onClick={() => setAboutOpen(true)}
                className={`px-2.5 py-1 rounded cursor-pointer border text-xs font-bold whitespace-nowrap transition-all ${
                  theme === 'dark'
                    ? 'bg-emerald-900/30 border-emerald-800 text-emerald-400 hover:bg-emerald-800'
                    : 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100'
                }`}
              >
                关于我们
              </button>
              <button
                type="button"
                onClick={switchStorySystem}
                aria-pressed={storySystem === 'exedra'}
                aria-label={
                  storySystem === 'magireco'
                    ? '切换到 Magia Exedra 剧情'
                    : '切换到 Magia Record 剧情'
                }
                className={`flex items-center gap-1 px-2.5 py-1 rounded cursor-pointer border text-xs font-bold whitespace-nowrap transition-all ${
                  storySystem === 'exedra'
                    ? theme === 'dark'
                      ? 'border-violet-700 bg-violet-900/40 text-violet-300 hover:bg-violet-800/60'
                      : 'border-violet-300 bg-violet-100 text-violet-800 hover:bg-violet-200'
                    : theme === 'dark'
                      ? 'border-blue-800 bg-blue-900/30 text-blue-300 hover:bg-blue-800'
                      : 'border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100'
                }`}
              >
                <Book size={14} />
                {storySystem === 'magireco' ? 'Exedra' : 'Magia Record'}
              </button>
            </div>

            <div
              className={`flex gap-1 p-1 rounded-full self-end md:self-auto ${
                theme === 'dark' ? 'bg-black/20' : 'bg-black/5'
              }`}
            >
              {(
                [
                  { key: 'light', icon: Sun, label: '明亮' },
                  { key: 'paper', icon: BookOpen, label: '纸张' },
                  { key: 'green', icon: Leaf, label: '护眼' },
                  { key: 'dark', icon: Moon, label: '深色' },
                ] as const
              ).map((option) => (
                <button
                  type="button"
                  key={option.key}
                  title={option.label}
                  aria-label={`${option.label}主题`}
                  aria-pressed={theme === option.key}
                  onClick={() => setTheme(option.key)}
                  className={`p-2 rounded-full ${
                    theme === option.key ? 'bg-white shadow text-black' : 'opacity-40'
                  }`}
                >
                  <option.icon size={14} />
                </button>
              ))}
            </div>
          </div>

          {searchMode !== 'title' && searchIndexBytes > 0 && (
            <p className="text-[11px] opacity-65">
              正文搜索会在首次使用时按需加载约{' '}
              {(searchIndexBytes / (1024 * 1024)).toFixed(1)} MiB 索引。
              内存较小的设备请使用“标题”模式。
            </p>
          )}

          <div className="md:hidden -mx-3">
            <CategoryNav
              categories={categories}
              activeCategory={lastCategory}
              searchActive={Boolean(normalizedQuery)}
              theme={theme}
              mobile
              onSelect={selectCategory}
            />
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-3 md:p-6 scroll-smooth">
          <div className="max-w-7xl mx-auto">
            {storySystem === 'magireco' && proofreadingStatus && (
              <section className={`mb-5 rounded-2xl border shadow-sm ${
                machineReviewPanelCollapsed ? 'p-2' : 'p-4'
              } ${
                theme === 'dark'
                  ? 'border-amber-800 bg-amber-950/40 text-amber-100'
                  : 'border-amber-300 bg-gradient-to-r from-amber-50 to-emerald-50 text-gray-900'
              }`}>
                {machineReviewPanelCollapsed && (
                  <button
                    type="button"
                    aria-controls={machineReviewPanelContentId}
                    aria-expanded={!machineReviewPanelCollapsed}
                    aria-label={`展开机器翻译人工校验清单，仍需 ${proofreadingStatus.remaining} 部`}
                    onClick={() => setMachineReviewPanelCollapsedPreference(false)}
                    className={`flex min-h-11 w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm font-black transition ${
                      theme === 'dark'
                        ? 'hover:bg-amber-900/50 focus-visible:bg-amber-900/50'
                        : 'hover:bg-white/70 focus-visible:bg-white/70'
                    } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500`}
                  >
                    <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                      <span>机器翻译人工校验清单</span>
                      <span className="rounded-full bg-amber-500 px-2 py-0.5 text-[10px] text-white">
                        仍需 {proofreadingStatus.remaining} 部
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1 text-xs">
                      展开
                      <ChevronDown aria-hidden="true" size={16} />
                    </span>
                  </button>
                )}
                <div
                  id={machineReviewPanelContentId}
                  hidden={machineReviewPanelCollapsed}
                >
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-base font-black">机器翻译人工校验清单</h2>
                        <span className="rounded-full bg-amber-500 px-2 py-0.5 text-[10px] font-black text-white">
                          动态
                        </span>
                      </div>
                      <p className="mt-1 text-sm opacity-80">
                        总计 {proofreadingStatus.total} 部，已人工校验 {proofreadingStatus.verified} 部，
                        仍需校验 <strong>{proofreadingStatus.remaining}</strong> 部。
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <div className="min-w-48 grow md:grow-0">
                        <div className="mb-1 flex justify-between text-[10px] font-bold opacity-70">
                          <span>校验进度</span>
                          <span>
                            {proofreadingStatus.total > 0
                              ? Math.round((proofreadingStatus.verified / proofreadingStatus.total) * 100)
                              : 0}%
                          </span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-black/10">
                          <div
                            className="h-full rounded-full bg-emerald-500 transition-all"
                            style={{
                              width: `${proofreadingStatus.total > 0
                                ? (proofreadingStatus.verified / proofreadingStatus.total) * 100
                                : 0}%`,
                            }}
                          />
                        </div>
                      </div>
                      <button
                        type="button"
                        aria-pressed={onlyNeedsReview}
                        onClick={() => setOnlyNeedsReview(value => !value)}
                        className={`rounded-lg border px-3 py-2 text-xs font-black transition ${
                          onlyNeedsReview
                            ? 'border-amber-600 bg-amber-500 text-white'
                            : theme === 'dark'
                              ? 'border-amber-700 bg-black/20 text-amber-200'
                              : 'border-amber-300 bg-white text-amber-800'
                        }`}
                      >
                        {onlyNeedsReview ? '显示当前分类全部剧情' : '只看机器翻译待校剧情'}
                      </button>
                      <Link
                        href="/review/machine-translations"
                        className="rounded-lg bg-amber-600 px-3 py-2 text-xs font-black text-white hover:bg-amber-700"
                      >
                        管理机器校验标记
                      </Link>
                      <Link
                        href="/review/submissions"
                        className="rounded-lg bg-purple-600 px-3 py-2 text-xs font-black text-white hover:bg-purple-700"
                      >
                        投稿审核
                      </Link>
                      <button
                        type="button"
                        aria-controls={machineReviewPanelContentId}
                        aria-expanded={!machineReviewPanelCollapsed}
                        aria-label="收起机器翻译人工校验清单"
                        title="收起校验清单"
                        onClick={() => setMachineReviewPanelCollapsedPreference(true)}
                        className={`flex min-h-9 items-center gap-1 rounded-lg border px-3 py-2 text-xs font-black transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 ${
                          theme === 'dark'
                            ? 'border-amber-700 bg-black/20 text-amber-200 hover:bg-amber-900/50'
                            : 'border-amber-300 bg-white text-amber-800 hover:bg-amber-100'
                        }`}
                      >
                        <ChevronUp aria-hidden="true" size={15} />
                        收起
                      </button>
                    </div>
                  </div>
                </div>
              </section>
            )}
            {storyError && (
              <div
                role="alert"
                className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
              >
                {storyError}
              </div>
            )}
            {searchError && (
              <div
                role="status"
                className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800"
              >
                {searchError}
              </div>
            )}
            {normalizedQuery.length === 1 &&
              (searchMode === 'all' || searchMode === 'content') && (
                <div className="mb-4 text-xs opacity-60">
                  正文搜索会在输入至少 2 个有效字符后开始；标题结果已显示。
                </div>
              )}
            {searchTruncated && (
              <div className="mb-4 text-xs opacity-60">
                正文匹配较多，当前只显示前 500 个结果。请继续输入以缩小范围。
              </div>
            )}

            {!normalizedQuery && (
              <h2 className="text-xl font-bold mb-4 opacity-80 px-1">
                {CATEGORY_CONFIG[lastCategory]?.label ?? lastCategory}
              </h2>
            )}
            {normalizedQuery && (
              <h2 className="text-xl font-bold mb-4 opacity-80 px-1">
                搜索结果：“{searchTerm}” {searchJp ? '（含日文）' : ''}
              </h2>
            )}

            <div className="columns-1 md:columns-2 xl:columns-3 gap-4 space-y-4">
              {displayedGroups.map((group) => (
                <FolderCard key={group.key} group={group} theme={theme} />
              ))}
            </div>
            {displayedGroups.length === 0 && !storyError && (
              <div className="text-center opacity-50 mt-10">没有找到相关剧情</div>
            )}
            <div className="h-20" />
          </div>
        </div>
      </main>
      <AboutModal
        isOpen={aboutOpen}
        onClose={() => setAboutOpen(false)}
        theme={theme}
      />
    </div>
  );
}
