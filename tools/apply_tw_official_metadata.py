#!/usr/bin/env python3
"""Apply generated official-TW provenance and titles to story_index.json.

This file only transforms generated catalogue data.  It never patches source
code, runs Git, deploys a site, or downloads an upstream package.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METADATA = ROOT / "artifacts/tw_official_metadata.generated.json"
DEFAULT_STORY_INDEX = ROOT / "website/public/story_index.json"
TW_FIELDS = (
    "official_tw",
    "official_tw_label",
    "official_tw_provenance",
    "official_tw_chapter_title",
    "official_tw_chapter_titles",
    "official_tw_section_titles",
)
CHAPTER_FOLDER_CATEGORIES = frozenset({"exedra_main", "exedra_sub"})


def apply_metadata(
    stories: list[dict[str, Any]],
    metadata: dict[str, dict[str, Any]],
) -> int:
    applied = 0
    for story in stories:
        if not isinstance(story, dict):
            continue
        if story.get("category", "").startswith("exedra_"):
            original = story.pop("official_tw_original_folder", None)
            if isinstance(original, str) and original:
                story["folder"] = original
            for field in TW_FIELDS:
                story.pop(field, None)

        identity = story.get("source_identity")
        info = metadata.get(identity) if isinstance(identity, str) else None
        if not isinstance(info, dict):
            continue
        chapter_title = str(info.get("chapterTitle") or "").strip()
        story["official_tw"] = True
        story["official_tw_label"] = "台服"
        story["official_tw_provenance"] = "official_tw_human"
        story["official_tw_chapter_title"] = chapter_title
        story["official_tw_chapter_titles"] = info.get("chapterTitles") or []
        story["official_tw_section_titles"] = info.get("sectionTitles") or []
        if chapter_title and story.get("category") in CHAPTER_FOLDER_CATEGORIES:
            current_folder = story.get("folder")
            if isinstance(current_folder, str) and current_folder != chapter_title:
                story["official_tw_original_folder"] = current_folder
            story["folder"] = chapter_title
        applied += 1
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--story-index", type=Path, default=DEFAULT_STORY_INDEX)
    args = parser.parse_args()

    metadata_value = json.loads(args.metadata.read_text(encoding="utf-8-sig"))
    metadata = metadata_value.get("stories") if isinstance(metadata_value, dict) else None
    if not isinstance(metadata, dict):
        raise RuntimeError("台服官方元数据缺少 stories")
    stories = json.loads(args.story_index.read_text(encoding="utf-8-sig"))
    if not isinstance(stories, list) or not all(isinstance(item, dict) for item in stories):
        raise RuntimeError("story_index 顶层不是对象数组")
    applied = apply_metadata(stories, metadata)
    if applied != len(metadata):
        raise RuntimeError(f"台服元数据未完全映射：{applied}/{len(metadata)}")
    temporary = args.story_index.with_suffix(args.story_index.suffix + ".tmp")
    temporary.write_text(
        json.dumps(stories, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.story_index)
    print(f"TW_STORY_METADATA_OK stories={applied}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
