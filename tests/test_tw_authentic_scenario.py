from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.import_exedra_official_tw import (
    Line,
    Section,
    build_report,
    render_cn,
)
from tools.tw_authentic_scenario import (
    load_name_translation_map,
    localize_events,
    materialize_tw_json,
)


class AuthenticTwScenarioTests(unittest.TestCase):
    def fixture(self) -> dict[str, object]:
        return {
            "origin": 0,
            "bookTitle": "魔法少女ストーリー_アリナ",
            "sheetList": [{
                "sheetName": "script",
                "headerRow": {
                    "rowNumber": 1,
                    "cellList": [
                        "ActionType", "Name", "Comment", "AssetID", "PositionID"
                    ],
                },
                "contentRowList": [
                    {
                        "rowNumber": 2,
                        "cellList": [
                            "Talk",
                            "阿莉娜‧格雷",
                            "阿莉娜其實一直都有自己的主題。",
                            "100831",
                            "Center",
                        ],
                    },
                    {
                        "rowNumber": 3,
                        "cellList": [
                            "Narration",
                            "",
                            "跳下去之後，才察覺到。",
                            "",
                            "",
                        ],
                    },
                ],
            }],
        }

    def test_authentic_tw_schema_and_speakers_are_preserved_then_simplified(self) -> None:
        replacements = str.maketrans({
            "實": "实",
            "題": "题",
            "後": "后",
            "覺": "觉",
        })
        convert = lambda value: value.translate(replacements)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "tw.json"
            output = root / "cn.json"
            source.write_text(
                json.dumps(self.fixture(), ensure_ascii=False),
                encoding="utf-8",
            )
            report = materialize_tw_json(source, output, convert)
            result = json.loads(output.read_text(encoding="utf-8"))
            row = result["sheetList"][0]["contentRowList"][0]["cellList"]
            self.assertEqual(row[1], "阿莉娜·格雷")
            self.assertEqual(row[2], "阿莉娜其实一直都有自己的主题。")
            self.assertEqual(row[3:], ["100831", "Center"])
            self.assertEqual(report["eventCount"], 2)

    def test_cn_txt_uses_tw_name_and_dictionary_for_jp_fallback(self) -> None:
        mapping = load_name_translation_map(
            Path("website/app/config/dictionary.ts")
        )
        tw_rows = [
            {
                "speaker": "阿莉娜‧格雷",
                "text": "自己的主題",
                "action": "Talk",
                "sheet_index": 0,
                "row_number": 2,
            },
            {
                "speaker": "",
                "text": "早乙女和子的台詞",
                "action": "Talk",
                "sheet_index": 0,
                "row_number": 3,
            },
        ]
        jp_lines = (
            Line("アリナ・グレイ", "x", "dialogue"),
            Line("早乙女和子", "y", "dialogue"),
        )
        convert = lambda value: value.replace("題", "题").replace("詞", "词")
        events, stats = localize_events(tw_rows, jp_lines, convert, mapping)
        self.assertEqual(events[0].speaker, "阿莉娜·格雷")
        self.assertEqual(events[1].speaker, "早乙女和子")
        self.assertEqual(stats["officialTwSpeakerEvents"], 1)
        self.assertEqual(stats["dictionaryFallbackSpeakerEvents"], 1)
        text = render_cn(
            (Section(1, "character_arina_3.json", jp_lines),),
            [events],
        )
        self.assertIn("阿莉娜·格雷：自己的主题", text)
        self.assertIn("早乙女和子：早乙女和子的台词", text)

    def test_report_accepts_localized_speaker_sequences_but_binds_each_side(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jp = root / "demo_jp.txt"
            cn = root / "demo_cn.txt"
            jp.write_text(
                "--- [Section 1] (Source: character_arina_3.json) ---\n"
                "アリナ・グレイ：日本語\n",
                encoding="utf-8",
            )
            cn.write_text(
                "--- [Section 1] (Source: character_arina_3.json) ---\n"
                "阿莉娜·格雷：简体中文\n",
                encoding="utf-8",
            )
            report = build_report(
                "3_Character",
                "character_arina",
                jp,
                cn,
                "fixture",
                [],
            )
            self.assertTrue(report["validation"]["speakerSequencesMayDiffer"])
            hashes = report["sections"][0]["speakerSequenceSha256"]
            self.assertEqual(hashes["jp"], hashes["cn"])
            self.assertTrue(
                report["validation"]["speakerSequencesMayDiffer"]
            )


if __name__ == "__main__":
    unittest.main()
