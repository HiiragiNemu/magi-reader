from __future__ import annotations

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
