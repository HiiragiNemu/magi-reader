from __future__ import annotations

import json
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
            self.assertTrue(hierarchy[component]["publishedModel"])
            self.assertEqual(hierarchy[component]["canonicalModelId"], "140100")
            self.assertEqual(hierarchy[component]["componentModelIds"], [])
            self.assertIn(component, hierarchy[component]["repositoryRelativeDir"])
            self.assertIn("角色分体", hierarchy[component]["modelFolder"])

    def test_hierarchy_hides_only_fully_hashed_exact_payload_aliases(self) -> None:
        hashes = {
            "sourceJsonSha256": "a" * 64,
            "cnJsonSha256": "b" * 64,
            "txtSha256": "c" * 64,
        }
        models = [
            {
                "id": "140100",
                "char": {"cn": "环彩羽＆环忧"},
                "voiceGroups": 39,
                "rawVoiceReferences": 78,
                **hashes,
            },
            {
                "id": "140101",
                "char": {"cn": "环彩羽"},
                "voiceGroups": 39,
                "rawVoiceReferences": 39,
                **hashes,
            },
            {
                "id": "140102",
                "char": {"cn": "环忧"},
                "voiceGroups": 39,
                "rawVoiceReferences": 39,
                **{**hashes, "txtSha256": "d" * 64},
            },
        ]
        hierarchy = voice_import.build_hierarchy_metadata(models)
        self.assertFalse(hierarchy["140101"]["publishedModel"])
        self.assertTrue(hierarchy["140102"]["publishedModel"])

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

    def test_real_combo_components_are_losslessly_public(self) -> None:
        manifest = json.loads(
            (
                voice_import.SOURCE_ROOT / "general_voice_manifest.json"
            ).read_text(encoding="utf-8")
        )
        models = manifest["models"]
        model_by_id = {model["id"]: model for model in models}
        components = [
            model
            for model in models
            if model["canonicalModelId"] != model["id"]
        ]
        self.assertEqual(len(models), 410)
        self.assertEqual(len(components), 38)
        self.assertTrue(all(model["publishedModel"] for model in models))

        source_ids = {
            path.stem
            for path in voice_import.SOURCE_ROOT.rglob("*.json")
            if voice_import.MODEL_RE.fullmatch(path.stem)
        }
        cn_json_ids = {
            path.name.removesuffix("_cn.json")
            for path in voice_import.CN_ROOT.rglob("*_cn.json")
            if voice_import.MODEL_RE.fullmatch(
                path.name.removesuffix("_cn.json")
            )
        }
        cn_txt_ids = {
            path.name.removesuffix("_cn.txt")
            for path in voice_import.CN_ROOT.rglob("*_cn.txt")
            if voice_import.MODEL_RE.fullmatch(
                path.name.removesuffix("_cn.txt")
            )
        }
        expected_ids = set(model_by_id)
        self.assertEqual(source_ids, expected_ids)
        self.assertEqual(cn_json_ids, expected_ids)
        self.assertEqual(cn_txt_ids, expected_ids)

        def cue_texts(model: dict) -> dict[str, set[str]]:
            path = voice_import.CN_ROOT.joinpath(
                *Path(model["cnJsonRelativePath"]).parts
            )
            document = json.loads(path.read_text(encoding="utf-8"))
            result: dict[str, set[str]] = {}
            for turns in document["story"].values():
                for turn in turns:
                    chara = turn.get("chara") if isinstance(turn, dict) else None
                    if not isinstance(chara, list):
                        continue
                    for event in chara:
                        if not isinstance(event, dict):
                            continue
                        voice = event.get("voice")
                        if isinstance(voice, str) and voice:
                            result.setdefault(voice, set()).add(
                                str(event.get("textHome") or "")
                            )
            return result

        unique_component_cues: set[tuple[str, str]] = set()
        translated_component_cues: set[tuple[str, str]] = set()
        for component in components:
            component_cues = cue_texts(component)
            canonical_cues = cue_texts(
                model_by_id[component["canonicalModelId"]]
            )
            for voice in set(component_cues) - set(canonical_cues):
                identity = (component["id"], voice)
                unique_component_cues.add(identity)
                if any(text.strip() for text in component_cues[voice]):
                    translated_component_cues.add(identity)

        self.assertEqual(len(unique_component_cues), 684)
        self.assertEqual(len(translated_component_cues), 108)

        story_index = json.loads(
            (
                ROOT
                / "website"
                / "public"
                / "story_index.json"
            ).read_text(encoding="utf-8")
        )
        voice_stories = {
            story["model_id"]: story
            for story in story_index
            if story.get("category") == "general_voice"
        }
        self.assertEqual(set(voice_stories), expected_ids)
        for component in components:
            model_id = component["id"]
            story = voice_stories[model_id]
            self.assertEqual(story["id"], f"voice_{model_id}")
            self.assertEqual(story["source_count"], 1)
            self.assertEqual(
                story["json_paths_cn"],
                [f"/data/general_voice/{model_id}/{model_id}_cn.json"],
            )
            self.assertNotIn("legacy_ids", story)
            canonical_story = voice_stories[component["canonicalModelId"]]
            self.assertNotIn(f"voice_{model_id}", canonical_story.get("legacy_ids", []))
            for web_path in (story["path_cn"], *story["json_paths_cn"]):
                self.assertTrue(
                    (ROOT / "website" / "public" / web_path.lstrip("/")).is_file(),
                    web_path,
                )


if __name__ == "__main__":
    unittest.main()
