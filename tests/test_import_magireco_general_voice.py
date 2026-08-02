from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import import_magireco_general_voice as voice_import  # noqa: E402


class GeneralVoiceImportTests(unittest.TestCase):
    def test_audited_gropu_typo_is_normalized(self) -> None:
        normalized = voice_import.normalize_script(
            {
                "version": 2,
                "story": {
                    "group_1": [],
                    "gropu_2": [{"chara": [{"voice": "voice_2"}]}],
                },
            },
            "390000",
        )
        self.assertEqual(
            list(normalized["story"]),
            ["group_1", "group_2"],
        )
        self.assertNotIn("gropu_2", normalized["story"])

    def test_typo_normalization_never_overwrites_a_real_group(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "invalid group"):
            voice_import.normalize_script(
                {
                    "story": {
                        "group_2": [],
                        "gropu_2": [],
                    },
                },
                "390000",
            )

    def test_non_group_content_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "invalid group"):
            voice_import.normalize_script(
                {"story": {"metadata": []}},
                "100100",
            )

    def test_txt_keeps_multiple_text_home_events_on_independent_lines(self) -> None:
        script = {
            "story": {
                "group_1": [
                    {
                        "autoTurnFirst": 2,
                        "chara": [
                            {
                                "voice": "voice_1",
                                "textHome": "第一句@后半\n末尾",
                            }
                        ],
                    },
                    {"chara": [{"textHome": "第二句"}]},
                ]
            }
        }
        model = {
            "id": "100100",
            "char": {"cn": "角色"},
        }
        rendered = voice_import.script_to_txt(script, model)
        self.assertIn(
            "角色：【voice_1｜2秒｜文本 1/2】第一句／后半／末尾",
            rendered,
        )
        self.assertIn(
            "角色：【voice_1｜2秒｜文本 2/2】第二句",
            rendered,
        )
        self.assertNotIn("第一句／后半 第二句", rendered)

    def test_txt_without_text_home_keeps_only_immutable_voice_prefix(self) -> None:
        rendered = voice_import.script_to_txt(
            {
                "story": {
                    "group_1": [{
                        "autoTurnFirst": 20.1,
                        "chara": [{
                            "voice": "vo_char_4062_00_01",
                            "motion": 200,
                        }],
                    }],
                },
            },
            {"id": "406200", "char": {"cn": "井之上泷奈"}},
        )
        self.assertIn("井之上泷奈：【vo_char_4062_00_01｜20.1秒】", rendered)
        self.assertNotIn("语音资源：", rendered)

    def test_duo_duplicate_voice_text_is_one_editable_line_and_conflicts_fail(self) -> None:
        script = {
            "story": {
                "group_1": [{
                    "autoTurnFirst": 3,
                    "chara": [
                        {"id": 140101, "voice": "duo_voice", "textHome": "同一句"},
                        {"id": 140102, "voice": "duo_voice", "textHome": "同一句"},
                    ],
                }],
            },
        }
        rendered = voice_import.script_to_txt(
            script,
            {"id": "140100", "char": {"cn": "环彩羽＆环忧"}},
        )
        self.assertEqual(rendered.count("同一句"), 1)
        self.assertEqual(rendered.count("duo_voice"), 1)

        script["story"]["group_1"][0]["chara"][1]["textHome"] = "冲突句"
        with self.assertRaisesRegex(RuntimeError, "textHome conflict"):
            voice_import.script_to_txt(
                script,
                {"id": "140100", "char": {"cn": "环彩羽＆环忧"}},
            )

    def test_hierarchy_groups_duo_components_without_deleting_models(self) -> None:
        models = [
            {
                "id": "140100",
                "char": {"cn": "环彩羽", "jp": "環 いろは"},
                "costume": {"cn": "环彩羽_巫女", "jp": "環 いろは(巫女)"},
                "voiceGroups": 39,
                "rawVoiceReferences": 78,
            },
            {
                "id": "140101",
                "char": {"cn": "环彩羽", "jp": "環 いろは"},
                "costume": {"cn": "环彩羽_巫女", "jp": "環 いろは(巫女)"},
                "voiceGroups": 39,
                "rawVoiceReferences": 60,
            },
            {
                "id": "140102",
                "char": {"cn": "环忧", "jp": "環 うい"},
                "costume": {"cn": "环忧_巫女", "jp": "環 うい(巫女)"},
                "voiceGroups": 39,
                "rawVoiceReferences": 60,
            },
        ]
        hierarchy = voice_import.build_hierarchy_metadata(models)
        self.assertEqual(set(hierarchy), {"140100", "140101", "140102"})
        self.assertIn("环彩羽＆环忧", hierarchy["140100"]["familyFolder"])
        self.assertTrue(hierarchy["140100"]["publishedModel"])
        self.assertEqual(
            hierarchy["140100"]["componentModelIds"],
            ["140101", "140102"],
        )
        for component in ("140101", "140102"):
            self.assertFalse(hierarchy[component]["publishedModel"])
            self.assertEqual(hierarchy[component]["canonicalModelId"], "140100")
            self.assertEqual(hierarchy[component]["componentModelIds"], [])
            self.assertIn(component, hierarchy[component]["repositoryRelativeDir"])

    def test_hierarchy_keeps_normal_costume_models_independently_published(self) -> None:
        models = [
            {
                "id": "100100",
                "char": {"cn": "环彩羽", "jp": "環 いろは"},
                "costume": {"cn": "环彩羽", "jp": "環 いろは"},
                "voiceGroups": 39,
                "rawVoiceReferences": 39,
            },
            {
                "id": "100150",
                "char": {"cn": "环彩羽", "jp": "環 いろは"},
                "costume": {"cn": "环彩羽_圣诞", "jp": "環 いろは(クリスマス)"},
                "voiceGroups": 43,
                "rawVoiceReferences": 43,
            },
        ]
        hierarchy = voice_import.build_hierarchy_metadata(models)
        self.assertTrue(hierarchy["100100"]["publishedModel"])
        self.assertTrue(hierarchy["100150"]["publishedModel"])
        self.assertNotEqual(
            hierarchy["100100"]["repositoryRelativeDir"],
            hierarchy["100150"]["repositoryRelativeDir"],
        )


if __name__ == "__main__":
    unittest.main()
