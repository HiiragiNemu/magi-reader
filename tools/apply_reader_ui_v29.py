#!/usr/bin/env python3
"""Move reader theme switching into the compact floating utility widget.

The migration is intentionally fail-closed: every source block must match the
validated V28 tree exactly before it is replaced.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "website/app/reader/[id]/page.tsx"
REFINEMENTS = ROOT / "website/app/ui-refinements.css"
TEST = ROOT / "website/tests/reader-utility-theme-switcher.test.mjs"


OLD_UTILITY_BLOCK = '''                  <div className="magi-reader-utility-actions">
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
'''

NEW_UTILITY_BLOCK = '''                  <div className="magi-reader-utility-actions">
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
                    <div
                      className="magi-reader-utility-theme-switcher"
                      role="group"
                      aria-label="阅读主题"
                    >
                      {([
                        { key: 'light', icon: Sun, label: '亮色' },
                        { key: 'paper', icon: BookOpen, label: '护眼' },
                        { key: 'dark', icon: Moon, label: '暗黑' },
                        { key: 'green', icon: Leaf, label: '绿色' },
                      ] as const).map(option => (
                        <button
                          type="button"
                          key={option.key}
                          data-theme-option={option.key}
                          aria-label={`切换为${option.label}主题`}
                          aria-pressed={theme === option.key}
                          title={option.label}
                          onClick={() => setTheme(option.key)}
                          className="magi-reader-theme-option"
                        >
                          <option.icon
                            size={15}
                            strokeWidth={theme === option.key ? 2.5 : 1.9}
                          />
                          <span className="sr-only">{option.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
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
'''

OLD_SETTINGS_THEME = '''                <div>
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
'''

CSS_APPEND = r'''

/* =========================================
   Reader UI V29 — compact intrinsic utility panel and theme switcher
   ========================================= */

.magi-reader-utility-widget,
.magi-reader-utility-widget.is-expanded {
  width: fit-content;
  max-width: calc(100vw - 1rem);
}

.magi-reader-utility-panel-floating {
  width: auto;
  max-width: calc(100vw - 2.35rem);
}

.magi-reader-utility-panel-floating .magi-reader-utility-content {
  width: max-content;
  max-width: 100%;
  flex-direction: column;
  align-items: stretch;
  gap: 0.28rem;
}

.magi-reader-utility-panel-floating .magi-reader-utility-actions {
  display: flex;
  width: auto;
  min-width: 0;
  flex: 0 1 auto;
  align-items: center;
  flex-wrap: nowrap;
  gap: 0.28rem;
}

.magi-reader-utility-panel-floating .magi-reader-page-summary {
  align-self: flex-end;
  min-width: 0;
  flex: none;
  padding-inline: 0.18rem;
  white-space: nowrap;
  font-size: 0.62rem;
  line-height: 1.25;
}

.magi-reader-utility-theme-switcher {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 0.16rem;
  padding: 0.16rem;
  border: 1px solid color-mix(in srgb, var(--magi-tool-border) 58%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--magi-tool-control) 74%, transparent);
  box-shadow:
    inset 1px 1px var(--magi-tool-inset),
    inset -1px -1px color-mix(in srgb, var(--magi-tool-shadow) 38%, transparent);
}

.magi-reader-theme-option {
  display: inline-grid;
  width: 1.72rem;
  height: 1.72rem;
  flex: 0 0 1.72rem;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 50%;
  background: transparent;
  opacity: 0.68;
  box-shadow: none;
  transition:
    transform 140ms ease,
    opacity 140ms ease,
    border-color 140ms ease,
    background-color 140ms ease,
    box-shadow 140ms ease;
}

.magi-reader-theme-option:hover,
.magi-reader-theme-option:focus-visible {
  opacity: 1;
  transform: translateY(-1px);
  outline: 2px solid var(--magi-tool-inset);
  outline-offset: -3px;
}

.magi-reader-theme-option[data-theme-option='light'] {
  color: #9a6500;
  background: radial-gradient(circle at 42% 38%, #fff8c8 0 28%, rgba(245, 190, 60, 0.22) 68%, transparent 70%);
}

.magi-reader-theme-option[data-theme-option='paper'] {
  color: #705535;
  background: linear-gradient(145deg, rgba(255, 249, 224, 0.94), rgba(205, 183, 132, 0.34));
}

.magi-reader-theme-option[data-theme-option='dark'] {
  color: #b9c8ff;
  background: radial-gradient(circle at 38% 36%, rgba(111, 128, 190, 0.58), rgba(23, 31, 58, 0.82) 72%);
}

.magi-reader-theme-option[data-theme-option='green'] {
  color: #176c3d;
  background: linear-gradient(145deg, rgba(225, 249, 231, 0.92), rgba(92, 171, 116, 0.3));
}

.magi-reader-theme-option[aria-pressed='true'] {
  opacity: 1;
  transform: translateY(-1px) scale(1.04);
  border-color: currentColor;
  box-shadow:
    0 2px 7px color-mix(in srgb, currentColor 25%, transparent),
    inset 0 0 0 2px color-mix(in srgb, var(--magi-tool-inset) 72%, transparent);
}

@media (max-width: 767px) {
  .magi-reader-utility-widget,
  .magi-reader-utility-widget.is-expanded {
    width: fit-content;
    max-width: calc(100vw - 0.7rem);
  }

  .magi-reader-utility-panel-floating {
    width: auto;
    max-width: calc(100vw - 2.05rem);
  }

  .magi-reader-utility-panel-floating .magi-reader-utility-content {
    width: min(19rem, calc(100vw - 3rem));
  }

  .magi-reader-utility-panel-floating .magi-reader-utility-search {
    width: 100%;
    flex: none;
  }

  .magi-reader-utility-panel-floating .magi-reader-utility-actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .magi-reader-utility-panel-floating .magi-reader-page-summary {
    align-self: flex-start;
    white-space: normal;
    text-align: left;
  }

  .magi-reader-theme-option {
    width: 1.66rem;
    height: 1.66rem;
    flex-basis: 1.66rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .magi-reader-theme-option {
    transition: none;
  }
}
'''

TEST_CONTENT = r'''import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const reader = readFileSync(
  new URL('../app/reader/[id]/page.tsx', import.meta.url),
  'utf8',
);
const css = readFileSync(
  new URL('../app/ui-refinements.css', import.meta.url),
  'utf8',
);

test('reader theme controls live in the floating utility panel', () => {
  const utilityStart = reader.indexOf('className="magi-reader-utility-actions"');
  const utilityEnd = reader.indexOf('</DraggableReaderWidget>', utilityStart);
  assert.ok(utilityStart >= 0 && utilityEnd > utilityStart);
  const utility = reader.slice(utilityStart, utilityEnd);

  assert.match(utility, /magi-reader-utility-theme-switcher/u);
  assert.match(utility, /aria-label="阅读主题"/u);
  for (const theme of ['light', 'paper', 'dark', 'green']) {
    assert.match(utility, new RegExp(`data-theme-option=\\{option\\.key\\}`));
    assert.match(reader, new RegExp(`key: '${theme}'`));
  }
  assert.match(utility, /onClick=\{\(\) => setTheme\(option\.key\)\}/u);
});

test('settings window no longer duplicates the theme selector', () => {
  const settingsStart = reader.indexOf('title="阅读设置"');
  const settingsEnd = reader.indexOf('</FloatingWindow>', settingsStart);
  assert.ok(settingsStart >= 0 && settingsEnd > settingsStart);
  const settings = reader.slice(settingsStart, settingsEnd);

  assert.doesNotMatch(settings, />主题</u);
  assert.doesNotMatch(settings, /setTheme\(/u);
  assert.match(settings, /字号（\{fontSize\}px）/u);
});

test('floating utility panel uses intrinsic width and themed icon buttons', () => {
  assert.match(
    css,
    /Reader UI V29[\s\S]*magi-reader-utility-widget[\s\S]*width: fit-content/u,
  );
  assert.match(css, /magi-reader-utility-content[\s\S]*flex-direction: column/u);
  assert.match(css, /magi-reader-utility-theme-switcher/u);
  for (const theme of ['light', 'paper', 'dark', 'green']) {
    assert.match(css, new RegExp(`data-theme-option='${theme}'`));
  }
  assert.match(css, /magi-reader-theme-option\[aria-pressed='true'\]/u);
});
'''


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
            f"{path.relative_to(ROOT)} replacement count={count}; expected 1"
        )
    write(path, source.replace(old, new, 1))


def main() -> int:
    replace_once(READER, OLD_UTILITY_BLOCK, NEW_UTILITY_BLOCK)
    replace_once(READER, OLD_SETTINGS_THEME, "")

    css = read(REFINEMENTS)
    if "Reader UI V29 — compact intrinsic utility panel" in css:
        raise RuntimeError("V29 CSS already exists")
    write(REFINEMENTS, css.rstrip() + CSS_APPEND + "\n")

    if TEST.exists():
        raise RuntimeError(f"test already exists: {TEST.relative_to(ROOT)}")
    write(TEST, TEST_CONTENT)

    print("READER_UI_V29_COMPACT_THEME_SWITCHER_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
