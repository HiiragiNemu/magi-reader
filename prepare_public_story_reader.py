#!/usr/bin/env python3
"""Prepare the full MagiReader application for the public story archive.

The source branch also contains proofreading and administrator workflows.  The
public archive keeps local editing/download support, but hides review-management
entry points and does not require a submissions KV or Turnstile credentials.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one occurrence, found {count}")
    return text.replace(old, new, 1)


def patch_home(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "const DEFAULT_CATEGORY: Record<StorySystem, string> = {\n  magireco: 'main_story',\n  exedra: 'exedra_main',\n};",
        "const DEFAULT_CATEGORY: Record<StorySystem, string> = {\n  magireco: 'main_story',\n  exedra: 'exedra_main',\n};\nconst PUBLIC_STORY_ARCHIVE = process.env.NEXT_PUBLIC_STORY_ARCHIVE === '1';",
        "public archive constant",
    )
    text = replace_once(
        text,
        "  useEffect(() => {\n    const controller = new AbortController();\n    void fetch('/api/proofreading/machine-status', {",
        "  useEffect(() => {\n    if (PUBLIC_STORY_ARCHIVE) return;\n    const controller = new AbortController();\n    void fetch('/api/proofreading/machine-status', {",
        "skip public machine-status request",
    )
    text = replace_once(
        text,
        "            {storySystem === 'magireco' && proofreadingStatus && (",
        "            {!PUBLIC_STORY_ARCHIVE && storySystem === 'magireco' && proofreadingStatus && (",
        "hide review management banner",
    )
    text = replace_once(text, "MagiReader", "剧情阅读器", "public reader brand")
    text = replace_once(text, "Archive v3.0", "Magia Record + Magia Exedra", "public reader subtitle")
    text = replace_once(text, "关于我们", "相关项目", "public related projects label")
    text = replace_once(
        text,
        "                相关项目\n              </button>\n              <button\n                type=\"button\"\n                onClick={switchStorySystem}",
        "                相关项目\n              </button>\n              <Link\n                href=\"/raw-json\"\n                className={`px-2.5 py-1 rounded border text-xs font-bold whitespace-nowrap transition-all ${\n                  theme === 'dark'\n                    ? 'border-purple-800 bg-purple-900/30 text-purple-300 hover:bg-purple-800'\n                    : 'border-purple-200 bg-purple-50 text-purple-700 hover:bg-purple-100'\n                }`}\n              >\n                原始JSON\n              </Link>\n              <button\n                type=\"button\"\n                onClick={switchStorySystem}",
        "home raw JSON link",
    )
    path.write_text(text, encoding="utf-8")


def patch_reader(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "const MAX_STORY_SOURCE_BYTES = 8 * 1024 * 1024;"
    text = replace_once(
        text,
        marker,
        marker + "\nconst PUBLIC_STORY_ARCHIVE = process.env.NEXT_PUBLIC_STORY_ARCHIVE === '1';",
        "reader public archive constant",
    )
    text = replace_once(
        text,
        "                  ) : (\n                    <p className=\"text-xs text-amber-800\">\n                      投稿服务尚未配置。你仍可下载 TXT，并将文件交给项目维护者。\n                    </p>\n                  )}",
        "                  ) : (\n                    <p className=\"text-xs text-amber-800\">\n                      {PUBLIC_STORY_ARCHIVE\n                        ? '公开阅读站仅提供本地编辑和 TXT 下载，不接收在线投稿。'\n                        : '投稿服务尚未配置。你仍可下载 TXT，并将文件交给项目维护者。'}\n                    </p>\n                  )}",
        "public local-edit notice",
    )
    text = replace_once(text, "🔗 我的工具与动态", "相关项目", "reader related projects label")
    text = replace_once(
        text,
        "          <div className=\"flex shrink-0 items-center gap-2\">\n            <button",
        "          <div className=\"flex shrink-0 items-center gap-2\">\n            <Link\n              href=\"/raw-json\"\n              title=\"浏览全部原始剧情JSON\"\n              className=\"rounded-full bg-purple-100 px-3 py-1.5 text-xs font-bold text-purple-700 transition hover:bg-purple-200\"\n            >\n              JSON\n            </Link>\n            <button",
        "reader raw JSON link",
    )
    path.write_text(text, encoding="utf-8")


def patch_layout(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, 'title: "MagiReader"', 'title: "魔法纪录与 Magia Exedra 剧情阅读器"', "metadata title")
    text = replace_once(text, 'description: "Magia Record Story Archive"', 'description: "魔法纪录与 Magia Exedra 中日双语剧情资料库"', "metadata description")
    text = replace_once(text, '<html lang="zh"', '<html lang="zh-CN"', "document language")
    path.write_text(text, encoding="utf-8")


def patch_about(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, "我的其他工具和动态", "相关资料与工具", "about heading")
    text = replace_once(text, "Made with ❤️ by MadeInMagius", "魔法纪录与 Magia Exedra 剧情资料", "about footer")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--website", type=Path, default=Path("website"))
    args = parser.parse_args()
    root = args.website.resolve()
    patch_home(root / "app" / "page.tsx")
    patch_reader(root / "app" / "reader" / "[id]" / "page.tsx")
    patch_layout(root / "app" / "layout.tsx")
    patch_about(root / "components" / "AboutModal.tsx")
    print("public story reader mode prepared")


if __name__ == "__main__":
    main()
