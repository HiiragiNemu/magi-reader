#!/usr/bin/env python3
"""Validate or upgrade the copied preservation reader application bundle.

UI v4 natively understands rendered-HTML snapshot records, so new builds do
not require destructive string replacement. Legacy bundles are still upgraded
when their old markers are present.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    args = parser.parse_args()
    path = args.app.resolve()
    text = path.read_text(encoding="utf-8")

    if "const UI_VERSION = 4" in text:
        required = (
            "record.html || articleFallback(record)",
            "data-theme=",
            "data-portal=",
            "enhanceArticle()",
        )
        missing = [marker for marker in required if marker not in text]
        if missing:
            raise RuntimeError(f"UI v4 bundle is incomplete: {missing}")
        print("UI v4 bundle is already native; no legacy patch required.")
        return

    replacements = (
        (
            "${renderWikitext(record.wikitext)}",
            "${record.html || renderWikitext(record.wikitext)}",
        ),
        (
            "record.wikitext || '（空页面）'",
            "record.rawHtml || record.wikitext || '（空页面）'",
        ),
        (
            "record.wikitext || ''",
            "record.rawHtml || record.wikitext || ''",
        ),
        ("复制原始 wikitext", "复制原始渲染HTML"),
        ("查看完整原始 wikitext（保真层）", "查看完整原始渲染HTML（保真层）"),
    )
    changed = False
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new)
            changed = True

    if not changed:
        raise RuntimeError("Unknown static application bundle: neither UI v4 nor a supported legacy bundle")

    path.write_text(text, encoding="utf-8")
    print("Legacy application bundle upgraded for rendered-HTML records.")


if __name__ == "__main__":
    main()
