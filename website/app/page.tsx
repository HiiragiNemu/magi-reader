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
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
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
  getSearchIndexSources,
  SEARCH_INDEX_SCOPE_CONFIG,
  type SearchIndexScope,
} from '@/lib/search-index-scope';
import {
  getMachineReviewPanelServerSnapshot,
  getMachineReviewPanelSnapshot,
  setMachineReviewPanelCollapsedPreference,
  subscribeMachineReviewPanel,
} from '@/lib/machine-review-panel';
import {
  HOME_SIDEBAR_WIDTH_DEFAULT,
  HOME_SIDEBAR_WIDTH_MAX,
  HOME_SIDEBAR_WIDTH_MIN,
  HOME_SIDEBAR_WIDTH_STEP,
  HOME_SIDEBAR_WIDTH_STORAGE_KEY,
  clampHomeSidebarWidth,
  parseStoredHomeSidebarWidth,
} from '@/lib/sidebar-width';

type SearchMode = 'all' | 'title' | 'content';
type StorySystem = SearchIndexScope;
type MobileReviewPlacement = 'floating' | 'toolbar';

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

type ProofreadingStatus = {
  total: number;
  verified: number;
  remaining: number;
  source_unverified_ids?: string[];
  /** Deprecated API compatibility alias. */
  machine_translation_ids?: string[];
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

const isDayArchiveTheme = (theme: string): boolean =>
  theme === 'light' || theme === 'paper';

const MOBILE_REVIEW_PLACEMENT_STORAGE_KEY =
  'magi-reader-mobile-review-placement-v1';

const pointInsideRect = (
  x: number,
  y: number,
  rect: DOMRect | undefined,
): boolean =>
  Boolean(
    rect
    && x >= rect.left
    && x <= rect.right
    && y >= rect.top
    && y <= rect.bottom,
  );

const getDisplayLabel = (story: Story): string => {
  const label = story.title || story.filename_cn || story.filename_jp || story.id;
  return label.replace(/(_cn|_jp)?\.txt$/i, '');
};

const storyProgress = (story: Story): number =>
  story.percent ?? (story.has_cn ? 100 : 0);

type TranslationProgressStatus = 'none' | 'partial' | 'complete';

const translationProgressStatus = (percent: number): TranslationProgressStatus =>
  percent === 0 ? 'none' : percent === 100 ? 'complete' : 'partial';

function FolderCard({ group, theme }: { group: StoryGroup; theme: string }) {
  const hasSearchMatches = Boolean(
    group.matchSnippets && Object.keys(group.matchSnippets).length > 0,
  );
  const [manuallyOpen, setManuallyOpen] = useState(hasSearchMatches);
  const contentId = useId();
  const sourceUnverifiedPending = group.items.filter(
    story => story.source_unverified && !story.human_verified,
  ).length;
  const sourceUnverifiedVerified = group.items.filter(
    story => story.source_unverified && story.human_verified,
  ).length;
  const officialTwStories = group.items.filter(
    story => isExedraCategory(story.category) && story.official_tw,
  );
  const officialTwLabel =
    officialTwStories[0]?.official_tw_label?.trim() || '台服';
  const isOfficialTwGroup = officialTwStories.length > 0;
  const isOpen = hasSearchMatches || manuallyOpen;
  const avgPercent = Math.round(
    group.items.reduce((sum, story) => sum + storyProgress(story), 0) /
      group.items.length,
  );
  const groupProgressStatus = translationProgressStatus(avgPercent);

  const isDark = theme === 'dark';
  const isDayArchive = isDayArchiveTheme(theme);
  let headerClass = '';
  let progressClass = '';

  if (sourceUnverifiedPending > 0) {
    headerClass = isDark
      ? 'bg-amber-950/70 border-amber-700 text-amber-100'
      : isDayArchive
        ? 'magi-home-light-folder-header magi-home-light-status-unverified'
        : 'bg-amber-100 border-amber-400 text-amber-950';
    progressClass = isDark
      ? 'text-amber-300'
      : isDayArchive
        ? 'magi-home-light-status-progress'
        : 'text-amber-800';
  } else if (isDark) {
    headerClass =
      avgPercent === 0
        ? 'bg-gray-800 border-gray-700 text-gray-400'
        : 'bg-emerald-900/40 border-emerald-800 text-emerald-100';
    progressClass = 'text-emerald-400';
  } else if (isDayArchive) {
    if (avgPercent === 0) {
      headerClass = 'magi-home-light-folder-header magi-home-light-folder-header-empty';
    } else if (avgPercent === 100) {
      headerClass = 'magi-home-light-folder-header magi-home-light-folder-header-complete';
    } else {
      headerClass = 'magi-home-light-folder-header magi-home-light-folder-header-partial';
    }
    progressClass = 'magi-home-light-progress';
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
      data-translation-status={groupProgressStatus}
      className={`break-inside-avoid mb-3 rounded-lg border shadow-sm transition-all ${
        sourceUnverifiedPending > 0
          ? isDark
            ? 'border-amber-700 ring-1 ring-amber-700/40'
            : isDayArchive
              ? 'magi-home-light-folder-card magi-home-light-folder-card-unverified'
              : 'border-amber-400 ring-1 ring-amber-300'
          : isDark
            ? 'border-gray-700'
            : isDayArchive
              ? 'magi-home-light-folder-card'
              : 'border-black/10'
      } ${isOpen ? '' : 'magi-folder-card-collapsed'}`}
    >
      <button
        type="button"
        aria-controls={contentId}
        aria-expanded={isOpen}
        onClick={() => setManuallyOpen(open => !open)}
        className={`magi-card-heading-grid w-full px-3 py-3 text-left transition-colors border-b ${
          isOpen ? 'border-inherit' : 'border-transparent'
        } ${headerClass}`}
      >
        <span className="magi-card-title-flow flex items-start gap-2">
          <span className="mt-0.5 flex-shrink-0">
            {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </span>
          {folderId && (
            <span className="font-mono text-xs opacity-70 bg-black/10 px-1 rounded flex-shrink-0 mt-0.5">
              {folderId}
            </span>
          )}
          <span
            className="min-w-0 flex-1 break-words text-sm font-bold leading-tight"
            style={{ color: characterFolderColorFor(group.category, displayTitle) }}
          >
            {displayTitle}
          </span>
        </span>
        <span className="magi-card-meta">
          {sourceUnverifiedPending > 0 && (
            <span className={`shrink-0 px-2 py-0.5 text-[10px] font-black ${
              isDayArchive
                ? 'magi-home-status-badge magi-home-status-badge-unverified'
                : 'rounded-full bg-amber-500 text-white'
            }`}>
              待核验 {sourceUnverifiedPending}
            </span>
          )}
          {sourceUnverifiedPending === 0 && sourceUnverifiedVerified > 0 && (
            <span className={`shrink-0 px-2 py-0.5 text-[10px] font-black ${
              isDayArchive
                ? 'magi-home-status-badge magi-home-status-badge-verified'
                : 'rounded-full bg-emerald-500 text-white'
            }`}>
              已校 {sourceUnverifiedVerified}
            </span>
          )}
          {isOfficialTwGroup && (
            <span
              className="magi-official-tw-badge"
              title="台服官方中文"
              aria-label="台服官方中文"
            >
              {officialTwLabel}
            </span>
          )}
          <span className={`shrink-0 font-mono text-[10px] ${progressClass}`}>
            {avgPercent}%
          </span>
        </span>
      </button>

      {isOpen && (
        <div
          id={contentId}
          className={`p-2 ${
            isDark
              ? 'bg-gray-900'
              : isDayArchive
                ? 'magi-home-light-folder-body'
                : 'bg-white/50'
          }`}
        >
          <div className="flex flex-wrap gap-2">
            {[...group.items]
              .sort((a, b) => NATURAL_COLLATOR.compare(a.id, b.id))
              .map(story => {
                const label = getDisplayLabel(story);
                const progress = storyProgress(story);
                const itemProgressStatus = translationProgressStatus(progress);
                const snippet = group.matchSnippets?.[story.id];
                const sourceUnverifiedPendingStory =
                  story.source_unverified && !story.human_verified;
                const buttonClass = sourceUnverifiedPendingStory
                  ? isDark
                    ? 'bg-amber-950/60 border-amber-600 text-amber-200'
                    : isDayArchive
                      ? 'magi-home-light-story-link magi-home-light-story-unverified'
                      : 'bg-amber-50 border-amber-400 text-amber-950'
                  : story.source_unverified && story.human_verified
                    ? isDark
                      ? 'bg-emerald-950/50 border-emerald-600 text-emerald-300'
                      : isDayArchive
                        ? 'magi-home-light-story-link magi-home-light-story-verified'
                        : 'bg-emerald-50 border-emerald-400 text-emerald-900'
                    : isDark
                      ? progress > 0
                        ? 'bg-emerald-900/30 border-emerald-700 text-emerald-400'
                        : 'bg-gray-800 border-gray-700 text-gray-500'
                      : isDayArchive
                        ? progress > 0
                          ? 'magi-home-light-story-link'
                          : 'magi-home-light-story-link magi-home-light-story-link-empty'
                        : progress > 0
                          ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                          : 'bg-white border-gray-200 text-gray-400';

                return (
                  <Link
                    key={`${story.id}:${story.path_cn ?? ''}:${story.path_jp ?? ''}`}
                    data-translation-status={itemProgressStatus}
                    href={`/reader/${encodeURIComponent(story.id)}?cn=${encodeURIComponent(
                      story.path_cn || '',
                    )}&jp=${encodeURIComponent(story.path_jp || '')}`}
                    prefetch={false}
                    className={`max-w-full min-w-0 overflow-hidden rounded border transition-all hover:scale-[1.01] ${buttonClass} ${
                      snippet ? 'w-full' : ''
                    }`}
                  >
                    <div className="magi-card-heading-grid min-w-0 px-2 py-1.5">
                      <span className="magi-card-title-flow break-words font-mono text-xs font-bold">
                        #{label}
                      </span>
                      <span className="magi-card-meta">
                        {sourceUnverifiedPendingStory && (
                          <span className={`px-1.5 py-0.5 text-[9px] font-black ${
                            isDayArchive
                              ? 'magi-home-status-badge magi-home-status-badge-unverified'
                              : 'rounded bg-amber-500 text-white'
                          }`}>
                            来源待核验
                          </span>
                        )}
                        {story.source_unverified && story.human_verified && (
                          <span className={`px-1.5 py-0.5 text-[9px] font-black ${
                            isDayArchive
                              ? 'magi-home-status-badge magi-home-status-badge-verified'
                              : 'rounded bg-emerald-600 text-white'
                          }`}>
                            人工已校
                          </span>
                        )}
                        {isExedraCategory(story.category) && story.official_tw && (
                          <span
                            className="magi-official-tw-badge"
                            title="台服官方中文"
                            aria-label="台服官方中文"
                          >
                            {story.official_tw_label?.trim() || '台服'}
                          </span>
                        )}
                        {progress < 100 && progress > 0 && (
                          <span className="text-[10px] opacity-60">{progress}%</span>
                        )}
                      </span>
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
          ? 'magi-home-mobile-category-nav flex overflow-x-auto p-2 gap-2 no-scrollbar bg-inherit border-b border-black/5'
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
            : isDayArchiveTheme(theme)
              ? 'magi-home-light-nav-active'
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
                : isDayArchiveTheme(theme)
                  ? 'magi-home-light-nav-item border-transparent'
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
  const [homeSidebarWidth, setHomeSidebarWidth] = useState(
    HOME_SIDEBAR_WIDTH_DEFAULT,
  );
  const homeSidebarWidthRef = useRef(HOME_SIDEBAR_WIDTH_DEFAULT);
  const homeSidebarResizeCleanupRef = useRef<(() => void) | null>(null);
  const [mobileReviewPlacement, setMobileReviewPlacement] =
    useState<MobileReviewPlacement>('floating');
  const [reviewDragPosition, setReviewDragPosition] =
    useState<{ x: number; y: number } | null>(null);
  const reviewDragStartRef = useRef<{
    pointerId: number;
    x: number;
    y: number;
  } | null>(null);
  const reviewDraggingRef = useRef(false);
  const reviewSuppressClickRef = useRef(false);
  const homeToolbarRef = useRef<HTMLDivElement>(null);
  const homeHeadingRef = useRef<HTMLDivElement>(null);

  const { theme, setTheme, lastCategory, setLastCategory } = useGlobal();
  const storySystem: StorySystem =
    lastCategory.startsWith('exedra_') ? 'exedra' : 'magireco';
  const compactSearchCharacters = Math.min(
    34,
    Math.max(
      12,
      Array.from(
        searchTerm ||
          (searchLoading ? '正在准备正文搜索' : '搜索标题或正文'),
      ).length + 3,
    ),
  );

  useEffect(() => {
    const restoreFrame = window.requestAnimationFrame(() => {
      let restoredWidth = HOME_SIDEBAR_WIDTH_DEFAULT;
      try {
        restoredWidth = parseStoredHomeSidebarWidth(
          window.localStorage.getItem(HOME_SIDEBAR_WIDTH_STORAGE_KEY),
        );
      } catch {
        // The default remains usable if storage is unavailable.
      }
      homeSidebarWidthRef.current = restoredWidth;
      setHomeSidebarWidth(restoredWidth);
    });
    return () => {
      window.cancelAnimationFrame(restoreFrame);
      homeSidebarResizeCleanupRef.current?.();
    };
  }, []);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(
        MOBILE_REVIEW_PLACEMENT_STORAGE_KEY,
      );
      if (stored === 'toolbar' || stored === 'floating') {
        // This one-time client preference hydration intentionally runs after mount.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setMobileReviewPlacement(stored);
      }
    } catch {
      // The floating placement remains the safe compact default.
    }
  }, []);

  const commitHomeSidebarWidth = useCallback((value: number) => {
    const bounded = clampHomeSidebarWidth(value);
    homeSidebarWidthRef.current = bounded;
    setHomeSidebarWidth(bounded);
    try {
      window.localStorage.setItem(HOME_SIDEBAR_WIDTH_STORAGE_KEY, String(bounded));
    } catch {
      // Resizing remains available even when persistence is blocked.
    }
  }, []);

  const beginHomeSidebarResize = useCallback((
    event: ReactPointerEvent<HTMLButtonElement>,
  ) => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    event.preventDefault();
    homeSidebarResizeCleanupRef.current?.();

    const startX = event.clientX;
    const startWidth = homeSidebarWidthRef.current;
    const onMove = (moveEvent: PointerEvent) => {
      const nextWidth = clampHomeSidebarWidth(
        startWidth + moveEvent.clientX - startX,
      );
      homeSidebarWidthRef.current = nextWidth;
      setHomeSidebarWidth(nextWidth);
    };
    const onEnd = () => {
      commitHomeSidebarWidth(homeSidebarWidthRef.current);
      homeSidebarResizeCleanupRef.current?.();
      homeSidebarResizeCleanupRef.current = null;
    };
    const cleanup = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onEnd);
      window.removeEventListener('pointercancel', onEnd);
      document.body.classList.remove('magi-sidebar-resizing');
    };

    homeSidebarResizeCleanupRef.current = cleanup;
    document.body.classList.add('magi-sidebar-resizing');
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onEnd, { once: true });
    window.addEventListener('pointercancel', onEnd, { once: true });
  }, [commitHomeSidebarWidth]);

  const commitMobileReviewPlacement = useCallback(
    (placement: MobileReviewPlacement) => {
      setMobileReviewPlacement(placement);
      try {
        window.localStorage.setItem(
          MOBILE_REVIEW_PLACEMENT_STORAGE_KEY,
          placement,
        );
      } catch {
        // Placement remains usable for the current visit.
      }
    },
    [],
  );

  const beginReviewButtonDrag = useCallback(
    (event: ReactPointerEvent<HTMLButtonElement>) => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      reviewDragStartRef.current = {
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
      };
      reviewDraggingRef.current = false;
      reviewSuppressClickRef.current = false;
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    [],
  );

  const moveReviewButtonDrag = useCallback(
    (event: ReactPointerEvent<HTMLButtonElement>) => {
      const start = reviewDragStartRef.current;
      if (!start || start.pointerId !== event.pointerId) return;
      if (
        !reviewDraggingRef.current
        && Math.hypot(event.clientX - start.x, event.clientY - start.y) < 8
      ) {
        return;
      }
      reviewDraggingRef.current = true;
      reviewSuppressClickRef.current = true;
      setReviewDragPosition({ x: event.clientX, y: event.clientY });
    },
    [],
  );

  const endReviewButtonDrag = useCallback(
    (event: ReactPointerEvent<HTMLButtonElement>) => {
      const start = reviewDragStartRef.current;
      if (!start || start.pointerId !== event.pointerId) return;
      if (reviewDraggingRef.current) {
        const toolbarRect = homeToolbarRef.current?.getBoundingClientRect();
        const headingRect = homeHeadingRef.current?.getBoundingClientRect();
        if (pointInsideRect(event.clientX, event.clientY, toolbarRect)) {
          commitMobileReviewPlacement('toolbar');
        } else if (pointInsideRect(event.clientX, event.clientY, headingRect)) {
          commitMobileReviewPlacement('floating');
        }
      }
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        // The browser may already have released capture.
      }
      reviewDragStartRef.current = null;
      reviewDraggingRef.current = false;
      setReviewDragPosition(null);
    },
    [commitMobileReviewPlacement],
  );

  const cancelReviewButtonDrag = useCallback(
    (event: ReactPointerEvent<HTMLButtonElement>) => {
      reviewDragStartRef.current = null;
      reviewDraggingRef.current = false;
      setReviewDragPosition(null);
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        // The browser may already have released capture.
      }
    },
    [],
  );

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
    const sourceUnverified = new Set(
      proofreadingStatus?.source_unverified_ids ??
        proofreadingStatus?.machine_translation_ids ??
        [],
    );
    const verified = new Set(proofreadingStatus?.verified_ids ?? []);
    return stories.map(story => ({
      ...story,
      source_unverified: sourceUnverified.has(story.id),
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
    searchSequenceRef.current += 1;
    workerRef.current = worker;
    worker.onmessage = (event: MessageEvent<SearchWorkerMessage>) => {
      if (workerRef.current !== worker) return;
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
      if (workerRef.current !== worker) return;
      setSearchLoading(false);
      setSearchError('正文搜索组件未能启动；标题搜索仍然可以使用。');
    };

    void getSearchIndexSources(controller.signal, storyIndexSha256, storySystem)
      .then((sources) => {
        if (controller.signal.aborted || workerRef.current !== worker) return;
        setSearchIndexBytes(sources[0]?.bytes ?? 0);
        worker.postMessage({ type: 'init', sources });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (workerRef.current !== worker) return;
        worker.postMessage({ type: 'init', sources: [] });
      });

    return () => {
      searchSequenceRef.current += 1;
      controller.abort();
      worker.terminate();
      if (workerRef.current === worker) workerRef.current = null;
    };
  }, [storyIndexSha256, storySystem]);

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
      if (onlyNeedsReview && (!story.source_unverified || story.human_verified)) {
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

  const switchToStorySystem = (nextSystem: StorySystem) => {
    if (nextSystem === storySystem) return;
    setLastCategory(DEFAULT_CATEGORY[nextSystem]);
    setSearchIndexBytes(0);
    if (nextSystem === 'exedra') setOnlyNeedsReview(false);
    updateSearchTerm('');
  };

  const switchStorySystem = () => {
    switchToStorySystem(storySystem === 'magireco' ? 'exedra' : 'magireco');
  };

  const renderMobileReviewButton = (
    placement: MobileReviewPlacement,
  ) => (
    <button
      type="button"
      data-placement={placement}
      aria-controls={machineReviewPanelContentId}
      aria-expanded={!machineReviewPanelCollapsed}
      aria-label={`${machineReviewPanelCollapsed ? '打开' : '收起'}校验清单，仍需 ${proofreadingStatus?.remaining ?? 0} 部`}
      title={
        placement === 'floating'
          ? '点击打开或收起；长按拖到顶部工具栏可吸附'
          : '点击打开或收起；长按拖到分类标题右侧可移回'
      }
      onPointerDown={beginReviewButtonDrag}
      onPointerMove={moveReviewButtonDrag}
      onPointerUp={endReviewButtonDrag}
      onPointerCancel={cancelReviewButtonDrag}
      onClick={event => {
        if (reviewSuppressClickRef.current) {
          event.preventDefault();
          reviewSuppressClickRef.current = false;
          return;
        }
        setMachineReviewPanelCollapsedPreference(
          !machineReviewPanelCollapsed,
        );
      }}
      style={
        reviewDragPosition
          ? {
              position: 'fixed',
              left: `${reviewDragPosition.x}px`,
              top: `${reviewDragPosition.y}px`,
              transform: 'translate(-50%, -50%)',
            }
          : undefined
      }
      className={`magi-home-mobile-review-button md:hidden ${
        reviewDragPosition ? 'is-dragging' : ''
      }`}
    >
      校验清单
    </button>
  );

  if (loading) {
    return (
      <div className="flex h-screen h-[100dvh] items-center justify-center opacity-50">
        数据加载中…
      </div>
    );
  }

  return (
    <div className={`magi-home-shell flex h-screen h-[100dvh] overflow-hidden ${
      theme === 'light'
        ? 'magi-home-light-root'
        : theme === 'paper'
          ? 'magi-home-paper-root'
          : ''
    }`}>
      <aside
        style={{
          '--magi-home-sidebar-width': `${homeSidebarWidth}px`,
        } as CSSProperties}
        className={`magi-home-sidebar relative z-20 hidden flex-shrink-0 flex-col border-r md:flex ${
          theme === 'dark'
            ? 'border-gray-800 bg-gray-900'
            : isDayArchiveTheme(theme)
              ? 'magi-home-light-sidebar'
              : 'border-black/5 bg-inherit'
        }`}
      >
        <div className="border-b border-inherit px-3 py-5">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2">
            <h1 className={`magi-reader-brand min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xl font-black ${
              isDayArchiveTheme(theme)
                ? 'magi-reader-brand-day-archive'
                : 'bg-clip-text text-transparent bg-gradient-to-r from-emerald-600 to-teal-500'
            }`}>
              MagiReader
            </h1>
            {storySystem === 'magireco' && proofreadingStatus && (
              <button
                type="button"
                aria-controls={machineReviewPanelContentId}
                aria-expanded={!machineReviewPanelCollapsed}
                aria-label={`${machineReviewPanelCollapsed ? '打开' : '收起'}校验清单，仍需 ${proofreadingStatus.remaining} 部`}
                title={`仍需人工校验 ${proofreadingStatus.remaining} 部`}
                onClick={() => setMachineReviewPanelCollapsedPreference(!machineReviewPanelCollapsed)}
                className={`inline-flex min-h-8 shrink-0 items-center rounded-md border px-1.5 py-1 text-[10px] font-black shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 ${
                  machineReviewPanelCollapsed
                    ? theme === 'dark'
                      ? 'border-amber-700 bg-amber-950/60 text-amber-200 hover:bg-amber-900/70'
                      : 'border-amber-300 bg-amber-50/80 text-amber-800 hover:bg-amber-100'
                    : 'border-amber-600 bg-amber-500 text-white hover:bg-amber-600'
                }`}
              >
                校验清单
              </button>
            )}
          </div>
          <p className="text-xs opacity-50 mt-1">Archive v3.1</p>
        </div>
        <CategoryNav
          categories={categories}
          activeCategory={lastCategory}
          searchActive={Boolean(normalizedQuery)}
          theme={theme}
          onSelect={selectCategory}
        />
        <button
          type="button"
          role="separator"
          aria-orientation="vertical"
          aria-label={`调整主目录宽度，当前 ${homeSidebarWidth} 像素`}
          aria-valuemin={HOME_SIDEBAR_WIDTH_MIN}
          aria-valuemax={HOME_SIDEBAR_WIDTH_MAX}
          aria-valuenow={homeSidebarWidth}
          title="拖动调整主目录宽度；双击恢复默认"
          onPointerDown={beginHomeSidebarResize}
          onDoubleClick={() => commitHomeSidebarWidth(HOME_SIDEBAR_WIDTH_DEFAULT)}
          onKeyDown={event => {
            if (event.key === 'ArrowLeft') {
              event.preventDefault();
              commitHomeSidebarWidth(homeSidebarWidth - HOME_SIDEBAR_WIDTH_STEP);
            } else if (event.key === 'ArrowRight') {
              event.preventDefault();
              commitHomeSidebarWidth(homeSidebarWidth + HOME_SIDEBAR_WIDTH_STEP);
            } else if (event.key === 'Home') {
              event.preventDefault();
              commitHomeSidebarWidth(HOME_SIDEBAR_WIDTH_MIN);
            } else if (event.key === 'End') {
              event.preventDefault();
              commitHomeSidebarWidth(HOME_SIDEBAR_WIDTH_MAX);
            }
          }}
          className="magi-sidebar-resize-handle absolute inset-y-0 -right-1 z-30 hidden w-2 cursor-col-resize touch-none md:block"
        />
      </aside>

      <main className="flex-1 flex flex-col min-w-0 bg-transparent">
        <header
          className={`border-b p-3 backdrop-blur z-10 flex flex-col gap-3 ${
            theme === 'dark'
              ? 'border-gray-800 bg-gray-900/90'
              : isDayArchiveTheme(theme)
                ? 'magi-home-light-toolbar'
                : 'border-black/5 bg-white/60'
          }`}
        >
          <div
            ref={homeToolbarRef}
            className={`magi-home-toolbar-row flex flex-wrap items-start justify-between gap-2 md:items-center ${
              reviewDragPosition ? 'magi-home-review-drop-target' : ''
            }`}
          >
            <div className="magi-home-toolbar-controls relative flex min-w-0 flex-1 flex-wrap items-center gap-2">
              <div
                className="magi-home-search-shell relative min-w-0"
                style={{
                  '--magi-home-search-width': `${compactSearchCharacters}em`,
                } as CSSProperties}
              >
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none opacity-50">
                  <Search size={16} />
                </div>
                <input
                  type="search"
                  aria-label="搜索剧情标题或正文"
                  placeholder={searchLoading ? '正在准备正文搜索…' : '搜索标题或正文…'}
                  className={`magi-home-search-input block h-10 w-full border rounded-lg py-2 pl-9 pr-3 text-sm leading-6 outline-none transition-all ${
                    theme === 'dark'
                      ? 'bg-gray-800 border-gray-700'
                      : isDayArchiveTheme(theme)
                        ? 'magi-home-light-control'
                        : 'bg-white/50 border-black/10'
                  }`}
                  value={searchTerm}
                  onChange={(event) => updateSearchTerm(event.target.value)}
                />
              </div>

              <div className={`flex shrink-0 items-center rounded-lg border p-0.5 ${
                isDayArchiveTheme(theme)
                  ? 'magi-home-light-control'
                  : 'border-gray-200 bg-gray-100 dark:border-gray-700 dark:bg-gray-800'
              }`}>
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
                        ? isDayArchiveTheme(theme)
                          ? 'magi-home-light-button-active'
                          : 'bg-white dark:bg-gray-600 text-blue-600 dark:text-blue-300 shadow-sm'
                        : isDayArchiveTheme(theme)
                          ? 'magi-home-light-segment'
                          : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>

              <label
                className={`flex items-center gap-1 px-2 rounded cursor-pointer border ${
                  isDayArchiveTheme(theme)
                    ? searchJp
                      ? 'magi-home-light-button-active'
                      : 'magi-home-light-button opacity-70'
                    : searchJp
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
                    : isDayArchiveTheme(theme)
                      ? 'magi-home-light-button'
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
                      : isDayArchiveTheme(theme)
                        ? 'magi-home-light-button-active'
                        : 'border-violet-300 bg-violet-100 text-violet-800 hover:bg-violet-200'
                    : theme === 'dark'
                      ? 'border-blue-800 bg-blue-900/30 text-blue-300 hover:bg-blue-800'
                      : isDayArchiveTheme(theme)
                        ? 'magi-home-light-button'
                        : 'border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100'
                }`}
              >
                <Book size={14} />
                {storySystem === 'magireco' ? 'Exedra' : 'Magia Record'}
              </button>
              {storySystem === 'magireco'
                && proofreadingStatus
                && mobileReviewPlacement === 'toolbar'
                && renderMobileReviewButton('toolbar')}
            </div>

            <div
              className={`magi-home-theme-switcher flex gap-1 p-1 rounded-full self-end md:self-auto ${
                theme === 'dark'
                  ? 'bg-black/20'
                  : isDayArchiveTheme(theme)
                    ? 'magi-home-light-control'
                    : 'bg-black/5'
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
                    theme === option.key
                      ? isDayArchiveTheme(theme)
                        ? 'magi-home-light-theme-active'
                        : 'bg-white shadow text-black'
                      : isDayArchiveTheme(theme)
                        ? 'magi-home-light-segment opacity-55'
                        : 'opacity-40'
                  }`}
                >
                  <option.icon size={14} />
                </button>
              ))}
            </div>
          </div>

          {searchMode !== 'title' && searchIndexBytes > 0 && (
            <p className="text-[11px] opacity-65">
              当前范围：{SEARCH_INDEX_SCOPE_CONFIG[storySystem].label}。正文搜索会在首次使用时按需加载约{' '}
              {(searchIndexBytes / (1024 * 1024)).toFixed(1)} MiB 索引。
              不会加载另一范围的正文对象；内存较小的设备请使用“标题”模式。
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

        <div className="magi-home-catalog flex-1 overflow-y-auto p-3 md:p-6 scroll-smooth">
          <div className="max-w-7xl mx-auto">
            {storySystem === 'magireco' && proofreadingStatus && (
              <section
                id={machineReviewPanelContentId}
                hidden={machineReviewPanelCollapsed}
                className={`mb-5 rounded-2xl border p-4 shadow-sm ${
                  theme === 'dark'
                    ? 'border-amber-800 bg-amber-950/40 text-amber-100'
                    : isDayArchiveTheme(theme)
                      ? 'magi-home-review-panel'
                      : 'border-amber-300 bg-gradient-to-r from-amber-50 to-emerald-50 text-gray-900'
                }`}
              >
                <div>
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-base font-black">来源待核验人工校验清单</h2>
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
                            className={`h-full rounded-full transition-all ${
                              isDayArchiveTheme(theme) ? 'magi-home-review-progress' : 'bg-emerald-500'
                            }`}
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
                        {onlyNeedsReview ? '显示当前分类全部剧情' : '只看来源待核验剧情'}
                      </button>
                      <Link
                        href="/review/machine-translations"
                        className="rounded-lg bg-amber-600 px-3 py-2 text-xs font-black text-white hover:bg-amber-700"
                      >
                        管理待核验标记
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
                        aria-label="收起来源待核验人工校验清单"
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

            <div
              ref={homeHeadingRef}
              className={`magi-home-section-heading-row ${
                reviewDragPosition ? 'magi-home-review-drop-target' : ''
              }`}
            >
              <h2 className={`px-1 text-xl font-bold opacity-80 ${
                isDayArchiveTheme(theme)
                  ? 'magi-home-light-section-title'
                  : ''
              }`}>
                {normalizedQuery
                  ? `搜索结果：“${searchTerm}” ${searchJp ? '（含日文）' : ''}`
                  : CATEGORY_CONFIG[lastCategory]?.label ?? lastCategory}
              </h2>
              {storySystem === 'magireco'
                && proofreadingStatus
                && mobileReviewPlacement === 'floating'
                && renderMobileReviewButton('floating')}
            </div>

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
