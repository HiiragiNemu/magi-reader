#!/usr/bin/env python3
"""Apply TW official labels, split-search UI, and reader sizing changes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def apply_story_metadata(metadata: dict[str, dict[str, Any]]) -> None:
    path = ROOT / "website/public/story_index.json"
    stories = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(stories, list):
        raise RuntimeError("story_index 顶层不是数组")
    applied = 0
    for story in stories:
        if not isinstance(story, dict):
            continue
        identity = story.get("source_identity")
        info = metadata.get(identity) if isinstance(identity, str) else None
        if not info:
            continue
        story["official_tw"] = True
        story["official_tw_label"] = "台服官方"
        story["official_tw_provenance"] = "official_tw_human"
        story["official_tw_chapter_title"] = info.get("chapterTitle") or ""
        story["official_tw_section_titles"] = info.get("sectionTitles") or []
        if story.get("category") == "exedra_main" and info.get("chapterTitle"):
            story["folder"] = info["chapterTitle"]
        applied += 1
    path.write_text(
        json.dumps(stories, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"TW_STORY_METADATA_OK stories={applied}")


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"补丁锚点数量异常：{path}: {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_sidebar() -> None:
    path = ROOT / "website/components/Sidebar.tsx"
    text = path.read_text(encoding="utf-8")
    if "SIDEBAR_WIDTH_STORAGE_KEY" in text:
        return
    replace_once(
        path,
        "import { useEffect, useMemo, useState, type ComponentType } from 'react';",
        "import { useEffect, useMemo, useRef, useState, type ComponentType, type PointerEvent as ReactPointerEvent } from 'react';",
    )
    replace_once(
        path,
        "  human_verified?: boolean;\n  legacy_ids?: string[];",
        "  human_verified?: boolean;\n  official_tw?: boolean;\n  official_tw_label?: string;\n  official_tw_chapter_title?: string;\n  official_tw_section_titles?: string[];\n  legacy_ids?: string[];",
    )
    replace_once(
        path,
        "const NATURAL_COLLATOR = new Intl.Collator(['zh-CN', 'ja-JP'], {\n  numeric: true,\n  sensitivity: 'base',\n});",
        "const NATURAL_COLLATOR = new Intl.Collator(['zh-CN', 'ja-JP'], {\n  numeric: true,\n  sensitivity: 'base',\n});\nconst SIDEBAR_WIDTH_STORAGE_KEY = 'magi-reader-sidebar-width-v1';\nconst SIDEBAR_WIDTH_MIN = 240;\nconst SIDEBAR_WIDTH_MAX = 560;",
    )
    replace_once(
        path,
        "  const [folderOverrides, setFolderOverrides] = useState<Record<string, boolean>>({});\n  const sidebarRef = useDialog<HTMLElement>(isOpen, onClose);",
        "  const [folderOverrides, setFolderOverrides] = useState<Record<string, boolean>>({});\n  const [sidebarWidth, setSidebarWidth] = useState(288);\n  const sidebarWidthRef = useRef(288);\n  const sidebarRef = useDialog<HTMLElement>(isOpen, onClose);\n\n  useEffect(() => {\n    const stored = Number(window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY));\n    if (Number.isFinite(stored)) {\n      const normalized = Math.min(SIDEBAR_WIDTH_MAX, Math.max(SIDEBAR_WIDTH_MIN, stored));\n      sidebarWidthRef.current = normalized;\n      setSidebarWidth(normalized);\n    }\n  }, []);\n\n  const startSidebarResize = (event: ReactPointerEvent<HTMLButtonElement>) => {\n    event.preventDefault();\n    const startX = event.clientX;\n    const startWidth = sidebarWidthRef.current;\n    const move = (moveEvent: PointerEvent) => {\n      const next = Math.min(\n        SIDEBAR_WIDTH_MAX,\n        Math.max(SIDEBAR_WIDTH_MIN, startWidth + moveEvent.clientX - startX),\n      );\n      sidebarWidthRef.current = next;\n      setSidebarWidth(next);\n    };\n    const stop = () => {\n      window.removeEventListener('pointermove', move);\n      window.removeEventListener('pointerup', stop);\n      window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(Math.round(sidebarWidthRef.current)));\n    };\n    window.addEventListener('pointermove', move);\n    window.addEventListener('pointerup', stop, { once: true });\n  };",
    )
    replace_once(
        path,
        "className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col overflow-hidden border-r transition-transform duration-300 md:relative md:translate-x-0 ${",
        "style={{ width: sidebarWidth }}\n        className={`fixed inset-y-0 left-0 z-50 flex flex-col overflow-hidden border-r transition-transform duration-300 md:relative md:translate-x-0 ${",
    )
    replace_once(
        path,
        "{story.sections.map(section => {\n                                          const details = sectionDetails(section);",
        "{story.sections.map((section, sectionIndex) => {\n                                          const details = sectionDetails(section);\n                                          const officialLabel = story.official_tw_section_titles?.[sectionIndex];",
    )
    replace_once(path, "title={section}", "title={officialLabel || section}")
    replace_once(path, "└ {details.label}", "└ {officialLabel || details.label}")
    replace_once(
        path,
        "        </div>\n      </aside>",
        "        </div>\n        <button\n          type=\"button\"\n          aria-label=\"拖动调整侧边栏宽度\"\n          title={`侧边栏宽度：${sidebarWidth}px`}\n          onPointerDown={startSidebarResize}\n          className=\"absolute inset-y-0 right-0 hidden w-2 cursor-col-resize touch-none md:block hover:bg-blue-400/20\"\n        />\n      </aside>",
    )


def patch_home() -> None:
    path = ROOT / "website/app/page.tsx"
    text = path.read_text(encoding="utf-8")
    if "SEARCH_INDEX_MANIFEST_URLS" in text:
        return
    replace_once(
        path,
        "const SEARCH_INDEX_MANIFEST_URL = '/search_index_manifest.json';\nconst SEARCH_INDEX_LOCAL_FALLBACK_URL = '/search_content.json';",
        "const SEARCH_INDEX_MANIFEST_URLS: Record<StorySystem, string> = {\n  magireco: '/search_index_manifest.magireco.json',\n  exedra: '/search_index_manifest.exedra.json',\n};\nconst SEARCH_INDEX_LOCAL_FALLBACK_URLS: Record<StorySystem, string> = {\n  magireco: '/search_content.magireco.json',\n  exedra: '/search_content.exedra.json',\n};",
    )
    replace_once(
        path,
        "const isSearchIndexManifest = (value: unknown): value is SearchIndexManifest => {",
        "const isSearchIndexManifest = (\n  value: unknown,\n  scope: StorySystem,\n): value is SearchIndexManifest => {",
    )
    replace_once(
        path,
        "manifest.object_key === `search/${sha256}.json` &&",
        "manifest.object_key === `search/${scope}/${sha256}.json` &&",
    )
    replace_once(
        path,
        "  storyIndexSha256: string,\n): Promise<SearchIndexSource[]> => {",
        "  storyIndexSha256: string,\n  scope: StorySystem,\n): Promise<SearchIndexSource[]> => {",
    )
    replace_once(path, "fetch(SEARCH_INDEX_MANIFEST_URL, {", "fetch(SEARCH_INDEX_MANIFEST_URLS[scope], {")
    replace_once(path, "if (!isSearchIndexManifest(manifest)) {", "if (!isSearchIndexManifest(manifest, scope)) {")
    replace_once(
        path,
        "{ url: SEARCH_INDEX_LOCAL_FALLBACK_URL, ...sourceMetadata },",
        "{ url: SEARCH_INDEX_LOCAL_FALLBACK_URLS[scope], ...sourceMetadata },",
    )
    replace_once(
        path,
        "  const machineVerified = group.items.filter(\n    story => story.machine_translation && story.human_verified,\n  ).length;",
        "  const machineVerified = group.items.filter(\n    story => story.machine_translation && story.human_verified,\n  ).length;\n  const officialTw = group.items.some(story => story.official_tw);",
    )
    replace_once(
        path,
        "          {machinePending > 0 && (",
        "          {officialTw && (\n            <span className=\"shrink-0 rounded-full border border-stone-500/20 bg-stone-500/10 px-2 py-0.5 text-[10px] font-bold text-stone-600 dark:text-stone-300\">\n              台服官方\n            </span>\n          )}\n          {machinePending > 0 && (",
    )
    replace_once(
        path,
        "void getSearchIndexSources(controller.signal, storyIndexSha256)",
        "void getSearchIndexSources(controller.signal, storyIndexSha256, storySystem)",
    )
    replace_once(path, "  }, [storyIndexSha256]);", "  }, [storyIndexSha256, storySystem]);")

    scope_ui = """
              <div className="flex items-center rounded-lg border border-stone-300/60 bg-stone-100/70 p-0.5 shadow-sm dark:border-gray-700 dark:bg-gray-800 shrink-0">
                {(
                  [
                    { id: 'magireco', label: '全魔法纪录' },
                    { id: 'exedra', label: '全 Exedra' },
                  ] as const
                ).map((option) => (
                  <button
                    type="button"
                    key={option.id}
                    aria-pressed={storySystem === option.id}
                    onClick={() => {
                      setLastCategory(DEFAULT_CATEGORY[option.id]);
                      if (option.id === 'exedra') setOnlyNeedsReview(false);
                      updateSearchTerm('');
                    }}
                    className={`rounded-md px-2.5 py-1.5 text-xs font-bold transition-all ${
                      storySystem === option.id
                        ? 'bg-white text-stone-700 shadow-sm dark:bg-gray-600 dark:text-white'
                        : 'text-stone-500 hover:text-stone-700 dark:text-gray-400 dark:hover:text-gray-200'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>

"""
    anchor = "              <div className=\"flex items-center bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5 border border-gray-200 dark:border-gray-700 shrink-0\">"
    replace_once(path, anchor, scope_ui + anchor)


def patch_reader() -> None:
    path = ROOT / "website/app/reader/[id]/page.tsx"
    text = path.read_text(encoding="utf-8")
    if "台服官方" not in text:
        replace_once(
            path,
            "                <span className=\"truncate font-mono text-emerald-600\">{id}</span>",
            "                <span className=\"truncate font-mono text-emerald-600\">{id}</span>\n                {currentStory?.official_tw && (\n                  <span className=\"rounded-full border border-stone-500/20 bg-stone-500/10 px-2 py-0.5 text-[10px] font-bold text-stone-600 dark:text-stone-300\">\n                    台服官方\n                  </span>\n                )}",
        )
    if "max-w-xs overflow-y-auto" in path.read_text(encoding="utf-8"):
        replace_once(
            path,
            "max-h-[calc(100dvh-2rem)] w-full max-w-xs overflow-y-auto",
            "max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto md:max-w-2xl",
        )


def main() -> int:
    metadata_value = json.loads(
        (ROOT / "artifacts/tw_official_metadata.generated.json").read_text(encoding="utf-8")
    )
    metadata = metadata_value.get("stories")
    if not isinstance(metadata, dict):
        raise RuntimeError("台服官方元数据缺少 stories")
    patch_sidebar()
    patch_home()
    patch_reader()
    apply_story_metadata(metadata)
    print(f"TW_FEATURE_PATCH_OK stories={len(metadata)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
