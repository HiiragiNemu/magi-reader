from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import generate_story_index as generate
from tools.apply_tw_official_metadata import apply_metadata


def _catalog(group: dict[str, object]) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "policy": generate.EXEDRA_TW_TITLE_CATALOG_POLICY,
        "source": {
            "masterRevision": "fixture-master",
            "manifests": {
                name: {"sha256": "a" * 64}
                for name in (
                    "getAdvMstList.json",
                    "getFieldStageMstList.json",
                    "getFieldPointMstList.json",
                    "getCollectionConditionMstList.json",
                )
            },
        },
        "summary": {"groups": 1},
        "groups": {str(group["sourceIdentity"]): group},
    }


class ExedraTwTitleCatalogIntegrationTests(unittest.TestCase):
    def test_committed_catalog_accepts_same_title_across_raw_stage_ids(self) -> None:
        catalog = generate.load_exedra_tw_title_catalog()
        group = catalog["groups"]["exedra:1_Main:main_embryoeve3"]
        self.assertEqual(group["fieldStageMstIds"], [621011, 621013])
        self.assertEqual(group["chapterTitles"], ["第六章 · 幸福之魔女"])
        self.assertEqual(group["chapterTitle"], "第六章 · 幸福之魔女")

    def test_loader_rejects_majority_selected_chapter_for_multi_stage_group(self) -> None:
        group = {
            "sourceIdentity": "exedra:1_Main:main_demo",
            "category": "1_Main",
            "groupKey": "main_demo",
            "sourceResources": ["1_main/main_demo_1"],
            "sourceCount": 1,
            "fieldStageMstIds": [100, 200],
            "chapterTitle": "错误多数章",
            "chapterTitles": ["第一章 · 甲", "第二章 · 乙"],
            "sectionTitles": ["小节一"],
            "sectionTitleSources": ["getAdvMstList.subName"],
            "resolvedSectionTitles": ["小节一"],
            "storyTitles": [],
            "storyTitleSource": "",
            "displayTitle": "main_demo",
            "displayTitleSource": "fallback_group_id",
            "unresolved": ["multiple_field_stages_no_single_chapter"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "catalog.json"
            path.write_text(json.dumps(_catalog(group)), encoding="utf-8")
            with self.assertRaisesRegex(generate.PipelineError, "禁止多数选章"):
                generate.load_exedra_tw_title_catalog(path)

    def test_post_generation_metadata_pass_cannot_restore_legacy_majority_chapter(self) -> None:
        identity = "exedra:1_Main:main_demo"
        stories = [
            {
                "source_identity": identity,
                "category": "exedra_main",
                "folder": "main_demo",
                "title": "main_demo",
            }
        ]
        legacy_metadata = {
            identity: {
                "chapterTitle": "错误多数章",
                "chapterTitles": ["错误多数章", "另一个章"],
                "sectionTitles": ["旧小节"],
                "officialStoryTitles": [],
                "officialStoryTitleSource": "",
            }
        }
        exact_group = {
            "sourceIdentity": identity,
            "category": "1_Main",
            "groupKey": "main_demo",
            "sourceResources": [
                "1_main/main_demo_1",
                "1_main/main_demo_2",
            ],
            "sourceCount": 2,
            "fieldStageMstIds": [100, 200],
            "chapterTitle": "",
            "chapterTitles": ["第一章 · 甲", "第二章 · 乙"],
            "sectionTitles": ["小节一", "小节二"],
            "sectionTitleSources": [
                "getAdvMstList.subName",
                "getAdvMstList.name",
            ],
            "resolvedSectionTitles": ["小节一", "小节二"],
            "storyTitles": [],
            "storyTitleSource": "",
            "displayTitle": "main_demo",
            "displayTitleSource": "fallback_group_id",
            "unresolved": ["multiple_field_stages_no_single_chapter"],
        }
        applied = apply_metadata(
            stories,
            legacy_metadata,
            _catalog(exact_group),
        )
        self.assertEqual(applied, 1)
        self.assertEqual(stories[0]["folder"], "main_demo")
        self.assertEqual(stories[0]["official_tw_chapter_title"], "")
        self.assertEqual(
            stories[0]["official_tw_chapter_titles"],
            ["第一章 · 甲", "第二章 · 乙"],
        )
        self.assertEqual(
            stories[0]["official_tw_section_titles"],
            ["小节一", "小节二"],
        )
        self.assertIn(
            "multiple_field_stages_no_single_chapter",
            stories[0]["official_tw_title_unresolved"],
        )

    def test_unknown_catalog_display_keeps_existing_title_and_folder(self) -> None:
        group = generate.OrganizedExedraGroup(
            manifest_id="exedra:8_Dungeon:unknown",
            raw_category="8_Dungeon",
            category="exedra_dungeon",
            group_key="unknown",
            output_dir=Path("8_Dungeon/unknown"),
            text_file=Path("8_Dungeon/unknown/unknown_jp.txt"),
            source_paths=("8_Dungeon/unknown/unknown.json",),
            source_names=("unknown.json",),
            title="已有标题",
        )
        story: dict[str, object] = {"folder": "原文件夹", "title": "已有标题"}
        generate._apply_exedra_tw_title_metadata(
            story=story,
            group=group,
            info={
                "sourceIdentity": group.manifest_id,
                "category": group.raw_category,
                "groupKey": group.group_key,
                "sourceCount": 1,
                "chapterTitle": "",
                "chapterTitles": [],
                "sectionTitles": ["unknown"],
                "sectionTitleSources": ["fallback_resource_id"],
                "resolvedSectionTitles": [],
                "storyTitles": ["场景补充"],
                "storyTitleSource": "tw_scenario_metadata.bookTitle",
                "displayTitle": "场景补充",
                "displayTitleSource": "tw_scenario_metadata",
                "unresolved": ["no_authoritative_section_title"],
            },
            master_revision="fixture-master",
        )
        self.assertEqual(story["folder"], "原文件夹")
        self.assertEqual(story["title"], "已有标题")
        self.assertEqual(story["official_tw_section_titles"], ["unknown"])


if __name__ == "__main__":
    unittest.main()
