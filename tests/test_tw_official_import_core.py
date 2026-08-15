from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.apply_tw_official_metadata import apply_metadata
from tools.tw_official_import_core import (
    official_scenario_title_card,
    optional_adv_title_catalog,
    resource_key,
    title_catalog,
)


class TwOfficialTitleCatalogTests(unittest.TestCase):
    def test_official_scenario_title_card_is_strict_and_preserves_official_text(self) -> None:
        self.assertEqual(
            official_scenario_title_card(
                "<size=150%>\u8056\u9b54\u6cd5\u5b78\u5712\u7684\u8056\u8a95\u7bc0\n\uff5e\u767d\u8272\u8056\u8a95\u8001\u4eba\u7bc7\uff5e</size>"
            ),
            "\u8056\u9b54\u6cd5\u5b78\u5712\u7684\u8056\u8a95\u7bc0 \uff5e\u767d\u8272\u8056\u8a95\u8001\u4eba\u7bc7\uff5e",
        )
        self.assertEqual(
            official_scenario_title_card(
                "<size=150%><color=black>CASE 03\n\u300c\u7bb1\u5ead\u7684\u5b87\u5b99\u8ad6 \u5f8c\u7bc7\u300d</color></size>"
            ),
            "CASE 03 \u300c\u7bb1\u5ead\u7684\u5b87\u5b99\u8ad6 \u5f8c\u7bc7\u300d",
        )
        self.assertEqual(
            official_scenario_title_card(
                "<size=150%><color=black>CASE 03\n\u300c\u7bb1\u5ead\u7684\u5b87\u5b99\u8ad6 \u5f8c\u7bc7\u300d\n\n\u5b8c</color></size>"
            ),
            "",
        )
        self.assertEqual(official_scenario_title_card("<size=60px>\u55b5\uff5e</size>"), "")
        self.assertEqual(
            official_scenario_title_card("<size=150%>\u672a\u77e5<title>\u5167\u5bb9</title></size>"),
            "",
        )
        self.assertEqual(
            official_scenario_title_card(
                "<size=150%><color=red>\u975e\u6cd5\u984f\u8272</color></size>"
            ),
            "",
        )

    def test_resource_key_collapses_scenario_inventory_filename(self) -> None:
        self.assertEqual(
            resource_key("1_Main/main_baraen1_1/main_baraen1_1.json"),
            "1_main/main_baraen1_1",
        )
        self.assertEqual(
            resource_key("1_Main/main_baraen1_1"),
            "1_main/main_baraen1_1",
        )

    def test_resource_key_keeps_non_repeated_nested_filename(self) -> None:
        self.assertEqual(
            resource_key("1_Main/main_baraen1_1/alternate.json"),
            "1_main/main_baraen1_1/alternate",
        )

    def test_scenario_title_card_only_replaces_technical_title(self) -> None:
        metadata = {
            "2_Sub/sub_demo": {
                "officialStoryTitles": ["CASE 01 \u300c\u5b98\u65b9\u6a19\u984c \u524d\u7bc7\u300d"],
                "officialStoryTitleSource": "scenario_title_card",
            }
        }
        technical = [{
            "source_identity": "2_Sub/sub_demo",
            "category": "exedra_sub",
            "title": "sub_demo",
            "folder": "sub_demo",
        }]
        self.assertEqual(apply_metadata(technical, metadata), 1)
        self.assertEqual(technical[0]["title"], "CASE 01 \u300c\u5b98\u65b9\u6a19\u984c \u524d\u7bc7\u300d")
        self.assertEqual(
            technical[0]["official_tw_story_title_source"],
            "scenario_title_card",
        )

        human = [{
            "source_identity": "2_Sub/sub_demo",
            "category": "exedra_sub",
            "title": "\u5df2\u6709\u4eba\u5de5\u6a19\u984c",
            "folder": "sub_demo",
        }]
        self.assertEqual(apply_metadata(human, metadata), 1)
        self.assertEqual(human[0]["title"], "\u5df2\u6709\u4eba\u5de5\u6a19\u984c")

    def test_title_catalog_maps_official_stage_and_adv_titles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def write(name: str, rows: list[dict[str, object]]) -> None:
                (root / name).write_text(
                    json.dumps({"payload": {"mstList": rows}}, ensure_ascii=False),
                    encoding="utf-8",
                )

            write(
                "getAdvMstList.json",
                [{
                    "advMstId": 16000001,
                    "advResourceName": "1_Main/main_baraen1_1",
                    "advTitleMstId": 1,
                    "name": "Episode1",
                    "subName": "Episode1",
                }],
            )
            write(
                "getFieldStageMstList.json",
                [{
                    "fieldStageMstId": 600001,
                    "fieldSeriesMstId": 60000,
                    "difficulty": 1,
                    "name": "蔷薇园的魔女 前篇 鹿目圆的记忆",
                    "subTitle": "第一章",
                }],
            )
            write(
                "getCollectionConditionMstList.json",
                [{
                    "objectType": 6,
                    "objectId": 16000001,
                    "fieldStageMstId": 600001,
                }],
            )

            titles = title_catalog(root)
            title = titles[resource_key(
                "1_Main/main_baraen1_1/main_baraen1_1.json"
            )]
            self.assertEqual(title["sectionTitle"], "Episode1")
            self.assertEqual(
                title["chapterTitle"],
                "第一章 · 蔷薇园的魔女 前篇 鹿目圆的记忆",
            )

    def test_optional_gallery_titles_are_exact_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(optional_adv_title_catalog(root), {})
            (root / "getAdvTitleMstList.json").write_text(
                json.dumps({"payload": {"mstList": [{
                    "advTitleMstId": 94,
                    "title": "调整师事件簿3",
                }]}}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertEqual(
                optional_adv_title_catalog(root),
                {94: "调整师事件簿3"},
            )


if __name__ == "__main__":
    unittest.main()
