from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import organize_exedra_scenarios as organizer


def make_windows_junction(link: Path, target: Path) -> None:
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=True,
        capture_output=True,
        text=True,
    )


def scenario_json(
    rows: list[dict[str, str]],
    *,
    headers: tuple[str, ...] = ("ActionType", "Name", "Comment"),
    second_sheet: list[dict[str, str]] | None = None,
    title: str = "Fixture",
) -> bytes:
    def sheet(items: list[dict[str, str]]) -> dict[str, object]:
        return {
            "sheetName": "script",
            "headerRow": {"cellList": list(headers)},
            "contentRowList": [
                {"cellList": [row.get(header, "") for header in headers]}
                for row in items
            ],
        }

    sheets = [sheet(rows)]
    if second_sheet is not None:
        sheets.append(sheet(second_sheet))
    return json.dumps(
        {"bookTitle": title, "sheetList": sheets},
        ensure_ascii=False,
    ).encode("utf-8")


class ExedraOrganizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "Scenarios"
        for category in organizer.CATEGORY_ORDER:
            (self.source / category).mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def add_json(
        self,
        category: str,
        source_dir: str,
        *,
        filename: str | None = None,
        rows: list[dict[str, str]] | None = None,
        raw: bytes | None = None,
        headers: tuple[str, ...] = ("ActionType", "Name", "Comment"),
        second_sheet: list[dict[str, str]] | None = None,
    ) -> Path:
        directory = self.source / category / source_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (filename or f"{source_dir}.json")
        path.write_bytes(
            raw
            if raw is not None
            else scenario_json(
                rows
                or [
                    {
                        "ActionType": "Talk",
                        "Name": "まどか",
                        "Comment": "text",
                    }
                ],
                headers=headers,
                second_sheet=second_sheet,
            )
        )
        return path

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_build_plan_rejects_source_directory_junction(self) -> None:
        outside = self.root / "outside-main-audit"
        outside.mkdir()
        (outside / "main_audit1_1.json").write_bytes(
            scenario_json(
                [
                    {
                        "ActionType": "Talk",
                        "Name": "まどか",
                        "Comment": "outside sentinel",
                    }
                ]
            )
        )
        junction = self.source / "1_Main" / "main_audit1_1"
        make_windows_junction(junction, outside)
        try:
            with self.assertRaises(organizer.OrganizerError):
                organizer.build_plan(self.source)
            self.assertEqual(
                (outside / "main_audit1_1.json").read_bytes(),
                scenario_json(
                    [
                        {
                            "ActionType": "Talk",
                            "Name": "まどか",
                            "Comment": "outside sentinel",
                        }
                    ]
                ),
            )
        finally:
            if os.path.lexists(junction):
                os.rmdir(junction)

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_validate_output_rejects_directory_junction(self) -> None:
        self.add_json("1_Main", "main_audit1_1")
        plan = organizer.build_plan(self.source)
        output = self.root / "organized"
        organizer.write_stage(plan, output)
        group_dir = output.joinpath(*plan.groups[0].output_dir.split("/"))
        outside = self.root / "outside-organized-group"
        group_dir.rename(outside)
        make_windows_junction(group_dir, outside)
        try:
            with self.assertRaises(organizer.OrganizerError):
                organizer.validate_output(plan, output)
            self.assertTrue(
                (outside / plan.sources[0].source_name).is_file()
            )
        finally:
            if os.path.lexists(group_dir):
                os.rmdir(group_dir)

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_publish_rejects_output_beneath_junction_into_source(self) -> None:
        self.add_json("1_Main", "main_audit1_1")
        inside_sentinel = self.source / "1_Main" / "original-sentinel.txt"
        outside_sentinel = self.root / "outside-sentinel.txt"
        inside_sentinel.write_text("inside must survive", encoding="utf-8")
        outside_sentinel.write_text("outside must survive", encoding="utf-8")
        plan = organizer.build_plan(self.source)
        alias = self.root / "alias-to-source-main"
        make_windows_junction(alias, self.source / "1_Main")
        output = alias / "organized-inside-source"
        try:
            with self.assertRaises(organizer.OrganizerError):
                organizer.publish_plan(plan, output)
            self.assertFalse(
                (self.source / "1_Main" / "organized-inside-source").exists()
            )
            self.assertEqual(
                inside_sentinel.read_text(encoding="utf-8"),
                "inside must survive",
            )
            self.assertEqual(
                outside_sentinel.read_text(encoding="utf-8"),
                "outside must survive",
            )
        finally:
            if os.path.lexists(alias):
                os.rmdir(alias)

    def test_group_rules_preserve_chapters_and_years(self) -> None:
        cases = {
            ("1_Main", "main_embryoeve1_1"): "main_embryoeve1",
            ("1_Main", "main_embryoeve2_1"): "main_embryoeve2",
            ("2_Sub", "sub_farewell_1"): "sub_farewell",
            ("2_Sub", "sub_swimwear2025_48"): "sub_swimwear2025",
            (
                "4_Portrait",
                "portrait_swimwear2025_mami_2",
            ): "portrait_swimwear2025_mami",
            (
                "4_Portrait",
                "portrait_magirekozero3_2",
            ): "portrait_magirekozero3",
            (
                "1_Main",
                "main_baraen1_prologue3",
            ): "main_baraen1_prologue",
            ("8_Dungeon", "65000_5_3"): "65000_5",
        }
        for (category, source_dir), expected in cases.items():
            with self.subTest(source_dir=source_dir):
                self.assertEqual(
                    organizer.group_key_for(category, source_dir), expected
                )

    def test_reaction_and_namae_special_grouping(self) -> None:
        self.assertEqual(
            organizer.group_key_for(
                "6_Reaction", "cv_100101_other_evo_fee_07"
            ),
            "cv_100101",
        )
        self.assertEqual(
            organizer.group_key_for("6_Reaction", "cv_113401_5"),
            "cv_113401",
        )
        self.assertEqual(
            organizer.group_key_for(
                "7_Namae", "flashback_reaction_rosegarden2_2"
            ),
            "flashback_reaction_rosegarden",
        )
        self.assertEqual(
            organizer.group_key_for("7_Namae", "story_namae14"),
            "story_namae",
        )

    def test_dynamic_headers_newlines_and_playvoice(self) -> None:
        path = self.add_json(
            "1_Main",
            "main_fixture_1",
            headers=("Comment", "ActionType", "Name", "Other"),
            rows=[
                {
                    "ActionType": "Talk",
                    "Name": "まどか",
                    "Comment": "line one\r\nline two\nline three",
                    "Other": "ignored",
                },
                {
                    "ActionType": "OnlyText",
                    "Name": "",
                    "Comment": "system text",
                },
                {
                    "ActionType": "PlayVoice",
                    "Name": "",
                    "Comment": "演出注释",
                },
            ],
            second_sheet=[
                {
                    "ActionType": "Narration",
                    "Name": "",
                    "Comment": "second sheet",
                }
            ],
        )
        document = json.loads(path.read_text("utf-8"))
        (
            dialogues,
            excluded,
            deduplicated,
            warnings,
        ) = organizer.extract_dialogues(document, is_reaction=False)
        self.assertEqual(warnings, [])
        self.assertEqual(excluded, 1)
        self.assertEqual(deduplicated, 0)
        self.assertEqual(len(dialogues), 3)
        self.assertEqual(
            dialogues[0].text, r"line one\nline two\nline three"
        )
        self.assertEqual(dialogues[1].speaker, "Narration")
        self.assertEqual(dialogues[2].sheet, 2)
        self.assertNotIn("演出注释", [line.text for line in dialogues])

    def test_identical_duplicate_sheet_is_emitted_only_once(self) -> None:
        repeated = [
            {
                "ActionType": "Talk",
                "Name": "",
                "Comment": "同じ台詞\n一度だけ",
            }
        ]
        path = self.add_json(
            "6_Reaction",
            "cv_114401_other_story_04",
            rows=repeated,
            second_sheet=repeated,
        )
        document = json.loads(path.read_text("utf-8"))
        (
            dialogues,
            excluded,
            deduplicated,
            warnings,
        ) = organizer.extract_dialogues(document, is_reaction=True)
        self.assertEqual(excluded, 0)
        self.assertEqual(deduplicated, 1)
        self.assertEqual(len(dialogues), 1)
        self.assertEqual(dialogues[0].speaker, "")
        self.assertEqual(dialogues[0].text, r"同じ台詞\n一度だけ")
        self.assertEqual(
            warnings, ["sheet-2:duplicate-of-sheet-1"]
        )

        plan = organizer.build_plan(self.source)
        manifest = organizer.manifest_for(plan)
        self.assertEqual(manifest["summary"]["deduplicatedSheetCount"], 1)
        self.assertEqual(manifest["summary"]["warningCount"], 1)

    def test_safe_speaker_state_matches_reader_json_parser(self) -> None:
        document = json.loads(
            scenario_json(
                [
                    {
                        "ActionType": "Put",
                        "Name": "鹿目まどか",
                        "AssetID": "100101",
                        "PositionID": "Left_2P",
                    },
                    {
                        "ActionType": "Talk",
                        "Comment": "位置から復元",
                        "PositionID": "Left_2P",
                    },
                    {
                        "ActionType": "Put",
                        "AssetID": "801400",
                        "PositionID": "Left_2P",
                    },
                    {
                        "ActionType": "Talk",
                        "Comment": "空のPutで古い名前を消す",
                        "PositionID": "Left_2P",
                    },
                    {
                        "ActionType": "Talk",
                        "Comment": "AssetIDから復元",
                        "AssetID": "A-Q",
                    },
                    {
                        "ActionType": "Narration",
                        "Comment": "位置があっても旁白",
                        "PositionID": "Left_2P",
                    },
                ],
                headers=(
                    "ActionType",
                    "Name",
                    "Comment",
                    "AssetID",
                    "PositionID",
                ),
            )
        )
        dialogues, _, _, _ = organizer.extract_dialogues(
            document,
            is_reaction=False,
        )
        self.assertEqual(
            [dialogue.speaker for dialogue in dialogues],
            ["鹿目まどか", "Narration", "A-Q", "Narration"],
        )

        asset_document = json.loads(
            scenario_json(
                [
                    {
                        "ActionType": "Put",
                        "Name": "生徒Ａ",
                        "AssetID": "800101",
                        "PositionID": "Left_2P",
                    },
                    {
                        "ActionType": "Put",
                        "Name": "生徒Ｂ",
                        "AssetID": "800200",
                        "PositionID": "Right_2P",
                    },
                    {
                        "ActionType": "Put",
                        "Name": "使い魔",
                        "AssetID": "adv_chara_03_007",
                        "PositionID": "Left",
                    },
                    {
                        "ActionType": "Talk",
                        "Comment": "キャー！",
                        "AssetID": "800101",
                        "PositionID": "Left_2P",
                    },
                    {
                        "ActionType": "Talk",
                        "Comment": "助けて！",
                        "AssetID": "800200",
                        "PositionID": "Right_2P",
                    },
                ],
                headers=(
                    "ActionType",
                    "Name",
                    "Comment",
                    "AssetID",
                    "PositionID",
                ),
            )
        )
        asset_dialogues, _, _, _ = organizer.extract_dialogues(
            asset_document,
            is_reaction=False,
        )
        self.assertEqual(
            [dialogue.speaker for dialogue in asset_dialogues],
            ["生徒Ａ", "生徒Ｂ"],
        )

        reaction = json.loads(
            scenario_json(
                [{"ActionType": "Talk", "Comment": "反応ボイス"}],
                title="鹿目まどか_魔法少女_覚醒ボイス_1",
            )
        )
        reaction_dialogues, _, _, _ = organizer.extract_dialogues(
            reaction,
            is_reaction=True,
        )
        self.assertEqual(reaction_dialogues[0].speaker, "鹿目まどか")

    def test_plan_owns_each_json_once_and_reaction_order_matches_source(self) -> None:
        for source_dir in (
            "cv_100101_other_story_02",
            "cv_100101_other_evo_fee_01",
            "cv_100101_other_story_01",
            "cv_100101_other_evo_fee_02",
        ):
            self.add_json("6_Reaction", source_dir)
        self.add_json("6_Reaction", "cv_113401_2")
        self.add_json("6_Reaction", "cv_113401_1")
        self.add_json("7_Namae", "story_namae00")
        self.add_json("7_Namae", "story_namae01")

        plan = organizer.build_plan(self.source)
        self.assertEqual(len(plan.sources), 8)
        self.assertEqual(
            len(
                {
                    source.source_path
                    for group in plan.groups
                    for source in group.sources
                }
            ),
            8,
        )
        group = next(
            item for item in plan.groups if item.group_id.endswith(":cv_100101")
        )
        self.assertEqual(
            [source.source_dir for source in group.sources],
            [
                "cv_100101_other_evo_fee_01",
                "cv_100101_other_story_01",
                "cv_100101_other_evo_fee_02",
                "cv_100101_other_story_02",
            ],
        )
        compact = next(
            item for item in plan.groups if item.group_id.endswith(":cv_113401")
        )
        self.assertEqual(
            [source.source_dir for source in compact.sources],
            ["cv_113401_1", "cv_113401_2"],
        )

    def test_generated_txt_and_combined_txt_are_never_source_inputs(self) -> None:
        self.add_json("3_Character", "character_asuka_0")
        source_dir = self.source / "3_Character" / "character_asuka_0"
        (source_dir / "character_asuka_0.txt").write_text(
            "must be ignored", encoding="utf-8"
        )
        reference = self.source / "Scenarios_full" / "3_Character_full"
        reference.mkdir(parents=True)
        (reference / "character_asuka_combined.txt").write_text(
            "must also be ignored", encoding="utf-8"
        )

        plan = organizer.build_plan(self.source)
        self.assertEqual(len(plan.sources), 1)
        self.assertEqual(len(plan.groups), 1)
        self.assertNotIn("must be ignored", plan.groups[0].text)

    def test_primary_json_sorts_before_duplicate_copy(self) -> None:
        primary = self.add_json(
            "1_Main",
            "main_nightmare_7",
            filename="main_nightmare_7.json",
        )
        duplicate = self.add_json(
            "1_Main",
            "main_nightmare_7",
            filename="main_nightmare_7 (2).json",
        )
        plan = organizer.build_plan(self.source)
        group = next(
            item
            for item in plan.groups
            if item.group_key == "main_nightmare"
        )
        self.assertEqual(
            [source.path for source in group.sources],
            [primary, duplicate],
        )

    def test_output_keeps_json_bytes_and_section_format(self) -> None:
        first = self.add_json(
            "3_Character",
            "character_asuka_0",
            rows=[
                {
                    "ActionType": "Talk",
                    "Name": "竜城明日香",
                    "Comment": "第一行\n第二行\n",
                }
            ],
        )
        second = self.add_json(
            "3_Character",
            "character_asuka_1",
            rows=[
                {
                    "ActionType": "Narration",
                    "Name": "",
                    "Comment": "narration",
                }
            ],
        )
        plan = organizer.build_plan(self.source)
        output = self.root / "organized"
        organizer.write_stage(plan, output)
        result = organizer.validate_output(plan, output)

        self.assertEqual(result["sources"], 2)
        self.assertEqual(
            (
                output
                / "3_Character"
                / "character_asuka"
                / first.name
            ).read_bytes(),
            first.read_bytes(),
        )
        self.assertEqual(
            (
                output
                / "3_Character"
                / "character_asuka"
                / second.name
            ).read_bytes(),
            second.read_bytes(),
        )
        text = (
            output
            / "3_Character"
            / "character_asuka"
            / "character_asuka_jp.txt"
        ).read_text("utf-8")
        self.assertIn(
            "--- [Section 1] (Source: character_asuka_0.json) ---", text
        )
        self.assertIn("竜城明日香: 第一行\\n第二行", text)
        self.assertNotIn("竜城明日香: 第一行\\n第二行\\n", text)
        self.assertIn(
            "--- [Section 2] (Source: character_asuka_1.json) ---", text
        )

    def test_publish_preserves_existing_output_as_backup(self) -> None:
        self.add_json("10_Battle", "battle_tart2_1")
        plan = organizer.build_plan(self.source)
        output = self.root / "Scenarios_full"
        output.mkdir()
        (output / "user-file.txt").write_text("keep me", encoding="utf-8")

        published, backup = organizer.publish_plan(plan, output)
        self.assertEqual(published, output.resolve())
        self.assertIsNotNone(backup)
        assert backup is not None
        self.assertEqual(
            (backup / "user-file.txt").read_text("utf-8"), "keep me"
        )
        self.assertTrue((published / organizer.MANIFEST_NAME).is_file())
        organizer.validate_output(plan, published)

    def test_output_validation_rejects_every_unplanned_file(self) -> None:
        self.add_json("1_Main", "main_test_1")
        plan = organizer.build_plan(self.source)
        unexpected_paths = (
            Path("README.tmp"),
            Path(
                "1_Main",
                "main_test",
                "unexpected_cn.txt",
            ),
        )

        for index, unexpected in enumerate(unexpected_paths, start=1):
            with self.subTest(unexpected=unexpected.as_posix()):
                output = self.root / f"unexpected-output-{index}"
                organizer.write_stage(plan, output)
                target = output / unexpected
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("unexpected", encoding="utf-8")
                with self.assertRaisesRegex(
                    organizer.OrganizerError,
                    "Output file mismatch",
                ):
                    organizer.validate_output(plan, output)

    def test_manifest_is_deterministic_and_reports_zero_ownership_errors(
        self,
    ) -> None:
        self.add_json("2_Sub", "sub_farewell_2")
        self.add_json("2_Sub", "sub_farewell_1")
        first_plan = organizer.build_plan(self.source)
        second_plan = organizer.build_plan(self.source)
        first = organizer.manifest_for(first_plan)
        second = organizer.manifest_for(second_plan)
        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["duplicateOwnershipCount"], 0)
        self.assertEqual(first["summary"]["omittedSourceCount"], 0)
        self.assertEqual(first["summary"]["sourceCount"], 2)
        self.assertEqual(first["summary"]["groupCount"], 1)

    def test_unreadable_json_aborts_before_output(self) -> None:
        self.add_json(
            "1_Main",
            "main_bad_1",
            raw=b"{ definitely not json",
        )
        output = self.root / "must-not-exist"
        with self.assertRaises(organizer.OrganizerError):
            plan = organizer.build_plan(self.source)
            organizer.publish_plan(plan, output)
        self.assertFalse(output.exists())

    def test_publish_refuses_to_overlap_original_source_tree(self) -> None:
        self.add_json("1_Main", "main_safe_1")
        plan = organizer.build_plan(self.source)
        original = next(self.source.rglob("*.json")).read_bytes()
        with self.assertRaises(organizer.OrganizerError):
            organizer.publish_plan(plan, self.source / "Scenarios_full")
        self.assertEqual(next(self.source.rglob("*.json")).read_bytes(), original)
        self.assertFalse((self.source / "Scenarios_full").exists())


if __name__ == "__main__":
    unittest.main()
