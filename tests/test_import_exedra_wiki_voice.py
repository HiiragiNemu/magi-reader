from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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

    def test_japanese_anchor_recovers_unique_row_on_verified_character_page(self) -> None:
        record = self.record(
            page="Lux☆Magica/Voice/zh",
            file_name="legacy_voice_number.ogg",
            text_jp="前 半\n後半",
        )
        selected = voice.select_voice_by_japanese_anchor(
            voice.index_records_by_japanese([record]),
            "cv_100101_other_evo_fee_01",
            ["前半", "後半"],
            voice.VerifiedPageIdentity(
                pages=("Lux☆Magica/Voice/zh",),
                exact_source_count=2,
            ),
        )
        self.assertEqual(selected.record, record)
        self.assertEqual(
            selected.match_method,
            "verified_page_unique_japanese_exact",
        )
        self.assertEqual(
            selected.verified_pages,
            ("Lux☆Magica/Voice/zh",),
        )

    def test_japanese_anchor_rejects_unverified_or_wrong_character_page(self) -> None:
        record = self.record(
            page="Other Character/Voice/zh",
            file_name="legacy_voice_number.ogg",
        )
        index = voice.index_records_by_japanese([record])
        with self.assertRaisesRegex(RuntimeError, "缺少角色页面身份证明"):
            voice.select_voice_by_japanese_anchor(
                index,
                "cv_100101_other_evo_fee_01",
                ["前半", "後半"],
                voice.VerifiedPageIdentity(
                    pages=(),
                    exact_source_count=0,
                ),
            )
        with self.assertRaisesRegex(RuntimeError, "没有整段日文精确候选"):
            voice.select_voice_by_japanese_anchor(
                index,
                "cv_100101_other_evo_fee_01",
                ["前半", "後半"],
                voice.VerifiedPageIdentity(
                    pages=("Lux☆Magica/Voice/zh",),
                    exact_source_count=2,
                ),
            )

    def test_japanese_anchor_rejects_two_file_identities_even_with_same_text(self) -> None:
        first = self.record(
            file_name="legacy_voice_one.ogg",
        )
        second = self.record(
            file_name="legacy_voice_two.ogg",
        )
        with self.assertRaisesRegex(RuntimeError, "候选不唯一"):
            voice.select_voice_by_japanese_anchor(
                voice.index_records_by_japanese([first, second]),
                "cv_100101_other_evo_fee_01",
                ["前半", "後半"],
                voice.VerifiedPageIdentity(
                    pages=("Lux☆Magica/Voice/zh",),
                    exact_source_count=2,
                ),
            )

    def test_japanese_anchor_does_not_accept_partial_or_near_japanese(self) -> None:
        record = self.record(
            file_name="legacy_voice_number.ogg",
            text_jp="前半聞く",
        )
        with self.assertRaisesRegex(RuntimeError, "没有整段日文精确候选"):
            voice.select_voice_by_japanese_anchor(
                voice.index_records_by_japanese([record]),
                "cv_100101_other_evo_fee_01",
                ["前半聴く"],
                voice.VerifiedPageIdentity(
                    pages=("Lux☆Magica/Voice/zh",),
                    exact_source_count=2,
                ),
            )

    def test_japanese_anchor_audit_keeps_structured_remaining_reasons(self) -> None:
        audit = voice.build_japanese_anchor_audit(
            [
                {
                    "groupKey": "cv_missing",
                    "status": "rejected",
                    "reasons": [
                        {
                            "source": "cv_missing_1.json",
                            "groupPageIdentityExactSourceCount": 0,
                            "verifiedWikiPages": [],
                            "verifiedPageExactJapaneseCandidateCount": 0,
                        }
                    ],
                },
                {
                    "groupKey": "cv_recovered",
                    "status": "ready",
                    "japaneseAnchorFallbackCount": 1,
                },
            ],
            [
                {
                    "title": "Lux☆Magica/Voice/zh",
                    "rowCount": 62,
                }
            ],
        )
        self.assertEqual(audit["recoveredGroupCount"], 1)
        self.assertEqual(audit["recoveredSourceCount"], 1)
        self.assertEqual(audit["remainingRejectedGroupCount"], 1)
        self.assertEqual(
            audit["remaining"][0]["reasonCounts"],
            {"no_verified_character_page_identity": 1},
        )
        self.assertEqual(
            audit["wikiSnapshot"]["luxMagicaVoiceZh"]["rowCount"],
            62,
        )

    def test_playable_json_generation_localizes_name_and_comment_cells(self) -> None:
        document = {
            "bookTitle": "voice",
            "sheetList": [
                {
                    "sheetName": "voice",
                    "headerRow": {
                        "cellList": [
                            "ActionType",
                            "Name",
                            "Comment",
                            "Resource",
                        ]
                    },
                    "contentRowList": [
                        {
                            "cellList": [
                                "Talk",
                                "鹿目まどか",
                                "日本語",
                                {"voice": "cv_test"},
                            ]
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary, "source.json")
            destination = Path(temporary, "translated.json")
            source.write_text(
                json.dumps(document, ensure_ascii=False),
                encoding="utf-8",
            )
            voice.common.apply_translated_texts(
                source,
                ["中文"],
                destination,
            )
            translated = json.loads(destination.read_text(encoding="utf-8"))

        before = document["sheetList"][0]["contentRowList"][0]["cellList"]
        after = translated["sheetList"][0]["contentRowList"][0]["cellList"]
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[1], "鹿目圆")
        self.assertEqual(after[2], "中文")
        self.assertEqual(after[3], before[3])
        self.assertEqual(translated["bookTitle"], document["bookTitle"])

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
