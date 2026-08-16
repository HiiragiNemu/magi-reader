#!/usr/bin/env python3
"""Tighten ambiguous one-shot Reader UI V26 migration anchors."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools/apply_reader_ui_v26.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: replacement count={count}; expected 1")
    return source.replace(old, new, 1)


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    ambiguous = '''    class_replacements = {
        'className="mt-4 rounded-xl border border-sky-200 bg-sky-50/80 p-3 text-sky-950"':
            'className="magi-proofreading-json-tools mt-3"',
        'className="flex flex-col gap-3"':
            'className="magi-proofreading-json-layout"',
        'className="text-xs font-bold"':
            'className="magi-proofreading-label"',
'''
    anchored = '''    replace_once(
        READER,
        """                <div
                  data-scenario-json-tools="true"
                  className="mt-4 rounded-xl border border-sky-200 bg-sky-50/80 p-3 text-sky-950"
                >
                  <div className="flex flex-col gap-3">
                    <label className="text-xs font-bold">
""",
        """                <div
                  data-scenario-json-tools="true"
                  className="magi-proofreading-json-tools mt-3"
                >
                  <div className="magi-proofreading-json-layout">
                    <label className="magi-proofreading-label">
""",
    )

    class_replacements = {
'''
    source = replace_once(
        source,
        ambiguous,
        anchored,
        "anchor JSON tools block",
    )

    old_loop = '''    for old, new in class_replacements.items():
        replace_once(READER, old, new)
'''
    new_loop = '''    expected_class_counts = {
        'className="text-xs font-bold text-emerald-900"': 2,
    }
    for old, new in class_replacements.items():
        reader_source = read(READER)
        expected = expected_class_counts.get(old, 1)
        count = reader_source.count(old)
        if count != expected:
            raise RuntimeError(
                "website/app/reader/[id]/page.tsx class replacement "
                f"count={count}; expected {expected}; target={old!r}"
            )
        write(READER, reader_source.replace(old, new))
'''
    source = replace_once(
        source,
        old_loop,
        new_loop,
        "replace class loop",
    )

    # The edge-turn button geometry remains in globals.css while the new V26
    # utility/editor rules are appended to ui-refinements.css. Validate the
    # effective cascade instead of pretending either stylesheet is standalone.
    reader_css_source = '''  const [reader, css] = await Promise.all([
    readFile(readerPath, 'utf8'),
    readFile(cssPath, 'utf8'),
  ]);
  assert.match(reader, /pageCount > 1'''
    reader_css_effective = '''  const [reader, globals, refinements] = await Promise.all([
    readFile(readerPath, 'utf8'),
    readFile(cssPath, 'utf8'),
    readFile(new URL('../app/ui-refinements.css', import.meta.url), 'utf8'),
  ]);
  const css = `${globals}\\n${refinements}`;
  assert.match(reader, /pageCount > 1'''
    source = replace_once(
        source,
        reader_css_source,
        reader_css_effective,
        "validate V26 Reader against effective stylesheet cascade",
    )

    home_test_start = '''test('home search grows from a compact measured width before other mobile controls', () => {
  assert.match(page, /compactSearchCharacters/u);'''
    home_test_start_fixed = '''test('home search grows from a compact measured width before other mobile controls', () => {
  const refinements = readFileSync(
    path.resolve('app', 'ui-refinements.css'),
    'utf8',
  );
  assert.match(page, /compactSearchCharacters/u);'''
    source = replace_once(
        source,
        home_test_start,
        home_test_start_fixed,
        "load refinements stylesheet in V26 home test",
    )
    source = replace_once(
        source,
        r"  assert.match(css, /\\.magi-home-search-shell\\s*\\{[\\s\\S]*--magi-home-search-width/u);",
        r"  assert.match(refinements, /\\.magi-home-search-shell\\s*\\{[\\s\\S]*--magi-home-search-width/u);",
        "assert V26 home search against refinements stylesheet",
    )

    TARGET.write_text(source, encoding="utf-8", newline="\n")
    print("READER_UI_V26_RUNNER_PATCHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
