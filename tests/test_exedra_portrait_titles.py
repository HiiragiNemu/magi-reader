from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import generate_story_index as generate


class ExedraPortraitTitleCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog_path = generate.DEFAULT_EXEDRA_PORTRAIT_TITLE_CATALOG
        self.catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))

    def test_catalog_exactly_covers_the_portrait_manifest(self) -> None:
        titles = generate.load_exedra_portrait_titles(self.catalog_path)
        manifest = json.loads(
            (
                generate.DEFAULT_EXEDRA_JP_DIR
                / generate.EXEDRA_MANIFEST_NAME
            ).read_text(encoding="utf-8")
        )
        expected = {
            group["groupKey"]
            for group in manifest["groups"]
            if group["category"] == "4_Portrait"
        }

        self.assertEqual(len(titles), generate.EXEDRA_PORTRAIT_EXPECTED_GROUPS)
        self.assertEqual(set(titles), expected)
        self.assertTrue(all(not title.startswith("portrait_") for title in titles.values()))

    def test_catalog_never_claims_an_official_chinese_title(self) -> None:
        entries = self.catalog["entries"]
        self.assertEqual(len(entries), 54)
        self.assertTrue(all(entry["officialChineseTitle"] is False for entry in entries))
        self.assertEqual(
            sum(entry["sourceLevel"].startswith("readable_fallback_") for entry in entries),
            6,
        )
        self.assertTrue(
            all(entry["officialJapaneseTitles"] for entry in entries)
        )

    def test_loader_rejects_an_official_chinese_misclassification(self) -> None:
        catalog = json.loads(json.dumps(self.catalog))
        catalog["entries"][0]["officialChineseTitle"] = True
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "portrait-titles.json"
            path.write_text(
                json.dumps(catalog, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                generate.PipelineError,
                "不得误称官方标题",
            ):
                generate.load_exedra_portrait_titles(path)

    def test_stable_group_keys_remain_separate_from_display_titles(self) -> None:
        titles = generate.load_exedra_portrait_titles(self.catalog_path)
        self.assertEqual(titles["portrait_baraen1"], "人生得一挚友")
        self.assertEqual(
            titles["portrait_scene0_homura"],
            "晓美焰 · Scene0 肖像剧情",
        )
        self.assertEqual(
            generate.safe_exedra_story_id(
                "exedra_portrait",
                "4_Portrait/portrait_baraen1/portrait_baraen1_jp.txt",
                "portrait_baraen1",
            ),
            "exedra_portrait_portrait_baraen1_5c2ab7efbb",
        )


if __name__ == "__main__":
    unittest.main()
