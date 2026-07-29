from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import import_exedra_human_text as human_import  # noqa: E402


class WikiParserTests(unittest.TestCase):
    def test_wikitext_parser_preserves_episode_and_narration_blocks(self) -> None:
        parsed = human_import.parse_wiki_wikitext(
            "\n".join(
                [
                    "=== Episode 0 ===",
                    "unlock text",
                    "{{Color Dialogue|环彩羽|Iroha Tamaki}}: 第一行",
                    "",
                    "=== Episode 1 ===",
                    "'''旁白第一行'''",
                    "'''旁白第二行'''",
                    "",
                    "{{Audio|voice.ogg}} {{Color Dialogue|丘比|Kyubey}}: 回答",
                ]
            )
        )
        self.assertEqual(parsed[0], ("第一行",))
        self.assertEqual(parsed[1], ("旁白第一行\\n旁白第二行", "回答"))

    def test_wikitext_parser_ignores_images_audio_and_unlock_copy(self) -> None:
        parsed = human_import.parse_wiki_wikitext(
            "\n".join(
                [
                    "=== Episode 3 ===",
                    "心之器 Lvl. 10 解锁",
                    "{{BackgroundImage|bg.png}}",
                    "{{BGMAudio|bgm.ogg}}",
                    "{{Color Dialogue|角色}}: 正文",
                ]
            )
        )
        self.assertEqual(parsed, {3: ("正文",)})

    def test_wikitext_parser_accepts_chinese_episode_headings(self) -> None:
        parsed = human_import.parse_wiki_wikitext(
            "\n".join(
                [
                    "=== 第0话 ===",
                    "{{Color Dialogue|三栗菖蒲}}: 杜鹃花之家",
                    "=== 第 1 話 ===",
                    "'''旁白正文'''",
                ]
            )
        )
        self.assertEqual(parsed[0], ("杜鹃花之家",))
        self.assertEqual(parsed[1], ("旁白正文",))

    def test_wikitext_parser_accepts_combined_speakers(self) -> None:
        parsed = human_import.parse_wiki_wikitext(
            "\n".join(
                [
                    "=== Episode 3 ===",
                    "{{Color Dialogue|明日香|Asuka Tatsuki}}＆"
                    "{{Color Dialogue|枫|Kaede Akino}}: ――！？",
                ]
            )
        )
        self.assertEqual(parsed[3], ("――！？",))

    def test_wikitext_parser_accepts_multiple_audio_templates(self) -> None:
        parsed = human_import.parse_wiki_wikitext(
            "\n".join(
                [
                    "=== Episode 1 ===",
                    "{{Audio|voice_a.ogg}} {{Audio|voice_b.ogg}} "
                    "{{Color Dialogue|鹿目询子}}: 两段语音同一行",
                ]
            )
        )
        self.assertEqual(parsed[1], ("两段语音同一行",))

    def test_wikitext_parser_preserves_audio_prefixed_bold_narration(
        self,
    ) -> None:
        parsed = human_import.parse_wiki_wikitext(
            "\n".join(
                [
                    "=== Episode 4 ===",
                    "{{Audio|voice_a.ogg}} '''第一段'''",
                    "'''第二段'''",
                    "",
                ]
            )
        )
        self.assertEqual(parsed[4], ("第一段\\n第二段",))


class AssParserTests(unittest.TestCase):
    def test_ass_parser_extracts_dialogue_and_skips_empty_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.ass"
            path.write_text(
                "\n".join(
                    [
                        "[Events]",
                        "Format: Layer, Start, End, Style, Actor, MarginL, MarginR, MarginV, Effect, Text",
                        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,第一行\\N第二行",
                        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\an8}",
                        "Comment: 0,0:00:02.00,0:00:03.00,Default,,0,0,0,,忽略",
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                human_import.parse_ass(path),
                ("第一行\\n第二行",),
            )

    def test_ass_source_metadata_reads_media_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.ass"
            path.write_text(
                "\n".join(
                    [
                        "[Script Info]",
                        "Title: MagiaTimeline Generated",
                        "Original Script: MagiaTimeline",
                        "[Aegisub Project Garbage]",
                        "Audio File: ../video/sample.mp4",
                        "Video File: ../video/sample.mp4",
                        "[Events]",
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                human_import.parse_ass_source_metadata(path),
                {
                    "Title": "MagiaTimeline Generated",
                    "Original Script": "MagiaTimeline",
                    "Audio File": "../video/sample.mp4",
                    "Video File": "../video/sample.mp4",
                },
            )


class MappingPolicyTests(unittest.TestCase):
    def test_all_character_groups_have_unique_explicit_ass_mappings(self) -> None:
        self.assertEqual(
            set(human_import.ASS_CHARACTER_BASES),
            set(human_import.CHARACTER_WIKI_SLUGS),
        )
        self.assertEqual(len(human_import.ASS_CHARACTER_BASES), 61)
        self.assertEqual(
            len(set(human_import.ASS_CHARACTER_BASES.values())),
            61,
        )

    def test_wiki_api_uses_real_mediawiki_path(self) -> None:
        self.assertEqual(
            human_import.WIKI_API,
            "https://exedra.wiki/w/api.php",
        )

    def test_non_character_wiki_categories_are_explicit(self) -> None:
        self.assertTrue(
            human_import._wiki_title_matches_category(
                "Rose/Main Story/Chinese",
                "1_Main",
            )
        )
        self.assertTrue(
            human_import._wiki_title_matches_category(
                "Event/Story/Chinese",
                "2_Sub",
            )
        )
        self.assertTrue(
            human_import._wiki_title_matches_category(
                "Event/Bonus Story/Chinese",
                "4_Portrait",
            )
        )
        self.assertFalse(
            human_import._wiki_title_matches_category(
                "Character/Story/Chinese",
                "4_Portrait",
            )
        )

    def test_main_like_ass_families_are_audit_only(self) -> None:
        self.assertFalse(
            any(key.startswith("main_") for key in human_import.ASS_STORY_FILES)
        )
        patterns = {
            family: human_import.re.compile(pattern, human_import.re.I)
            for family, pattern in human_import.MAIN_ASS_FAMILY_PATTERNS.items()
        }
        self.assertTrue(patterns["Opening"].match("Opening0.ass"))
        self.assertTrue(patterns["Tutorial"].match("Tutorial8.ass"))
        self.assertTrue(patterns["Main0"].match("Main0-5.ass"))
        self.assertFalse(patterns["TartMain"].match("TartMain1_Bonus.ass"))

    def test_exact_page_match_can_split_one_episode_into_two_sections(
        self,
    ) -> None:
        page = human_import.WikiPage(
            title="Test/Main Story/Japanese",
            episodes={
                7: human_import.ParsedWikiEpisode(
                    texts=("日文甲", "日文乙"),
                    speaker_keys=(("a",), ("b",)),
                )
            },
            source_url="https://exedra.wiki/wiki/Test/Main_Story/Japanese",
            source_sha256="1" * 64,
        )
        match = human_import.match_japanese_page_to_group(
            {"groupKey": "test"},
            page,
            json_sections=(("日文甲",), ("日文乙",)),
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(
            match.chunks,
            (
                human_import.AlignmentChunk(
                    wiki_start=0,
                    wiki_count=1,
                    target_start=0,
                    target_count=2,
                ),
            ),
        )

    def test_prealigned_wiki_page_splits_translations_by_json_section(
        self,
    ) -> None:
        japanese = human_import.WikiPage(
            title="Test/Main Story/Japanese",
            episodes={
                7: human_import.ParsedWikiEpisode(
                    texts=("日文甲", "日文乙"),
                    speaker_keys=(("a",), ("b",)),
                )
            },
            source_url="https://exedra.wiki/wiki/Test/Main_Story/Japanese",
            source_sha256="1" * 64,
        )
        chinese = human_import.WikiPage(
            title="Test/Main Story/Chinese",
            episodes={
                7: human_import.ParsedWikiEpisode(
                    texts=("中文甲", "中文乙"),
                    speaker_keys=(("a",), ("b",)),
                )
            },
            source_url="https://exedra.wiki/wiki/Test/Main_Story/Chinese",
            source_sha256="2" * 64,
        )
        match = human_import.WikiGroupMatch(
            episode_numbers=(7,),
            chunks=(
                human_import.AlignmentChunk(
                    wiki_start=0,
                    wiki_count=1,
                    target_start=0,
                    target_count=2,
                ),
            ),
        )
        translated, anchors = human_import._prealign_wiki_page_to_group(
            chinese,
            japanese,
            match,
            (("日文甲",), ("日文乙",)),
        )
        self.assertEqual(translated[0].texts, ("中文甲",))
        self.assertEqual(translated[1].texts, ("中文乙",))
        self.assertTrue(translated[0].alignment["prealignedWikiPage"])
        self.assertEqual(anchors[1].texts, ("日文乙",))

    def test_explicit_ass_page_requires_exact_event_count(self) -> None:
        japanese = human_import.WikiPage(
            title="Test/Story/Japanese",
            episodes={
                1: human_import.ParsedWikiEpisode(
                    texts=("日文甲", "日文乙"),
                    speaker_keys=(("a",), ("b",)),
                )
            },
            source_url="https://exedra.wiki/wiki/Test/Story/Japanese",
            source_sha256="1" * 64,
        )
        match = human_import.WikiGroupMatch(
            episode_numbers=(1,),
            chunks=(
                human_import.AlignmentChunk(
                    wiki_start=0,
                    wiki_count=1,
                    target_start=0,
                    target_count=1,
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "story.ass"
            path.write_text(
                "\n".join(
                    [
                        "Video File: story.mp4",
                        "[Events]",
                        "Dialogue: 0,0:00:00.00,0:00:01.00,"
                        "Default,,0,0,0,,只有一行",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "事件数不完全相等"):
                human_import._prealign_ass_page_to_group(
                    {"story.ass": path},
                    ("story.ass",),
                    japanese,
                    match,
                    (("日文甲", "日文乙"),),
                )

    def test_explicit_ass_page_projects_exact_rows(self) -> None:
        japanese = human_import.WikiPage(
            title="Test/Story/Japanese",
            episodes={
                1: human_import.ParsedWikiEpisode(
                    texts=("日文甲", "日文乙"),
                    speaker_keys=(("a",), ("b",)),
                )
            },
            source_url="https://exedra.wiki/wiki/Test/Story/Japanese",
            source_sha256="1" * 64,
        )
        match = human_import.WikiGroupMatch(
            episode_numbers=(1,),
            chunks=(
                human_import.AlignmentChunk(
                    wiki_start=0,
                    wiki_count=1,
                    target_start=0,
                    target_count=1,
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "story.ass"
            path.write_text(
                "\n".join(
                    [
                        "Video File: story.mp4",
                        "[Events]",
                        "Dialogue: 0,0:00:00.00,0:00:01.00,"
                        "Default,,0,0,0,,中文甲",
                        "Dialogue: 0,0:00:01.00,0:00:02.00,"
                        "Default,,0,0,0,,中文乙",
                    ]
                ),
                encoding="utf-8",
            )
            translated, anchors = human_import._prealign_ass_page_to_group(
                {"story.ass": path},
                ("story.ass",),
                japanese,
                match,
                (("日文甲", "日文乙"),),
            )
        self.assertEqual(translated[0].texts, ("中文甲", "中文乙"))
        self.assertTrue(translated[0].alignment["prealignedAssPage"])
        self.assertEqual(anchors[0].texts, ("日文甲", "日文乙"))

    def test_explicit_ass_page_rejects_missing_media_identity(self) -> None:
        japanese = human_import.WikiPage(
            title="Test/Story/Japanese",
            episodes={
                1: human_import.ParsedWikiEpisode(
                    texts=("日文甲",),
                    speaker_keys=(("a",),),
                )
            },
            source_url="https://exedra.wiki/wiki/Test/Story/Japanese",
            source_sha256="1" * 64,
        )
        match = human_import.WikiGroupMatch(
            episode_numbers=(1,),
            chunks=(
                human_import.AlignmentChunk(
                    wiki_start=0,
                    wiki_count=1,
                    target_start=0,
                    target_count=1,
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "story.ass"
            path.write_text(
                "Dialogue: 0,0:00:00.00,0:00:01.00,"
                "Default,,0,0,0,,中文甲\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "身份元数据"):
                human_import._prealign_ass_page_to_group(
                    {"story.ass": path},
                    ("story.ass",),
                    japanese,
                    match,
                    (("日文甲",),),
                )


class JsonMutationProofTests(unittest.TestCase):
    def test_localized_json_changes_only_playable_comment_cells(self) -> None:
        document = {
            "bookTitle": "fixture",
            "sheetList": [
                {
                    "headerRow": {
                        "cellList": [
                            "ActionType",
                            "Name",
                            "Comment",
                            "AssetId",
                        ]
                    },
                    "contentRowList": [
                        {
                            "rowNumber": 1,
                            "cellList": ["Talk", "角色", "日本語", "voice_1"],
                        },
                        {
                            "rowNumber": 2,
                            "cellList": ["Put", "", "", "asset_2"],
                        },
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jp_path = root / "jp.json"
            cn_path = root / "cn.json"
            jp_path.write_bytes(human_import.common.json_bytes(document))
            human_import.common.apply_translated_texts(
                jp_path,
                ["中文"],
                cn_path,
            )
            proof = human_import.validate_only_comment_changed(
                jp_path,
                cn_path,
                ["中文"],
            )
            self.assertTrue(proof["nonCommentFieldsMatch"])
            self.assertTrue(proof["playableCommentSequenceMatches"])

            changed = json.loads(cn_path.read_text(encoding="utf-8"))
            changed["sheetList"][0]["contentRowList"][0]["cellList"][3] = (
                "tampered"
            )
            cn_path.write_bytes(human_import.common.json_bytes(changed))
            with self.assertRaisesRegex(RuntimeError, "Comment 以外"):
                human_import.validate_only_comment_changed(
                    jp_path,
                    cn_path,
                    ["中文"],
                )


class JapaneseAnchorAlignmentTests(unittest.TestCase):
    def test_anchor_expands_json_ruby_to_wiki_rendered_order(self) -> None:
        self.assertEqual(
            human_import.normalize_japanese_anchor(
                "『<r=ラ・ピュセル>乙女</r>』"
            ),
            human_import.normalize_japanese_anchor(
                "『乙女ラ・ピュセル』"
            ),
        )

    def test_exact_anchor_accepts_one_wiki_row_for_two_adjacent_json_rows(
        self,
    ) -> None:
        chunks = human_import._exact_chunk_alignment(
            ("前半後半",),
            ("前半", "後半"),
        )
        self.assertEqual(
            chunks,
            (
                human_import.AlignmentChunk(
                    wiki_start=0,
                    wiki_count=1,
                    target_start=0,
                    target_count=2,
                ),
            ),
        )

    def test_exact_anchor_rejects_semantic_difference(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "无法精确锚定"):
            human_import._exact_chunk_alignment(
                ("原文甲",),
                ("原文乙",),
            )

    def test_chinese_merged_row_is_split_at_deterministic_punctuation(
        self,
    ) -> None:
        chinese = human_import.HumanEpisode(
            texts=("今天明确说了，让我别和她们走得太近",),
            speaker_keys=(("ayame_mikuri",),),
            source_type="exedra_wiki_human",
            source_name="test",
            source_url="https://exedra.wiki/wiki/Test/Story/Chinese",
            source_sha256="1" * 64,
        )
        japanese = human_import.ParsedWikiEpisode(
            texts=("今日、はっきり言われた", "仲良くするなって"),
            speaker_keys=(
                ("ayame_mikuri",),
                ("ayame_mikuri",),
            ),
        )
        aligned = human_import.align_wiki_episode(
            chinese,
            japanese,
            ("今日、はっきり言われた", "仲良くするなって"),
            japanese_url="https://exedra.wiki/wiki/Test/Story/Japanese",
            japanese_sha256="2" * 64,
        )
        self.assertEqual(
            aligned.texts,
            ("今天明确说了，", "让我别和她们走得太近"),
        )
        self.assertEqual(
            aligned.alignment["method"],
            "exact_japanese_wiki_anchor",
        )

    def test_chinese_merged_row_without_boundary_is_rejected(self) -> None:
        chinese = human_import.HumanEpisode(
            texts=("无法安全拆开的连续文本",),
            speaker_keys=(("same",),),
            source_type="exedra_wiki_human",
            source_name="test",
            source_url="https://exedra.wiki/wiki/Test/Story/Chinese",
            source_sha256="1" * 64,
        )
        japanese = human_import.ParsedWikiEpisode(
            texts=("前半", "后半"),
            speaker_keys=(("same",), ("same",)),
        )
        with self.assertRaisesRegex(RuntimeError, "标点/换行边界"):
            human_import.align_wiki_episode(
                chinese,
                japanese,
                ("前半", "后半"),
                japanese_url="https://exedra.wiki/wiki/Test/Story/Japanese",
                japanese_sha256="2" * 64,
            )

    def test_ass_shortfall_only_fills_unique_punctuation_event(self) -> None:
        japanese = human_import.ParsedWikiEpisode(
            texts=("台詞A", "…………", "台詞B"),
            speaker_keys=(("a",), ("a",), ("a",)),
        )
        aligned = human_import.align_ass_episode(
            ("中文A", "中文B"),
            japanese,
            ("台詞A", "…………", "台詞B"),
            source_name="test.ass",
            source_sha256="3" * 64,
            japanese_url="https://exedra.wiki/wiki/Test/Story/Japanese",
            japanese_sha256="2" * 64,
        )
        self.assertEqual(aligned.texts, ("中文A", "…………", "中文B"))
        self.assertEqual(
            aligned.alignment["omittedPunctuationJsonIndexes"],
            [1],
        )

    def test_ass_shortfall_rejects_non_unique_punctuation_omission(self) -> None:
        japanese = human_import.ParsedWikiEpisode(
            texts=("……", "台詞", "！？"),
            speaker_keys=((), ("a",), ()),
        )
        with self.assertRaisesRegex(RuntimeError, "静默标点"):
            human_import.align_ass_episode(
                ("中文", "中文二"),
                japanese,
                ("……", "台詞", "！？"),
                source_name="test.ass",
                source_sha256="3" * 64,
                japanese_url="https://exedra.wiki/wiki/Test/Story/Japanese",
                japanese_sha256="2" * 64,
            )


if __name__ == "__main__":
    unittest.main()
