#!/usr/bin/env python3
"""Apply generated official-TW provenance and titles to story_index.json.

This file only transforms generated catalogue data.  It never patches source
code, runs Git, deploys a site, or downloads an upstream package.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEFAULT_METADATA = ROOT / "artifacts/tw_official_metadata.generated.json"
DEFAULT_TITLE_CATALOG = ROOT / "artifacts/exedra_tw_manifest_titles.generated.json"
DEFAULT_STORY_INDEX = ROOT / "website/public/story_index.json"
TW_FIELDS = (
    "official_tw",
    "official_tw_label",
    "official_tw_provenance",
    "official_tw_chapter_title",
    "official_tw_chapter_titles",
    "official_tw_section_titles",
    "official_tw_story_titles",
    "official_tw_story_title_source",
    "official_tw_title_status",
    "official_tw_title_unresolved",
    "official_tw_title_catalog_source",
)
CHAPTER_FOLDER_CATEGORIES = frozenset({"exedra_main", "exedra_sub"})
TECHNICAL_TITLE = re.compile(
    r"^(?:sub|main|portrait|character|reaction|act|contents|map|pp|play|flashback)[ _-]",
    re.IGNORECASE,
)


def apply_metadata(
    stories: list[dict[str, Any]],
    metadata: dict[str, dict[str, Any]],
    title_catalog: dict[str, Any] | None = None,
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
        official_story_titles = [
            str(value).strip()
            for value in (info.get("officialStoryTitles") or [])
            if str(value).strip()
        ]
        story["official_tw_story_titles"] = official_story_titles
        story_title_source = str(info.get("officialStoryTitleSource") or "").strip()
        story["official_tw_story_title_source"] = story_title_source
        title_candidate = (
            official_story_titles[0]
            if len(official_story_titles) == 1
            else " / ".join(official_story_titles)
        )
        current_title = str(story.get("title") or "").strip()
        scenario_title_may_replace = (
            not current_title
            or bool(TECHNICAL_TITLE.match(current_title.replace("_", " ")))
        )
        if title_candidate and (
            story_title_source != "scenario_title_card" or scenario_title_may_replace
        ):
            story["title"] = title_candidate
        if chapter_title and story.get("category") in CHAPTER_FOLDER_CATEGORIES:
            current_folder = story.get("folder")
            if isinstance(current_folder, str) and current_folder != chapter_title:
                story["official_tw_original_folder"] = current_folder
            story["folder"] = chapter_title
        applied += 1

    if title_catalog is not None:
        source = title_catalog.get("source")
        title_groups = title_catalog.get("groups")
        if not isinstance(source, dict) or not isinstance(title_groups, dict):
            raise RuntimeError("Exedra TW 标题目录缺少 source/groups")
        master_revision = str(source.get("masterRevision") or "")
        if not master_revision:
            raise RuntimeError("Exedra TW 标题目录缺少 masterRevision")
        title_applied = 0
        for story in stories:
            identity = story.get("source_identity")
            info = title_groups.get(identity) if isinstance(identity, str) else None
            if not isinstance(info, dict):
                continue
            category = str(story.get("category") or "")
            group_key = str(info.get("groupKey") or "")
            if (
                not category.startswith("exedra_")
                or info.get("sourceIdentity") != identity
                or not group_key
            ):
                raise RuntimeError(f"Exedra TW 标题目录与 story 不一致：{identity}")
            chapter_title = str(info.get("chapterTitle") or "")
            chapter_titles = [str(value) for value in info.get("chapterTitles") or []]
            section_titles = [str(value) for value in info.get("sectionTitles") or []]
            section_sources = [
                str(value) for value in info.get("sectionTitleSources") or []
            ]
            resolved_section_titles = [
                str(value) for value in info.get("resolvedSectionTitles") or []
            ]
            story_titles = [str(value) for value in info.get("storyTitles") or []]
            unresolved = [str(value) for value in info.get("unresolved") or []]
            stage_ids = info.get("fieldStageMstIds")
            unique_chapter_titles = list(dict.fromkeys(chapter_titles))
            if (
                not isinstance(stage_ids, list)
                or (len(unique_chapter_titles) == 1) != bool(chapter_title)
                or len(section_titles) != int(info.get("sourceCount") or -1)
                or len(section_sources) != len(section_titles)
                or list(
                    dict.fromkeys(
                        title
                        for title, source_name in zip(
                            section_titles, section_sources
                        )
                        if source_name.startswith("getAdvMstList.")
                    )
                )
                != resolved_section_titles
            ):
                raise RuntimeError(
                    f"Exedra TW 标题目录单章/小节规则无效：{identity}"
                )

            # This pass runs after the legacy TW metadata applicator in deploy.
            # A unique exact FieldStage wins. Multi-stage/no-stage main and sub
            # groups explicitly return to the organizer group ID so the legacy
            # majority chapter cannot leak back into folder.
            if chapter_title:
                story["folder"] = chapter_title
            elif category in CHAPTER_FOLDER_CATEGORIES:
                story["folder"] = group_key

            display_title = str(info.get("displayTitle") or "")
            display_source = str(info.get("displayTitleSource") or "")
            current_title = str(story.get("title") or "").strip()
            technical_title = (
                not current_title
                or current_title in {group_key, group_key.replace("_", " ")}
                or "_" in current_title
                or bool(TECHNICAL_TITLE.match(current_title.replace("_", " ")))
            )
            if display_source == "getAdvMstList" and display_title:
                story["title"] = display_title
            elif (
                display_source
                in {
                    "tw_scenario_title_card",
                    "tw_scenario_metadata",
                    "human_cn_scenario_metadata",
                }
                and display_title
                and technical_title
            ):
                story["title"] = display_title

            story.update(
                {
                    "official_tw_chapter_title": chapter_title,
                    "official_tw_chapter_titles": chapter_titles,
                    "official_tw_section_titles": section_titles,
                    "official_tw_story_titles": story_titles,
                    "official_tw_story_title_source": str(
                        info.get("storyTitleSource") or ""
                    ),
                    "official_tw_title_status": (
                        "resolved"
                        if not unresolved
                        else "partial"
                        if chapter_title or resolved_section_titles or story_titles
                        else "unresolved"
                    ),
                    "official_tw_title_unresolved": unresolved,
                    "official_tw_title_catalog_source": (
                        "exedra_tw_manifest_titles.generated.json@"
                        + master_revision
                    ),
                }
            )
            title_applied += 1
        if title_applied != len(title_groups):
            raise RuntimeError(
                f"Exedra TW 标题目录未完全映射：{title_applied}/{len(title_groups)}"
            )
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--title-catalog", type=Path, default=DEFAULT_TITLE_CATALOG)
    parser.add_argument("--story-index", type=Path, default=DEFAULT_STORY_INDEX)
    args = parser.parse_args()

    metadata_value = json.loads(args.metadata.read_text(encoding="utf-8-sig"))
    metadata = metadata_value.get("stories") if isinstance(metadata_value, dict) else None
    if not isinstance(metadata, dict):
        raise RuntimeError("台服官方元数据缺少 stories")
    from generate_story_index import (
        load_exedra_tw_title_catalog,
        select_compatible_exedra_tw_title_catalog,
    )

    loaded_title_catalog = load_exedra_tw_title_catalog(args.title_catalog)
    source_contract = metadata_value.get("sourceContract")
    title_catalog = select_compatible_exedra_tw_title_catalog(
        loaded_title_catalog,
        source_contract if isinstance(source_contract, dict) else None,
    )
    if title_catalog is None:
        expected = (
            source_contract.get("sourceRevisions", {}).get("manifests")
            if isinstance(source_contract, dict)
            else None
        )
        actual = loaded_title_catalog["source"]["masterRevision"]
        print(
            "TW_TITLE_CATALOG_SKIPPED "
            f"catalog_revision={actual} source_revision={expected}"
        )
    stories = json.loads(args.story_index.read_text(encoding="utf-8-sig"))
    if not isinstance(stories, list) or not all(isinstance(item, dict) for item in stories):
        raise RuntimeError("story_index 顶层不是对象数组")
    applied = apply_metadata(stories, metadata, title_catalog)
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
