from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "scripts"
    / "materialize_proofreading_assets.py"
)
spec = importlib.util.spec_from_file_location(
    "materialize_proofreading_assets", MODULE_PATH
)
assert spec and spec.loader
materialize = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = materialize
spec.loader.exec_module(materialize)


def write_json(path: Path, value: object, *, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=indent) + "\n",
        encoding="utf-8",
    )


def exedra_sheet(comment: str, *, duplicate: bool = False) -> dict:
    sheet = {
        "headerRow": {
            "cellList": ["ActionType", "Name", "Comment", "AssetId"]
        },
        "contentRowList": [
            {
                "rowNumber": 2,
                "cellList": ["Talk", "角色", comment, "keep-asset"],
            }
        ],
    }
    return {"sheetList": [sheet, json.loads(json.dumps(sheet))] if duplicate else [sheet]}


def without_text_home(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: without_text_home(item)
            for key, item in value.items()
            if key != "textHome"
        }
    if isinstance(value, list):
        return [without_text_home(item) for item in value]
    return value


class MaterializeProofreadingAssetsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_voice_manifests(
        self,
        *,
        model_id: str,
        source: Path,
        txt: Path,
    ) -> tuple[Path, Path]:
        manifest = {
            "version": 1,
            "sourceCommit": "6d921b630f41341a1c5aba66ec355ef9017e778d",
            "modelCount": 1,
            "models": [
                {
                    "id": model_id,
                    "groups": 2,
                    "voices": 2,
                    "jsonSha256": materialize.sha256_bytes(
                        source.read_bytes()
                    ),
                    "txtSha256": materialize.sha256_bytes(txt.read_bytes()),
                }
            ],
        }
        source_manifest = (
            self.root
            / "magireco-voice-source-master/Scenarios_full/general_voice/"
            "general_voice_manifest.json"
        )
        cn_manifest = (
            self.root
            / "magireco-voice-translate-data-master/Scenarios_full/"
            "general_voice/general_voice_manifest.json"
        )
        write_json(source_manifest, manifest)
        write_json(cn_manifest, manifest)
        return source_manifest, cn_manifest

    def test_json_serializer_preserves_compact_template_style(self) -> None:
        document = {"story": {"group_1": [{"textHome": "中文"}]}}
        template = (
            json.dumps(
                document,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        self.assertEqual(
            materialize.json_bytes_like(document, template),
            template,
        )

    def test_magireco_generates_json_then_canonical_txt(self) -> None:
        folder = Path(
            "magireco-translate-data-master/Scenarios_full/"
            "character_story/1001 - 测试"
        )
        txt = self.root / folder / "100101_1.txt"
        source = self.root / folder / "100101-1.json"
        document = {
            "story": {
                "group_1": [
                    {
                        "bg": "bg_keep.jpg",
                        "nameLeft": "原名",
                        "textLeft": "旧句@[se:ding]后句",
                    },
                    {
                        "select": [
                            {
                                "textSelect": "旧选项",
                                "group": "group_2",
                                "alternativeId": "keep-id",
                            }
                        ]
                    },
                ],
                "group_2": [
                    {
                        "nameNarration": "",
                        "narration": "旧旁白",
                        "bgm": "keep-bgm",
                    }
                ],
            },
            "version": 3,
        }
        write_json(source, document, indent=1)
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_text(
            "--- [Section 1] (Source: 100101-1.json) ---\n"
            "新名：新句\\n后句\n"
            "选项：【新选项】→ group_2\n\n"
            "--- [Section 1 - Branch 2] (Source: 100101-1.json) ---\n"
            "旁白：新旁白\n",
            encoding="utf-8",
        )

        report = materialize.materialize(
            txt, repo_root=self.root, write=True
        )

        output = json.loads(source.read_text(encoding="utf-8"))
        first = output["story"]["group_1"][0]
        self.assertEqual(first["bg"], "bg_keep.jpg")
        self.assertEqual(first["nameLeft"], "新名")
        self.assertEqual(first["textLeft"], "新句@[se:ding]后句")
        option = output["story"]["group_1"][1]["select"][0]
        self.assertEqual(option["textSelect"], "新选项")
        self.assertEqual(option["group"], "group_2")
        self.assertEqual(option["alternativeId"], "keep-id")
        narration = output["story"]["group_2"][0]
        self.assertEqual(narration["narration"], "新旁白")
        self.assertEqual(narration["bgm"], "keep-bgm")
        self.assertIn("[se:ding]", source.read_text(encoding="utf-8"))

        canonical = txt.read_text(encoding="utf-8")
        self.assertIn("新名：新句\\n后句", canonical)
        self.assertIn("选项: 【新选项】→ group_2", canonical)
        self.assertEqual(report["game"], "magireco")
        self.assertTrue(report["validation"]["jsonToTxtRoundTripMatch"])
        self.assertTrue(
            txt.with_suffix(".proofreading-report.json").is_file()
        )

    def test_general_voice_generates_playable_json_then_canonical_txt(self) -> None:
        model_id = "100100"
        txt = (
            self.root
            / "magireco-voice-translate-data-master/Scenarios_full/"
            "general_voice"
            / model_id
            / f"{model_id}_cn.txt"
        )
        source = (
            self.root
            / "magireco-voice-source-master/Scenarios_full/general_voice"
            / model_id
            / f"{model_id}.json"
        )
        original = {
            "story": {
                "group_1": [
                    {
                        "autoTurnFirst": 2.5,
                        "chara": [
                            {
                                "id": 100100,
                                "voice": "vo_keep_01",
                                "textHome": "旧句@后句",
                                "motion": 200,
                            }
                        ],
                    },
                    {
                        "chara": [
                            {
                                "id": 100100,
                                "textHome": "续句",
                                "motion": 100,
                            }
                        ]
                    },
                ],
                "group_2": [
                    {
                        "autoTurnFirst": 1.0,
                        "chara": [
                            {
                                "id": 100100,
                                "voice": "vo_keep_02",
                                "textHome": "第二句",
                                "face": "keep.exp.json",
                            }
                        ],
                    }
                ],
            },
            "version": 3,
        }
        write_json(source, original)
        txt.parent.mkdir(parents=True, exist_ok=True)
        base = (
            f"--- [Section 1] (Source: {model_id}.json) ---\n"
            "环彩羽：【vo_keep_01｜2.5秒｜文本 1/2】旧句／后句\n"
            "环彩羽：【vo_keep_01｜2.5秒｜文本 2/2】续句\n\n"
            f"--- [Section 2] (Source: {model_id}.json) ---\n"
            "环彩羽：【vo_keep_02｜1秒】第二句\n"
        )
        txt.write_text(base, encoding="utf-8")
        source_manifest, cn_manifest = self.write_voice_manifests(
            model_id=model_id,
            source=source,
            txt=txt,
        )
        reviewed = (
            base.replace("旧句／后句", "修正句／修正后句")
            .replace("】续句", "】修正续句")
        )

        report = materialize.materialize(
            txt,
            repo_root=self.root,
            write=True,
            reviewed_text=reviewed,
        )

        output = json.loads(source.read_text(encoding="utf-8"))
        first = output["story"]["group_1"][0]["chara"][0]
        self.assertEqual(first["textHome"], "修正句@修正后句")
        self.assertEqual(first["voice"], "vo_keep_01")
        self.assertEqual(first["motion"], 200)
        continuation = output["story"]["group_1"][1]["chara"][0]
        self.assertEqual(continuation["textHome"], "修正续句")
        self.assertEqual(continuation["motion"], 100)
        second = output["story"]["group_2"][0]["chara"][0]
        self.assertEqual(second["face"], "keep.exp.json")
        self.assertEqual(
            without_text_home(output),
            without_text_home(original),
        )
        self.assertEqual(report["game"], "magireco_voice")
        self.assertIn(
            "magireco-voice-source-master/Scenarios_full/general_voice/"
            "100100/100100.json",
            report["materializedPaths"],
        )
        self.assertIn(
            "magireco-voice-source-master/Scenarios_full/general_voice/"
            "general_voice_manifest.json",
            report["materializedPaths"],
        )
        self.assertIn(
            "magireco-voice-translate-data-master/Scenarios_full/"
            "general_voice/general_voice_manifest.json",
            report["materializedPaths"],
        )
        self.assertTrue(
            report["validation"]["generalVoiceManifestHashesUpdated"]
        )
        canonical = txt.read_text(encoding="utf-8")
        self.assertIn("修正句／修正后句", canonical)
        self.assertIn("修正续句", canonical)
        self.assertEqual(
            source_manifest.read_bytes(),
            cn_manifest.read_bytes(),
        )
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        model = manifest["models"][0]
        self.assertEqual(
            model["jsonSha256"],
            materialize.sha256_bytes(source.read_bytes()),
        )
        self.assertEqual(
            model["txtSha256"],
            materialize.sha256_bytes(txt.read_bytes()),
        )

    def test_general_voice_rejects_mismatched_integrity_manifests(self) -> None:
        model_id = "100100"
        txt = (
            self.root
            / "magireco-voice-translate-data-master/Scenarios_full/"
            "general_voice"
            / model_id
            / f"{model_id}_cn.txt"
        )
        source = (
            self.root
            / "magireco-voice-source-master/Scenarios_full/general_voice"
            / model_id
            / f"{model_id}.json"
        )
        write_json(
            source,
            {
                "story": {
                    "group_1": [
                        {"chara": [{"voice": "voice", "textHome": "旧句"}]}
                    ]
                }
            },
        )
        txt.parent.mkdir(parents=True, exist_ok=True)
        base = (
            f"--- [Section 1] (Source: {model_id}.json) ---\n"
            "角色：【voice｜0秒】旧句\n"
        )
        txt.write_text(base, encoding="utf-8")
        _source_manifest, cn_manifest = self.write_voice_manifests(
            model_id=model_id,
            source=source,
            txt=txt,
        )
        cn_manifest.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(
            materialize.MaterializeError,
            "来源/中文完整性清单不一致",
        ):
            materialize.materialize(
                txt,
                repo_root=self.root,
                write=False,
                reviewed_text=base.replace("旧句", "新句"),
            )

    def test_general_voice_rejects_resource_label_change(self) -> None:
        model_id = "100100"
        txt = (
            self.root
            / "magireco-voice-translate-data-master/Scenarios_full/"
            "general_voice"
            / model_id
            / f"{model_id}_cn.txt"
        )
        source = (
            self.root
            / "magireco-voice-source-master/Scenarios_full/general_voice"
            / model_id
            / f"{model_id}.json"
        )
        write_json(
            source,
            {
                "story": {
                    "group_1": [
                        {
                            "chara": [
                                {
                                    "voice": "vo_keep_01",
                                    "textHome": "旧句",
                                }
                            ]
                        }
                    ]
                }
            },
        )
        txt.parent.mkdir(parents=True, exist_ok=True)
        base = (
            f"--- [Section 1] (Source: {model_id}.json) ---\n"
            "环彩羽：【vo_keep_01｜2.5秒】旧句\n"
        )
        txt.write_text(base, encoding="utf-8")
        reviewed = base.replace("vo_keep_01", "vo_tampered")

        with self.assertRaises(materialize.MaterializeError):
            materialize.materialize(
                txt,
                repo_root=self.root,
                write=False,
                reviewed_text=reviewed,
            )

    def _write_exedra_fixture(
        self, *, reviewed_speaker: str = "角色"
    ) -> tuple[Path, Path]:
        category = "3_Character"
        group = "character_test"
        cn_folder = (
            self.root
            / "magiraexedra-translate-data-master/Scenarios_full"
            / category
            / group
        )
        jp_folder = (
            self.root
            / "magiraexedra-source-master/Scenarios_full"
            / category
            / group
        )
        cn_json = cn_folder / "character_test_0.json"
        jp_json = jp_folder / "character_test_0.json"
        write_json(jp_json, exedra_sheet("日文", duplicate=True))
        write_json(cn_json, exedra_sheet("旧中文", duplicate=True))
        jp_txt = jp_folder / "character_test_jp.txt"
        jp_txt.write_text(
            "--- [Section 1] (Source: character_test_0.json) ---\n"
            "角色：日文\n",
            encoding="utf-8",
        )
        manifest = {
            "schemaVersion": 1,
            "groups": [
                {
                    "id": "exedra:3_Character:character_test",
                    "category": category,
                    "groupKey": group,
                    "outputDir": f"{category}/{group}",
                    "textFile": f"{category}/{group}/{group}_jp.txt",
                    "sources": [
                        f"{category}/character_test_0/character_test_0.json"
                    ],
                }
            ],
        }
        write_json(
            self.root
            / "magiraexedra-source-master/Scenarios_full/exedra_manifest.json",
            manifest,
        )
        txt = cn_folder / "character_test_cn.txt"
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_text(
            "--- [Section 1] (Source: character_test_0.json) ---\n"
            f"{reviewed_speaker}：修正中文\n",
            encoding="utf-8",
        )
        return txt, cn_json

    def test_exedra_updates_duplicate_sheets_and_validation_sidecars(self) -> None:
        txt, cn_json = self._write_exedra_fixture()

        report = materialize.materialize(
            txt, repo_root=self.root, write=True
        )

        output = json.loads(cn_json.read_text(encoding="utf-8"))
        for sheet in output["sheetList"]:
            cells = sheet["contentRowList"][0]["cellList"]
            self.assertEqual(cells[1], "角色")
            self.assertEqual(cells[2], "修正中文")
            self.assertEqual(cells[3], "keep-asset")
        self.assertEqual(report["game"], "exedra")
        import_report = json.loads(
            txt.with_name(
                "character_test_cn.import-report.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(import_report["status"], "validated")
        self.assertEqual(
            import_report["provenance"], "community_proofread_human"
        )
        self.assertTrue(import_report["validation"]["passed"])
        provenance = json.loads(
            txt.with_name(
                "character_test_cn.provenance.json"
            ).read_text(encoding="utf-8")
        )
        self.assertFalse(provenance["machineTranslation"])
        self.assertEqual(
            provenance["provenance"], "community_proofread_human"
        )

    def test_exedra_rejects_speaker_identity_change_without_partial_writes(self) -> None:
        txt, cn_json = self._write_exedra_fixture()
        before = cn_json.read_bytes()
        reviewed = txt.read_text(encoding="utf-8").replace(
            "角色：修正中文", "冒充角色：修正中文"
        )

        with self.assertRaises(materialize.MaterializeError):
            materialize.materialize(
                txt,
                repo_root=self.root,
                write=True,
                reviewed_text=reviewed,
            )

        self.assertEqual(cn_json.read_bytes(), before)
        self.assertFalse(
            txt.with_suffix(".proofreading-report.json").exists()
        )

    def test_rejects_magireco_event_count_change(self) -> None:
        folder = Path(
            "magireco-translate-data-master/Scenarios_full/event_story/test"
        )
        source = self.root / folder / "500001-1.json"
        txt = self.root / folder / "500001_1.txt"
        write_json(
            source,
            {
                "story": {
                    "group_1": [
                        {"nameLeft": "角色", "textLeft": "只有一行"}
                    ]
                },
                "version": 3,
            },
        )
        txt.write_text(
            "--- [Section 1] (Source: 500001-1.json) ---\n"
            "角色：第一行\n"
            "角色：凭空增加的一行\n",
            encoding="utf-8",
        )
        before = source.read_bytes()

        with self.assertRaises(materialize.MaterializeError):
            materialize.materialize(
                txt, repo_root=self.root, write=True
            )

        self.assertEqual(source.read_bytes(), before)

    def test_rejects_changed_choice_target(self) -> None:
        folder = Path(
            "magireco-translate-data-master/Scenarios_full/event_story/test"
        )
        source = self.root / folder / "500002-1.json"
        txt = self.root / folder / "500002_1.txt"
        write_json(
            source,
            {
                "story": {
                    "group_1": [
                        {
                            "select": [
                                {
                                    "textSelect": "选项",
                                    "group": "group_2",
                                }
                            ]
                        }
                    ]
                },
                "version": 3,
            },
        )
        txt.write_text(
            "--- [Section 1] (Source: 500002-1.json) ---\n"
            "选项：【篡改目标】→ group_9\n",
            encoding="utf-8",
        )

        with self.assertRaises(materialize.MaterializeError):
            materialize.materialize(
                txt, repo_root=self.root, write=False
            )

    def test_scene0_extended_rows_preserve_playback_commands(self) -> None:
        folder = Path(
            "magireco-translate-data-master/Scenarios_full/Scene0支线/film1"
        )
        source = self.root / folder / "900101-010.json"
        txt = self.root / folder / "900101_010.txt"
        write_json(
            source,
            {
                "story": {
                    "group_1": [
                        {
                            "nameFnarration": "圆",
                            "progressFnarration": "旧独白",
                            "bg": "keep-bg",
                        },
                        {
                            "nameAvLeft": "丘比",
                            "textAvLeft": "旧对话",
                            "motion": "keep-motion",
                        },
                    ]
                },
                "version": 3,
            },
        )
        txt.write_text(
            "--- [Section 010] (Source: 900101-010.json) ---\n"
            '@S0\t{"kind":"fnarration","speaker":"圆","text":"新独白",'
            '"command":"progressFnarration"}\n'
            '@S0\t{"kind":"dialogue","speaker":"丘比","text":"新对话",'
            '"command":"textAvLeft","position":"left"}\n',
            encoding="utf-8",
        )

        materialize.materialize(txt, repo_root=self.root, write=True)

        output = json.loads(source.read_text(encoding="utf-8"))
        first, second = output["story"]["group_1"]
        self.assertEqual(first["progressFnarration"], "新独白")
        self.assertEqual(first["bg"], "keep-bg")
        self.assertEqual(second["textAvLeft"], "新对话")
        self.assertEqual(second["motion"], "keep-motion")
        canonical = txt.read_text(encoding="utf-8")
        self.assertIn('"command":"progressFnarration"', canonical)
        self.assertIn('"command":"textAvLeft","position":"left"', canonical)


if __name__ == "__main__":
    unittest.main()
