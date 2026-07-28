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


if __name__ == "__main__":
    unittest.main()
