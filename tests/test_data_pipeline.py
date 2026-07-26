from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from argparse import Namespace
from collections import Counter
from pathlib import Path
from unittest import mock

import build_search_index_v6 as search
import generate_story_index as generate
import organize_exedra_scenarios as organizer


def make_windows_junction(link: Path, target: Path) -> None:
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=True,
        capture_output=True,
        text=True,
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def exedra_json(
    rows: list[list[str]],
    headers: list[str] | None = None,
    *,
    duplicate_sheet: bool = False,
) -> dict[str, object]:
    headers = headers or [
        "ActionType",
        "Name",
        "Comment",
        "AssetID",
        "PositionID",
    ]
    sheet = {
        "sheetName": "script",
        "headerRow": {
            "rowNumber": 1,
            "cellList": headers,
            "isHeader": True,
            "isComment": False,
            "isBlank": False,
        },
        "contentRowList": [
            {
                "rowNumber": index + 2,
                "cellList": row,
                "isHeader": False,
                "isComment": False,
                "isBlank": False,
            }
            for index, row in enumerate(rows)
        ],
    }
    return {
        "origin": 0,
        "spreadsheetId": "",
        "bookTitle": "fixture",
        "sheetList": [sheet, json.loads(json.dumps(sheet))]
        if duplicate_sheet
        else [sheet],
    }


class ExedraParserTests(unittest.TestCase):
    def test_dynamic_headers_onlytext_and_duplicate_sheet(self) -> None:
        data = exedra_json(
            [
                ["Talk", "一行目\n二行目", ""],
                ["OnlyText", "名前なしも保持", ""],
                ["ChangeBG", "制作メモ", ""],
            ],
            headers=["ActionType", "Comment", "Name"],
            duplicate_sheet=True,
        )

        rows, diagnostics = generate.extract_exedra_dialogue_rows(data)

        self.assertEqual([row["text"] for row in rows], ["一行目\n二行目", "名前なしも保持"])
        self.assertTrue(any("重复" in diagnostic for diagnostic in diagnostics))

    def test_exedra_ids_use_complete_source_identity(self) -> None:
        first = generate.safe_exedra_story_id(
            "exedra_main",
            "1_Main/main_a_1/main_a_1.txt",
            "main_a_1",
        )
        second = generate.safe_exedra_story_id(
            "exedra_main",
            "1_Main/main_a_2/main_a_2.txt",
            "main_a_2",
        )
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("exedra_main_"))


class PipelineBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.jp = self.root / "jp"
        self.cn = self.root / "cn"
        self.exedra_raw = self.root / "exedra-raw"
        self.exedra = self.root / "exedra-organized"
        self.exedra_cn = self.root / "exedra-cn"
        self.stage = self.root / "stage-public"
        self.stage.mkdir()
        self.titles = self.root / "titles.json"
        write_json(self.titles, {"310011": "旧格式标题"})

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_valid_exedra_cn_report(
        self,
        *,
        category: str = "1_Main",
        group_key: str = "main_demo",
    ) -> Path:
        jp_path = (
            self.exedra / category / group_key / f"{group_key}_jp.txt"
        )
        cn_path = (
            self.exedra_cn / category / group_key / f"{group_key}_cn.txt"
        )
        jp_sections = generate._exedra_alignment_sections(jp_path)
        cn_sections = generate._exedra_alignment_sections(cn_path)
        self.assertEqual(len(jp_sections), len(cn_sections))
        report = {
            "schemaVersion": 1,
            "status": "validated",
            "group": {
                "category": category,
                "groupKey": group_key,
            },
            "jp": {
                "contentSha256": generate._sha256_utf8_text_file(jp_path),
                "sectionCount": len(jp_sections),
                "readerNormalizedBlockCount": sum(
                    section.reader_block_count for section in jp_sections
                ),
            },
            "cn": {
                "renderedSha256": generate._sha256_utf8_text_file(cn_path),
                "sectionCount": len(cn_sections),
                "readerNormalizedBlockCount": sum(
                    section.reader_block_count for section in cn_sections
                ),
            },
            "validation": {
                "passed": True,
                "usesLcs": False,
                "usesFuzzyMatching": False,
                "allowsReordering": False,
                "mismatchCount": 0,
            },
            "sections": [
                {
                    "section": index,
                    "wikiEpisode": index,
                    "source": jp_section.source_name,
                    "readerNormalizedBlocks": {
                        "jp": jp_section.reader_block_count,
                        "cn": cn_section.reader_block_count,
                        "matches": True,
                    },
                    "speakerSequenceSha256": {
                        # The real importer obtains the JP value after applying
                        # its reviewed name mapping.  This fixture represents
                        # that approved mapping with the independently parsed
                        # current CN sequence.
                        "jp": cn_section.speaker_sequence_sha256,
                        "cn": cn_section.speaker_sequence_sha256,
                    },
                }
                for index, (jp_section, cn_section) in enumerate(
                    zip(jp_sections, cn_sections),
                    start=1,
                )
            ],
            "mismatches": [],
        }
        report_path = cn_path.with_name(
            f"{group_key}_cn.import-report.json"
        )
        write_json(report_path, report)
        return report_path

    def _make_sources(self) -> None:
        legacy_rel = Path("character_story") / "1001 - 环彩羽" / "310011_1.txt"
        write_text(
            self.jp / legacy_rel,
            "---[Section 1] (Source: 310011-1.json) ---\n"
            "いろは: おはよう\\nございます\n",
        )
        write_text(
            self.cn / legacy_rel,
            "---[Section 1] (Source: 310011-1.json) ---\n"
            "彩羽: 早上好\n",
        )

        for category in organizer.CATEGORY_ORDER:
            (self.exedra_raw / category).mkdir(parents=True, exist_ok=True)
        covered_json = (
            self.exedra_raw / "1_Main" / "main_demo_1" / "main_demo_1.json"
        )
        write_json(
            covered_json,
            exedra_json(
                [["Talk", "鹿目まどか", "<r=のろけ>惚気</r>", "", ""]]
            ),
        )

        fallback_json = (
            self.exedra_raw
            / "10_Battle"
            / "battle_demo_1"
            / "battle_demo_1.json"
        )
        write_json(
            fallback_json,
            exedra_json(
                [
                    ["Talk", "タルト", "絶対に！\r\nもうあきらめない", "", ""],
                    ["OnlyText", "", "<color=#3bbeff>色</color>", "", ""],
                ]
            ),
        )
        no_text_json = (
            self.exedra_raw / "1_Main" / "movie_only" / "movie_only.json"
        )
        write_json(
            no_text_json,
            exedra_json([["PlayMovie", "", "", "movie", ""]]),
        )
        organizer.publish_plan(
            organizer.build_plan(self.exedra_raw),
            self.exedra,
        )
        write_text(
            self.exedra_cn
            / "1_Main"
            / "main_demo"
            / "main_demo_cn.txt",
            "--- [Section 1] (Source: main_demo_1.json) ---\n"
            "鹿目圆: <r=秀恩爱>惚気</r>\n",
        )
        self._write_valid_exedra_cn_report()

    def test_unclassified_legacy_folder_is_preserved_in_public_path(self) -> None:
        write_text(
            self.cn / "special" / "special-chapter-info.txt",
            "旁白: 兼容旧网址\n",
        )
        stories, _ = generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=None,
            exedra_cn_dir=None,
            titles_path=self.titles,
        )
        story = next(item for item in stories if item["id"] == "special-chapter-info")
        self.assertEqual(
            story["path_cn"],
            "/data/Unclassified/special/special-chapter-info_cn.txt",
        )
        self.assertTrue(
            (
                self.stage
                / "data"
                / "Unclassified"
                / "special"
                / "special-chapter-info_cn.txt"
            ).is_file()
        )

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_manifest_rejects_organized_directory_junction(self) -> None:
        self._make_sources()
        group_dir = self.exedra / "1_Main" / "main_demo"
        outside = self.root / "outside-organized-main-demo"
        group_dir.rename(outside)
        make_windows_junction(group_dir, outside)
        try:
            with self.assertRaises(generate.PipelineError):
                generate.load_exedra_manifest(
                    self.exedra,
                    stats=Counter(),
                )
            self.assertTrue((outside / "main_demo_jp.txt").is_file())
        finally:
            if os.path.lexists(group_dir):
                os.rmdir(group_dir)

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_cn_discovery_rejects_directory_junction(self) -> None:
        self._make_sources()
        groups = generate.load_exedra_manifest(
            self.exedra,
            stats=Counter(),
        )
        category_dir = self.exedra_cn / "1_Main"
        outside = self.root / "outside-cn-main"
        category_dir.rename(outside)
        make_windows_junction(category_dir, outside)
        try:
            with self.assertRaises(generate.PipelineError):
                generate._find_exedra_cn_sources(self.exedra_cn, groups)
            self.assertTrue(
                (outside / "main_demo" / "main_demo_cn.txt").is_file()
            )
        finally:
            if os.path.lexists(category_dir):
                os.rmdir(category_dir)

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_safe_replace_rejects_staged_junction_without_target_mutation(
        self,
    ) -> None:
        stage = self.root / "junction-stage"
        target = self.root / "junction-target"
        outside = self.root / "outside-stage-data"
        (stage / "data").mkdir(parents=True)
        outside.mkdir()
        write_text(outside / "external.txt", "outside sentinel")
        write_json(stage / "story_index.json", [])
        write_text(target / "data" / "old.txt", "old data")
        write_json(target / "story_index.json", [{"id": "old"}])
        junction = stage / "data" / "escaped"
        make_windows_junction(junction, outside)
        try:
            with self.assertRaises(generate.PipelineError):
                generate.safe_replace_generated(stage, target)
            self.assertEqual(
                (target / "data" / "old.txt").read_text(encoding="utf-8"),
                "old data",
            )
            self.assertEqual(
                json.loads(
                    (target / "story_index.json").read_text(encoding="utf-8")
                ),
                [{"id": "old"}],
            )
            self.assertEqual(
                (outside / "external.txt").read_text(encoding="utf-8"),
                "outside sentinel",
            )
        finally:
            if os.path.lexists(junction):
                os.rmdir(junction)

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_safe_replace_rejects_target_beneath_ancestor_junction(
        self,
    ) -> None:
        stage = self.root / "ancestor-junction-stage"
        outside = self.root / "outside-public-parent"
        real_public = outside / "public"
        backup_container = outside / ".magi-reader-generation-backups"
        (stage / "data").mkdir(parents=True)
        (real_public / "data").mkdir(parents=True)
        backup_container.mkdir(parents=True)
        write_text(stage / "data" / "new.txt", "new data")
        write_json(stage / "story_index.json", [])
        old_data = real_public / "data" / "old.txt"
        old_index = real_public / "story_index.json"
        backup_sentinel = backup_container / "outside-sentinel.txt"
        write_text(old_data, "old data")
        write_json(old_index, [{"id": "old"}])
        write_text(backup_sentinel, "backup parent must survive")
        alias = self.root / "alias-to-outside-public-parent"
        make_windows_junction(alias, outside)
        try:
            with self.assertRaises(generate.PipelineError):
                generate.safe_replace_generated(stage, alias / "public")
            self.assertEqual(old_data.read_text(encoding="utf-8"), "old data")
            self.assertEqual(
                json.loads(old_index.read_text(encoding="utf-8")),
                [{"id": "old"}],
            )
            self.assertFalse((real_public / "data" / "new.txt").exists())
            self.assertEqual(
                backup_sentinel.read_text(encoding="utf-8"),
                "backup parent must survive",
            )
            self.assertEqual(
                [path.name for path in backup_container.iterdir()],
                ["outside-sentinel.txt"],
            )
        finally:
            if os.path.lexists(alias):
                os.rmdir(alias)

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_file_tree_helpers_reject_target_junction_before_deletion(
        self,
    ) -> None:
        source = self.root / "source-tree"
        target = self.root / "target-tree"
        outside = self.root / "outside-target-tree"
        source.mkdir()
        target.mkdir()
        outside.mkdir()
        sentinel = outside / "sentinel.txt"
        sentinel.write_text("must survive", encoding="utf-8")
        junction = target / "escaped"
        make_windows_junction(junction, outside)
        try:
            with self.assertRaises(generate.PipelineError):
                generate._file_tree_snapshot(target)
            with self.assertRaises(generate.PipelineError):
                generate._sync_file_tree(source, target)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "must survive")
            self.assertTrue(junction.is_junction())
        finally:
            if os.path.lexists(junction):
                os.rmdir(junction)

    def _make_collision_sources(self) -> None:
        base = "---[Section 1] (Source: fixture.json) ---\n"
        write_text(
            self.jp
            / "character_story"
            / "1001 - 环彩羽"
            / "310011_1.txt",
            f"{base}いろは: non-conflict\n",
        )
        write_text(
            self.cn
            / "character_story"
            / "1001 - 环彩羽"
            / "310011_1.txt",
            f"{base}彩羽: 非冲突\n",
        )

        mirror_sources = [
            (
                "420131-0记忆博物馆-序",
                "420131_0-0.txt",
                "序-区间",
            ),
            (
                "420131-0记忆博物馆-序",
                "420131_0.txt",
                "序-完整",
            ),
            (
                "420131-1~4记忆博物馆-篠目夜鹤",
                "420131_1-4.txt",
                "夜鹤",
            ),
        ]
        for folder, filename, marker in mirror_sources:
            write_text(
                self.jp / "mirror_story" / folder / filename,
                f"{base}旁白: {marker}\n",
            )

        paired_rel = (
            Path("event_story")
            / "5170 - 七彩夏日绘"
            / "5170100-09_30-39.txt"
        )
        conflicting_rel = (
            Path("event_story")
            / "5192 - 七彩夏日绘"
            / "5170100-09_30-39.txt"
        )
        write_text(self.jp / paired_rel, f"{base}旁白: 5170 JP\n")
        write_text(self.cn / paired_rel, f"{base}旁白: 5170 CN\n")
        write_text(self.jp / conflicting_rel, f"{base}旁白: 5192 JP\n")

    def test_magireco_collisions_are_split_without_cross_language_mixing(self) -> None:
        self._make_collision_sources()
        stories, stats = generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=None,
            exedra_cn_dir=None,
            titles_path=self.titles,
        )

        self.assertEqual(len(stories), 6)
        self.assertEqual(stats["magireco_logical_stories"], 6)
        self.assertEqual(stats["magireco_legacy_id_collision_groups"], 2)
        self.assertEqual(stats["magireco_collision_stories"], 5)
        self.assertEqual(stats["input_source_files"], 8)
        self.assertEqual(stats["orphan_sources"], 0)
        self.assertEqual(stats["ownership_collisions"], 0)

        non_conflict = next(story for story in stories if story["id"] == "310011")
        self.assertTrue(non_conflict["has_cn"])
        self.assertTrue(non_conflict["has_jp"])

        mirror = [story for story in stories if story["category"] == "mirror_story"]
        self.assertEqual(len(mirror), 3)
        self.assertEqual(len({story["id"] for story in mirror}), 3)
        self.assertTrue(
            all(story["id"].startswith("mirror_story_420131_") for story in mirror)
        )
        self.assertTrue(all(story["has_jp"] and not story["has_cn"] for story in mirror))

        event = [story for story in stories if story["category"] == "event_story"]
        self.assertEqual(len(event), 2)
        paired = next(
            story for story in event if "/5170 - 七彩夏日绘/" in story["source_identity"]
        )
        jp_only = next(
            story for story in event if "/5192 - 七彩夏日绘/" in story["source_identity"]
        )
        self.assertTrue(paired["has_cn"] and paired["has_jp"])
        self.assertTrue(jp_only["has_jp"] and not jp_only["has_cn"])
        self.assertNotEqual(paired["id"], jp_only["id"])

    def test_magireco_generation_is_deterministic(self) -> None:
        self._make_collision_sources()
        first, first_stats = generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=None,
            exedra_cn_dir=None,
            titles_path=self.titles,
        )
        second_stage = self.root / "stage-public-2"
        second_stage.mkdir()
        second, second_stats = generate.build_story_catalog(
            staging_public_dir=second_stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=None,
            exedra_cn_dir=None,
            titles_path=self.titles,
        )

        self.assertEqual(first, second)
        self.assertEqual(first_stats, second_stats)

    def test_duplicate_language_identity_fails_fast(self) -> None:
        relative = Path("main_story") / "demo" / "101001_1.txt"
        write_text(self.jp / relative, "旁白: first\n")
        write_text(
            self.jp / relative.with_name("101001_1_jp.txt"),
            "旁白: duplicate\n",
        )
        with self.assertRaisesRegex(generate.PipelineError, "多个 jp 输入"):
            generate.build_story_catalog(
                staging_public_dir=self.stage,
                jp_dir=self.jp,
                cn_dir=self.cn,
                exedra_jp_dir=None,
                exedra_cn_dir=None,
                titles_path=self.titles,
            )

    def test_catalog_publishes_organized_groups_and_pairs_cn(self) -> None:
        self._make_sources()
        stories, stats = generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=self.exedra,
            exedra_cn_dir=self.exedra_cn,
            titles_path=self.titles,
        )

        self.assertEqual(len(stories), 4)
        self.assertEqual(len({story["id"] for story in stories}), 4)
        legacy = next(story for story in stories if story["id"] == "310011")
        self.assertTrue(legacy["has_cn"])
        self.assertTrue(legacy["has_jp"])
        self.assertEqual(legacy["title"], "旧格式标题")

        main_group = next(
            story
            for story in stories
            if story.get("source_identity") == "exedra:1_Main:main_demo"
        )
        self.assertEqual(main_group["source_format"], "organized_txt")
        self.assertEqual(main_group["category"], "exedra_main")
        self.assertTrue(main_group["has_cn"])
        self.assertTrue(main_group["has_jp"])
        self.assertTrue(main_group["path_cn"].endswith("main_demo_cn.txt"))
        self.assertTrue(main_group["path_jp"].endswith("main_demo_jp.txt"))

        battle = next(
            story
            for story in stories
            if story.get("source_identity") == "exedra:10_Battle:battle_demo"
        )
        self.assertEqual(battle["category"], "exedra_battle")
        self.assertFalse(battle["has_cn"])
        self.assertTrue(battle["path_jp"].endswith("_jp.txt"))

        self.assertEqual(stats["exedra_manifest_groups"], 3)
        self.assertEqual(stats["exedra_manifest_json_sources"], 3)
        self.assertEqual(stats["exedra_manifest_json_verified"], 3)
        self.assertEqual(stats["exedra_jp_groups"], 3)
        self.assertEqual(stats["exedra_cn_groups"], 1)
        self.assertEqual(stats["exedra_untranslated_groups"], 2)
        self.assertEqual(stats["input_source_files"], 6)
        self.assertEqual(stats["manifest_source_files"], 6)
        self.assertEqual(stats["orphan_sources"], 0)
        self.assertEqual(stats["ownership_collisions"], 0)

        validation = generate.validate_catalog(stories, self.stage)
        self.assertEqual(validation["stories"], 4)
        self.assertEqual(validation["source_files"], 6)

    def test_cn_turn_mismatch_is_rejected_without_realigning(self) -> None:
        self._make_sources()
        cn_path = (
            self.exedra_cn
            / "1_Main"
            / "main_demo"
            / "main_demo_cn.txt"
        )
        write_text(
            cn_path,
            cn_path.read_text(encoding="utf-8") + "晓美焰: 多出的发言块\n",
        )
        with self.assertRaisesRegex(generate.PipelineError, "说话轮次不一致"):
            generate.build_story_catalog(
                staging_public_dir=self.stage,
                jp_dir=self.jp,
                cn_dir=self.cn,
                exedra_jp_dir=self.exedra,
                exedra_cn_dir=self.exedra_cn,
                titles_path=self.titles,
            )

    def test_cn_without_import_report_is_rejected(self) -> None:
        self._make_sources()
        report_path = (
            self.exedra_cn
            / "1_Main"
            / "main_demo"
            / "main_demo_cn.import-report.json"
        )
        report_path.unlink()

        with self.assertRaisesRegex(generate.PipelineError, "缺少相邻.*导入报告"):
            generate.build_story_catalog(
                staging_public_dir=self.stage,
                jp_dir=self.jp,
                cn_dir=self.cn,
                exedra_jp_dir=self.exedra,
                exedra_cn_dir=self.exedra_cn,
                titles_path=self.titles,
            )

    def test_cn_wrong_speaker_with_same_turn_count_is_rejected(self) -> None:
        self._make_sources()
        cn_path = (
            self.exedra_cn
            / "1_Main"
            / "main_demo"
            / "main_demo_cn.txt"
        )
        write_text(
            cn_path,
            cn_path.read_text(encoding="utf-8").replace("鹿目圆:", "晓美焰:"),
        )
        report_path = cn_path.with_name("main_demo_cn.import-report.json")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        # Bypass the whole-file binding to prove that the independently
        # recomputed per-Section speaker+kind sequence is also mandatory.
        report["cn"]["renderedSha256"] = generate._sha256_utf8_text_file(cn_path)
        write_json(report_path, report)

        with self.assertRaisesRegex(generate.PipelineError, "说话人/旁白顺序哈希"):
            generate.build_story_catalog(
                staging_public_dir=self.stage,
                jp_dir=self.jp,
                cn_dir=self.cn,
                exedra_jp_dir=self.exedra,
                exedra_cn_dir=self.exedra_cn,
                titles_path=self.titles,
            )

    def test_valid_cn_import_report_is_accepted(self) -> None:
        self._make_sources()

        stories, stats = generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=self.exedra,
            exedra_cn_dir=self.exedra_cn,
            titles_path=self.titles,
        )

        main_group = next(
            story
            for story in stories
            if story.get("source_identity") == "exedra:1_Main:main_demo"
        )
        self.assertTrue(main_group["has_cn"])
        self.assertEqual(stats["exedra_cn_groups"], 1)

    def test_tampered_cn_file_is_rejected_by_report_hash(self) -> None:
        self._make_sources()
        cn_path = (
            self.exedra_cn
            / "1_Main"
            / "main_demo"
            / "main_demo_cn.txt"
        )
        write_text(
            cn_path,
            cn_path.read_text(encoding="utf-8").replace("惚気", "篡改正文"),
        )

        with self.assertRaisesRegex(generate.PipelineError, "CN 内容哈希"):
            generate.build_story_catalog(
                staging_public_dir=self.stage,
                jp_dir=self.jp,
                cn_dir=self.cn,
                exedra_jp_dir=self.exedra,
                exedra_cn_dir=self.exedra_cn,
                titles_path=self.titles,
            )

    def test_tampered_cn_report_is_rejected(self) -> None:
        self._make_sources()
        report_path = (
            self.exedra_cn
            / "1_Main"
            / "main_demo"
            / "main_demo_cn.import-report.json"
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["validation"]["allowsReordering"] = True
        write_json(report_path, report)

        with self.assertRaisesRegex(generate.PipelineError, "明确禁止"):
            generate.build_story_catalog(
                staging_public_dir=self.stage,
                jp_dir=self.jp,
                cn_dir=self.cn,
                exedra_jp_dir=self.exedra,
                exedra_cn_dir=self.exedra_cn,
                titles_path=self.titles,
            )

    def test_tampered_organized_txt_is_rejected_by_manifest_hash(self) -> None:
        self._make_sources()
        jp_path = (
            self.exedra
            / "1_Main"
            / "main_demo"
            / "main_demo_jp.txt"
        )
        write_text(
            jp_path,
            jp_path.read_text(encoding="utf-8").replace("惚気", "tampered"),
        )

        with self.assertRaisesRegex(
            generate.PipelineError,
            "TXT 与 manifest 哈希不一致",
        ):
            generate.build_story_catalog(
                staging_public_dir=self.stage,
                jp_dir=self.jp,
                cn_dir=self.cn,
                exedra_jp_dir=self.exedra,
                exedra_cn_dir=self.exedra_cn,
                titles_path=self.titles,
            )

    def test_search_uses_manifest_ids_and_organized_txt(self) -> None:
        self._make_sources()
        stories, _ = generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=self.exedra,
            exedra_cn_dir=self.exedra_cn,
            titles_path=self.titles,
        )
        search_stats: dict[str, int] = {}
        entries = search.build_search_entries(
            stories=stories,
            public_dir=self.stage,
            titles=generate.load_titles(self.titles),
            stats=search_stats,
        )

        self.assertEqual(len(entries), 6)
        self.assertEqual(search_stats["manifest_source_slots"], 6)
        self.assertEqual(search_stats["search_indexed_slots"], 6)
        self.assertEqual(search_stats["search_fallback_slots"], 0)
        self.assertEqual(
            len({(entry["id"], entry["l"]) for entry in entries}),
            len(entries),
        )
        ids = {entry["id"] for entry in entries}
        self.assertEqual(ids, {story["id"] for story in stories})
        battle_story = next(
            story
            for story in stories
            if story.get("source_identity") == "exedra:10_Battle:battle_demo"
        )
        battle_search = next(
            entry for entry in entries if entry["id"] == battle_story["id"]
        )
        self.assertIn("もうあきらめない", battle_search["c"])
        self.assertIn("色", battle_search["c"])
        self.assertNotIn("<color", battle_search["c"])

        main_story = next(
            story
            for story in stories
            if story.get("source_identity") == "exedra:1_Main:main_demo"
        )
        main_search = next(
            entry
            for entry in entries
            if entry["id"] == main_story["id"] and entry["l"] == "jp"
        )
        self.assertIn("惚気", main_search["c"])

        with self.assertRaises(search.PipelineError):
            search.build_search_entries(
                stories=[*stories, stories[0]],
                public_dir=self.stage,
                titles={},
            )

    def test_content_addressed_manifest_and_stale_index_rejection(self) -> None:
        self._make_sources()
        stories, _ = generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=self.exedra,
            exedra_cn_dir=self.exedra_cn,
            titles_path=self.titles,
        )
        entries = search.build_search_entries(
            stories=stories,
            public_dir=self.stage,
            titles=generate.load_titles(self.titles),
        )
        story_index_path = self.stage / "story_index.json"
        output_path = self.stage / "search_content.json"
        manifest_path = self.stage / "search_index_manifest.json"
        story_index_bytes = story_index_path.read_bytes()
        manifest = search.write_search_artifacts_atomic(
            entries,
            output_path=output_path,
            manifest_path=manifest_path,
            story_index_bytes=story_index_bytes,
        )

        self.assertEqual(manifest["bytes"], output_path.stat().st_size)
        self.assertEqual(manifest["entries"], 6)
        self.assertEqual(
            manifest["object_key"],
            f"search/{manifest['sha256']}.json",
        )
        loaded_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        search.validate_search_manifest(
            loaded_manifest,
            payload=output_path.read_bytes(),
            entry_count=6,
            story_index_bytes=story_index_bytes,
        )

        source_to_change = self.stage / stories[0]["path_jp"].lstrip("/")
        source_to_change.write_text(
            source_to_change.read_text(encoding="utf-8") + "旁白: changed\n",
            encoding="utf-8",
        )
        args = Namespace(
            public_dir=str(self.stage),
            story_index=str(story_index_path),
            output=str(output_path),
            manifest=str(manifest_path),
            titles=str(self.titles),
            object_key_prefix="search",
            validate_only=True,
            dry_run=False,
        )
        with self.assertRaisesRegex(search.PipelineError, "内容陈旧"):
            search.run(args)

    def test_manifest_rejects_an_empty_or_unloadably_large_index(self) -> None:
        with self.assertRaisesRegex(search.PipelineError, "大小"):
            search.build_search_manifest(
                b"",
                entry_count=1,
                story_index_bytes=b"[]",
            )
        with self.assertRaisesRegex(search.PipelineError, "条目数"):
            search.build_search_manifest(
                b"[]",
                entry_count=0,
                story_index_bytes=b"[]",
            )
        with mock.patch.object(search, "MAX_SEARCH_INDEX_BYTES", 1):
            with self.assertRaisesRegex(search.PipelineError, "大小"):
                search.build_search_manifest(
                    b"[]",
                    entry_count=1,
                    story_index_bytes=b"[]",
                )

    def test_header_only_source_keeps_one_search_slot(self) -> None:
        source = self.jp / "main_story" / "header-only" / "101001_1.txt"
        write_text(source, "---[Section 1] (Source: unknown.json) ---\n")
        stories, _ = generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=None,
            exedra_cn_dir=None,
            titles_path=self.titles,
        )
        search_stats: dict[str, int] = {}
        entries = search.build_search_entries(
            stories=stories,
            public_dir=self.stage,
            titles={},
            stats=search_stats,
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], "101001")
        self.assertEqual(entries[0]["l"], "jp")
        self.assertEqual(entries[0]["c"], "101001_1")
        self.assertEqual(search_stats["search_fallback_slots"], 1)

    def test_safe_replace_installs_only_valid_staging(self) -> None:
        self._make_sources()
        stories, _ = generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=self.exedra,
            exedra_cn_dir=self.exedra_cn,
            titles_path=self.titles,
        )
        target = self.root / "target-public"
        write_text(target / "data" / "old.txt", "old")
        write_json(target / "story_index.json", [{"id": "old"}])

        backup = generate.safe_replace_generated(self.stage, target)

        self.assertFalse((target / "data" / "old.txt").exists())
        installed = json.loads((target / "story_index.json").read_text(encoding="utf-8"))
        self.assertEqual(installed, stories)
        self.assertIsNotNone(backup)
        assert backup is not None
        self.assertEqual((backup / "data" / "old.txt").read_text(), "old")
        self.assertEqual(
            json.loads((backup / "story_index.json").read_text()),
            [{"id": "old"}],
        )

    def test_copy_sync_fallback_rolls_back_after_install_failure(self) -> None:
        self._make_sources()
        generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=self.exedra,
            exedra_cn_dir=self.exedra_cn,
            titles_path=self.titles,
        )
        target = self.root / "rollback-target"
        write_text(target / "data" / "old.txt", "old")
        write_json(target / "story_index.json", [{"id": "old"}])
        backup_root = self.root / "rollback-backups" / "snapshot"
        staged_file = next(
            path for path in (self.stage / "data").rglob("*") if path.is_file()
        ).resolve()
        original_copy = generate._atomic_copy_verified
        injected = False

        def fail_one_install(source: Path, destination: Path) -> None:
            nonlocal injected
            if source.resolve() == staged_file and not injected:
                injected = True
                raise OSError("injected install failure")
            original_copy(source, destination)

        with (
            mock.patch.object(
                generate,
                "_atomic_copy_verified",
                side_effect=fail_one_install,
            ),
            self.assertRaisesRegex(generate.PipelineError, "已恢复旧版本"),
        ):
            generate._safe_copy_sync_replace(
                staged_data=self.stage / "data",
                staged_index=self.stage / "story_index.json",
                target_data=target / "data",
                target_index=target / "story_index.json",
                backup_root=backup_root,
                backup_data=backup_root / "data",
                backup_index=backup_root / "story_index.json",
            )

        self.assertTrue(injected)
        self.assertEqual((target / "data" / "old.txt").read_text(), "old")
        self.assertEqual(
            json.loads((target / "story_index.json").read_text()),
            [{"id": "old"}],
        )
        self.assertEqual((backup_root / "data" / "old.txt").read_text(), "old")

    def test_copy_sync_backup_failure_never_changes_target(self) -> None:
        self._make_sources()
        generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=self.exedra,
            exedra_cn_dir=self.exedra_cn,
            titles_path=self.titles,
        )
        target = self.root / "backup-failure-target"
        write_text(target / "data" / "old.txt", "old")
        write_json(target / "story_index.json", [{"id": "old"}])
        backup_root = self.root / "failed-backups" / "snapshot"

        with (
            mock.patch(
                "generate_story_index.shutil.copytree",
                side_effect=OSError("injected backup failure"),
            ),
            self.assertRaisesRegex(OSError, "injected backup failure"),
        ):
            generate._safe_copy_sync_replace(
                staged_data=self.stage / "data",
                staged_index=self.stage / "story_index.json",
                target_data=target / "data",
                target_index=target / "story_index.json",
                backup_root=backup_root,
                backup_data=backup_root / "data",
                backup_index=backup_root / "story_index.json",
            )

        self.assertEqual((target / "data" / "old.txt").read_text(), "old")
        self.assertEqual(
            json.loads((target / "story_index.json").read_text()),
            [{"id": "old"}],
        )
        self.assertFalse(backup_root.exists())

    def test_dry_run_does_not_replace_target(self) -> None:
        self._make_sources()
        target = self.root / "target-public"
        write_text(target / "data" / "sentinel.txt", "keep")
        write_json(target / "story_index.json", [{"id": "sentinel"}])
        args = Namespace(
            public_dir=str(target),
            titles=str(self.titles),
            jp_dir=str(self.jp),
            cn_dir=str(self.cn),
            exedra_jp_dir=str(self.exedra),
            exedra_cn_dir=str(self.exedra_cn),
            exedra_dir=None,
            validate_only=False,
            dry_run=True,
            skip_magireco=False,
            skip_exedra=False,
        )

        self.assertEqual(generate.run_generation(args), 0)
        self.assertEqual((target / "data" / "sentinel.txt").read_text(), "keep")
        current = json.loads((target / "story_index.json").read_text())
        self.assertEqual(current, [{"id": "sentinel"}])

    def test_module_reload_has_no_filesystem_mutation(self) -> None:
        with (
            mock.patch("shutil.rmtree") as remove,
            mock.patch("shutil.copy2") as copy,
            mock.patch("os.replace") as replace,
        ):
            import importlib

            importlib.reload(generate)
        remove.assert_not_called()
        copy.assert_not_called()
        replace.assert_not_called()


@unittest.skipUnless(
    os.environ.get("EXEDRA_ORGANIZED_DIR"),
    "set EXEDRA_ORGANIZED_DIR for the real corpus integration test",
)
class RealExedraCorpusTests(unittest.TestCase):
    def test_real_corpus_builds_with_unique_ids(self) -> None:
        source = Path(os.environ["EXEDRA_ORGANIZED_DIR"]).resolve()
        with tempfile.TemporaryDirectory() as temp_dir:
            stage = Path(temp_dir) / "public"
            stage.mkdir()
            empty_jp = Path(temp_dir) / "missing-jp"
            empty_cn = Path(temp_dir) / "missing-cn"
            titles = Path(temp_dir) / "titles.json"
            write_json(titles, {})

            stories, stats = generate.build_story_catalog(
                staging_public_dir=stage,
                jp_dir=empty_jp,
                cn_dir=empty_cn,
                exedra_jp_dir=source,
                exedra_cn_dir=empty_cn,
                titles_path=titles,
                include_magireco=False,
            )

            self.assertEqual(len(stories), 443)
            self.assertEqual(len(stories), len({story["id"] for story in stories}))
            self.assertEqual(stats["exedra_manifest_groups"], 443)
            self.assertEqual(stats["exedra_manifest_json_sources"], 3061)
            self.assertEqual(stats["exedra_manifest_json_verified"], 3061)
            self.assertEqual(stats["exedra_jp_groups"], 443)
            self.assertEqual(stats["exedra_cn_groups"], 0)
            self.assertEqual(stats["input_source_files"], 443)
            self.assertEqual(stats["manifest_source_files"], 443)
            self.assertEqual(stats["orphan_sources"], 0)
            self.assertEqual(stats["ownership_collisions"], 0)
            self.assertIn("exedra_battle", {story["category"] for story in stories})

            search_stats: dict[str, int] = {}
            entries = search.build_search_entries(
                stories=stories,
                public_dir=stage,
                titles={},
                stats=search_stats,
            )
            self.assertEqual(len(entries), len(stories))
            self.assertEqual(search_stats["manifest_source_slots"], 443)
            search.validate_search_entries(entries, stories=stories)


@unittest.skipUnless(
    os.environ.get("MAGIRECO_REAL_AUDIT"),
    "set MAGIRECO_REAL_AUDIT=1 for the real Magia Record audit test",
)
class RealMagiaRecordAuditTests(unittest.TestCase):
    def test_all_real_sources_are_reachable_and_owned_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stage = Path(temp_dir) / "public"
            stage.mkdir()
            regenerated, stats = generate.build_story_catalog(
                staging_public_dir=stage,
                jp_dir=generate.DEFAULT_DIR_JP,
                cn_dir=generate.DEFAULT_DIR_CN,
                exedra_jp_dir=None,
                exedra_cn_dir=None,
                titles_path=generate.DEFAULT_TITLES_PATH,
            )

            source_count = sum(
                1 for _ in generate.DEFAULT_DIR_JP.rglob("*.txt")
            ) + sum(1 for _ in generate.DEFAULT_DIR_CN.rglob("*.txt"))
            self.assertEqual(source_count, 4025)
            self.assertEqual(len(regenerated), 2394)
            self.assertEqual(stats["magireco_logical_stories"], 2394)
            self.assertEqual(stats["magireco_legacy_id_collision_groups"], 283)
            self.assertEqual(stats["magireco_collision_stories"], 570)
            self.assertEqual(stats["input_source_files"], source_count)
            self.assertEqual(stats["manifest_source_files"], source_count)
            self.assertEqual(stats["orphan_sources"], 0)
            self.assertEqual(stats["ownership_collisions"], 0)

            manifest_slots = {
                (story["source_identity"].casefold(), lang)
                for story in regenerated
                for lang in ("cn", "jp")
                if story[f"path_{lang}"]
            }
            expected_slots: set[tuple[str, str]] = set()
            for lang, root in (
                ("jp", generate.DEFAULT_DIR_JP),
                ("cn", generate.DEFAULT_DIR_CN),
            ):
                for source_path in root.rglob("*.txt"):
                    identity, _, _ = generate.magireco_source_identity(
                        root,
                        source_path,
                    )
                    expected_slots.add((identity, lang))
            self.assertEqual(manifest_slots, expected_slots)

            identities_420131 = [
                story
                for story in regenerated
                if story["category"] == "mirror_story"
                and story["raw_id"] == "420131"
            ]
            self.assertEqual(len(identities_420131), 3)
            self.assertEqual(
                len({story["source_identity"] for story in identities_420131}),
                3,
            )

            identities_5170100 = [
                story
                for story in regenerated
                if story["category"] == "event_story"
                and story["file_stem"] == "5170100-09_30-39"
            ]
            self.assertEqual(len(identities_5170100), 2)
            self.assertEqual(
                sorted(story["has_cn"] for story in identities_5170100),
                [False, True],
            )


if __name__ == "__main__":
    unittest.main()
