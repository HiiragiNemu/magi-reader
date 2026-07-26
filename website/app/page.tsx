"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useId,
  useState,
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

type SearchIndexManifest = {
  version: 1;
  sha256: string;
  bytes: number;
  entries: number;
  object_key: string;
  story_index_sha256: string;
};

type SearchIndexSource = {
  url: string;
  sha256: string;
  bytes: number;
  entries: number;
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
  exedra_main: { label: '1 主线', icon: Book },
  exedra_sub: { label: '2 Sub', icon: Layers },
  exedra_character: { label: '3 角色', icon: User },
  exedra_portrait: { label: '4 肖像', icon: User },
  exedra_reaction: { label: '6 语音', icon: FileText },
  exedra_namae: { label: '7 Namae', icon: Folder },
  exedra_dungeon: { label: '8 Dungeon', icon: Layers },
  exedra_battle: { label: '10 战斗', icon: Folder },
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
  return (
    manifest.version === 1 &&
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
    /^[a-f0-9]{64}$/.test(manifest.story_index_sha256)
  );
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
    sha256: manifest.sha256,
    bytes: manifest.bytes,
    entries: manifest.entries,
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
  const isOpen = hasSearchMatches || manuallyOpen;
  const avgPercent = Math.round(
    group.items.reduce((sum, story) => sum + storyProgress(story), 0) /
      group.items.length,
  );

  const isDark = theme === 'dark';
  let headerClass = '';
  let progressClass = '';

  if (isDark) {
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
        isDark ? 'border-gray-700' : 'border-black/10'
      }`}
    >
      <button
        type="button"
        aria-controls={contentId}
        aria-expanded={isOpen}
        onClick={() => setManuallyOpen((open) => !open)}
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
              .map((story) => {
                const label = getDisplayLabel(story);
                const progress = storyProgress(story);
                const snippet = group.matchSnippets?.[story.id];
                const buttonClass = isDark
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
                    className={`rounded border transition-all hover:scale-[1.01] ${buttonClass} overflow-hidden ${
                      snippet ? 'w-full' : ''
                    }`}
                  >
                    <div className="px-2 py-1.5 flex justify-between items-center gap-2">
                      <span className="font-mono text-xs font-bold break-all">#{label}</span>
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
  const [textMatches, setTextMatches] = useState<Record<string, string>>({});
  const [aboutOpen, setAboutOpen] = useState(false);
  const [searchJp, setSearchJp] = useState(false);
  const [searchMode, setSearchMode] = useState<SearchMode>('all');
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
    if (stories.length === 0) return;
    const categoriesForSystem = Array.from(
      new Set(
        stories
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
  }, [lastCategory, setLastCategory, stories, storySystem]);

  useEffect(() => {
    if (!storyIndexSha256) return;
    const controller = new AbortController();
    const worker = new Worker('/search-worker.js');
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
      .then((sources) => worker.postMessage({ type: 'init', sources }))
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

    for (const story of stories) {
      const category = story.category || 'Unclassified';
      const storyIsExedra = category.startsWith('exedra_');
      if (
        (storySystem === 'exedra' && (!storyIsExedra || !isExedraCategory(category))) ||
        (storySystem === 'magireco' && storyIsExedra)
      ) {
        continue;
      }
      foundCategories.add(category);

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
  }, [stories, storySystem, lastCategory, normalizedQuery, searchMode, textMatches]);

  const selectCategory = (category: string) => {
    setLastCategory(category);
    updateSearchTerm('');
  };

  const switchStorySystem = () => {
    const nextSystem: StorySystem =
      storySystem === 'magireco' ? 'exedra' : 'magireco';
    setLastCategory(DEFAULT_CATEGORY[nextSystem]);
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
