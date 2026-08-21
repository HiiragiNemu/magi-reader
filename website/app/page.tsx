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
  Settings,
} from 'lucide-react';
import { useGlobal } from '@/app/providers';
import { characterFolderColorFor } from '@/app/config/dictionary';
import { type Story } from '@/components/Sidebar';
import AboutModal from '@/components/AboutModal';
import LocalStoryPicker from '@/components/LocalStoryPicker';
import MadeInMagiusLogo from '@/components/MadeInMagiusLogo';
import SiteSettingsWindow from '@/components/SiteSettingsWindow';
import { normalizeSearchText } from '@/lib/search';
import { loadStoryIndex } from '@/lib/story-index';
import { storySectionDetails } from '@/lib/story-parser';
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

type SourceVisualStatus =
  | 'exedra-official-tw'
  | 'exedra-human-cn'
  | 'magireco-source-unverified'
  | 'magireco-human-verified'
  | 'magireco-human-cn'
  | 'neutral';

type GroupSourceProgress = {
  humanPercent: number;
  verifiedPercent: number;
  translatedPercent: number;
};

type CategorySourceFilter =
  | 'all'
  | 'human-cn'
  | 'machine-verified'
  | 'machine-unverified';

type CategorySourceFilterCounts = Record<CategorySourceFilter, number>;
type CategorySourceProgressMetric = {
  value: number;
  maximum: number;
  chapters: number;
  available: boolean;
};
type CategorySourceFilterProgress = Record<
  CategorySourceFilter,
  CategorySourceProgressMetric
>;
type CategorySourceConnections = ReadonlyMap<
  string,
  ReadonlySet<CategorySourceFilter>
>;

const MAX_CONNECTED_CATEGORIES = 3;
const CATEGORY_ANCHOR_INDEX_BY_SLOT = [1, 0, 2] as const;

const CATEGORY_SOURCE_FILTERS: ReadonlyArray<{
  value: CategorySourceFilter;
  label: string;
}> = [
  { value: 'all', label: '全部' },
  { value: 'human-cn', label: '人工汉化' },
  { value: 'machine-verified', label: '机翻已校对' },
  { value: 'machine-unverified', label: '机翻未校对' },
];
const ALL_SOURCE_CONNECTION: ReadonlySet<CategorySourceFilter> = new Set(['all']);

const emptyCategorySourceFilterCounts = (): CategorySourceFilterCounts => ({
  'all': 0,
  'human-cn': 0,
  'machine-verified': 0,
  'machine-unverified': 0,
});

const emptyCategorySourceFilterProgress = (
  sourceStatusKnown: boolean,
): CategorySourceFilterProgress => ({
  'all': { value: 0, maximum: 0, chapters: 0, available: true },
  'human-cn': { value: 0, maximum: 0, chapters: 0, available: sourceStatusKnown },
  'machine-verified': { value: 0, maximum: 0, chapters: 0, available: sourceStatusKnown },
  'machine-unverified': { value: 0, maximum: 0, chapters: 0, available: sourceStatusKnown },
});

const categorySourceProgressPercent = (
  metric: CategorySourceProgressMetric,
): number => metric.available && metric.maximum > 0
  ? Math.min(100, Math.max(0, Math.round((metric.value / metric.maximum) * 100)))
  : 0;

const categorySourceFilterProgressForStories = (
  stories: readonly Story[],
  sourceStatusKnown: boolean,
): CategorySourceFilterProgress => {
  const progress = emptyCategorySourceFilterProgress(sourceStatusKnown);
  for (const story of stories) {
    const translationPercent = Math.min(100, Math.max(0, storyProgress(story)));
    progress.all.value += translationPercent;
    progress.all.maximum += 100;
    progress.all.chapters += 1;

    // story.percent is the only translation-progress measure uniformly exposed
    // by the page Story type, so categories use equal story/chapter weight.
    if (!sourceStatusKnown) continue;

    // Official Traditional Chinese chapters are not counted as fan translation.
    if (!story.source_unverified && !story.official_tw) {
      progress['human-cn'].value += translationPercent;
      progress['human-cn'].maximum += 100;
      progress['human-cn'].chapters += 1;
    }

    // Review state is only available as one verified boolean per source-unverified
    // story, so the two existing machine-review buckets are complementary shares.
    if (story.source_unverified) {
      progress['machine-verified'].maximum += 1;
      progress['machine-verified'].chapters += 1;
      progress['machine-unverified'].maximum += 1;
      progress['machine-unverified'].chapters += 1;
      if (story.human_verified) {
        progress['machine-verified'].value += 1;
      } else {
        progress['machine-unverified'].value += 1;
      }
    }
  }
  return progress;
};

const categorySourceProgressText = (
  filter: CategorySourceFilter,
  metric: CategorySourceProgressMetric,
  percent: number,
): string => {
  if (!metric.available) {
    return `${CATEGORY_SOURCE_FILTERS.find(option => option.value === filter)?.label ?? filter}进度数据尚未加载。`;
  }
  if (metric.maximum === 0) {
    return `${CATEGORY_SOURCE_FILTERS.find(option => option.value === filter)?.label ?? filter}进度 0%，暂无可计算章节。`;
  }
  if (filter === 'all') {
    return `全部剧情翻译进度 ${percent}%，按 ${metric.chapters} 个章节的现有翻译百分比等权聚合。`;
  }
  if (filter === 'human-cn') {
    return `人工汉化覆盖进度 ${percent}%，按 ${metric.chapters} 个未标记来源待核验且非官方繁中的目标章节等权聚合现有翻译百分比。`;
  }
  if (filter === 'machine-verified') {
    return `机翻已校对栏占比 ${percent}%，${metric.value}/${metric.maximum} 个来源待核验章节具有整故事已校对标记，按故事级布尔校对状态聚合。`;
  }
  return `机翻未校对栏占比 ${percent}%，${metric.value}/${metric.maximum} 个来源待核验章节尚无整故事已校对标记，按故事级布尔校对状态聚合。`;
};

const translationProgressStatus = (percent: number): TranslationProgressStatus =>
  percent === 0 ? 'none' : percent === 100 ? 'complete' : 'partial';

const storySourceVisualStatus = (story: Story): SourceVisualStatus => {
  if (isExedraCategory(story.category)) {
    if (story.official_tw) return 'exedra-official-tw';
    if (story.has_cn && storyProgress(story) === 100) return 'exedra-human-cn';
    return 'neutral';
  }
  if (story.source_unverified && !story.human_verified) {
    return 'magireco-source-unverified';
  }
  if (story.source_unverified && story.human_verified) {
    return 'magireco-human-verified';
  }
  if (story.has_cn && !story.source_unverified && storyProgress(story) === 100) {
    return 'magireco-human-cn';
  }
  return 'neutral';
};

const groupSourceVisualStatus = (stories: readonly Story[]): SourceVisualStatus => {
  const statuses = new Set(stories.map(storySourceVisualStatus));
  for (const status of [
    'magireco-source-unverified',
    'magireco-human-verified',
    'exedra-official-tw',
    'exedra-human-cn',
    'magireco-human-cn',
  ] as const) {
    if (statuses.has(status)) return status;
  }
  return 'neutral';
};

const groupSourceProgressForStories = (
  stories: readonly Story[],
): GroupSourceProgress => {
  const maximum = stories.length * 100;
  let humanValue = 0;
  let verifiedValue = 0;

  for (const story of stories) {
    const translationPercent = Math.min(100, Math.max(0, storyProgress(story)));
    if (story.source_unverified) {
      if (story.human_verified) verifiedValue += translationPercent;
    } else if (!story.official_tw) {
      humanValue += translationPercent;
    }
  }

  const toPercent = (value: number): number => maximum > 0
    ? Math.round((value / maximum) * 1000) / 10
    : 0;

  return {
    humanPercent: toPercent(humanValue),
    verifiedPercent: toPercent(verifiedValue),
    translatedPercent: toPercent(humanValue + verifiedValue),
  };
};

const storyMatchesCategorySourceFilter = (
  story: Story,
  filter: CategorySourceFilter,
): boolean => {
  if (filter === 'all') return true;
  if (filter === 'human-cn') {
    return Boolean(
      story.has_cn
      && !story.source_unverified
      && !story.official_tw,
    );
  }
  if (filter === 'machine-verified') {
    return Boolean(story.source_unverified && story.human_verified);
  }
  if (filter === 'machine-unverified') {
    return Boolean(story.source_unverified && !story.human_verified);
  }
  return false;
};

const storyMatchesCategorySourceFilters = (
  story: Story,
  filters: ReadonlySet<CategorySourceFilter>,
): boolean => filters.has('all')
  || Array.from(filters).some(filter => storyMatchesCategorySourceFilter(story, filter));

function FolderCard({ group, theme }: { group: StoryGroup; theme: string }) {
  const hasSearchMatches = Boolean(
    group.matchSnippets && Object.keys(group.matchSnippets).length > 0,
  );
  /* Folders and their nested Episode lists stay collapsed by default;
     search matches expand only the outer folder. */
  const [manuallyOpen, setManuallyOpen] = useState(hasSearchMatches);
  const [openStoryKeys, setOpenStoryKeys] = useState<Set<string>>(
    () => new Set(),
  );
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
  const groupSourceStatus = groupSourceVisualStatus(group.items);
  const groupSourceProgress = groupSourceProgressForStories(group.items);
  const groupSourceProgressEnabled = !isExedraCategory(group.category)
    && groupSourceProgress.translatedPercent > 0;

  const isDark = theme === 'dark';
  const isDayArchive = isDayArchiveTheme(theme);
  let headerClass = '';
  let progressClass = '';

  if (isDark) {
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
      data-source-status={groupSourceStatus}
      data-source-progress={groupSourceProgressEnabled ? 'true' : 'false'}
      data-human-progress-percent={groupSourceProgress.humanPercent}
      data-verified-progress-percent={groupSourceProgress.verifiedPercent}
      style={{
        '--magi-folder-human-progress-end': `${groupSourceProgress.humanPercent}%`,
        '--magi-folder-translated-progress-end': `${groupSourceProgress.translatedPercent}%`,
      } as CSSProperties}
      className={`magi-folder-source-card break-inside-avoid mb-3 rounded-lg border shadow-sm transition-all ${
        isDark
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
        className={`magi-card-heading-grid magi-folder-heading-flow w-full px-3 py-3 text-left transition-colors border-b ${
          isOpen ? 'border-inherit' : 'border-transparent'
        } ${headerClass}`}
      >
        <span className="magi-card-title-flow flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="mt-0.5 flex-shrink-0">
            {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </span>
          {folderId && (
            <span className="magi-folder-id font-mono text-xs opacity-70 bg-black/10 px-1 rounded flex-shrink-0 mt-0.5">
              {folderId}
            </span>
          )}
          <span
            className="magi-folder-display-title min-w-0 break-words text-sm font-bold leading-tight"
            style={{ color: characterFolderColorFor(group.category, displayTitle) }}
          >
            {displayTitle}
          </span>
          <span className="magi-card-meta">
          {sourceUnverifiedPending > 0 && (
            <span className={`magi-home-status-badge magi-home-status-badge-unverified shrink-0 px-2 py-0.5 text-[10px] font-black ${
              isDayArchive
                ? ''
                : 'rounded-full bg-amber-500 text-white'
            }`}>
              待核验 {sourceUnverifiedPending}
            </span>
          )}
          {sourceUnverifiedPending === 0 && sourceUnverifiedVerified > 0 && (
            <span className={`magi-home-status-badge magi-home-status-badge-verified shrink-0 px-2 py-0.5 text-[10px] font-black ${
              isDayArchive
                ? ''
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
          {groupSourceStatus === 'exedra-human-cn' && (
            <span className="magi-source-status-badge magi-source-status-badge-exedra-human">
              人工中文
            </span>
          )}
          <span className={`shrink-0 font-mono text-[10px] ${progressClass}`}>
            {avgPercent}%
          </span>
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
          <div className="magi-home-folder-tree">
            {[...group.items]
              .sort((a, b) => NATURAL_COLLATOR.compare(a.id, b.id))
              .map((story, storyIndex) => {
                const label = getDisplayLabel(story);
                const episodeLinks = Array.from(new Map(
                  (story.sections ?? []).map((section, sectionIndex) => {
                    const details = storySectionDetails(section);
                    const sectionNumber = section.match(/Section\s*(\d+)/i)?.[1]
                      || String(sectionIndex + 1);
                    const branchNumber = section.match(
                      /(?:Branch|分支|group)\s*_?\s*(\d+)/i,
                    )?.[1];
                    const officialTitle = isExedraCategory(story.category)
                      ? story.official_tw_section_titles?.[sectionIndex]?.trim()
                      : '';
                    return [
                      details.anchorId,
                      {
                        ...details,
                        title:
                          officialTitle
                          || `Episode${sectionNumber}${branchNumber ? ` · 分支${branchNumber}` : ''}`,
                      },
                    ] as const;
                  }),
                ).values());
                const progress = storyProgress(story);
                const itemProgressStatus = translationProgressStatus(progress);
                const sourceVisualStatus = storySourceVisualStatus(story);
                const snippet = group.matchSnippets?.[story.id];
                const sourceUnverifiedPendingStory =
                  story.source_unverified && !story.human_verified;
                const sourceMarkerClass = sourceUnverifiedPendingStory
                  ? isDayArchive
                    ? 'magi-home-light-story-unverified'
                    : ''
                  : story.source_unverified && story.human_verified && isDayArchive
                    ? 'magi-home-light-story-verified'
                    : '';
                const buttonClass = isDark
                  ? progress > 0
                    ? 'bg-emerald-900/30 border-emerald-700 text-emerald-400'
                    : 'bg-gray-800 border-gray-700 text-gray-500'
                  : isDayArchive
                    ? progress > 0
                      ? `magi-home-light-story-link ${sourceMarkerClass}`
                      : `magi-home-light-story-link magi-home-light-story-link-empty ${sourceMarkerClass}`
                    : progress > 0
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                      : 'bg-white border-gray-200 text-gray-400';
                const storyHref = `/reader/${encodeURIComponent(story.id)}?cn=${encodeURIComponent(
                  story.path_cn || '',
                )}&jp=${encodeURIComponent(story.path_jp || '')}`;
                const storyKey = `${story.id}:${story.path_cn ?? ''}:${story.path_jp ?? ''}`;
                const storyContentId = `${contentId}-story-${storyIndex}`;
                const isStoryOpen = openStoryKeys.has(storyKey);

                return (
                  <div
                    key={storyKey}
                    className="magi-home-story-tree-node"
                    data-tree-state={isStoryOpen ? 'open' : 'closed'}
                  >
                    <span className="magi-home-story-tree-junction" aria-hidden="true" />
                    <article
                      data-translation-status={itemProgressStatus}
                      data-source-status={sourceVisualStatus}
                      className={`magi-story-source-link max-w-full min-w-0 overflow-hidden rounded border transition-all hover:scale-[1.01] ${buttonClass} ${
                        snippet ? 'w-full' : ''
                      }`}
                    >
                    <div className="relative z-10 flex min-w-0 items-stretch">
                      {episodeLinks.length > 0 && (
                        <button
                          type="button"
                          aria-controls={storyContentId}
                          aria-expanded={isStoryOpen}
                          aria-label={`${isStoryOpen ? '收起' : '展开'} ${label} Episode`}
                          onClick={() => {
                            setOpenStoryKeys(current => {
                              const next = new Set(current);
                              if (next.has(storyKey)) {
                                next.delete(storyKey);
                              } else {
                                next.add(storyKey);
                              }
                              return next;
                            });
                          }}
                          className="magi-home-story-toggle flex shrink-0 items-center justify-center px-2 transition-opacity hover:opacity-100"
                        >
                          {isStoryOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                        </button>
                      )}
                      <Link
                        href={storyHref}
                        prefetch={false}
                        className="magi-home-story-primary-link block min-w-0 flex-1"
                      >
                        <div className="magi-card-heading-grid min-w-0 px-2 py-1.5">
                          <span className="magi-card-title-flow magi-home-story-tree-title break-words font-mono text-xs font-bold">
                            <span
                              className="magi-home-tree-folder-icon"
                              data-open={isStoryOpen ? 'true' : 'false'}
                              aria-hidden="true"
                            />
                            <span className="magi-home-story-tree-label">#{label}</span>
                          </span>
                          <span className="magi-card-meta">
                          {sourceUnverifiedPendingStory && (
                            <span className={`magi-home-status-badge magi-home-status-badge-unverified px-1.5 py-0.5 text-[9px] font-black ${
                              isDayArchive
                                ? ''
                                : 'rounded bg-amber-500 text-white'
                            }`}>
                              来源待核验
                            </span>
                          )}
                          {story.source_unverified && story.human_verified && (
                            <span className={`magi-home-status-badge magi-home-status-badge-verified px-1.5 py-0.5 text-[9px] font-black ${
                              isDayArchive
                                ? ''
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
                          {sourceVisualStatus === 'exedra-human-cn' && (
                            <span className="magi-source-status-badge magi-source-status-badge-exedra-human">
                              人工中文
                            </span>
                          )}
                          {progress < 100 && progress > 0 && (
                            <span className="text-[10px] opacity-60">{progress}%</span>
                          )}
                          </span>
                        </div>
                        {snippet && (
                          <div
                            className={`magi-home-search-snippet reader-font-cn-body px-2 py-1.5 text-xs font-serif border-t ${
                              isDark
                                ? 'border-white/10 text-gray-300'
                                : 'border-black/5 text-gray-600'
                            }`}
                          >
                            …{snippet}…
                          </div>
                        )}
                      </Link>
                    </div>
                    {episodeLinks.length > 0 && isStoryOpen && (
                      <nav
                        id={storyContentId}
                        aria-label={`${label} Episode`}
                        className="magi-home-episode-list relative z-10 flex flex-wrap gap-1 border-t border-current/10 px-2 py-1 text-[10px] leading-relaxed"
                      >
                        {episodeLinks.map(episode => (
                          <Link
                            key={episode.anchorId}
                            href={`${storyHref}&section=${encodeURIComponent(episode.anchorId)}#${episode.anchorId}`}
                            prefetch={false}
                            data-section-anchor={episode.anchorId}
                            className="magi-home-episode-link rounded px-1.5 py-0.5 opacity-70 transition hover:opacity-100 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1"
                          >
                            <span className="magi-home-episode-branch" aria-hidden="true" />
                            <span className="magi-home-tree-episode-node" aria-hidden="true" />
                            <span className="magi-home-episode-label">{episode.title}</span>
                          </Link>
                        ))}
                      </nav>
                    )}
                    </article>
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}

function StableFolderColumns({
  groups,
  theme,
}: {
  groups: StoryGroup[];
  theme: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [columnCount, setColumnCount] = useState(1);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const updateColumnCount = () => {
      const width = container.clientWidth;
      const rootFontSize = Number.parseFloat(
        window.getComputedStyle(document.documentElement).fontSize,
      ) || 16;
      const minimumColumnWidth = 15 * rootFontSize;
      const gap = 0.58 * rootFontSize;
      const nextColumnCount = width <= 40 * rootFontSize
        ? 1
        : Math.max(
            1,
            Math.min(8, Math.floor((width + gap) / (minimumColumnWidth + gap))),
          );

      setColumnCount(current => current === nextColumnCount ? current : nextColumnCount);
    };

    updateColumnCount();
    const resizeObserver = new ResizeObserver(updateColumnCount);
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  const columns = useMemo(() => {
    const nextColumns = Array.from(
      { length: Math.max(1, columnCount) },
      () => [] as StoryGroup[],
    );
    groups.forEach((group, index) => {
      nextColumns[index % nextColumns.length].push(group);
    });
    return nextColumns;
  }, [columnCount, groups]);

  return (
    <div
      ref={containerRef}
      className="magi-home-folder-columns"
      style={{
        '--magi-folder-column-count': columnCount,
      } as CSSProperties}
    >
      {columns.map((column, columnIndex) => (
        <div
          key={`stable-folder-column-${columnIndex}`}
          className="magi-home-folder-column"
        >
          {column.map(group => (
            <FolderCard key={group.key} group={group} theme={theme} />
          ))}
        </div>
      ))}
    </div>
  );
}

type CategoryNavProps = {
  categories: string[];
  activeCategory: string;
  selectedCategories: ReadonlySet<string>;
  sourceConnections: CategorySourceConnections;
  sourceFilterCounts: Record<string, CategorySourceFilterCounts>;
  sourceFilterProgress: Record<string, CategorySourceFilterProgress>;
  searchActive: boolean;
  theme: string;
  mobile?: boolean;
  onSelect: (category: string) => void;
  onToggleCategory: (category: string) => void;
  onSelectSourceFilter: (filter: CategorySourceFilter) => void;
  onToggleSourceFilter: (
    category: string,
    filter: CategorySourceFilter,
  ) => void;
};

function CategoryNav({
  categories,
  activeCategory,
  selectedCategories,
  sourceConnections,
  sourceFilterCounts,
  sourceFilterProgress,
  searchActive,
  theme,
  mobile = false,
  onSelect,
  onToggleCategory,
  onSelectSourceFilter,
  onToggleSourceFilter,
}: CategoryNavProps) {
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const navRef = useRef<HTMLElement | null>(null);
  const triggerRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const categorySelectRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const optionRefs = useRef<Array<HTMLDivElement | null>>([]);
  const anchorRefs = useRef<Array<Array<HTMLButtonElement | null>>>([]);
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const overlayCategory = !mobile
    && !searchActive
    && expandedCategory === activeCategory
    ? expandedCategory
    : null;
  const [overlayLayout, setOverlayLayout] = useState({
    top: 0,
    left: 0,
    width: 0,
    height: 0,
    menuLeft: 0,
    menuWidth: 0,
  });
  const [connectorGeometry, setConnectorGeometry] = useState<{
    overlayCategory: string | null;
    width: number;
    height: number;
    lines: Array<{
      category: string;
      optionIndex: number;
      x1: number;
      y1: number;
      x2: number;
      y2: number;
      anchorIndex: number;
      distance: number;
      slope: number;
    }>;
  }>({ overlayCategory: null, width: 0, height: 0, lines: [] });

  const connectedCategoryOrder = useMemo(
    () => Array.from(selectedCategories).slice(0, MAX_CONNECTED_CATEGORIES),
    [selectedCategories],
  );

  const updateOverlayLayout = useCallback(() => {
    const nav = navRef.current;
    if (!nav || !overlayCategory) return;

    const navRect = nav.getBoundingClientRect();
    const viewportWidth = nav.clientWidth;
    const viewportHeight = nav.clientHeight;
    if (viewportWidth <= 0 || viewportHeight <= 0) return;

    const widestTriggerRight = Array.from(triggerRefs.current.values()).reduce(
      (right, trigger) => Math.max(
        right,
        trigger.getBoundingClientRect().right - navRect.left,
      ),
      0,
    );
    const rightInset = 8;
    const connectorGap = 8;
    const minimumMenuWidth = Math.min(50, Math.max(1, viewportWidth - rightInset));
    const desiredMenuWidth = Math.min(56, Math.max(1, viewportWidth - rightInset * 2));
    const rightAlignedLeft = Math.max(
      0,
      viewportWidth - rightInset - desiredMenuWidth,
    );
    const blankAreaLeft = Math.max(0, widestTriggerRight + connectorGap);
    const latestMenuLeft = Math.min(
      Math.max(rightAlignedLeft, blankAreaLeft),
      Math.max(0, viewportWidth - rightInset - minimumMenuWidth),
    );
    const latestLayout = {
      top: nav.scrollTop,
      left: nav.scrollLeft,
      width: viewportWidth,
      height: viewportHeight,
      menuLeft: latestMenuLeft,
      menuWidth: Math.max(1, viewportWidth - rightInset - latestMenuLeft),
    };

    setOverlayLayout(current => (
      current.top === latestLayout.top
      && current.left === latestLayout.left
      && current.width === latestLayout.width
      && current.height === latestLayout.height
      && current.menuLeft === latestLayout.menuLeft
      && current.menuWidth === latestLayout.menuWidth
        ? current
        : latestLayout
    ));
  }, [overlayCategory]);

  const measureConnectorGeometry = useCallback(() => {
    const svg = svgRef.current;
    const anchors = CATEGORY_SOURCE_FILTERS.map((_, optionIndex) => (
      [0, 1, 2].map(anchorIndex => (
        anchorRefs.current[optionIndex]?.[anchorIndex] ?? null
      ))
    ));
    if (
      !svg
      || connectedCategoryOrder.length === 0
      || connectedCategoryOrder.some(category => !categorySelectRefs.current.get(category))
      || anchors.some(optionAnchors => optionAnchors.some(anchor => !anchor))
    ) return;

    const svgRect = svg.getBoundingClientRect();
    if (svgRect.width <= 0 || svgRect.height <= 0) return;

    const latestGeometry = {
      overlayCategory,
      width: svgRect.width,
      height: svgRect.height,
      lines: connectedCategoryOrder.flatMap((category, categorySlot) => {
        const trigger = categorySelectRefs.current.get(category)!;
        const triggerRect = trigger.getBoundingClientRect();
        const x1 = triggerRect.left + triggerRect.width / 2 - svgRect.left;
        const y1 = triggerRect.top + triggerRect.height / 2 - svgRect.top;
        const anchorIndex = CATEGORY_ANCHOR_INDEX_BY_SLOT[categorySlot];
        return CATEGORY_SOURCE_FILTERS.map((_, optionIndex) => {
          const anchor = anchors[optionIndex][anchorIndex]!;
          const anchorRect = anchor.getBoundingClientRect();
          const x2 = anchorRect.left + anchorRect.width / 2 - svgRect.left;
          const y2 = anchorRect.top + anchorRect.height / 2 - svgRect.top;
          const dx = x2 - x1;
          const dy = y2 - y1;
          return {
            category,
            optionIndex,
            x1,
            y1,
            x2,
            y2,
            anchorIndex,
            distance: Math.hypot(dx, dy),
            slope: dy / (Math.abs(dx) < 0.001 ? 0.001 : dx),
          };
        });
      }),
    };

    setConnectorGeometry(current => {
      const unchanged = current.overlayCategory === latestGeometry.overlayCategory
        && current.width === latestGeometry.width
        && current.height === latestGeometry.height
        && current.lines.length === latestGeometry.lines.length
        && current.lines.every((line, index) => {
          const latestLine = latestGeometry.lines[index];
          return line.x1 === latestLine.x1
            && line.category === latestLine.category
            && line.optionIndex === latestLine.optionIndex
            && line.y1 === latestLine.y1
            && line.x2 === latestLine.x2
            && line.y2 === latestLine.y2
            && line.anchorIndex === latestLine.anchorIndex
            && line.distance === latestLine.distance
            && line.slope === latestLine.slope;
        });
      return unchanged ? current : latestGeometry;
    });
  }, [connectedCategoryOrder, overlayCategory]);

  useEffect(() => {
    if (!overlayCategory) return;

    const nav = navRef.current;
    if (!nav) return;
    let animationFrame = 0;
    const refreshGeometry = () => {
      updateOverlayLayout();
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(measureConnectorGeometry);
    };

    refreshGeometry();
    nav.addEventListener('scroll', refreshGeometry, { passive: true });
    window.addEventListener('resize', refreshGeometry);
    const resizeObserver = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(refreshGeometry);
    if (resizeObserver) {
      resizeObserver.observe(nav);
      triggerRefs.current.forEach(trigger => resizeObserver.observe(trigger));
      categorySelectRefs.current.forEach(selector => resizeObserver.observe(selector));
      optionRefs.current.forEach((option) => {
        if (option) resizeObserver.observe(option);
      });
      anchorRefs.current.forEach((optionAnchors) => {
        optionAnchors.forEach((anchor) => {
          if (anchor) resizeObserver.observe(anchor);
        });
      });
    }

    return () => {
      window.cancelAnimationFrame(animationFrame);
      nav.removeEventListener('scroll', refreshGeometry);
      window.removeEventListener('resize', refreshGeometry);
      resizeObserver?.disconnect();
    };
  }, [
    categories,
    measureConnectorGeometry,
    overlayCategory,
    updateOverlayLayout,
  ]);

  useEffect(() => {
    if (!overlayCategory) return;
    const animationFrame = window.requestAnimationFrame(measureConnectorGeometry);
    return () => window.cancelAnimationFrame(animationFrame);
  }, [measureConnectorGeometry, overlayCategory, overlayLayout]);

  const overlayConfig = overlayCategory
    ? CATEGORY_CONFIG[overlayCategory] || { label: overlayCategory, icon: Folder }
    : null;
  const disabledBranchPalette = {
    background: 'var(--magi-category-disabled-surface, rgba(214, 218, 218, 0.9))',
    border: 'var(--magi-category-disabled-edge, rgba(104, 111, 112, 0.44))',
    text: 'var(--magi-category-disabled-text, rgba(72, 78, 80, 0.58))',
    line: 'var(--magi-category-disabled-line, rgba(96, 103, 104, 0.4))',
  };

  return (
    <nav
      ref={navRef}
      className={
        mobile
          ? 'magi-home-mobile-category-nav flex overflow-x-auto p-2 gap-2 no-scrollbar bg-inherit border-b border-black/5'
          : 'magi-home-category-nav relative flex-1 overflow-y-auto p-2 space-y-1'
      }
    >
      {categories.map((category) => {
        const config = CATEGORY_CONFIG[category] || { label: category, icon: Folder };
        const Icon = config.icon;
        const isActive = activeCategory === category && !searchActive;
        const isSelected = selectedCategories.has(category);
        const isExpanded = !mobile
          && !searchActive
          && expandedCategory === category;
        const activeClass =
          theme === 'dark'
            ? 'bg-emerald-900/50 text-emerald-400 border-emerald-500'
            : isDayArchiveTheme(theme)
              ? 'magi-home-light-nav-active'
              : 'bg-emerald-50 text-emerald-700 border-emerald-500';

        return (
          <div
            key={category}
            className="magi-home-category-node relative flex w-full items-start"
            data-category={category}
            data-active={isActive ? 'true' : 'false'}
            data-selected={isSelected ? 'true' : 'false'}
            data-expanded={isExpanded ? 'true' : 'false'}
          >
            <button
              ref={(node) => {
                if (node) {
                  triggerRefs.current.set(category, node);
                } else {
                  triggerRefs.current.delete(category);
                }
              }}
              type="button"
              aria-current={isActive ? 'page' : undefined}
              aria-expanded={mobile ? undefined : isExpanded}
              aria-controls={mobile ? undefined : `category-filters-${category}`}
              onClick={() => {
                if (mobile) {
                  onSelect(category);
                  return;
                }
                setConnectorGeometry({
                  overlayCategory: null,
                  width: 0,
                  height: 0,
                  lines: [],
                });
                if (isActive) {
                  onSelect(category);
                  setExpandedCategory(current => current === category ? null : category);
                  return;
                }
                onSelect(category);
                setExpandedCategory(category);
              }}
              className={`magi-home-category-trigger relative z-10 inline-flex w-max max-w-full shrink-0 items-center gap-1.5 px-2 py-2 rounded-md text-sm font-bold transition-all whitespace-nowrap ${
                mobile ? 'border-b-2 rounded-none' : 'border-l-4'
              } ${
                isSelected
                  ? activeClass
                  : isDayArchiveTheme(theme)
                    ? 'magi-home-light-nav-item border-transparent'
                    : 'text-gray-500 hover:bg-black/5 border-transparent'
              }`}
              style={{ width: 'max-content', maxWidth: '100%', flex: '0 0 auto' }}
              data-selected={isSelected ? 'true' : 'false'}
            >
              <Icon size={16} />
              <span>{config.label}</span>
              {!mobile && (
                <ChevronDown
                  aria-hidden="true"
                  size={13}
                  className={`magi-home-category-disclosure ml-0.5 transition-transform ${
                    isExpanded ? 'rotate-180' : ''
                  }`}
                />
              )}
            </button>
            {!mobile && (
              <button
                ref={(node) => {
                  if (node) {
                    categorySelectRefs.current.set(category, node);
                  } else {
                    categorySelectRefs.current.delete(category);
                  }
                }}
                type="button"
                aria-label={`${isSelected ? '取消' : '加入'}${config.label}多选`}
                aria-pressed={isSelected}
                disabled={!isSelected && selectedCategories.size >= MAX_CONNECTED_CATEGORIES}
                title={!isSelected && selectedCategories.size >= MAX_CONNECTED_CATEGORIES
                  ? `最多同时连接 ${MAX_CONNECTED_CATEGORIES} 个分类`
                  : undefined}
                data-category={category}
                data-selected={isSelected ? 'true' : 'false'}
                className="magi-home-category-select-box relative z-20 ml-1 mt-2 inline-grid shrink-0 place-items-center border"
                onClick={(event) => {
                  event.stopPropagation();
                  onToggleCategory(category);
                }}
              >
                <span aria-hidden="true" className="magi-home-category-select-square" />
              </button>
            )}
          </div>
        );
      })}
      {overlayCategory && overlayConfig && (
        <div
          ref={overlayRef}
          className="magi-home-category-branch-overlay pointer-events-none absolute z-[80] overflow-visible"
          data-category={overlayCategory}
          data-overlay="true"
          data-overlay-placement="viewport-top"
          style={{
            top: overlayLayout.top,
            left: overlayLayout.left,
            width: overlayLayout.width,
            height: overlayLayout.height,
            margin: 0,
            pointerEvents: 'none',
            visibility: connectorGeometry.overlayCategory === overlayCategory
              && connectorGeometry.lines.length
                === connectedCategoryOrder.length * CATEGORY_SOURCE_FILTERS.length
              ? 'visible'
              : 'hidden',
          }}
        >
          <svg
            ref={svgRef}
            className="magi-home-category-overlay-lines pointer-events-none absolute inset-0 h-full w-full overflow-visible"
            viewBox={`0 0 ${connectorGeometry.width || overlayLayout.width || 1} ${
              connectorGeometry.height || overlayLayout.height || 1
            }`}
            preserveAspectRatio="none"
            role="group"
            aria-label="分类与译文来源连接线"
            style={{
              color: 'var(--magi-category-branch-line, rgba(57, 66, 68, 0.58))',
              overflow: 'visible',
              zIndex: 0,
            }}
          >
            {connectorGeometry.lines.map((line) => {
              const filter = CATEGORY_SOURCE_FILTERS[line.optionIndex].value;
              const lineEnabled = (
                sourceFilterCounts[line.category]?.[filter] ?? 0
              ) > 0;
              const lineSelected = sourceConnections.get(line.category)?.has(filter) ?? false;
              return (
                <g key={`${line.category}:${filter}`}>
                  <line
                    className="magi-home-category-branch-line"
                    data-category={line.category}
                    data-filter-index={line.optionIndex}
                    data-connector-shape={line.optionIndex === 0 ? 'straight' : 'diagonal'}
                    data-anchor-index={line.anchorIndex}
                    data-anchor-position={['top', 'middle', 'bottom'][line.anchorIndex]}
                    data-connector-distance={line.distance}
                    data-connector-slope={line.slope}
                    data-enabled={lineEnabled ? 'true' : 'false'}
                    data-selected={lineSelected ? 'true' : 'false'}
                    x1={line.x1}
                    y1={line.y1}
                    x2={line.x2}
                    y2={line.y2}
                    style={{
                      animation: 'none',
                      opacity: 1,
                      stroke: lineEnabled
                        ? lineSelected
                          ? 'var(--magi-category-branch-selected-line, var(--magi-category-branch-line, rgba(57, 66, 68, 0.92)))'
                          : 'var(--magi-category-branch-line, rgba(57, 66, 68, 0.78))'
                        : disabledBranchPalette.line,
                      strokeDasharray: 'none',
                      strokeDashoffset: 0,
                      strokeLinecap: 'round',
                      strokeWidth: 2.6,
                    }}
                  />
                  {lineEnabled && lineSelected && (
                    <line
                      className="magi-home-category-branch-line-hit"
                      aria-label={`取消${CATEGORY_CONFIG[line.category]?.label ?? line.category}与${CATEGORY_SOURCE_FILTERS[line.optionIndex].label}连接`}
                      role="button"
                      tabIndex={0}
                      x1={line.x1}
                      y1={line.y1}
                      x2={line.x2}
                      y2={line.y2}
                      onClick={() => onToggleSourceFilter(line.category, filter)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          onToggleSourceFilter(line.category, filter);
                        }
                      }}
                    />
                  )}
                </g>
              );
            })}
          </svg>
          <div
            id={`category-filters-${overlayCategory}`}
            role="group"
            aria-label={`${overlayConfig.label}译文状态`}
            className="magi-home-category-filter-overlay-menu pointer-events-auto absolute top-2 z-10 grid min-w-0 gap-1"
            data-category={overlayCategory}
            data-overlay="true"
            style={{
              left: overlayLayout.menuLeft,
              width: overlayLayout.menuWidth,
              maxWidth: `calc(100% - ${overlayLayout.menuLeft}px)`,
              top: 8,
              height: `calc(100% - 16px)`,
              gridAutoRows: 'max-content',
              alignContent: 'space-evenly',
              justifyItems: 'end',
              pointerEvents: 'auto',
            }}
          >
            {CATEGORY_SOURCE_FILTERS.map((option, optionIndex) => {
              const enabled = connectedCategoryOrder.some(category => (
                sourceFilterCounts[category]?.[option.value] ?? 0
              ) > 0);
              const selected = connectedCategoryOrder.some(category => (
                sourceConnections.get(category)?.has(option.value) ?? false
              ));
              const progressMetric = connectedCategoryOrder.reduce<CategorySourceProgressMetric>(
                (combined, category) => {
                  const categoryProgress = sourceFilterProgress[category]?.[option.value];
                  if (!categoryProgress) return combined;
                  return {
                    value: combined.value + categoryProgress.value,
                    maximum: combined.maximum + categoryProgress.maximum,
                    chapters: combined.chapters + categoryProgress.chapters,
                    available: combined.available && categoryProgress.available,
                  };
                },
                { value: 0, maximum: 0, chapters: 0, available: true },
              );
              const progressPercent = option.value === 'machine-unverified'
                && progressMetric.available
                && progressMetric.maximum > 0
                ? 100 - categorySourceProgressPercent({
                    ...progressMetric,
                    value: progressMetric.maximum - progressMetric.value,
                  })
                : categorySourceProgressPercent(progressMetric);
              const progressText = categorySourceProgressText(
                option.value,
                progressMetric,
                progressPercent,
              );
              const progressBasis = option.value === 'all' || option.value === 'human-cn'
                ? 'translation-percent-average'
                : option.value === 'machine-verified'
                  ? 'reviewed-story-share'
                  : 'pending-story-share';
              return (
                <div
                  ref={(node) => {
                    optionRefs.current[optionIndex] = node;
                  }}
                  key={option.value}
                  className="magi-home-category-filter relative min-w-0 rounded px-2 py-1 text-left text-[11px] font-bold transition"
                  data-category={overlayCategory}
                  data-filter={option.value}
                  data-filter-index={optionIndex}
                  data-connector-shape={optionIndex === 0 ? 'straight' : 'diagonal'}
                  data-enabled={enabled ? 'true' : 'false'}
                  data-selected={selected ? 'true' : 'false'}
                  data-progress-percent={progressPercent}
                  data-progress-basis={progressBasis}
                  data-progress-available={progressMetric.available ? 'true' : 'false'}
                  style={{
                    '--magi-category-filter-progress': `${progressPercent}%`,
                    background: enabled ? undefined : disabledBranchPalette.background,
                    borderColor: enabled ? undefined : disabledBranchPalette.border,
                    color: enabled ? undefined : disabledBranchPalette.text,
                    gridTemplateColumns: 'minmax(0, 1fr)',
                    justifyItems: 'center',
                    minHeight: 'max-content',
                    height: 'max-content',
                    width: 'max-content',
                    minWidth: 30,
                    maxWidth: '100%',
                    alignSelf: 'start',
                    justifySelf: 'end',
                    opacity: 1,
                  } as CSSProperties}
                >
                  <button
                    type="button"
                    disabled={!enabled}
                    aria-label={`${option.label}单选`}
                    aria-pressed={selected}
                    onClick={() => onSelectSourceFilter(option.value)}
                    className="magi-home-category-filter-hit absolute inset-0 z-[2] rounded-[inherit] border-0 bg-transparent p-0"
                  />
                  <output
                    className="sr-only"
                    role="progressbar"
                    aria-label={`${option.label}进度`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={progressMetric.available && progressMetric.maximum > 0
                      ? progressPercent
                      : undefined}
                    aria-valuetext={progressText}
                  >
                    {progressText}
                  </output>
                  <span
                    className="magi-home-category-filter-anchor-set pointer-events-none absolute inset-0"
                    style={{
                      color: enabled
                        ? 'var(--magi-category-branch-line, currentColor)'
                        : disabledBranchPalette.line,
                      overflow: 'visible',
                      textOverflow: 'clip',
                    }}
                  >
                    {[18, 50, 82].map((topPercent, anchorIndex) => {
                      const categorySlot = CATEGORY_ANCHOR_INDEX_BY_SLOT.findIndex(
                        candidate => candidate === anchorIndex,
                      );
                      const anchorCategory = connectedCategoryOrder[categorySlot];
                      const anchorEnabled = Boolean(
                        anchorCategory
                        && (sourceFilterCounts[anchorCategory]?.[option.value] ?? 0) > 0,
                      );
                      const anchorSelected = Boolean(
                        anchorCategory
                        && sourceConnections.get(anchorCategory)?.has(option.value),
                      );
                      return (
                        <button
                          ref={(node) => {
                            const optionAnchors = anchorRefs.current[optionIndex]
                              ?? (anchorRefs.current[optionIndex] = []);
                            optionAnchors[anchorIndex] = node;
                          }}
                          key={topPercent}
                          type="button"
                          disabled={!anchorEnabled}
                          aria-label={anchorCategory
                            ? `${anchorSelected ? '取消' : '连接'}${CATEGORY_CONFIG[anchorCategory]?.label ?? anchorCategory}与${option.label}`
                            : `${option.label}空连接位`}
                          aria-pressed={anchorSelected}
                          onClick={(event) => {
                            event.stopPropagation();
                            if (anchorCategory) {
                              onToggleSourceFilter(anchorCategory, option.value);
                            }
                          }}
                          onKeyDown={event => event.stopPropagation()}
                          className="magi-home-category-filter-anchor-dot pointer-events-auto absolute grid place-items-center"
                          data-anchor-index={anchorIndex}
                          data-anchor-position={['top', 'middle', 'bottom'][anchorIndex]}
                          data-connected={anchorCategory ? 'true' : 'false'}
                          data-selected={anchorSelected ? 'true' : 'false'}
                          data-enabled={anchorEnabled ? 'true' : 'false'}
                          data-anchor-kind={anchorIndex === 1 ? 'connector' : 'selector'}
                          style={{
                            left: -1,
                            top: `${topPercent}%`,
                            width: 22,
                            height: 22,
                            overflow: 'visible',
                            transform: 'translate(-50%, -50%)',
                          }}
                        >
                          <span aria-hidden="true" className="magi-home-category-filter-anchor-glyph" />
                        </button>
                      );
                    })}
                  </span>
                  <span
                    className="min-w-0"
                    style={{
                      overflow: 'visible',
                      textOverflow: 'clip',
                      whiteSpace: 'normal',
                      writingMode: 'vertical-rl',
                      textOrientation: 'upright',
                      overflowWrap: 'normal',
                      justifySelf: 'center',
                      pointerEvents: 'none',
                    }}
                  >
                    {option.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </nav>
  );
}

export default function Home() {
  const { theme, setTheme, lastCategory, setLastCategory } = useGlobal();
  const storySystem: StorySystem =
    lastCategory.startsWith('exedra_') ? 'exedra' : 'magireco';
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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [searchJp, setSearchJp] = useState(false);
  const [searchMode, setSearchMode] = useState<SearchMode>('title');
  const [proofreadingStatus, setProofreadingStatus] = useState<ProofreadingStatus | null>(null);
  const [onlyNeedsReview, setOnlyNeedsReview] = useState(false);
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(
    () => new Set([lastCategory]),
  );
  const [sourceConnections, setSourceConnections] = useState<
    Map<string, Set<CategorySourceFilter>>
  >(() => new Map([[lastCategory, new Set(['all'])]]));
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
      queueMicrotask(() => {
        setLastCategory(fallback);
        setSelectedCategories(new Set([fallback]));
        setSourceConnections(new Map([[fallback, new Set(['all'])]]));
      });
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
  const categorySourceFilterCounts = useMemo(() => {
    const counts: Record<string, CategorySourceFilterCounts> = {};
    for (const story of enrichedStories) {
      const category = story.category || 'Unclassified';
      const storyIsExedra = category.startsWith('exedra_');
      if (
        (storySystem === 'exedra' && (!storyIsExedra || !isExedraCategory(category)))
        || (storySystem === 'magireco' && storyIsExedra)
      ) {
        continue;
      }
      const categoryCounts = counts[category]
        ?? (counts[category] = emptyCategorySourceFilterCounts());
      categoryCounts.all += 1;
      if (storyMatchesCategorySourceFilter(story, 'human-cn')) {
        categoryCounts['human-cn'] += 1;
      }
      if (storyMatchesCategorySourceFilter(story, 'machine-verified')) {
        categoryCounts['machine-verified'] += 1;
      } else if (storyMatchesCategorySourceFilter(story, 'machine-unverified')) {
        categoryCounts['machine-unverified'] += 1;
      }
    }
    return counts;
  }, [enrichedStories, storySystem]);

  const categorySourceFilterProgress = useMemo(() => {
    const storiesByCategory = new Map<string, Story[]>();
    for (const story of enrichedStories) {
      const category = story.category || 'Unclassified';
      const storyIsExedra = category.startsWith('exedra_');
      if (
        (storySystem === 'exedra' && (!storyIsExedra || !isExedraCategory(category)))
        || (storySystem === 'magireco' && storyIsExedra)
      ) {
        continue;
      }
      const categoryStories = storiesByCategory.get(category) ?? [];
      categoryStories.push(story);
      storiesByCategory.set(category, categoryStories);
    }
    const progress: Record<string, CategorySourceFilterProgress> = {};
    const sourceStatusKnown = storySystem === 'exedra' || proofreadingStatus !== null;
    for (const [category, categoryStories] of storiesByCategory) {
      progress[category] = categorySourceFilterProgressForStories(
        categoryStories,
        sourceStatusKnown,
      );
    }
    return progress;
  }, [enrichedStories, proofreadingStatus, storySystem]);

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

      const categorySelected = selectedCategories.size === 0
        ? category === lastCategory
        : selectedCategories.has(category);
      const shouldShow = normalizedQuery ? matches : categorySelected;
      if (!shouldShow) continue;
      if (
        !normalizedQuery
        && !storyMatchesCategorySourceFilters(
          story,
          sourceConnections.get(category) ?? ALL_SOURCE_CONNECTION,
        )
      ) {
        continue;
      }

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
  }, [enrichedStories, storySystem, lastCategory, normalizedQuery, searchMode, textMatches, onlyNeedsReview, selectedCategories, sourceConnections]);

  const selectCategory = (category: string) => {
    setSelectedCategories(new Set([category]));
    setSourceConnections(new Map([[category, new Set(['all'])]]));
    setLastCategory(category);
    setOnlyNeedsReview(false);
    updateSearchTerm('');
  };

  const toggleCategory = (category: string) => {
    setOnlyNeedsReview(false);
    updateSearchTerm('');
    const next = new Set(
      selectedCategories.size > 0 ? selectedCategories : [lastCategory],
    );
    if (next.has(category)) {
      if (next.size === 1) return;
      next.delete(category);
      setSourceConnections(connections => {
        const updated = new Map(connections);
        updated.delete(category);
        return updated;
      });
      if (category === lastCategory) {
        setLastCategory(next.values().next().value ?? lastCategory);
      }
    } else {
      if (next.size >= MAX_CONNECTED_CATEGORIES) return;
      next.add(category);
      setSourceConnections(connections => {
        const updated = new Map(connections);
        updated.set(category, new Set(['all']));
        return updated;
      });
    }
    setSelectedCategories(next);
  };

  const selectCategorySourceFilter = (filter: CategorySourceFilter) => {
    const connectedCategories = selectedCategories.size > 0
      ? selectedCategories
      : new Set([lastCategory]);
    setSourceConnections(new Map(
      Array.from(connectedCategories, category => (
        [category, new Set<CategorySourceFilter>([filter])] as const
      )),
    ));
    setOnlyNeedsReview(false);
    updateSearchTerm('');
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        homeHeadingRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        });
      });
    });
  };

  const toggleCategorySourceFilter = (
    category: string,
    filter: CategorySourceFilter,
  ) => {
    if (!selectedCategories.has(category)) return;
    setSourceConnections(current => {
      const next = new Map(current);
      const categoryFilters = new Set(
        current.get(category) ?? ALL_SOURCE_CONNECTION,
      );
      if (filter === 'all') {
        next.set(category, new Set(['all']));
        return next;
      }
      categoryFilters.delete('all');
      if (categoryFilters.has(filter)) categoryFilters.delete(filter);
      else categoryFilters.add(filter);
      next.set(
        category,
        categoryFilters.size > 0 ? categoryFilters : new Set(['all']),
      );
      return next;
    });
    setOnlyNeedsReview(false);
    updateSearchTerm('');
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        homeHeadingRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        });
      });
    });
  };

  const selectedCategorySummary = useMemo(() => {
    const categoryKeys = selectedCategories.size > 0
      ? categories.filter(category => selectedCategories.has(category))
      : [lastCategory];
    const counts = emptyCategorySourceFilterCounts();
    for (const category of categoryKeys) {
      const categoryCounts = categorySourceFilterCounts[category];
      if (!categoryCounts) continue;
      counts.all += categoryCounts.all;
      counts['human-cn'] += categoryCounts['human-cn'];
      counts['machine-verified'] += categoryCounts['machine-verified'];
      counts['machine-unverified'] += categoryCounts['machine-unverified'];
    }
    return {
      label: categoryKeys
        .map(category => CATEGORY_CONFIG[category]?.label ?? category)
        .join(' + '),
      counts,
    };
  }, [categories, categorySourceFilterCounts, lastCategory, selectedCategories]);

  const switchToStorySystem = (nextSystem: StorySystem) => {
    if (nextSystem === storySystem) return;
    setLastCategory(DEFAULT_CATEGORY[nextSystem]);
    setSelectedCategories(new Set([DEFAULT_CATEGORY[nextSystem]]));
    setSourceConnections(new Map([
      [DEFAULT_CATEGORY[nextSystem], new Set(['all'])],
    ]));
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
      className={`magi-home-mobile-review-button transition md:hidden focus-visible:outline-none ${
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
    <div
      data-theme={theme}
      className={`magi-home-shell magi-home-${theme}-root ${storySystem === 'exedra' ? 'magi-exedra-ui-scope' : ''} flex h-screen h-[100dvh] overflow-hidden`}
    >
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
        <div className="magi-brand-panel border-b border-inherit px-3 py-5">
          <div className="magi-brand-row">
            <h1 className="magi-reader-brand min-w-0">
              <MadeInMagiusLogo />
            </h1>
            {proofreadingStatus && (
              <button
                type="button"
                aria-controls={machineReviewPanelContentId}
                aria-expanded={!machineReviewPanelCollapsed}
                aria-label={`${machineReviewPanelCollapsed ? '打开' : '收起'}校验清单，仍需 ${proofreadingStatus.remaining} 部`}
                title={`仍需人工校验 ${proofreadingStatus.remaining} 部`}
                onClick={() => setMachineReviewPanelCollapsedPreference(!machineReviewPanelCollapsed)}
                className="magi-home-review-trigger inline-flex min-h-8 shrink-0 items-center rounded-md border px-1.5 py-1 text-[10px] font-black transition focus-visible:outline-none"
              >
                校验清单
              </button>
            )}
          </div>
        </div>
        <CategoryNav
          categories={categories}
          activeCategory={lastCategory}
          selectedCategories={selectedCategories}
          sourceConnections={sourceConnections}
          sourceFilterCounts={categorySourceFilterCounts}
          sourceFilterProgress={categorySourceFilterProgress}
          searchActive={Boolean(normalizedQuery)}
          theme={theme}
          onSelect={selectCategory}
          onToggleCategory={toggleCategory}
          onSelectSourceFilter={selectCategorySourceFilter}
          onToggleSourceFilter={toggleCategorySourceFilter}
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
          className={`magi-home-toolbar-shell border-b p-3 backdrop-blur z-10 flex flex-col gap-3 ${
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
                aria-label="打开字体与站点设置"
                title="字体与站点设置"
                onClick={() => setSettingsOpen(true)}
                className={`inline-flex min-h-9 min-w-9 items-center justify-center rounded-lg border p-2 transition-all ${
                  theme === 'dark'
                    ? 'border-gray-700 bg-gray-800 text-gray-200 hover:bg-gray-700'
                    : isDayArchiveTheme(theme)
                      ? 'magi-home-light-button'
                      : 'border-gray-200 bg-white/70 text-gray-700 hover:bg-white'
                }`}
              >
                <Settings aria-hidden="true" size={16} />
              </button>
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
              {proofreadingStatus
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
              selectedCategories={selectedCategories}
              sourceConnections={sourceConnections}
              sourceFilterCounts={categorySourceFilterCounts}
              sourceFilterProgress={categorySourceFilterProgress}
              searchActive={Boolean(normalizedQuery)}
              theme={theme}
              mobile
              onSelect={selectCategory}
              onToggleCategory={toggleCategory}
              onSelectSourceFilter={selectCategorySourceFilter}
              onToggleSourceFilter={toggleCategorySourceFilter}
            />
          </div>
        </header>

        <div className="magi-home-catalog flex-1 overflow-y-auto p-3 md:p-6 scroll-smooth">
          <div className="max-w-7xl mx-auto">
            {proofreadingStatus && (
              <section
                id={machineReviewPanelContentId}
                hidden={machineReviewPanelCollapsed}
                className="magi-home-review-panel mb-5 rounded-2xl border p-4"
              >
                <div>
                  <div className="magi-home-review-panel-layout flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div className="magi-home-review-intro">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-base font-black">魔法纪录来源待核验人工校验清单</h2>
                        <span className="magi-home-review-live-badge rounded-full px-2 py-0.5 text-[10px] font-black">
                          动态
                        </span>
                      </div>
                      <p className="magi-home-review-summary mt-1 text-sm opacity-80">
                        总计 {proofreadingStatus.total} 部，已人工校验 {proofreadingStatus.verified} 部，
                        仍需校验 <strong>{proofreadingStatus.remaining}</strong> 部。
                      </p>
                    </div>
                    <div className="magi-home-review-toolbar flex flex-wrap items-center gap-3">
                      <div className="magi-home-review-meter min-w-48 grow md:grow-0">
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
                            className="magi-home-review-progress h-full rounded-full transition-all"
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
                        onClick={() => {
                          if (storySystem === 'exedra') {
                            switchToStorySystem('magireco');
                            setOnlyNeedsReview(true);
                            return;
                          }
                          setOnlyNeedsReview(value => !value);
                        }}
                        className={`magi-home-review-action rounded-lg border px-3 py-2 text-xs font-black transition ${
                          onlyNeedsReview ? 'is-active' : ''
                        }`}
                      >
                        {storySystem === 'exedra'
                          ? '切换到魔法纪录待核验'
                          : onlyNeedsReview
                            ? '显示当前分类全部剧情'
                            : '只看来源待核验剧情'}
                      </button>
                      <Link
                        href="/review/machine-translations"
                        className="magi-home-review-action is-primary rounded-lg border px-3 py-2 text-xs font-black transition"
                      >
                        管理待核验标记
                      </Link>
                      <div className="magi-home-review-tail-actions">
                        <Link
                          href="/review/submissions"
                          className="magi-home-review-action is-secondary rounded-lg border px-3 py-2 text-xs font-black transition"
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
                          className="magi-home-review-action flex min-h-9 items-center gap-1 rounded-lg border px-3 py-2 text-xs font-black transition focus-visible:outline-none"
                        >
                          <ChevronUp aria-hidden="true" size={15} />
                          收起
                        </button>
                      </div>
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
              <div className="magi-home-section-heading-main min-w-0">
                <h2 className={`px-1 text-xl font-bold opacity-80 ${
                  isDayArchiveTheme(theme)
                    ? 'magi-home-light-section-title'
                    : ''
                }`}>
                  {normalizedQuery
                    ? `搜索结果：“${searchTerm}” ${searchJp ? '（含日文）' : ''}`
                    : selectedCategorySummary.label}
                </h2>
                {!normalizedQuery && (
                  <div
                    className="magi-home-section-statistics"
                    aria-label={`总数量 ${selectedCategorySummary.counts.all}，人工翻译 ${selectedCategorySummary.counts['human-cn']}，机翻待校对 ${selectedCategorySummary.counts['machine-unverified']}，机翻已校对 ${selectedCategorySummary.counts['machine-verified']}`}
                  >
                    <span data-stat="total">总数 {selectedCategorySummary.counts.all}</span>
                    <span data-stat="human">人工 {selectedCategorySummary.counts['human-cn']}</span>
                    <span data-stat="pending">待校 {selectedCategorySummary.counts['machine-unverified']}</span>
                    <span data-stat="verified">已校 {selectedCategorySummary.counts['machine-verified']}</span>
                  </div>
                )}
              </div>
              {proofreadingStatus
                && mobileReviewPlacement === 'floating'
                && renderMobileReviewButton('floating')}
            </div>

            <StableFolderColumns groups={displayedGroups} theme={theme} />
            {displayedGroups.length === 0 && !storyError && (
              <div className="text-center opacity-50 mt-10">没有找到相关剧情</div>
            )}
            <div className="h-20" />
          </div>
        </div>
      </main>
      <SiteSettingsWindow
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        theme={theme}
        setTheme={setTheme}
        isExedra={storySystem === 'exedra'}
      />
      <AboutModal
        isOpen={aboutOpen}
        onClose={() => setAboutOpen(false)}
        theme={theme}
      />
    </div>
  );
}
