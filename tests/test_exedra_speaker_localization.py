from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.tw_authentic_scenario import (
    load_name_translation_map,
    materialize_human_json,
    render_human_cn,
    translate_speaker,
    validate_human_json,
)
from tools.import_exedra_official_tw import Line, Section


class ExedraSpeakerLocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mapping = load_name_translation_map(
            Path("website/app/config/dictionary.ts")
        )

    def test_dictionary_canonicalizes_japanese_and_tw_punctuation(self) -> None:
        self.assertEqual(
            translate_speaker("アリナ・グレイ", self.mapping),
            "阿莉娜·格雷",
        )
        self.assertEqual(
            translate_speaker("阿莉娜‧格雷", self.mapping),
            "阿莉娜·格雷",
        )
        self.assertEqual(
            translate_speaker("水波レナ＆秋野かえで", self.mapping),
            "水波玲奈＆秋野枫",
        )

    def test_human_json_localizes_name_and_comment_only(self) -> None:
        fixture = {
            "bookTitle": "fixture",
            "sheetList": [{
                "headerRow": {
                    "cellList": [
                        "ActionType", "Name", "Comment", "AssetID", "PositionID"
                    ]
                },
                "contentRowList": [{
                    "rowNumber": 2,
                    "cellList": [
                        "Talk", "水波レナ", "日本語", "100201", "Center"
                    ],
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jp = root / "jp.json"
            cn = root / "cn.json"
            jp.write_text(
                json.dumps(fixture, ensure_ascii=False),
                encoding="utf-8",
            )
            result = materialize_human_json(
                jp,
                ["简体正文"],
                cn,
                self.mapping,
            )
            value = json.loads(cn.read_text(encoding="utf-8"))
            row = value["sheetList"][0]["contentRowList"][0]["cellList"]
            self.assertEqual(row[1], "水波玲奈")
            self.assertEqual(row[2], "简体正文")
            self.assertEqual(row[3:], ["100201", "Center"])
            self.assertEqual(result["eventCount"], 1)
            proof = validate_human_json(
                jp,
                cn,
                ["简体正文"],
                self.mapping,
            )
            self.assertTrue(proof["canonicalNameFields"])

    def test_human_txt_uses_dictionary_speakers(self) -> None:
        sections = (
            Section(
                1,
                "fixture.json",
                (
                    Line("リズ・ホークウッド", "x", "dialogue"),
                    Line("Narration", "y", "narration"),
                ),
            ),
        )
        rendered = render_human_cn(
            sections,
            [["正文", "旁白正文"]],
            self.mapping,
        )
        self.assertIn("莉兹·霍克伍德：正文", rendered)
        self.assertIn("旁白：旁白正文", rendered)


if __name__ == "__main__":
    unittest.main()
