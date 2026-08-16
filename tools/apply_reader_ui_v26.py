#!/usr/bin/env python3
"""Apply the compact Reader navigation and theme-native proofreading UI.

This is a one-shot, fail-closed migration. Every replacement is anchored to the
validated 6ff6652 tree; a missing or duplicated marker aborts before publication.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "website/app/page.tsx"
READER = ROOT / "website/app/reader/[id]/page.tsx"
PREFERENCES = ROOT / "website/lib/reader-display-preferences.ts"
PREFERENCES_TEST = ROOT / "website/lib/reader-display-preferences.test.ts"
READER_TEST = ROOT / "website/tests/reader-visual-controls.test.mjs"
HOME_TEST = ROOT / "website/tests/homepage-official-tw-theme.test.mjs"
REFINEMENTS = ROOT / "website/app/ui-refinements.css"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8", newline="\n")


def replace_once(path: Path, old: str, new: str) -> None:
    source = read(path)
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} replacement count={count}; expected 1"
        )
    write(path, source.replace(old, new, 1))


def replace_between(
    path: Path,
    start_marker: str,
    end_marker: str,
    replacement: str,
) -> None:
    source = read(path)
    start = source.find(start_marker)
    if start < 0:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} start marker missing: {start_marker!r}"
        )
    if source.find(start_marker, start + 1) >= 0:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} start marker is not unique"
        )
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} end marker missing: {end_marker!r}"
        )
    write(path, source[:start] + replacement + source[end:])


def append_once(path: Path, marker: str, content: str) -> None:
    source = read(path)
    if marker in source:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} already contains migration marker"
        )
    write(path, source.rstrip() + "\n\n" + content.strip() + "\n")


def patch_home() -> None:
    replace_once(
        HOME,
        """  const storySystem: StorySystem =
    lastCategory.startsWith('exedra_') ? 'exedra' : 'magireco';
""",
        """  const storySystem: StorySystem =
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
""",
    )
    replace_once(
        HOME,
        '<div className="flex flex-col md:flex-row md:items-center justify-between gap-3">',
        '<div className="magi-home-toolbar-row flex flex-wrap items-start justify-between gap-2 md:items-center">',
    )
    replace_once(
        HOME,
        '<div className="relative flex-1 max-w-4xl flex flex-wrap gap-2">',
        '<div className="magi-home-toolbar-controls relative flex min-w-0 flex-1 flex-wrap items-center gap-2">',
    )
    replace_once(
        HOME,
        '              <div className="relative flex-1 min-w-56">\n',
        """              <div
                className="magi-home-search-shell relative min-w-0"
                style={{
                  '--magi-home-search-width': `${compactSearchCharacters}em`,
                } as CSSProperties}
              >
""",
    )
    replace_once(
        HOME,
        """            <div
              className={`flex gap-1 p-1 rounded-full self-end md:self-auto ${
""",
        """            <div
              className={`magi-home-theme-switcher flex gap-1 p-1 rounded-full self-end md:self-auto ${
""",
    )


def patch_preferences() -> None:
    replace_once(
        PREFERENCES,
        """  fontControlOpen: true,
  showLineBreaks: false,
};
""",
        """  fontControlOpen: true,
  showLineBreaks: true,
};
""",
    )
    replace_once(
        PREFERENCES,
        """      fontControlOpen: record.fontControlOpen !== false,
      showLineBreaks: record.showLineBreaks === true,
""",
        """      fontControlOpen: record.fontControlOpen !== false,
      showLineBreaks:
        typeof record.showLineBreaks === 'boolean'
          ? record.showLineBreaks
          : DEFAULT_PREFERENCES.showLineBreaks,
""",
    )
    replace_once(
        PREFERENCES,
        """    fontControlOpen: preferences.fontControlOpen !== false,
    showLineBreaks: preferences.showLineBreaks === true,
""",
        """    fontControlOpen: preferences.fontControlOpen !== false,
    showLineBreaks: preferences.showLineBreaks !== false,
""",
    )


def patch_reader() -> None:
    replace_once(
        READER,
        """  const [aboutOpen, setAboutOpen] = useState(false);
  const [editMessage, setEditMessage] = useState('');
""",
        """  const [aboutOpen, setAboutOpen] = useState(false);
  const [utilityPanelOpen, setUtilityPanelOpen] = useState(true);
  const [editMessage, setEditMessage] = useState('');
""",
    )
    replace_once(
        READER,
        """    setSearchQuery('');
    setCurrentMatchIndex(-1);

    const fetchSource = async (
""",
        """    setSearchQuery('');
    setCurrentMatchIndex(-1);
    setUtilityPanelOpen(true);

    const fetchSource = async (
""",
    )
    replace_once(
        READER,
        """        <header className={`magi-reader-header z-20 flex shrink-0 items-center justify-between border-b px-4 py-2 ${HEADER_STYLES[theme]}`}>
          <div className="flex min-w-0 items-center gap-3">
""",
        """        <header className={`magi-reader-header magi-reader-header-compact z-20 flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1 border-b px-2 py-1.5 ${HEADER_STYLES[theme]}`}>
          <div className="magi-reader-header-identity flex min-w-0 flex-1 items-center gap-2">
""",
    )
    replace_once(
        READER,
        '<div className="flex min-w-0 flex-wrap items-center gap-2 text-sm font-bold">',
        '<div className="magi-reader-header-meta flex min-w-0 flex-nowrap items-center gap-1 text-sm font-bold">',
    )
    replace_once(
        READER,
        '<div className="magi-reader-search-shell group relative mx-4 hidden min-w-64 max-w-md flex-1 lg:flex">',
        '<div className="magi-reader-search-shell group relative mx-2 hidden min-w-48 max-w-sm flex-[0_1_20rem] lg:flex">',
    )
    replace_once(
        READER,
        '<div className="flex shrink-0 items-center gap-2">',
        '<div className="magi-reader-header-actions ml-auto flex shrink-0 items-center gap-1">',
    )

    replace_once(
        READER,
        '<section className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50/80 p-4 shadow-sm">',
        '<section className="magi-proofreading-panel mb-4 p-3">',
    )
    old_toolbar = """                <div className="flex flex-wrap items-center gap-3">
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
"""
    new_toolbar = """                <div className="magi-proofreading-toolbar">
                  <span className="magi-proofreading-kicker">初始化</span>
                  <button
                    type="button"
                    data-variant="secondary"
                    onClick={() => initializeEditing('empty')}
                    className="magi-proofreading-button"
                  >
                    仅填入译名
                  </button>
                  <button
                    type="button"
                    data-variant="secondary"
                    onClick={() => initializeEditing('jp')}
                    className="magi-proofreading-button"
                  >
                    填入日文原文
                  </button>
                  <label
                    data-variant="secondary"
                    className="magi-proofreading-button cursor-pointer"
                  >
                    上传 JSON / TXT
                    <input
                      type="file"
                      accept=".json,.txt"
                      className="hidden"
                      onChange={uploadTranslation}
                    />
                  </label>
                  <button
                    type="button"
                    data-variant="primary"
                    onClick={downloadTranslation}
                    className="magi-proofreading-button"
                  >
                    下载当前进度（UTF-8）
                  </button>
                  <label className="magi-proofreading-linebreak-toggle">
                    <input
                      type="checkbox"
                      checked={readerDisplayPreferences.showLineBreaks}
                      onChange={event =>
                        updateReaderDisplayPreferences({
                          showLineBreaks: event.target.checked,
                        })
                      }
                    />
                    <span>
                      <strong>显示换行符 <span aria-hidden="true">↵</span></strong>
                      <small>按 Enter 插入真实换行；TXT / JSON 下载会保留。</small>
                    </span>
                  </label>
                </div>
"""
    replace_once(READER, old_toolbar, new_toolbar)

    class_replacements = {
        'className="mt-4 rounded-xl border border-sky-200 bg-sky-50/80 p-3 text-sky-950"':
            'className="magi-proofreading-json-tools mt-3"',
        'className="flex flex-col gap-3"':
            'className="magi-proofreading-json-layout"',
        'className="text-xs font-bold"':
            'className="magi-proofreading-label"',
        'className="mt-1 min-h-11 w-full rounded-lg border border-sky-200 bg-white px-3 py-2 font-normal text-gray-900 outline-none focus:border-sky-500 disabled:cursor-not-allowed disabled:opacity-60"':
            'className="magi-proofreading-select"',
        'className="grid grid-cols-1 gap-2 sm:grid-cols-3"':
            'className="magi-proofreading-json-actions"',
        'className="min-h-11 rounded-lg border border-blue-300 bg-white px-3 py-2 text-xs font-bold text-blue-700 shadow-sm hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-40"':
            'data-variant="secondary" className="magi-proofreading-button magi-proofreading-json-button"',
        'className="min-h-11 rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-bold text-emerald-700 shadow-sm hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-40"':
            'data-variant="secondary" className="magi-proofreading-button magi-proofreading-json-button"',
        'className="min-h-11 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-bold text-white shadow hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"':
            'data-variant="primary" className="magi-proofreading-button magi-proofreading-json-button"',
        'className="mt-2 text-xs font-bold text-red-700"':
            'className="magi-proofreading-alert mt-2"',
        'className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-900"':
            'className="magi-proofreading-alert mt-2"',
        'className="mt-2 text-[11px] text-sky-800/80"':
            'className="magi-proofreading-help mt-2"',
        'className="mt-4 grid gap-3 md:grid-cols-2"':
            'className="magi-proofreading-fields mt-3"',
        'className="text-xs font-bold text-emerald-900"':
            'className="magi-proofreading-label"',
        'className="mt-1 w-full rounded-lg border border-emerald-200 bg-white px-3 py-2 font-normal outline-none focus:border-emerald-500"':
            'className="magi-proofreading-input"',
        'className="mt-1 w-full resize-y rounded-lg border border-emerald-200 bg-white px-3 py-2 font-normal outline-none focus:border-emerald-500"':
            'className="magi-proofreading-input magi-proofreading-note"',
        'className="mt-3 rounded-lg border border-emerald-200 bg-white/70 p-3"':
            'className="magi-proofreading-submit-panel mt-3"',
        'className="text-xs text-emerald-800"':
            'className="magi-proofreading-help"',
        'className="mb-2 rounded bg-amber-50 px-2 py-1 text-[10px] text-amber-800"':
            'className="magi-proofreading-alert mb-2"',
        'className="text-[10px] text-emerald-700/70"':
            'className="magi-proofreading-help"',
        'className="rounded-lg bg-purple-600 px-4 py-2 text-xs font-bold text-white shadow hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-40"':
            'data-variant="primary" className="magi-proofreading-button"',
        'className="text-xs text-amber-800"':
            'className="magi-proofreading-alert"',
        'className="mt-2 text-[10px] text-emerald-700/70"':
            'className="magi-proofreading-help mt-2"',
        'className="mt-2 rounded bg-white/70 px-2 py-1 text-xs text-emerald-900"':
            'className="magi-proofreading-status mt-2"',
        'className="font-bold text-blue-700 underline"':
            'className="magi-proofreading-status-link font-bold underline"',
    }
    for old, new in class_replacements.items():
        replace_once(READER, old, new)

    utility_start = '            <div className="magi-reader-mobile-search relative mb-4 px-1 lg:hidden">'
    utility_end = '            {!loadError && visibleRenderList.map((row, offset) => {'
    utility_markup = """            {!loadError && utilityPanelOpen && (
              <section
                className="magi-reader-utility-panel"
                aria-label="阅读导航与分页"
              >
                <button
                  type="button"
                  aria-label="关闭阅读导航栏"
                  title="关闭阅读导航栏"
                  onClick={() => setUtilityPanelOpen(false)}
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
            )}

            {!loadError && !utilityPanelOpen && (
              <button
                type="button"
                onClick={() => setUtilityPanelOpen(true)}
                className="magi-reader-utility-reopen"
              >
                ⌂ 导航
              </button>
            )}

"""
    replace_between(READER, utility_start, utility_end, utility_markup)

    replace_once(
        READER,
        """            {!loadError && renderList.length > STORY_ROWS_PER_PAGE && (
              <StoryPagination
                page={visiblePage}
                pageCount={pageCount}
                start={pageStart}
                end={Math.min(pageStart + visibleRenderList.length, renderList.length)}
                total={renderList.length}
                onPage={changeVisiblePage}
              />
            )}
""",
        "",
    )
    replace_between(
        READER,
        "type StoryPaginationProps = {",
        "type StoryRowProps = {",
        "",
    )

    row_class_replacements = {
        'className="reader-font-cn-title flex w-full max-w-xl items-center gap-2 rounded-xl border-2 border-amber-300 bg-amber-50 p-2 text-xs font-bold text-amber-900"':
            'className="magi-translation-choice-shell reader-font-cn-title flex w-full max-w-xl items-center gap-2 p-2 text-xs font-bold"',
        'className="reader-font-cn-title min-w-0 flex-1 rounded border border-amber-200 bg-white px-2 py-1.5 font-normal text-black outline-none focus:ring-2 focus:ring-amber-400"':
            'className="magi-translation-choice-input reader-font-cn-title min-w-0 flex-1 px-2 py-1.5 font-normal outline-none"',
        """className={`reader-font-cn-title w-20 flex-shrink-0 rounded border px-1 py-1 text-right text-[11px] font-bold leading-tight outline-none focus:ring-2 focus:ring-emerald-500 md:w-24 ${
                  theme === 'dark'
                    ? 'border-gray-700 bg-gray-800 text-white'
                    : 'border-gray-200 bg-white text-black'
                }`}""":
            'className="magi-translation-speaker-input reader-font-cn-title w-20 flex-shrink-0 px-1 py-1 text-right font-bold leading-tight outline-none md:w-24"',
        """className={`reader-font-cn-body relative z-0 block w-full rounded border p-2 font-sans text-sm outline-none transition focus:ring-2 focus:ring-emerald-500 ${
                    theme === 'dark'
                      ? 'border-gray-700 bg-gray-800 text-white'
                      : 'border-gray-200 bg-white text-black'
                  }`}""":
            'className="magi-translation-textarea reader-font-cn-body relative z-0 block w-full p-2 font-sans outline-none transition"',
        'className="reader-font-cn-body pointer-events-none absolute inset-0 z-10 select-none overflow-hidden whitespace-pre-wrap break-words rounded border border-transparent p-2 font-sans text-sm"':
            'className="magi-translation-linebreak-overlay reader-font-cn-body pointer-events-none absolute inset-0 z-10 select-none overflow-hidden whitespace-pre-wrap break-words p-2 font-sans"',
        """className={`exedra-jp-story-text min-w-0 flex-1 break-words whitespace-pre-wrap font-sans text-sm opacity-70 ${lineTextAlignClass(row.jp)} ${lineKindClass(row.jp)}`}""":
            """className={`exedra-jp-story-text min-w-0 flex-1 break-words whitespace-pre-wrap font-sans opacity-70 ${lineTextAlignClass(row.jp)} ${lineKindClass(row.jp)}`}""",
        """className={`${language === 'cn' ? 'reader-font-cn-title' : 'reader-font-jp-title'} h-fit w-20 flex-shrink-0 break-words rounded px-1 pt-1 text-right text-[11px] font-bold leading-tight md:w-24 ${""":
            """className={`magi-reader-speaker-label ${language === 'cn' ? 'reader-font-cn-title' : 'reader-font-jp-title'} h-fit w-20 flex-shrink-0 break-words rounded px-1 pt-1 text-right font-bold leading-tight md:w-24 ${""",
    }
    for old, new in row_class_replacements.items():
        replace_once(READER, old, new)


def patch_tests() -> None:
    replace_once(
        PREFERENCES_TEST,
        """test('reader display preferences keep the current 768px width as the safe default', () => {
  assert.deepEqual(parseReaderDisplayPreferences(null), {
    textWidthPx: DEFAULT_READER_TEXT_WIDTH,
    fontSizePx: DEFAULT_READER_FONT_SIZE,
    fontControlOpen: true,
    showLineBreaks: false,
  });
  assert.deepEqual(parseReaderDisplayPreferences('{broken'), {
    textWidthPx: DEFAULT_READER_TEXT_WIDTH,
    fontSizePx: DEFAULT_READER_FONT_SIZE,
    fontControlOpen: true,
    showLineBreaks: false,
  });
});
""",
        """test('reader display preferences default to visible line-break markers', () => {
  assert.deepEqual(parseReaderDisplayPreferences(null), {
    textWidthPx: DEFAULT_READER_TEXT_WIDTH,
    fontSizePx: DEFAULT_READER_FONT_SIZE,
    fontControlOpen: true,
    showLineBreaks: true,
  });
  assert.deepEqual(parseReaderDisplayPreferences('{broken'), {
    textWidthPx: DEFAULT_READER_TEXT_WIDTH,
    fontSizePx: DEFAULT_READER_FONT_SIZE,
    fontControlOpen: true,
    showLineBreaks: true,
  });
});
""",
    )
    replace_once(
        PREFERENCES_TEST,
        """test('reader display preferences accept only an explicit boolean marker choice', () => {
  assert.equal(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 768, showLineBreaks: 'true' }),
    ).showLineBreaks,
    false,
  );
});
""",
        """test('legacy or malformed marker choices fall back to the visible default', () => {
  assert.equal(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 768, showLineBreaks: 'true' }),
    ).showLineBreaks,
    true,
  );
  assert.equal(
    parseReaderDisplayPreferences(
      JSON.stringify({ textWidthPx: 768, showLineBreaks: false }),
    ).showLineBreaks,
    false,
  );
});
""",
    )

    first_test_start = "test('reader exposes a complete in-page search label at desktop and mobile widths'"
    first_test_end = "test('reader offers a closable quick font ruler"
    replace_between(
        READER_TEST,
        first_test_start,
        first_test_end,
        """test('reader exposes desktop search and compact utility-panel mobile search', async () => {
  const reader = await readFile(readerPath, 'utf8');
  assert.equal((reader.match(/placeholder=\"页内搜索\"/g) ?? []).length, 2);
  assert.match(reader, /magi-reader-search-shell[\\s\\S]*min-w-48/);
  assert.match(reader, /magi-reader-search-shell[\\s\\S]*lg:flex/);
  assert.match(reader, /magi-reader-utility-search[\\s\\S]*lg:hidden/);
  assert.doesNotMatch(reader, /magi-reader-mobile-search/);
  assert.match(reader, /magi-reader-search-input h-9[\\s\\S]*leading-5/);
  assert.match(reader, /title=\"输入关键词后按 Enter 跳到下一处\"/);
});

""",
    )

    pagination_start = "test('reader provides persistent boundary-aware edge pagination without covering mobile text'"
    pagination_end = "test('day Reader chrome is neutral"
    replace_between(
        READER_TEST,
        pagination_start,
        pagination_end,
        """test('reader keeps edge pagination while merging page status into a closable utility window', async () => {
  const [reader, css] = await Promise.all([
    readFile(readerPath, 'utf8'),
    readFile(cssPath, 'utf8'),
  ]);
  assert.match(reader, /pageCount > 1 && \\([\\s\\S]*?aria-label=\"剧情快速翻页\"/);
  assert.match(reader, /visiblePage > 0 && \\([\\s\\S]*?aria-label=\"上一页\"/);
  assert.match(reader, /visiblePage \\+ 1 < pageCount && \\([\\s\\S]*?aria-label=\"下一页\"/);
  assert.match(reader, /magi-reader-utility-panel/);
  assert.match(reader, /aria-label=\"关闭阅读导航栏\"/);
  assert.match(reader, /magi-reader-page-summary/);
  assert.match(reader, /第 \\{visiblePage \\+ 1\\} \\/ \\{pageCount\\} 页/);
  assert.match(reader, /magi-reader-utility-reopen/);
  assert.doesNotMatch(reader, /<StoryPagination/);
  assert.doesNotMatch(reader, /← 上一页/);
  assert.doesNotMatch(reader, /下一页 →/);
  assert.match(reader, /window\\.addEventListener\\('keydown', handlePageTurnKeyDown\\)/);
  assert.match(reader, /onTouchStart=\\{handlePageTouchStart\\}/);
  assert.match(reader, /onTouchEnd=\\{handlePageTouchEnd\\}/);
  assert.match(reader, /paddingInline: 'clamp\\(3\\.25rem, 6vw, 4rem\\)'/);
  assert.match(css, /\\.magi-reader-utility-panel[\\s\\S]*backdrop-filter:/);
  assert.match(css, /\\.magi-reader-page-turn[\\s\\S]*?min-width:\\s*2\\.8rem;/);
});

""",
    )

    append_once(
        HOME_TEST,
        "home search grows from a compact measured width",
        """test('home search grows from a compact measured width before other mobile controls', () => {
  assert.match(page, /compactSearchCharacters/u);
  assert.match(page, /--magi-home-search-width/u);
  assert.match(page, /magi-home-search-shell relative min-w-0/u);
  assert.match(page, /magi-home-theme-switcher/u);
  assert.match(css, /\\.magi-home-search-shell\\s*\\{[\\s\\S]*--magi-home-search-width/u);
});
""",
    )


def patch_css() -> None:
    append_once(
        REFINEMENTS,
        "Reader UI V26",
        r"""
/* =========================================
   Reader UI V26 — compact chrome, technical glass and theme-native editing
   ========================================= */

/* The home search starts at the width required by its label, then grows with
   typed content. On mobile, search and theme controls are laid out before the
   remaining toolbar controls so the theme switcher cannot fall to a third row. */
.magi-home-search-shell {
  --magi-home-search-width: 12em;
  width: min(var(--magi-home-search-width), 100%);
  max-width: min(36rem, 100%);
  flex: 0 1 var(--magi-home-search-width);
  transition: width 160ms ease, flex-basis 160ms ease;
}

.magi-home-search-shell .magi-home-search-input {
  width: 100%;
  min-width: 0;
}

.magi-home-theme-switcher {
  flex: none;
}

@media (max-width: 767px) {
  .magi-home-toolbar-row {
    align-items: center;
  }

  .magi-home-toolbar-controls {
    display: contents;
  }

  .magi-home-search-shell {
    order: 0;
    min-width: 12rem;
    max-width: calc(100% - 8.6rem);
  }

  .magi-home-theme-switcher {
    order: 1;
    align-self: center !important;
    margin-left: auto;
  }

  .magi-home-toolbar-controls > :not(.magi-home-search-shell) {
    order: 2;
  }
}

@media (max-width: 380px) {
  .magi-home-search-shell {
    min-width: 11.25rem;
    max-width: calc(100% - 8.1rem);
  }
}

/* Compact Reader title bar: identity and controls share available width rather
   than creating mostly empty rows on phones. */
.magi-reader-header-compact {
  min-height: 3.25rem;
  align-content: center;
}

.magi-reader-header-identity,
.magi-reader-header-meta {
  min-width: 0;
}

.magi-reader-header-meta .magi-reader-story-id {
  min-width: 0;
  max-width: min(24rem, 42vw);
}

.magi-reader-header-actions {
  margin-left: auto;
}

@media (max-width: 767px) {
  .magi-reader-header-compact {
    padding-block: 0.35rem !important;
  }

  .magi-reader-header-identity {
    flex: 1 1 calc(100% - 10.5rem);
    gap: 0.35rem;
  }

  .magi-reader-header-meta {
    gap: 0.2rem;
  }

  .magi-reader-header-meta .magi-reader-story-id {
    max-width: 10.5rem;
  }

  .magi-reader-header-actions {
    gap: 0.15rem;
  }

  .magi-reader-header-actions > button {
    padding: 0.42rem;
  }
}

/* Technical glass palette shared by navigation and proofreading tools. */
.magi-reader-root {
  --magi-tool-text: #2d3334;
  --magi-tool-muted: #667071;
  --magi-tool-border: rgba(74, 81, 82, 0.68);
  --magi-tool-inset: rgba(255, 255, 255, 0.7);
  --magi-tool-surface: rgba(226, 230, 230, 0.9);
  --magi-tool-surface-strong: rgba(242, 244, 243, 0.96);
  --magi-tool-control: rgba(241, 243, 242, 0.9);
  --magi-tool-accent: #596263;
  --magi-tool-accent-text: #f7f8f8;
  --magi-tool-shadow: rgba(30, 34, 35, 0.2);
  --magi-tool-alert: rgba(223, 201, 145, 0.55);
}

.magi-reader-theme-paper {
  --magi-tool-text: #342b20;
  --magi-tool-muted: #74664f;
  --magi-tool-border: rgba(89, 69, 40, 0.68);
  --magi-tool-inset: rgba(255, 249, 225, 0.72);
  --magi-tool-surface: rgba(225, 208, 161, 0.9);
  --magi-tool-surface-strong: rgba(246, 235, 202, 0.96);
  --magi-tool-control: rgba(247, 237, 207, 0.91);
  --magi-tool-accent: #6a5333;
  --magi-tool-accent-text: #fff7df;
  --magi-tool-shadow: rgba(57, 42, 22, 0.21);
  --magi-tool-alert: rgba(177, 128, 43, 0.22);
}

.magi-reader-theme-green {
  --magi-tool-text: #17372d;
  --magi-tool-muted: #527064;
  --magi-tool-border: rgba(52, 94, 76, 0.58);
  --magi-tool-inset: rgba(247, 255, 249, 0.72);
  --magi-tool-surface: rgba(205, 226, 212, 0.9);
  --magi-tool-surface-strong: rgba(232, 244, 235, 0.96);
  --magi-tool-control: rgba(236, 247, 239, 0.92);
  --magi-tool-accent: #376b55;
  --magi-tool-accent-text: #f4fff8;
  --magi-tool-shadow: rgba(25, 67, 51, 0.19);
  --magi-tool-alert: rgba(200, 164, 71, 0.24);
}

.magi-reader-theme-dark {
  --magi-tool-text: #edf2f3;
  --magi-tool-muted: #a9b5b8;
  --magi-tool-border: rgba(174, 188, 192, 0.48);
  --magi-tool-inset: rgba(255, 255, 255, 0.12);
  --magi-tool-surface: rgba(35, 43, 49, 0.92);
  --magi-tool-surface-strong: rgba(48, 58, 65, 0.97);
  --magi-tool-control: rgba(43, 52, 59, 0.94);
  --magi-tool-accent: #c6d1d4;
  --magi-tool-accent-text: #182024;
  --magi-tool-shadow: rgba(0, 0, 0, 0.42);
  --magi-tool-alert: rgba(153, 112, 36, 0.3);
}

/* The page counter now belongs to the Home/Tools glass window. */
.magi-reader-utility-panel {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  margin: 0.35rem auto 0.9rem;
  padding: 0.72rem 2.55rem 0.72rem 0.72rem;
  border: 1px solid var(--magi-tool-border);
  color: var(--magi-tool-text);
  background:
    linear-gradient(118deg, var(--magi-tool-inset), transparent 42%),
    var(--magi-tool-surface);
  box-shadow:
    5px 7px 18px var(--magi-tool-shadow),
    inset 1px 1px var(--magi-tool-inset);
  backdrop-filter: blur(14px) saturate(0.82);
  -webkit-backdrop-filter: blur(14px) saturate(0.82);
  clip-path: polygon(
    0.7rem 0,
    calc(100% - 0.7rem) 0,
    100% 0.7rem,
    100% calc(100% - 0.7rem),
    calc(100% - 0.7rem) 100%,
    0.7rem 100%,
    0 calc(100% - 0.7rem),
    0 0.7rem
  );
}

.magi-reader-utility-panel::before {
  content: '';
  position: absolute;
  z-index: -1;
  inset: 0.34rem;
  border: 1px solid color-mix(in srgb, var(--magi-tool-border) 58%, transparent);
  pointer-events: none;
  clip-path: inherit;
}

.magi-reader-utility-panel::after {
  content: '';
  position: absolute;
  z-index: -1;
  width: 1.05rem;
  height: 1.05rem;
  top: 0.48rem;
  left: 0.48rem;
  border-top: 2px solid var(--magi-tool-border);
  border-left: 2px solid var(--magi-tool-border);
  opacity: 0.7;
  pointer-events: none;
}

.magi-reader-theme-paper .magi-reader-utility-panel {
  border-radius: 1.35rem;
  clip-path: none;
  outline: 1px solid rgba(91, 69, 38, 0.42);
  outline-offset: -0.38rem;
}

.magi-reader-utility-content {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 0.55rem;
}

.magi-reader-utility-search {
  position: relative;
  width: min(18rem, 100%);
}

.magi-reader-utility-search .magi-reader-search-input {
  border: 1px solid color-mix(in srgb, var(--magi-tool-border) 62%, transparent);
  color: var(--magi-tool-text);
  background: var(--magi-tool-control);
  box-shadow: inset 1px 1px var(--magi-tool-inset);
}

.magi-reader-search-next {
  position: absolute;
  right: 0.35rem;
  top: 50%;
  min-width: 2.4rem;
  padding: 0.22rem 0.35rem;
  border: 1px solid var(--magi-tool-border);
  color: var(--magi-tool-accent-text);
  background: var(--magi-tool-accent);
  font-size: 0.68rem;
  transform: translateY(-50%);
}

.magi-reader-utility-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
}

.magi-reader-utility-button,
.magi-reader-utility-reopen {
  display: inline-flex;
  min-height: 2.15rem;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--magi-tool-border);
  color: var(--magi-tool-text);
  background: var(--magi-tool-control);
  box-shadow:
    inset 1px 1px var(--magi-tool-inset),
    2px 3px 7px color-mix(in srgb, var(--magi-tool-shadow) 62%, transparent);
  font-size: 0.72rem;
  font-weight: 800;
}

.magi-reader-utility-button {
  padding: 0.42rem 0.72rem;
}

.magi-reader-utility-button:hover,
.magi-reader-utility-button:focus-visible,
.magi-reader-utility-reopen:hover,
.magi-reader-utility-reopen:focus-visible {
  color: var(--magi-tool-accent-text);
  background: var(--magi-tool-accent);
  outline: 2px solid var(--magi-tool-inset);
  outline-offset: 1px;
}

.magi-reader-page-summary {
  flex: 1 1 16rem;
  min-width: 0;
  color: var(--magi-tool-muted);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 0.72rem;
  line-height: 1.35;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.magi-reader-utility-close {
  position: absolute;
  z-index: 3;
  top: 0.36rem;
  right: 0.36rem;
  display: grid;
  width: 1.72rem;
  height: 1.72rem;
  place-items: center;
  border: 1px solid var(--magi-tool-border);
  color: var(--magi-tool-text);
  background: var(--magi-tool-control);
  box-shadow:
    inset 1px 1px var(--magi-tool-inset),
    inset -1px -1px color-mix(in srgb, var(--magi-tool-border) 48%, transparent);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 1rem;
  line-height: 1;
}

.magi-reader-theme-paper .magi-reader-utility-close {
  border-radius: 0.48rem;
}

.magi-reader-utility-close:hover,
.magi-reader-utility-close:focus-visible {
  color: #fff;
  background: #8d4339;
  outline: 1px solid #fff;
  outline-offset: -3px;
}

.magi-reader-utility-reopen {
  margin: 0.25rem 0 0.75rem auto;
  padding: 0.35rem 0.65rem;
}

/* Theme-native proofreading controls replace the former white, blue and purple
   surfaces. The same variables also skin every per-line editor input. */
.magi-proofreading-panel {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  border: 1px solid var(--magi-tool-border);
  border-radius: 0.35rem;
  color: var(--magi-tool-text);
  background:
    linear-gradient(126deg, var(--magi-tool-inset), transparent 36%),
    var(--magi-tool-surface);
  box-shadow:
    6px 8px 20px var(--magi-tool-shadow),
    inset 1px 1px var(--magi-tool-inset);
  backdrop-filter: blur(12px) saturate(0.84);
  -webkit-backdrop-filter: blur(12px) saturate(0.84);
}

.magi-proofreading-panel::before,
.magi-proofreading-panel::after {
  content: '';
  position: absolute;
  z-index: -1;
  width: 1rem;
  height: 1rem;
  pointer-events: none;
  opacity: 0.72;
}

.magi-proofreading-panel::before {
  top: 0.55rem;
  left: 0.55rem;
  border-top: 2px solid var(--magi-tool-border);
  border-left: 2px solid var(--magi-tool-border);
}

.magi-proofreading-panel::after {
  right: 0.55rem;
  bottom: 0.55rem;
  border-right: 2px solid var(--magi-tool-border);
  border-bottom: 2px solid var(--magi-tool-border);
}

.magi-reader-theme-paper .magi-proofreading-panel {
  border-radius: 1.3rem;
  outline: 1px solid rgba(94, 70, 37, 0.42);
  outline-offset: -0.38rem;
}

.magi-proofreading-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 0.45rem;
}

.magi-proofreading-kicker {
  display: inline-flex;
  min-height: 2.15rem;
  align-items: center;
  padding-inline: 0.2rem;
  color: var(--magi-tool-muted);
  font-size: 0.72rem;
  font-weight: 900;
}

.magi-proofreading-button {
  display: inline-flex;
  min-height: 2.15rem;
  flex: 1 1 8.5rem;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  padding: 0.42rem 0.68rem;
  border: 1px solid var(--magi-tool-border);
  border-radius: 0.3rem;
  color: var(--magi-tool-text);
  background: var(--magi-tool-control);
  box-shadow:
    inset 1px 1px var(--magi-tool-inset),
    2px 3px 8px color-mix(in srgb, var(--magi-tool-shadow) 60%, transparent);
  font-size: 0.72rem;
  font-weight: 900;
  text-align: center;
  transition: filter 120ms ease, transform 120ms ease;
}

.magi-reader-theme-paper .magi-proofreading-button {
  border-radius: 0.75rem;
}

.magi-proofreading-button[data-variant='primary'] {
  color: var(--magi-tool-accent-text);
  background: var(--magi-tool-accent);
}

.magi-proofreading-button:hover,
.magi-proofreading-button:focus-visible {
  filter: brightness(1.06);
  transform: translateY(-1px);
  outline: 2px solid var(--magi-tool-inset);
  outline-offset: 1px;
}

.magi-proofreading-button:disabled {
  cursor: not-allowed;
  filter: grayscale(0.45);
  opacity: 0.42;
  transform: none;
}

.magi-proofreading-linebreak-toggle {
  display: flex;
  min-height: 2.15rem;
  flex: 1 1 15rem;
  align-items: center;
  gap: 0.48rem;
  padding: 0.38rem 0.65rem;
  border: 1px solid var(--magi-tool-border);
  border-radius: 0.3rem;
  color: var(--magi-tool-text);
  background: var(--magi-tool-control);
  box-shadow: inset 1px 1px var(--magi-tool-inset);
  cursor: pointer;
}

.magi-reader-theme-paper .magi-proofreading-linebreak-toggle {
  border-radius: 0.75rem;
}

.magi-proofreading-linebreak-toggle input {
  width: 1rem;
  height: 1rem;
  flex: none;
  accent-color: var(--magi-tool-accent);
}

.magi-proofreading-linebreak-toggle span {
  display: grid;
  min-width: 0;
}

.magi-proofreading-linebreak-toggle strong {
  font-size: 0.72rem;
}

.magi-proofreading-linebreak-toggle small {
  color: var(--magi-tool-muted);
  font-size: 0.62rem;
  line-height: 1.25;
}

.magi-proofreading-json-tools,
.magi-proofreading-submit-panel {
  border: 1px solid color-mix(in srgb, var(--magi-tool-border) 72%, transparent);
  border-radius: 0.42rem;
  color: var(--magi-tool-text);
  background: color-mix(
    in srgb,
    var(--magi-tool-surface-strong) 88%,
    transparent
  );
  box-shadow: inset 1px 1px var(--magi-tool-inset);
}

.magi-proofreading-json-tools {
  padding: 0.72rem;
}

.magi-proofreading-submit-panel {
  padding: 0.68rem;
}

.magi-reader-theme-paper .magi-proofreading-json-tools,
.magi-reader-theme-paper .magi-proofreading-submit-panel {
  border-radius: 1rem;
}

.magi-proofreading-json-layout {
  display: grid;
  gap: 0.62rem;
}

.magi-proofreading-json-actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.45rem;
}

.magi-proofreading-json-button {
  min-height: 2.35rem;
  flex-basis: auto;
  padding-block: 0.45rem;
}

.magi-proofreading-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.65rem;
}

.magi-proofreading-label {
  display: grid;
  gap: 0.28rem;
  color: var(--magi-tool-text);
  font-size: 0.72rem;
  font-weight: 900;
}

.magi-proofreading-select,
.magi-proofreading-input,
.magi-translation-speaker-input,
.magi-translation-textarea,
.magi-translation-choice-input {
  width: 100%;
  border: 1px solid var(--magi-tool-border);
  border-radius: 0.28rem;
  color: var(--magi-tool-text);
  background: var(--magi-tool-control);
  box-shadow: inset 1px 1px var(--magi-tool-inset);
  outline: none;
}

.magi-proofreading-select,
.magi-proofreading-input {
  min-height: 2.45rem;
  padding: 0.48rem 0.65rem;
  font-weight: 400;
}

.magi-proofreading-note {
  min-height: 3.25rem;
  resize: vertical;
}

.magi-reader-theme-paper .magi-proofreading-select,
.magi-reader-theme-paper .magi-proofreading-input,
.magi-reader-theme-paper .magi-translation-speaker-input,
.magi-reader-theme-paper .magi-translation-textarea,
.magi-reader-theme-paper .magi-translation-choice-input {
  border-radius: 0.72rem;
}

.magi-proofreading-select:focus,
.magi-proofreading-input:focus,
.magi-translation-speaker-input:focus,
.magi-translation-textarea:focus,
.magi-translation-choice-input:focus {
  border-color: var(--magi-tool-accent);
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--magi-tool-accent) 34%, transparent),
    inset 1px 1px var(--magi-tool-inset);
}

.magi-proofreading-select:disabled {
  cursor: not-allowed;
  opacity: 0.48;
}

.magi-proofreading-input::placeholder,
.magi-translation-textarea::placeholder,
.magi-translation-speaker-input::placeholder,
.magi-translation-choice-input::placeholder {
  color: var(--magi-tool-muted);
  opacity: 0.75;
}

.magi-proofreading-alert {
  padding: 0.42rem 0.55rem;
  border: 1px solid color-mix(in srgb, var(--magi-tool-border) 55%, transparent);
  border-radius: 0.3rem;
  color: var(--magi-tool-text);
  background: var(--magi-tool-alert);
  font-size: 0.68rem;
  font-weight: 700;
}

.magi-proofreading-help {
  color: var(--magi-tool-muted);
  font-size: 0.65rem;
  line-height: 1.4;
}

.magi-proofreading-status {
  padding: 0.42rem 0.55rem;
  border: 1px solid color-mix(in srgb, var(--magi-tool-border) 58%, transparent);
  border-radius: 0.3rem;
  color: var(--magi-tool-text);
  background: var(--magi-tool-control);
  font-size: 0.7rem;
}

.magi-proofreading-status-link {
  color: var(--magi-tool-accent);
}

.magi-translation-choice-shell {
  border: 1px solid var(--magi-tool-border);
  border-radius: 0.4rem;
  color: var(--magi-tool-text);
  background: var(--magi-tool-surface);
}

.magi-translation-speaker-input {
  width: 5rem;
  font-size: 0.74em;
}

.magi-translation-textarea {
  min-height: 2.65em;
  resize: vertical;
  font-size: inherit;
  line-height: inherit;
}

.magi-translation-linebreak-overlay {
  border: 1px solid transparent;
  border-radius: 0.28rem;
  color: transparent;
  font-size: inherit;
  line-height: inherit;
}

.magi-reader-speaker-label {
  font-size: 0.74em;
}

/* A fixed text-sm class previously kept Japanese at 14px while Chinese inherited
   the global slider. Both language panes and the editing textarea now inherit
   the same Reader font size. */
.exedra-jp-story-text,
.reader-font-jp-body,
.reader-font-cn-body {
  font-size: inherit;
}

/* Stronger technical treatment for white windows and warm rounded treatment for
   the paper theme, without copying any reference artwork. */
.magi-reader-theme-light .magi-floating-window-light {
  outline: 1px solid rgba(76, 83, 84, 0.46);
  outline-offset: -0.38rem;
  box-shadow:
    7px 9px 22px rgba(29, 33, 34, 0.26),
    inset 1px 1px rgba(255, 255, 255, 0.78) !important;
}

.magi-reader-theme-paper .magi-floating-window-paper {
  border-width: 1px;
  outline: 1px solid rgba(94, 70, 37, 0.48);
  outline-offset: -0.42rem;
  box-shadow:
    14px 18px 40px rgba(48, 35, 19, 0.27),
    inset 1px 1px rgba(255, 248, 220, 0.7) !important;
}

@media (max-width: 640px) {
  .magi-reader-utility-panel {
    margin-top: 0.15rem;
    padding: 0.62rem 2.35rem 0.62rem 0.62rem;
  }

  .magi-reader-utility-content {
    gap: 0.45rem;
  }

  .magi-reader-utility-search {
    width: min(16.5rem, 100%);
  }

  .magi-reader-utility-actions {
    gap: 0.35rem;
  }

  .magi-reader-utility-button {
    min-height: 2rem;
    padding: 0.34rem 0.55rem;
    font-size: 0.68rem;
  }

  .magi-reader-page-summary {
    flex-basis: 100%;
    text-align: left;
  }

  .magi-proofreading-panel {
    padding: 0.68rem !important;
  }

  .magi-proofreading-kicker {
    flex: 0 0 100%;
    min-height: auto;
  }

  .magi-proofreading-button {
    flex-basis: calc(50% - 0.25rem);
    min-width: 0;
  }

  .magi-proofreading-linebreak-toggle {
    flex-basis: 100%;
  }

  .magi-proofreading-json-actions {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .magi-proofreading-json-button:last-child {
    grid-column: 1 / -1;
  }

  .magi-proofreading-fields {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .magi-home-search-shell,
  .magi-proofreading-button {
    transition: none;
  }
}
""",
    )


def main() -> int:
    patch_home()
    patch_preferences()
    patch_reader()
    patch_tests()
    patch_css()
    print("READER_UI_V26_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
