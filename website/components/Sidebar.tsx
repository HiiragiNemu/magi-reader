"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import Link from 'next/link';
import {
  Book,
  Calendar,
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  Layers,
  User,
  X,
} from 'lucide-react';

import { characterFolderColorFor } from '@/app/config/dictionary';
import { useGlobal } from '@/app/providers';
import { categoryOrder } from '@/lib/category-order';
import { makeSectionAnchorId } from '@/lib/story-parser';
import {
  resolveOfficialChapterTitle,
  resolveOfficialSectionTitle,
} from '@/lib/official-tw-titles';
import {
  SIDEBAR_WIDTH_DEFAULT,
  SIDEBAR_WIDTH_MAX,
  SIDEBAR_WIDTH_MIN,
  SIDEBAR_WIDTH_STEP,
  SIDEBAR_WIDTH_STORAGE_KEY,
  clampSidebarWidth,
  parseStoredSidebarWidth,
} from '@/lib/sidebar-width';
import { useDialog } from '@/lib/use-dialog';

export type Story = {
  id: string;
  category: string;
  folder: string;
  percent: number;
  has_cn: boolean;
  has_jp?: boolean;
  filename_cn?: string;
  filename_jp?: string;
  path_cn?: string;
  path_jp?: string;
  title?: string;
  sections?: string[];
  game?: string;
  source_identity?: string;
  source_unverified?: boolean;
  /** Deprecated compatibility field; use source_unverified for new code. */
  machine_translation?: boolean;
  human_verified?: boolean;
  official_tw?: boolean;
  official_tw_label?: string;
  official_tw_chapter_title?: string;
  official_tw_section_titles?: string[];
  legacy_ids?: string[];
};

type CategoryConfig = {
  label: string;
  icon: ComponentType<{ size?: number; className?: string }>;
};

export const CATEGORY_CONFIG: Record<string, CategoryConfig> = {
  main_story: { label: '主线剧情', icon: Book },
  event_story: { label: '活动剧情', icon: Calendar },
  character_story: { label: '魔法少女', icon: User },
  costume_story: { label: '服装剧情', icon: Layers },
  login_story: { label: '登录剧情', icon: FileText },
  mirror_story: { label: '镜层/其他', icon: Folder },
  scene0_main: { label: 'Scene0 主线', icon: Book },
  scene0_sub: { label: 'Scene0 支线', icon: User },
  exedra_main: { label: '主线', icon: Book },
  exedra_sub: { label: '活动', icon: Layers },
  exedra_character: { label: '角色', icon: User },
  exedra_portrait: { label: '肖像', icon: User },
  exedra_reaction: { label: '语音', icon: FileText },
  exedra_namae: { label: 'Namae', icon: Folder },
  exedra_dungeon: { label: '过场动画字幕', icon: Layers },
  exedra_battle: { label: '战斗', icon: Folder },
  Unclassified: { label: '未分类', icon: Folder },
};

const EXEDRA_CATEGORIES = new Set([
  'exedra_main',
  'exedra_sub',
  'exedra_character',
  'exedra_portrait',
  'exedra_reaction',
  'exedra_namae',
  'exedra_dungeon',
  'exedra_battle',
]);
const NATURAL_COLLATOR = new Intl.Collator(['zh-CN', 'ja-JP'], {
  numeric: true,
  sensitivity: 'base',
});

type SidebarProps = {
  stories: Story[];
  currentId?: string;
  isOpen: boolean;
  onClose: () => void;
  className?: string;
};

const storyPercent = (story: Story): number => {
  const value = story.percent ?? (story.has_cn ? 100 : 0);
  return Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0));
};

const displayLabel = (story: Story): string => {
  const raw = story.filename_cn || story.filename_jp || story.id;
  const clean = raw.replace(/(_cn|_jp)?\.(?:txt|json)$/i, '');
  return story.title ? `${clean} : ${story.title}` : clean;
};

const displayFolder = (category: string, folder: string): string => {
  if (category === 'character_story' || category === 'costume_story') return folder;
  return folder.replace(/^\d+ - /, '').replace(/^Event_\d+/, 'Event');
};

const sectionDetails = (raw: string): {
  anchorId: string;
  label: string;
} => {
  const source = raw.match(/^(.*?)\s+Section\s*\d+\b/i)?.[1]?.trim() || '';
  const section = raw.match(/Section\s*(\d+)/i)?.[1] || '';
  const branch = raw.match(/(?:Branch|分支|group)\s*_?\s*(\d+)/i)?.[1];
  return {
    anchorId: source && section
      ? makeSectionAnchorId(source, section, branch)
      : raw.replace(/\s+/g, '-').toLowerCase(),
    label: raw
      .replace(/Section\s*\d+\s*/i, '')
      .replace(/\s*-\s*Branch\s*/i, ' ⇄ 分支 ')
      .trim(),
  };
};

export default function Sidebar({
  stories,
  currentId,
  isOpen,
  onClose,
  className = '',
}: SidebarProps) {
  const { theme, lastCategory, setLastCategory } = useGlobal();
  const [categoryOverrides, setCategoryOverrides] = useState<Record<string, boolean>>({});
  const [folderOverrides, setFolderOverrides] = useState<Record<string, boolean>>({});
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_WIDTH_DEFAULT);
  const resizeCleanupRef = useRef<(() => void) | null>(null);
  const sidebarRef = useDialog<HTMLElement>(isOpen, onClose);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      setSidebarWidth(parseStoredSidebarWidth(
        window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY),
      ));
    } catch {
      setSidebarWidth(SIDEBAR_WIDTH_DEFAULT);
    }
    return () => resizeCleanupRef.current?.();
  }, []);

  const commitSidebarWidth = useCallback((value: number) => {
    const bounded = clampSidebarWidth(value);
    setSidebarWidth(bounded);
    try {
      window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(bounded));
    } catch {
      // Storage may be unavailable in private browsing; resizing still works.
    }
  }, []);

  const beginResize = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    event.preventDefault();
    resizeCleanupRef.current?.();
    const startX = event.clientX;
    const startWidth = sidebarWidth;
    const onMove = (moveEvent: PointerEvent) => {
      setSidebarWidth(clampSidebarWidth(startWidth + moveEvent.clientX - startX));
    };
    const onEnd = (endEvent: PointerEvent) => {
      const finalWidth = clampSidebarWidth(startWidth + endEvent.clientX - startX);
      commitSidebarWidth(finalWidth);
      resizeCleanupRef.current?.();
      resizeCleanupRef.current = null;
    };
    const cleanup = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onEnd);
      window.removeEventListener('pointercancel', onEnd);
      document.body.classList.remove('magi-sidebar-resizing');
    };
    resizeCleanupRef.current = cleanup;
    document.body.classList.add('magi-sidebar-resizing');
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onEnd, { once: true });
    window.addEventListener('pointercancel', onEnd, { once: true });
  }, [commitSidebarWidth, sidebarWidth]);

  const currentStory = useMemo(
    () => stories.find(story => story.id === currentId),
    [currentId, stories],
  );
  const showExedra =
    currentStory
      ? currentStory.game === 'exedra' || currentStory.category.startsWith('exedra_')
      : lastCategory.startsWith('exedra_');

  const groupedData = useMemo(() => {
    const result: Record<string, Record<string, Story[]>> = {};
    for (const story of stories) {
      const category = story.category || 'Unclassified';
      const storyIsExedra =
        story.game === 'exedra' || category.startsWith('exedra_');
      if (storyIsExedra !== showExedra) continue;
      if (showExedra && !EXEDRA_CATEGORIES.has(category)) continue;
      const folder = story.folder || '未分类';
      result[category] ??= {};
      result[category][folder] ??= [];
      result[category][folder].push(story);
    }
    return result;
  }, [showExedra, stories]);

  useEffect(() => {
    if (!currentId || !currentStory) return;

    const category = currentStory.category || 'Unclassified';
    const folder = currentStory.folder || '未分类';
    const folderKey = `${category}\u0000${folder}`;
    setCategoryOverrides(previous =>
      previous[category] === true
        ? previous
        : { ...previous, [category]: true },
    );
    setFolderOverrides(previous =>
      previous[folderKey] === true
        ? previous
        : { ...previous, [folderKey]: true },
    );

    const timer = window.setTimeout(() => {
      const container = scrollContainerRef.current;
      const target = document.getElementById(`nav-item-${currentId}`);
      if (!container || !target || !container.contains(target)) return;

      const containerRect = container.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const targetTop =
        container.scrollTop
        + targetRect.top
        - containerRect.top
        - (container.clientHeight - targetRect.height) / 2;
      container.scrollTo({
        top: Math.max(0, targetTop),
        behavior: 'smooth',
      });
    }, 120);
    return () => window.clearTimeout(timer);
  }, [currentId, currentStory, isOpen, stories.length]);

  const themeClass =
    theme === 'dark'
      ? 'bg-gray-900/70 glass-morphism border-gray-700 text-gray-300'
      : theme === 'paper'
        ? 'bg-[#f0e6d2]/60 glass-morphism border-[#dcd6b6] text-[#5c4b37]'
        : theme === 'green'
          ? 'bg-[#d8e6d1]/60 glass-morphism border-[#b8cbb0] text-[#1b4d1b]'
          : 'bg-[#ded6c3]/65 glass-morphism border-[#9d927e]/35 text-[#5d564b] shadow-[10px_0_28px_rgba(77,68,52,0.08)]';
  const hoverClass =
    theme === 'green'
      ? 'hover:bg-[#b0e2bd]'
      : theme === 'dark'
        ? 'hover:bg-gray-800'
        : theme === 'paper'
          ? 'hover:bg-black/5'
          : 'hover:bg-[#81745e]/10';

  return (
    <>
      {isOpen && (
        <button
          type="button"
          aria-label="关闭剧情目录"
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}
      <aside
        ref={sidebarRef}
        role={isOpen ? 'dialog' : undefined}
        aria-modal={isOpen || undefined}
        aria-label="剧情目录"
        tabIndex={-1}
        style={{ '--magi-sidebar-width': `${sidebarWidth}px` } as CSSProperties}
        className={`magi-reader-sidebar fixed inset-y-0 left-0 z-50 flex flex-col overflow-hidden border-r transition-transform duration-300 md:relative md:translate-x-0 ${
          isOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full'
        } ${themeClass} ${className}`}
      >
        <div className="flex shrink-0 items-center justify-between border-b bg-inherit p-4">
          <Link
            href="/"
            className={`text-xl font-black ${
              theme === 'light' || theme === 'paper'
                ? 'magi-reader-brand-day-archive'
                : 'bg-gradient-to-r from-emerald-600 to-teal-500 bg-clip-text text-transparent'
            }`}
          >
            MagiReader
          </Link>
          <button
            type="button"
            aria-label="关闭剧情目录"
            onClick={onClose}
            className={`rounded-full p-2 hover:bg-black/10 active:scale-95 md:hidden ${
              theme === 'dark' ? 'text-white' : 'text-gray-800'
            }`}
          >
            <X size={24} />
          </button>
        </div>

        <div
          ref={scrollContainerRef}
          data-sidebar-scroll-container="true"
          className="scrollbar-thin flex-1 overflow-y-auto p-2"
        >
          {Object.keys(groupedData)
            .sort(
              (a, b) =>
                categoryOrder(a) - categoryOrder(b) ||
                NATURAL_COLLATOR.compare(a, b),
            )
            .map(category => {
            const config = CATEGORY_CONFIG[category] || { label: category, icon: Folder };
            const Icon = config.icon;
            const defaultOpen =
              category === currentStory?.category ||
              (!currentStory && category === lastCategory);
            const categoryOpen = categoryOverrides[category] ?? defaultOpen;

            return (
              <section key={category} className="mb-1">
                <button
                  type="button"
                  aria-expanded={categoryOpen}
                  onClick={() => {
                    setLastCategory(category);
                    setCategoryOverrides(previous => ({
                      ...previous,
                      [category]: !(previous[category] ?? defaultOpen),
                    }));
                  }}
                  className={`flex w-full items-center gap-2 rounded-md px-2 py-3 text-sm font-bold transition-colors ${
                    categoryOpen ? 'bg-black/10' : 'opacity-70'
                  } ${hoverClass}`}
                >
                  {categoryOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <Icon size={18} className="shrink-0" />
                  <span className="whitespace-nowrap">{config.label}</span>
                </button>

                {categoryOpen && (
                  <div className="ml-2 mt-1 space-y-1 border-l-2 border-current border-opacity-10 pl-2">
                    {Object.keys(groupedData[category])
                      .sort((a, b) => NATURAL_COLLATOR.compare(a, b))
                      .map(folder => {
                        const folderKey = `${category}\u0000${folder}`;
                        const defaultFolderOpen =
                          category === currentStory?.category &&
                          folder === currentStory.folder;
                        const folderOpen =
                          folderOverrides[folderKey] ?? defaultFolderOpen;
                        const items = [...groupedData[category][folder]].sort(
                          (left, right) =>
                            NATURAL_COLLATOR.compare(left.id, right.id),
                        );
                        const average = items.length
                          ? Math.round(
                              items.reduce(
                                (sum, story) => sum + storyPercent(story),
                                0,
                              ) / items.length,
                            )
                          : 0;
                        const folderLabel = resolveOfficialChapterTitle(
                          items,
                          displayFolder(category, folder),
                        );
                        const folderClass =
                          average === 100
                            ? theme === 'dark'
                              ? 'text-emerald-400'
                              : 'font-bold text-emerald-700'
                            : average > 0
                              ? 'text-emerald-600'
                              : 'text-gray-500';

                        return (
                          <div
                            key={folder}
                            className={folderOpen ? '' : 'magi-sidebar-folder-collapsed'}
                          >
                          <button
                            type="button"
                            aria-expanded={folderOpen}
                            onClick={() => setFolderOverrides(previous => ({
                              ...previous,
                              [folderKey]: !(previous[folderKey] ?? defaultFolderOpen),
                            }))}
                            className={`magi-reader-sidebar-folder-button flex w-full items-center justify-between rounded px-2 py-2 text-left text-xs transition-colors ${hoverClass}`}
                          >
                            <span
                              className={`mr-1 break-words leading-tight ${folderClass}`}
                              style={{
                                color: characterFolderColorFor(category, folderLabel),
                              }}
                            >
                              {folderLabel}
                            </span>
                            <span className="shrink-0 rounded bg-black/5 px-1 text-[10px] opacity-50">
                              {items.length}
                            </span>
                          </button>

                          {folderOpen && (
                            <div className="ml-2 mt-0.5 space-y-0.5">
                              {items.map(story => {
                                const active = story.id === currentId;
                                const percent = storyPercent(story);
                                const label = displayLabel(story);
                                const inactiveClass =
                                  percent > 0
                                    ? theme === 'dark'
                                      ? 'border-emerald-500/50 bg-emerald-900/30 text-emerald-400 hover:bg-emerald-900/40'
                                      : theme === 'light'
                                        ? 'border-[#93866f]/40 bg-[#d8cfbd]/60 text-[#514a3f] hover:bg-[#cec3ae]/75'
                                        : 'border-emerald-500/50 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                                    : theme === 'dark'
                                      ? 'border-gray-700 bg-gray-800 text-gray-500 hover:bg-gray-700'
                                      : theme === 'light'
                                        ? 'border-[#a79b84]/30 bg-[#ece6d9]/45 text-[#756d60] hover:bg-[#ddd4c3]/65'
                                        : 'border-gray-200 bg-white text-gray-400 hover:bg-gray-50';
                                const activeClass =
                                  theme === 'green'
                                    ? 'border-[#1B5E20] bg-[#2E7D32] text-white'
                                    : theme === 'dark'
                                      ? 'border-blue-500 bg-blue-900/30 text-blue-300'
                                      : theme === 'light'
                                        ? 'border-[#81745e] bg-[#c9bea9]/75 text-[#403a32]'
                                        : 'border-blue-500 bg-blue-50 text-blue-700';

                                return (
                                  <div key={story.id} className="mb-1">
                                    <Link
                                      id={`nav-item-${story.id}`}
                                      href={`/reader/${encodeURIComponent(story.id)}?cn=${encodeURIComponent(story.path_cn || '')}&jp=${encodeURIComponent(story.path_jp || '')}`}
                                      prefetch={false}
                                      onClick={onClose}
                                      title={label}
                                      aria-current={active ? 'page' : undefined}
                                      className={`block truncate rounded-sm border-l-2 px-2 py-1.5 font-mono text-xs transition-all ${
                                        active ? activeClass : inactiveClass
                                      }`}
                                    >
                                      <span className="mr-2">{label}</span>
                                      {story.official_tw && (
                                        <span className="magi-reader-source-badge mr-1 inline-flex rounded-full border border-[#81745e]/35 bg-[#f0eadf]/60 px-1.5 py-0.5 font-sans text-[9px] font-bold text-[#655d50]">
                                          {story.official_tw_label || '台服'}
                                        </span>
                                      )}
                                      {percent < 100 && !active && (
                                        <span className="inline-block text-[9px] opacity-60">{percent}%</span>
                                      )}
                                    </Link>

                                    {active && story.sections && story.sections.length > 0 && (
                                      <div className="ml-3 mt-1 space-y-0.5 border-l border-current border-opacity-10">
                                        {story.sections.map((section, sectionIndex) => {
                                          const details = sectionDetails(section);
                                          const sectionLabel = resolveOfficialSectionTitle(
                                            story.official_tw_section_titles,
                                            sectionIndex + 1,
                                            details.label,
                                          );
                                          return (
                                            <button
                                              type="button"
                                              key={section}
                                              title={sectionLabel}
                                              onClick={() => {
                                                onClose();
                                                const element = document.getElementById(details.anchorId);
                                                element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                                element?.classList.add('ring-4', 'ring-amber-400');
                                                window.setTimeout(
                                                  () => element?.classList.remove('ring-4', 'ring-amber-400'),
                                                  1500,
                                                );
                                              }}
                                              className={`block w-full truncate px-2 py-1 text-left text-[10px] transition ${
                                                theme === 'dark'
                                                  ? 'text-gray-400 hover:bg-white/10 hover:text-white'
                                                  : 'text-gray-600 hover:bg-black/5 hover:text-black'
                                              }`}
                                            >
                                              └ {sectionLabel}
                                            </button>
                                          );
                                        })}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                          </div>
                        );
                      })}
                  </div>
                )}
              </section>
            );
          })}
        </div>
        <button
          type="button"
          role="separator"
          aria-orientation="vertical"
          aria-label={`调整剧情目录宽度，当前 ${sidebarWidth} 像素`}
          aria-valuemin={240}
          aria-valuemax={560}
          aria-valuenow={sidebarWidth}
          title="拖动调整目录宽度；双击恢复默认"
          onPointerDown={beginResize}
          onDoubleClick={() => commitSidebarWidth(SIDEBAR_WIDTH_DEFAULT)}
          onKeyDown={event => {
            if (event.key === 'ArrowLeft') {
              event.preventDefault();
              commitSidebarWidth(sidebarWidth - SIDEBAR_WIDTH_STEP);
            } else if (event.key === 'ArrowRight') {
              event.preventDefault();
              commitSidebarWidth(sidebarWidth + SIDEBAR_WIDTH_STEP);
            } else if (event.key === 'Home') {
              event.preventDefault();
              commitSidebarWidth(SIDEBAR_WIDTH_MIN);
            } else if (event.key === 'End') {
              event.preventDefault();
              commitSidebarWidth(SIDEBAR_WIDTH_MAX);
            }
          }}
          className="magi-sidebar-resize-handle absolute inset-y-0 right-0 hidden w-2 cursor-col-resize touch-none md:block"
        />
      </aside>
    </>
  );
}
