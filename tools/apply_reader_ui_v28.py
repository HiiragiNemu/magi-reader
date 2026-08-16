#!/usr/bin/env python3
"""Apply Reader UI V28 floating-widget and mobile-width refinements.

The migration is intentionally fail-closed: every source anchor must occur
exactly once before it is replaced.  It leaves story data, translation text,
search indexes and playback structures untouched.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "website/app/reader/[id]/page.tsx"
SIDEBAR = ROOT / "website/components/Sidebar.tsx"
REFINEMENTS = ROOT / "website/app/ui-refinements.css"
PREFERENCES = ROOT / "website/lib/reader-display-preferences.ts"
V27_TEST = ROOT / "website/tests/reader-ui-v27.test.mjs"
VISUAL_TEST = ROOT / "website/tests/reader-visual-controls.test.mjs"
V28_TEST = ROOT / "website/tests/reader-ui-v28.test.mjs"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def replace_once(path: Path, old: str, new: str) -> None:
    source = read(path)
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} replacement count={count}; expected 1\n"
            f"anchor={old[:160]!r}"
        )
    write(path, source.replace(old, new, 1))


def replace_between(
    path: Path,
    start_marker: str,
    end_marker: str,
    replacement: str,
) -> None:
    source = read(path)
    if source.count(start_marker) != 1:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} block start is not unique: {start_marker!r}"
        )
    start = source.index(start_marker)
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} block end not found: {end_marker!r}"
        )
    write(path, source[:start] + replacement + source[end:])


def patch_reader() -> None:
    replace_once(
        READER,
        "import FloatingWindow from '@/components/FloatingWindow';\n",
        "import FloatingWindow from '@/components/FloatingWindow';\n"
        "import DraggableReaderWidget from '@/components/DraggableReaderWidget';\n",
    )
    replace_once(
        READER,
        "const BILINGUAL_LAYOUT_STORAGE_KEY = 'magi-reader-bilingual-layout-v1';\n"
        "const STORY_ROWS_PER_PAGE = 200;\n",
        "const BILINGUAL_LAYOUT_STORAGE_KEY = 'magi-reader-bilingual-layout-v1';\n"
        "const UTILITY_WIDGET_POSITION_STORAGE_KEY =\n"
        "  'magi-reader-utility-widget-position-v1';\n"
        "const FONT_WIDGET_POSITION_STORAGE_KEY =\n"
        "  'magi-reader-font-widget-position-v1';\n"
        "const STORY_ROWS_PER_PAGE = 200;\n",
    )
    replace_once(
        READER,
        "  const [aboutOpen, setAboutOpen] = useState(false);\n"
        "  const [utilityPanelOpen, setUtilityPanelOpen] = useState(true);\n"
        "  const [utilityPanelClosing, setUtilityPanelClosing] = useState(false);\n"
        "  const utilityPanelCloseTimerRef = useRef<number | null>(null);\n"
        "  const [editMessage, setEditMessage] = useState('');\n",
        "  const [aboutOpen, setAboutOpen] = useState(false);\n"
        "  const [utilityPanelOpen, setUtilityPanelOpen] = useState(true);\n"
        "  const [editMessage, setEditMessage] = useState('');\n",
    )
    replace_between(
        READER,
        "  useEffect(() => () => {\n"
        "    if (utilityPanelCloseTimerRef.current !== null) {\n",
        "  const directSourceResolution = useMemo(() => {\n",
        "  const openUtilityPanel = () => setUtilityPanelOpen(true);\n\n"
        "  const closeUtilityPanel = () => setUtilityPanelOpen(false);\n\n",
    )
    replace_once(READER, "    setUtilityPanelOpen(true);\n", "")
    replace_once(
        READER,
        "        utilityPanelOpen={utilityPanelOpen}\n"
        "        onOpenUtilityPanel={openUtilityPanel}\n",
        "",
    )
    replace_once(
        READER,
        "                {!utilityPanelOpen && (\n"
        "                  <button\n"
        "                    type=\"button\"\n"
        "                    aria-label=\"展开阅读导航\"\n"
        "                    title=\"展开阅读导航\"\n"
        "                    onClick={openUtilityPanel}\n"
        "                    className=\"magi-reader-utility-dock magi-reader-utility-dock-mobile magi-reader-utility-reopen md:hidden\"\n"
        "                  >\n"
        "                    <span aria-hidden=\"true\">⌂</span>\n"
        "                    <span className=\"sr-only\">导航</span>\n"
        "                  </button>\n"
        "                )}\n",
        "",
    )

    utility_widget = '''        </div>

        {!loadError && (
          <DraggableReaderWidget
            storageKey={UTILITY_WIDGET_POSITION_STORAGE_KEY}
            defaultDock="top-right"
            ariaLabel="阅读导航悬浮工具"
            dragHandleLabel="拖动阅读导航悬浮工具"
            className={`magi-reader-utility-widget ${
              utilityPanelOpen ? 'is-expanded' : 'is-collapsed'
            }`}
          >
            {utilityPanelOpen ? (
              <section
                className="magi-reader-utility-panel magi-reader-utility-panel-floating"
                aria-label="阅读导航与分页"
              >
                <button
                  type="button"
                  aria-label="收起阅读导航"
                  title="收起为右上角悬浮按钮"
                  onClick={closeUtilityPanel}
                  className="magi-reader-utility-close"
                >
                  ×
                </button>
                <div className="magi-reader-utility-content">
                  <div className="magi-reader-utility-search lg:hidden">
                    <Search
                      size={16}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 opacity-45"
                    />
                    <input
                      type="search"
                      aria-label="在当前剧情中搜索"
                      placeholder="页内搜索"
                      title="输入关键词后按 Enter 跳到下一处"
                      value={searchQuery}
                      onChange={event => changeSearch(event.target.value)}
                      onKeyDown={event => {
                        if (event.key === 'Enter') jumpToNextMatch();
                      }}
                      className="magi-reader-search-input h-9 w-full py-1.5 pl-9 pr-14 text-sm leading-5 outline-none"
                    />
                    {searchQuery && (
                      <button
                        type="button"
                        onClick={jumpToNextMatch}
                        className="magi-reader-search-next"
                      >
                        {matchedIndices.length
                          ? `${currentMatchIndex >= 0 ? currentMatchIndex + 1 : 0}/${matchedIndices.length} ↓`
                          : '0'}
                      </button>
                    )}
                  </div>
                  <div className="magi-reader-utility-actions">
                    <Link href="/" className="magi-reader-utility-button">
                      🏠 返回首页
                    </Link>
                    <button
                      type="button"
                      onClick={() => setAboutOpen(true)}
                      className="magi-reader-utility-button"
                    >
                      🔗 我的工具与动态
                    </button>
                    <span
                      aria-live="polite"
                      className="magi-reader-page-summary"
                    >
                      第 {visiblePage + 1} / {pageCount} 页 · 第 {pageStart + 1}–
                      {Math.min(
                        pageStart + visibleRenderList.length,
                        renderList.length,
                      )} 行，共 {renderList.length} 行
                    </span>
                  </div>
                </div>
              </section>
            ) : (
              <button
                type="button"
                aria-label="展开阅读导航"
                title="展开返回首页、工具与分页信息"
                onClick={openUtilityPanel}
                className="magi-reader-utility-fab"
              >
                <span aria-hidden="true">⌂</span>
                <span>导航</span>
              </button>
            )}
          </DraggableReaderWidget>
        )}

        <main
'''
    replace_between(
        READER,
        "          {!loadError && utilityPanelOpen && (\n",
        "        <main\n",
        utility_widget,
    )

    replace_once(
        READER,
        "          style={{\n"
        "            fontSize: `${fontSize}px`,\n"
        "            lineHeight,\n"
        "            ...(pageCount > 1\n"
        "              ? { paddingInline: 'clamp(3.25rem, 6vw, 4rem)' }\n"
        "              : {}),\n"
        "          }}\n",
        "          style={{\n"
        "            fontSize: `${fontSize}px`,\n"
        "            lineHeight,\n"
        "          }}\n",
    )

    replace_once(
        READER,
        "  const renderList = useMemo(\n"
        "    () => alignStoryLines(displayedCnLines, displayedJpLines),\n"
        "    [displayedCnLines, displayedJpLines],\n"
        "  );\n"
        "  const pageCount = Math.max(1, Math.ceil(renderList.length / STORY_ROWS_PER_PAGE));\n",
        "  const renderList = useMemo(\n"
        "    () => alignStoryLines(displayedCnLines, displayedJpLines),\n"
        "    [displayedCnLines, displayedJpLines],\n"
        "  );\n"
        "  const firstStoryHeaderIndex = useMemo(\n"
        "    () => renderList.findIndex(row => row.cn?.isHeader || row.jp?.isHeader),\n"
        "    [renderList],\n"
        "  );\n"
        "  const pageCount = Math.max(1, Math.ceil(renderList.length / STORY_ROWS_PER_PAGE));\n",
    )
    replace_once(
        READER,
        "                   officialSectionTitles={currentStory?.official_tw_section_titles}\n"
        "                  isEditMode={isEditMode}\n",
        "                   officialSectionTitles={currentStory?.official_tw_section_titles}\n"
        "                  isFirstStoryHeader={index === firstStoryHeaderIndex}\n"
        "                  isEditMode={isEditMode}\n",
    )
    replace_once(
        READER,
        "  officialSectionTitles?: string[];\n"
        "  isEditMode: boolean;\n",
        "  officialSectionTitles?: string[];\n"
        "  isFirstStoryHeader: boolean;\n"
        "  isEditMode: boolean;\n",
    )
    replace_once(
        READER,
        "  officialSectionTitles,\n"
        "  isEditMode,\n",
        "  officialSectionTitles,\n"
        "  isFirstStoryHeader,\n"
        "  isEditMode,\n",
    )
    replace_once(
        READER,
        "        lang={isExedra ? (header === row.jp ? 'ja' : 'zh-Hans') : undefined}\n"
        "        className={`mb-4 mt-6 border-t-2 pt-4 text-center ${\n",
        "        lang={isExedra ? (header === row.jp ? 'ja' : 'zh-Hans') : undefined}\n"
        "        data-reader-first-header={isFirstStoryHeader || undefined}\n"
        "        className={`mb-4 text-center ${\n"
        "          isFirstStoryHeader\n"
        "            ? 'mt-0 pt-0'\n"
        "            : 'mt-6 border-t-2 pt-4'\n"
        "        } ${\n",
    )

    source = read(READER)
    font_start_marker = (
        "        <div\n"
        "          className={`magi-reader-font-control magi-reader-font-control-${theme} ${\n"
    )
    font_end_marker = "\n\n        <FloatingWindow\n"
    if source.count(font_start_marker) != 1:
        raise RuntimeError("font control start marker is not unique")
    start = source.index(font_start_marker)
    end = source.find(font_end_marker, start)
    if end < 0:
        raise RuntimeError("font control end marker is missing")
    block = source[start:end]
    wrapped = (
        "        <DraggableReaderWidget\n"
        "          storageKey={FONT_WIDGET_POSITION_STORAGE_KEY}\n"
        "          defaultDock=\"bottom-right\"\n"
        "          ariaLabel=\"快速字号悬浮工具\"\n"
        "          dragHandleLabel=\"拖动快速字号悬浮工具\"\n"
        "          className=\"magi-reader-font-widget\"\n"
        "        >\n"
        + block
        + "\n        </DraggableReaderWidget>"
    )
    write(READER, source[:start] + wrapped + source[end:])


def patch_sidebar() -> None:
    replace_once(
        SIDEBAR,
        "  utilityPanelOpen: boolean;\n"
        "  onOpenUtilityPanel: () => void;\n",
        "",
    )
    replace_once(
        SIDEBAR,
        "  utilityPanelOpen,\n"
        "  onOpenUtilityPanel,\n",
        "",
    )
    replace_once(
        SIDEBAR,
        "          {!utilityPanelOpen && (\n"
        "            <button\n"
        "              type=\"button\"\n"
        "              aria-label=\"展开阅读导航\"\n"
        "              title=\"展开阅读导航\"\n"
        "              onClick={onOpenUtilityPanel}\n"
        "              className=\"magi-reader-utility-dock magi-reader-utility-dock-desktop hidden md:inline-flex\"\n"
        "            >\n"
        "              <span aria-hidden=\"true\">⌂</span>\n"
        "              <span>导航</span>\n"
        "            </button>\n"
        "          )}\n",
        "",
    )


def patch_preferences() -> None:
    replace_once(
        PREFERENCES,
        "export const READER_TEXT_WIDTH_MIN = 640;\n"
        "export const READER_TEXT_WIDTH_MAX = 1280;\n"
        "export const READER_TEXT_WIDTH_STEP = 32;\n"
        "export const DEFAULT_READER_TEXT_WIDTH = 768;\n",
        "export const READER_TEXT_WIDTH_MIN = 320;\n"
        "export const READER_TEXT_WIDTH_MAX = 1280;\n"
        "export const READER_TEXT_WIDTH_STEP = 32;\n"
        "export const DEFAULT_READER_TEXT_WIDTH = 1024;\n",
    )


def patch_css() -> None:
    css = read(REFINEMENTS).rstrip()
    if "Reader UI V28 — draggable floating navigation" in css:
        raise RuntimeError("V28 CSS already exists")
    css += r'''

/* =========================================
   Reader UI V28 — draggable floating navigation and full-width mobile reading
   ========================================= */

.magi-reader-floating-widget {
  position: fixed;
  z-index: 56;
  display: flex;
  max-width: calc(100vw - 1rem);
  max-height: calc(100dvh - 1rem);
  align-items: stretch;
  overflow: hidden;
  border: 1px solid var(--magi-tool-border);
  color: var(--magi-tool-text);
  background:
    linear-gradient(118deg, var(--magi-tool-inset), transparent 44%),
    var(--magi-tool-surface);
  box-shadow:
    7px 9px 22px var(--magi-tool-shadow),
    inset 1px 1px var(--magi-tool-inset);
  backdrop-filter: blur(12px) saturate(0.84);
  -webkit-backdrop-filter: blur(12px) saturate(0.84);
  touch-action: none;
}

.magi-reader-floating-widget[data-default-dock='top-right'] {
  top: max(4.35rem, calc(env(safe-area-inset-top) + 4rem));
  right: max(0.7rem, env(safe-area-inset-right));
}

.magi-reader-floating-widget[data-default-dock='bottom-right'] {
  right: max(0.7rem, env(safe-area-inset-right));
  bottom: max(0.7rem, env(safe-area-inset-bottom));
}

.magi-reader-theme-paper .magi-reader-floating-widget {
  border-color: rgba(74, 58, 35, 0.55);
  border-radius: 1rem;
  background:
    linear-gradient(118deg, rgba(255, 249, 225, 0.74), transparent 44%),
    rgba(225, 211, 171, 0.95);
  box-shadow:
    7px 9px 22px rgba(55, 42, 25, 0.22),
    inset 1px 1px rgba(255, 250, 227, 0.72);
}

.magi-reader-theme-dark .magi-reader-floating-widget {
  background:
    linear-gradient(118deg, rgba(255, 255, 255, 0.1), transparent 44%),
    rgba(38, 45, 51, 0.96);
}

.magi-reader-theme-green .magi-reader-floating-widget {
  background:
    linear-gradient(118deg, rgba(247, 255, 249, 0.72), transparent 44%),
    rgba(209, 230, 215, 0.96);
}

.magi-reader-floating-widget.is-dragging {
  z-index: 80;
  cursor: grabbing;
  opacity: 0.94;
  box-shadow:
    14px 18px 36px var(--magi-tool-shadow),
    inset 1px 1px var(--magi-tool-inset);
}

.magi-reader-floating-grip {
  display: grid;
  width: 1.35rem;
  min-width: 1.35rem;
  place-items: center;
  border: 0;
  border-right: 1px solid color-mix(in srgb, var(--magi-tool-border) 62%, transparent);
  border-radius: 0 !important;
  color: var(--magi-tool-muted);
  background: color-mix(in srgb, var(--magi-tool-control) 76%, transparent);
  box-shadow: inset 1px 1px var(--magi-tool-inset);
  cursor: grab;
  touch-action: none;
  user-select: none;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 0.72rem;
  line-height: 0.72;
  letter-spacing: -0.22em;
}

.magi-reader-floating-grip:active {
  cursor: grabbing;
}

.magi-reader-floating-grip:focus-visible {
  outline: 2px solid var(--magi-tool-accent);
  outline-offset: -3px;
}

.magi-reader-utility-widget {
  width: min(44rem, calc(100vw - 1rem));
}

.magi-reader-utility-widget.is-collapsed {
  width: auto;
}

.magi-reader-utility-panel-floating {
  position: relative;
  width: 100%;
  min-width: 0;
  max-height: min(10.5rem, calc(100dvh - 5.5rem));
  margin: 0;
  padding: 0.48rem 2.2rem 0.48rem 0.55rem;
  overflow: auto;
  border: 0;
  border-radius: 0;
  outline: 0;
  color: inherit;
  background: transparent;
  box-shadow: none;
  clip-path: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

.magi-reader-utility-panel-floating::before,
.magi-reader-utility-panel-floating::after {
  display: none;
  content: none;
}

.magi-reader-utility-panel-floating .magi-reader-utility-content {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.magi-reader-utility-panel-floating .magi-reader-utility-actions {
  min-width: 0;
  flex: 1;
  flex-wrap: nowrap;
  gap: 0.35rem;
}

.magi-reader-utility-panel-floating .magi-reader-utility-button {
  min-height: 1.9rem;
  flex: none;
  padding: 0.3rem 0.55rem;
  font-size: 0.66rem;
}

.magi-reader-utility-panel-floating .magi-reader-page-summary {
  flex: 1 1 auto;
  white-space: nowrap;
  font-size: 0.66rem;
}

.magi-reader-utility-fab {
  display: inline-flex;
  min-height: 2.35rem;
  align-items: center;
  justify-content: center;
  gap: 0.28rem;
  padding: 0.35rem 0.68rem;
  border: 0;
  color: var(--magi-tool-text);
  background: transparent;
  font-size: 0.72rem;
  font-weight: 900;
  white-space: nowrap;
}

.magi-reader-utility-fab:hover,
.magi-reader-utility-fab:focus-visible {
  color: var(--magi-tool-accent-text);
  background: var(--magi-tool-accent);
  outline: 2px solid var(--magi-tool-inset);
  outline-offset: -3px;
}

.magi-reader-font-widget {
  width: auto;
}

.magi-reader-font-widget .magi-reader-font-control {
  position: static;
  right: auto;
  bottom: auto;
  z-index: auto;
  max-width: calc(100vw - 2.35rem);
  border: 0;
  border-radius: 0;
  color: inherit;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

.magi-reader-theme-paper .magi-reader-font-widget .magi-reader-font-control {
  background: transparent;
  box-shadow: none;
}

.magi-reader-first-header,
[data-reader-first-header='true'] {
  border-top-width: 0 !important;
}

@media (min-width: 768px) {
  .magi-reader-theme-light .magi-reader-document,
  .magi-reader-theme-paper .magi-reader-document {
    padding: 1rem clamp(1rem, 2vw, 2rem) 6rem;
  }
}

@media (max-width: 767px) {
  .magi-reader-floating-widget[data-default-dock='top-right'] {
    top: max(7.15rem, calc(env(safe-area-inset-top) + 6.8rem));
    right: max(0.35rem, env(safe-area-inset-right));
  }

  .magi-reader-floating-widget[data-default-dock='bottom-right'] {
    right: max(0.35rem, env(safe-area-inset-right));
    bottom: max(0.35rem, env(safe-area-inset-bottom));
  }

  .magi-reader-utility-widget {
    width: calc(100vw - 0.7rem);
  }

  .magi-reader-utility-widget.is-collapsed {
    width: auto;
  }

  .magi-reader-utility-panel-floating {
    max-height: min(9.5rem, calc(100dvh - 7.6rem));
    padding: 0.42rem 1.95rem 0.42rem 0.42rem;
  }

  .magi-reader-utility-panel-floating .magi-reader-utility-content {
    flex-wrap: wrap;
    gap: 0.3rem;
  }

  .magi-reader-utility-panel-floating .magi-reader-utility-search {
    width: 100%;
    flex: 1 1 100%;
  }

  .magi-reader-utility-panel-floating .magi-reader-utility-actions {
    flex: 1 1 100%;
    flex-wrap: wrap;
    gap: 0.28rem;
  }

  .magi-reader-utility-panel-floating .magi-reader-utility-button {
    min-height: 1.82rem;
    padding: 0.26rem 0.46rem;
    font-size: 0.62rem;
  }

  .magi-reader-utility-panel-floating .magi-reader-page-summary {
    flex: 1 1 10rem;
    white-space: normal;
    text-align: left;
    font-size: 0.62rem;
  }

  .magi-reader-main,
  .magi-reader-main-paginated {
    padding-right: 0.3rem !important;
    padding-left: 0.3rem !important;
  }

  .magi-reader-document {
    width: 100% !important;
    padding-right: 0.18rem !important;
    padding-left: 0.18rem !important;
  }

  .magi-reader-theme-paper .magi-reader-document {
    border-radius: 0.72rem;
  }

  .magi-reader-page-turn {
    width: 2.05rem;
    min-width: 2.05rem;
    height: 3rem;
    opacity: 0.84;
  }

  .magi-reader-page-turn-prev {
    left: -0.48rem;
  }

  .magi-reader-page-turn-next {
    right: -0.48rem;
  }

  .magi-reader-page-turn-triangle {
    scale: 0.82;
  }

  .magi-reader-speaker-label,
  .magi-translation-speaker-input {
    width: 4.1rem !important;
    padding-right: 0.12rem !important;
    padding-left: 0.12rem !important;
  }

  .reader-font-cn-body,
  .reader-font-jp-body {
    gap: 0.42rem !important;
  }

  .magi-bilingual-pair {
    margin-bottom: 0.35rem;
    padding-bottom: 0.55rem;
  }

  .magi-reader-font-control-open {
    width: min(15rem, calc(100vw - 2.5rem));
  }
}

@media (prefers-reduced-motion: reduce) {
  .magi-reader-floating-widget {
    transition: none;
  }
}
'''
    write(REFINEMENTS, css + "\n")


def patch_tests() -> None:
    write(
        V27_TEST,
        '''import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const reader = readFileSync(
  new URL('../app/reader/[id]/page.tsx', import.meta.url),
  'utf8',
);
const sidebar = readFileSync(
  new URL('../components/Sidebar.tsx', import.meta.url),
  'utf8',
);
const home = readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf8');
const css = readFileSync(
  new URL('../app/ui-refinements.css', import.meta.url),
  'utf8',
);

test('desktop sidebar expands and centers the active story without scrolling the document', () => {
  assert.match(sidebar, /data-sidebar-scroll-container="true"/u);
  assert.match(sidebar, /scrollContainerRef/u);
  assert.match(sidebar, /setCategoryOverrides/u);
  assert.match(sidebar, /setFolderOverrides/u);
  assert.match(sidebar, /container\.scrollTo\(\{/u);
  assert.doesNotMatch(sidebar, /if \(!isOpen \|\| !currentId\) return/u);
});

test('reader navigation is an independent draggable floating widget, never a sidebar or header dock', () => {
  assert.match(reader, /DraggableReaderWidget/u);
  assert.match(reader, /UTILITY_WIDGET_POSITION_STORAGE_KEY/u);
  assert.match(reader, /magi-reader-utility-widget/u);
  assert.match(reader, /magi-reader-utility-panel-floating/u);
  assert.match(reader, /magi-reader-utility-fab/u);
  assert.doesNotMatch(reader, /magi-reader-utility-panel-overlay/u);
  assert.doesNotMatch(reader, /magi-reader-utility-dock-mobile/u);
  assert.doesNotMatch(sidebar, /utilityPanelOpen/u);
  assert.doesNotMatch(sidebar, /onOpenUtilityPanel/u);
  assert.doesNotMatch(sidebar, /magi-reader-utility-dock-desktop/u);
  assert.match(css, /\.magi-reader-floating-widget/u);
  assert.match(css, /\.magi-reader-utility-panel-floating/u);
});

test('mobile home toolbar packs controls and supports a draggable review button dock', () => {
  assert.match(home, /MOBILE_REVIEW_PLACEMENT_STORAGE_KEY/u);
  assert.match(home, /mobileReviewPlacement/u);
  assert.match(home, /setPointerCapture/u);
  assert.match(home, /homeToolbarRef/u);
  assert.match(home, /homeHeadingRef/u);
  assert.match(home, /renderMobileReviewButton\('floating'\)/u);
  assert.match(home, /renderMobileReviewButton\('toolbar'\)/u);
  assert.match(home, /magi-home-mobile-category-nav/u);
  assert.match(css, /\.magi-home-mobile-review-button/u);
  assert.match(css, /\.magi-home-mobile-review-button\[data-placement='floating'\]::before/u);
  assert.match(css, /\.magi-home-toolbar-row\s*\{[\s\S]*justify-content: flex-start !important/u);
});
''',
    )

    replace_once(
        VISUAL_TEST,
        "  assert.match(reader, /magi-reader-utility-reopen/);\n",
        "  assert.match(reader, /magi-reader-utility-fab/);\n"
        "  assert.match(reader, /magi-reader-utility-panel-floating/);\n",
    )
    replace_once(
        VISUAL_TEST,
        "  assert.match(reader, /paddingInline: 'clamp\\(3\\.25rem, 6vw, 4rem\\)'/);\n",
        "  assert.doesNotMatch(reader, /paddingInline: 'clamp\\(3\\.25rem, 6vw, 4rem\\)'/);\n"
        "  assert.match(refinements, /\\.magi-reader-main-paginated[\\s\\S]*padding-right: 0\\.3rem !important/);\n",
    )
    replace_once(
        VISUAL_TEST,
        "  assert.match(reader, /magi-reader-font-control-open/);\n",
        "  assert.match(reader, /magi-reader-font-control-open/);\n"
        "  assert.match(reader, /FONT_WIDGET_POSITION_STORAGE_KEY/);\n"
        "  assert.match(reader, /className=\"magi-reader-font-widget\"/);\n",
    )

    write(
        V28_TEST,
        '''import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const widget = readFileSync(
  new URL('../components/DraggableReaderWidget.tsx', import.meta.url),
  'utf8',
);
const reader = readFileSync(
  new URL('../app/reader/[id]/page.tsx', import.meta.url),
  'utf8',
);
const sidebar = readFileSync(
  new URL('../components/Sidebar.tsx', import.meta.url),
  'utf8',
);
const preferences = readFileSync(
  new URL('../lib/reader-display-preferences.ts', import.meta.url),
  'utf8',
);
const css = readFileSync(
  new URL('../app/ui-refinements.css', import.meta.url),
  'utf8',
);

test('reader floating widgets use pointer capture, viewport clamping and persisted positions', () => {
  assert.match(widget, /setPointerCapture/u);
  assert.match(widget, /releasePointerCapture/u);
  assert.match(widget, /window\.localStorage\.setItem\(storageKey/u);
  assert.match(widget, /window\.localStorage\.removeItem\(storageKey/u);
  assert.match(widget, /new ResizeObserver\(keepInsideViewport\)/u);
  assert.match(widget, /data-default-dock=\{defaultDock\}/u);
  assert.match(widget, /onDoubleClick=\{resetPosition\}/u);
  assert.match(widget, /magi-reader-floating-grip/u);
});

test('navigation and font controls are separate draggable upper/lower floating widgets', () => {
  assert.match(reader, /magi-reader-utility-widget-position-v1/u);
  assert.match(reader, /magi-reader-font-widget-position-v1/u);
  assert.equal((reader.match(/<DraggableReaderWidget/g) ?? []).length, 2);
  assert.match(reader, /defaultDock="top-right"/u);
  assert.match(reader, /defaultDock="bottom-right"/u);
  assert.match(reader, /magi-reader-utility-panel-floating/u);
  assert.match(reader, /magi-reader-utility-fab/u);
  assert.match(reader, /magi-reader-font-widget/u);
  assert.doesNotMatch(reader, /magi-reader-utility-dock/u);
  assert.doesNotMatch(sidebar, /magi-reader-utility-dock/u);
});

test('the first Episode header has no separator or reserved top band', () => {
  assert.match(reader, /firstStoryHeaderIndex/u);
  assert.match(reader, /data-reader-first-header=\{isFirstStoryHeader \|\| undefined\}/u);
  assert.match(reader, /isFirstStoryHeader[\s\S]*?\? 'mt-0 pt-0'[\s\S]*?: 'mt-6 border-t-2 pt-4'/u);
});

test('mobile reading width is viewport-efficient and remains adjustable', () => {
  assert.match(preferences, /READER_TEXT_WIDTH_MIN = 320/u);
  assert.match(preferences, /DEFAULT_READER_TEXT_WIDTH = 1024/u);
  assert.doesNotMatch(reader, /paddingInline: 'clamp\(3\.25rem, 6vw, 4rem\)'/u);
  assert.match(css, /\.magi-reader-main,[\s\S]*?\.magi-reader-main-paginated[\s\S]*?padding-right: 0\.3rem !important;[\s\S]*?padding-left: 0\.3rem !important;/u);
  assert.match(css, /\.magi-reader-document[\s\S]*?padding-right: 0\.18rem !important;[\s\S]*?padding-left: 0\.18rem !important;/u);
  assert.match(css, /\.magi-reader-page-turn-next[\s\S]*?right: -0\.48rem/u);
});
''',
    )


def main() -> int:
    patch_reader()
    patch_sidebar()
    patch_preferences()
    patch_css()
    patch_tests()
    print("READER_UI_V28_FLOATING_WIDGETS_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
