#!/usr/bin/env python3
"""Apply deployment-mode fixes to the copied static application bundle."""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(f"static app patch target not found: {old[:120]}")
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    args = parser.parse_args()
    path = args.app.resolve()
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "const outline = (item.headings || []).filter((entry) => entry.level <= 4);",
        "const outline = (item.headings || []).filter((entry) => entry.level <= 4 && entry.id);",
    )
    text = replace_once(
        text,
        "href=\"#section-${index}-${attr(plain(entry.text).replace(/\\s+/g, '-'))}\"",
        "href=\"#${attr(entry.id)}\"",
    )
    text = replace_once(
        text,
        "if (!target) return;\n    const routeButton = target.closest('[data-route]');",
        "if (!target) return;\n"
        "    const tocLink = target.closest('.toc a[href^=\"#\"]');\n"
        "    if (tocLink) {\n"
        "      event.preventDefault();\n"
        "      const id = tocLink.getAttribute('href')?.slice(1);\n"
        "      if (id) document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });\n"
        "      return;\n"
        "    }\n"
        "    const routeButton = target.closest('[data-route]');",
    )
    text = text.replace(
        "MediaWiki API生成不可编辑的静态快照",
        "公开文章与分类链接图生成不可编辑的静态快照",
    )
    text = text.replace(
        "${escapeHtml(source.api)}",
        "${escapeHtml(source.base || source.api || 'https://magireco.moe')}",
    )
    text = text.replace(
        "每个页面均保留完整 wikitext、修订号、时间、字节数和 SHA-256",
        "每个页面均保留完整原始渲染HTML、修订号、来源地址、字节数和 SHA-256",
    )
    text = text.replace(
        "尚未解释的复杂模板仍以模板参数块展示，并可在页面底部展开完整源代码",
        "模板展开后的实际访客内容被直接保存，并可在页面底部展开完整原始HTML",
    )

    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
