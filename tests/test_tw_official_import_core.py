from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.tw_official_import_core import (
    optional_adv_title_catalog,
    resource_key,
    title_catalog,
)


class TwOfficialTitleCatalogTests(unittest.TestCase):
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
