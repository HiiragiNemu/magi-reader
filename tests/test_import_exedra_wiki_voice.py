from __future__ import annotations

import unittest

from tools import import_exedra_wiki_voice as voice


class ExedraWikiVoiceImportTests(unittest.TestCase):
    def record(
        self,
        *,
        page: str = "Lux☆Magica/Voice/zh",
        file_name: str = "cv_100101_other_evo_fee_01.ogg",
        text_jp: str = "前半後半",
        text_cn: str = "前半，后半。",
    ) -> voice.WikiVoice:
        return voice.WikiVoice(
            page_title=page,
            page_url=voice.page_url(page),
            page_sha256="a" * 64,
            file_name=file_name,
            text_jp=text_jp,
            text_cn=text_cn,
        )

    def test_parse_voice_page_handles_multiline_fields_and_nested_template(self) -> None:
        raw = """{{PAGELANGUAGE:zh}}
{{Character Voice Row
|name_en = Voice 1
|file_name = cv_100101_other_evo_fee_01.ogg
|text_en = 呐，丘比，
这是中文。
|text_jp = ねぇ、キュゥべえ
これは日本語。
|unused = {{nested|value}}
}}
"""
        parsed = voice.parse_voice_page("Lux☆Magica/Voice/zh", raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].file_name, "cv_100101_other_evo_fee_01.ogg")
        self.assertEqual(parsed[0].text_cn, "呐，丘比，\n这是中文。")
        self.assertEqual(parsed[0].text_jp, "ねぇ、キュゥべえ\nこれは日本語。")

    def test_select_requires_exact_filename_and_normalized_joined_japanese(self) -> None:
        record = self.record(text_jp="前 半\n後半")
        index = voice.index_records([record])
        selected = voice.select_voice(
            index,
            "cv_100101_other_evo_fee_01",
            ["前半", "後半"],
        )
        self.assertEqual(selected.record, record)
        with self.assertRaises(FileNotFoundError):
            voice.select_voice(index, "CV_100101_OTHER_EVO_FEE_01", ["前半", "後半"])
        with self.assertRaises(RuntimeError):
            voice.select_voice(
                index,
                "cv_100101_other_evo_fee_01",
                ["不同"],
            )

    def test_equivalent_duplicates_are_safe_but_chinese_conflicts_reject(self) -> None:
        first = self.record(page="Lux☆Magica/Voice/zh")
        equivalent = self.record(page="Madoka Kaname/Voice/zh")
        selected = voice.select_voice(
            voice.index_records([first, equivalent]),
            "cv_100101_other_evo_fee_01",
            ["前半", "後半"],
        )
        self.assertEqual(
            selected.equivalent_pages,
            ("Lux☆Magica/Voice/zh", "Madoka Kaname/Voice/zh"),
        )
        conflict = self.record(
            page="Other/Voice/zh",
            text_cn="含义不同。",
        )
        with self.assertRaises(RuntimeError):
            voice.select_voice(
                voice.index_records([first, conflict]),
                "cv_100101_other_evo_fee_01",
                ["前半", "後半"],
            )

    def test_segmentation_uses_punctuation_and_preserves_all_chinese(self) -> None:
        source = "第一句话，第二句话！最后一句。"
        segments = voice.split_chinese_by_japanese(
            source,
            ["第一段较长", "第二段", "第三段"],
        )
        self.assertEqual(len(segments), 3)
        self.assertTrue(all(segment.strip() for segment in segments))
        self.assertEqual(
            voice.chinese_signature("".join(segments)),
            voice.chinese_signature(source),
        )
        self.assertTrue(segments[0][-1] in voice.STRONG_PUNCTUATION | voice.WEAK_PUNCTUATION)

    def test_segmentation_rejects_too_short_chinese(self) -> None:
        with self.assertRaises(RuntimeError):
            voice.split_chinese_by_japanese("中", ["一", "二"])

    def test_wiki_api_path_and_voice_suffix_are_fixed(self) -> None:
        self.assertEqual(voice.WIKI_API, "https://exedra.wiki/w/api.php")
        self.assertEqual(voice.VOICE_TITLE_SUFFIX, "/Voice/zh")

    def test_declared_reaction_alias_is_an_exact_manifest_duplicate(self) -> None:
        manifest = voice.common.load_json(voice.MANIFEST)
        groups = {
            str(item.get("groupKey")): item
            for item in manifest["groups"]
            if item.get("category") == "6_Reaction"
        }
        mapping = voice.validate_strict_reaction_group_alias(
            groups["cv_100803"],
            groups["cv_100805"],
        )
        self.assertEqual(len(mapping), 14)
        self.assertEqual(
            mapping["cv_100803_other_evo_fee_01"],
            "cv_100805_other_evo_fee_01",
        )
        self.assertEqual(
            mapping["cv_100803_other_story_07"],
            "cv_100805_other_story_07",
        )


if __name__ == "__main__":
    unittest.main()
