from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.generate_exedra_tw_manifest_titles import build_catalog


class ExedraTwManifestTitleGeneratorTests(unittest.TestCase):
    def _write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def _sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_exact_bridges_no_majority_and_scenario_is_only_supplemental(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifests = root / "Manifests"
            scenarios = root / "Resources" / "Scenarios"
            jp_root = root / "jp"
            cn_root = root / "cn"
            manifests.mkdir(parents=True)
            scenarios.mkdir(parents=True)
            jp_root.mkdir()
            cn_root.mkdir()

            def write_mst(name: str, rows: list[dict[str, object]]) -> None:
                self._write_json(manifests / name, {"payload": {"mstList": rows}})

            write_mst(
                "getAdvMstList.json",
                [
                    {
                        "advMstId": 1,
                        "advResourceName": "1_Main/main_demo_1",
                        "advTitleMstId": 999,
                        "name": "名称不应优先",
                        "subName": "小节一",
                    },
                    {
                        "advMstId": 2,
                        "advResourceName": "1_Main/main_demo_2",
                        "advTitleMstId": 999,
                        "name": "小节二",
                        "subName": "",
                    },
                    {
                        "advMstId": 3,
                        "advResourceName": "1_Main/main_demo_3",
                        "advTitleMstId": 999,
                        "name": "小节三",
                        "subName": "",
                    },
                    {
                        "advMstId": 4,
                        "advResourceName": "7_Namae/namae_demo",
                        "advTitleMstId": 999,
                        "name": "名字演出",
                        "subName": "",
                    },
                ],
            )
            write_mst(
                "getFieldStageMstList.json",
                [
                    {
                        "fieldStageMstId": 100,
                        "fieldSeriesMstId": 10,
                        "name": "章节甲",
                        "subTitle": "第一章",
                    },
                    {
                        "fieldStageMstId": 200,
                        "fieldSeriesMstId": 20,
                        "name": "章节乙",
                        "subTitle": "第二章",
                    },
                ],
            )
            write_mst(
                "getFieldPointMstList.json",
                [
                    {
                        "fieldPointMstId": 11,
                        "fieldStratumMstId": 1009,
                        "needViewAdvMstIds": "1",
                        "pointType": 1,
                        "pointValue2": 0,
                    },
                    {
                        "fieldPointMstId": 12,
                        "fieldStratumMstId": 1008,
                        "needViewAdvMstIds": "",
                        "pointType": 1,
                        "pointValue2": 0,
                    },
                    {
                        "fieldPointMstId": 21,
                        "fieldStratumMstId": 2001,
                        "needViewAdvMstIds": "",
                        "pointType": 2,
                        "pointValue2": 3,
                    },
                ],
            )
            write_mst(
                "getCollectionConditionMstList.json",
                [
                    {
                        "collectionConditionMstId": 1201,
                        "objectType": 6,
                        "objectId": 2,
                        "fieldPointMstId": 12,
                        "fieldStratumMstId": 1008,
                        "fieldStageMstId": 100,
                        "fieldSeriesMstId": 10,
                    }
                ],
            )

            files = []
            for name in (
                "getAdvMstList.json",
                "getFieldStageMstList.json",
                "getFieldPointMstList.json",
                "getCollectionConditionMstList.json",
            ):
                rows = json.loads((manifests / name).read_text(encoding="utf-8"))[
                    "payload"
                ]["mstList"]
                files.append(
                    {
                        "file": name,
                        "entries": len(rows),
                        "sha256": self._sha256(manifests / name),
                        "endpoint": "/fixture/" + name,
                        "revision": "fixture",
                    }
                )
            self._write_json(
                manifests / "tw_gallery_export_report.json",
                {
                    "schemaVersion": 1,
                    "complete": True,
                    "masterRevision": "fixture-master",
                    "files": files,
                },
            )

            source_paths = [
                "1_Main/main_demo_1/main_demo_1.json",
                "1_Main/main_demo_2/main_demo_2.json",
                "1_Main/main_demo_3/main_demo_3.json",
                "7_Namae/namae_demo/namae_demo.json",
                "8_Dungeon/no_adv/no_adv.json",
            ]
            scenario_entries = []
            for source_path in source_paths:
                scenario_path = scenarios.joinpath(*Path(source_path).parts)
                self._write_json(
                    scenario_path,
                    {
                        "bookTitle": "场景补充 " + scenario_path.stem,
                        "sheetList": [],
                    },
                )
                scenario_entries.append(
                    {
                        "fullPath": "Scenarios/" + source_path,
                        "decodedSha256": self._sha256(scenario_path),
                        "decodedSize": scenario_path.stat().st_size,
                        "revision": "scenario-fixture",
                    }
                )
            self._write_json(
                manifests / "tw" / "resolved_catalog_v3.json",
                {
                    "schemaVersion": 1,
                    "language": "zh_TW",
                    "resolvedManifestSha256": "a" * 64,
                    "generatedAt": 1,
                    "entries": scenario_entries,
                },
            )

            groups = [
                {
                    "id": "exedra:1_Main:main_demo",
                    "category": "1_Main",
                    "groupKey": "main_demo",
                    "sources": source_paths[:3],
                },
                {
                    "id": "exedra:7_Namae:namae_demo",
                    "category": "7_Namae",
                    "groupKey": "namae_demo",
                    "sources": [source_paths[3]],
                },
                {
                    "id": "exedra:8_Dungeon:no_adv",
                    "category": "8_Dungeon",
                    "groupKey": "no_adv",
                    "sources": [source_paths[4]],
                },
            ]
            sources = [
                {
                    "sourcePath": source_path,
                    "groupId": next(
                        group["id"]
                        for group in groups
                        if source_path in group["sources"]
                    ),
                }
                for source_path in source_paths
            ]
            exedra_manifest = root / "exedra_manifest.json"
            self._write_json(
                exedra_manifest,
                {
                    "schemaVersion": 1,
                    "categoryOrder": [
                        "1_Main",
                        "2_Sub",
                        "3_Character",
                        "4_Portrait",
                        "6_Reaction",
                        "7_Namae",
                        "8_Dungeon",
                        "10_Battle",
                    ],
                    "groups": groups,
                    "sources": sources,
                },
            )

            catalog = build_catalog(
                manifest_root=manifests,
                scenario_root=scenarios,
                exedra_manifest_path=exedra_manifest,
                exedra_jp_root=jp_root,
                exedra_cn_root=cn_root,
                convert=lambda value: value,
            )

            multi = catalog["groups"]["exedra:1_Main:main_demo"]
            self.assertEqual(multi["fieldStageMstIds"], [100, 200])
            self.assertEqual(multi["chapterTitle"], "")
            self.assertEqual(multi["chapterStatus"], "ambiguous")
            self.assertIn(
                "multiple_field_stages_no_single_chapter", multi["unresolved"]
            )
            self.assertEqual(multi["sectionTitles"], ["小节一", "小节二", "小节三"])
            first = catalog["resources"]["1_main/main_demo_1"]
            self.assertEqual(first["sectionTitle"], "小节一")
            self.assertEqual(first["sectionTitleSource"], "getAdvMstList.subName")

            no_adv = catalog["resources"]["8_dungeon/no_adv"]
            self.assertEqual(no_adv["sectionTitle"], "no_adv")
            self.assertEqual(no_adv["sectionStatus"], "unresolved")
            self.assertEqual(no_adv["sectionTitleSource"], "fallback_resource_id")
            self.assertEqual(no_adv["supplementalStoryTitle"], "场景补充 no_adv")
            self.assertEqual(
                no_adv["supplementalStoryTitleSource"],
                "tw_scenario_metadata.bookTitle",
            )
            no_adv_group = catalog["groups"]["exedra:8_Dungeon:no_adv"]
            self.assertEqual(no_adv_group["sectionTitles"], ["no_adv"])
            self.assertEqual(no_adv_group["storyTitles"], ["场景补充 no_adv"])

            namae = catalog["groups"]["exedra:7_Namae:namae_demo"]
            self.assertEqual(namae["sectionTitles"], ["名字演出"])
            self.assertEqual(namae["displayTitleSource"], "getAdvMstList")


if __name__ == "__main__":
    unittest.main()
