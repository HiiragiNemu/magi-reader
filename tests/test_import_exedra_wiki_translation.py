from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import import_exedra_wiki_translation as importer


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "exedra_wiki_translation"
JP_FIXTURE = FIXTURES / "rena_subset_jp.txt"
WIKI_FIXTURE = FIXTURES / "rena_subset.wiki"
DICTIONARY = ROOT / "website" / "app" / "config" / "dictionary.ts"


def make_windows_junction(link: Path, target: Path) -> None:
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=True,
        capture_output=True,
        text=True,
    )


class ExedraWikiTranslationImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.jp_raw = JP_FIXTURE.read_text("utf-8")
        self.wiki_raw = WIKI_FIXTURE.read_text("utf-8")
        self.sections = importer.parse_section_text(self.jp_raw)
        self.episodes = importer.parse_wikitext(self.wiki_raw)
        dictionary, self.dictionary_sha = importer.load_name_translation_map(
            DICTIONARY
        )
        self.speaker_map = importer.build_speaker_map(
            dictionary, "character_rena"
        )

    def bundle(
        self,
        output_root: Path,
        *,
        episodes: tuple[importer.WikiEpisode, ...] | None = None,
    ) -> importer.ValidationBundle:
        revision = importer.WikiRevision(
            page="Rena Minami/Story/Chinese",
            revision_id=59193,
            timestamp="2025-07-23T05:40:28Z",
            author="Chie",
            sha1="fixture",
            content=self.wiki_raw,
            source=str(WIKI_FIXTURE),
        )
        return importer.validate_translation(
            sections=self.sections,
            episodes=episodes or self.episodes,
            speaker_map=self.speaker_map,
            wiki_revision=revision,
            jp_path=JP_FIXTURE,
            dictionary_path=DICTIONARY,
            dictionary_sha256=self.dictionary_sha,
            group_key="character_rena",
            category="3_Character",
            target_path=(
                output_root
                / "3_Character"
                / "character_rena"
                / "character_rena_cn.txt"
            ),
            jp_content_sha256=importer.sha256_text(self.jp_raw),
            generated_at="2026-07-26T00:00:00+00:00",
        )

    def test_fixture_preserves_wiki_events_and_matches_reader_blocks(self) -> None:
        self.assertEqual(
            [len(section.events) for section in self.sections], [3, 7, 2]
        )
        self.assertEqual(
            [len(episode.events) for episode in self.episodes], [3, 5, 2]
        )
        self.assertEqual(
            [
                len(importer.merge_reader_blocks(section.events))
                for section in self.sections
            ],
            [1, 4, 2],
        )
        self.assertEqual(
            [
                len(importer.merge_reader_blocks(episode.events))
                for episode in self.episodes
            ],
            [1, 4, 2],
        )

        bundle = self.bundle(Path("unused-output"))
        self.assertTrue(bundle.passed)
        self.assertEqual(bundle.report["jp"]["rawEventCount"], 12)
        self.assertEqual(bundle.report["cn"]["rawEventCount"], 10)
        self.assertEqual(
            bundle.report["jp"]["readerNormalizedBlockCount"], 7
        )
        self.assertEqual(
            bundle.report["cn"]["readerNormalizedBlockCount"], 7
        )
        self.assertIn(
            "--- [Section 1] (Source: character_rena_0.json) ---",
            bundle.rendered_text,
        )
        self.assertIn(
            r"水波玲奈: 第一行\n仍是第一行", bundle.rendered_text
        )
        self.assertIn(
            r"旁白: 第一段旁白\n第二段旁白", bundle.rendered_text
        )
        self.assertIn("水波玲奈: 合并翻译的续句", bundle.rendered_text)
        self.assertIn("玲奈＆桃子: 一起", bundle.rendered_text)

    def test_section_source_name_may_contain_parentheses_but_not_paths(
        self,
    ) -> None:
        parsed = importer.parse_section_text(
            "--- [Section 1] (Source: story(part).json) ---\n"
            "水波レナ: 台詞\n"
        )
        self.assertEqual(parsed[0].source_name, "story(part).json")
        with self.assertRaises(importer.ImporterError):
            importer.parse_section_text(
                "--- [Section 1] (Source: nested/story.json) ---\n"
                "水波レナ: 台詞\n"
            )

    def test_speaker_mismatch_is_reported_without_guessing(self) -> None:
        changed = self.wiki_raw.replace(
            "{{Color Dialogue|秋野枫|Kaede Akino}}: 回复",
            "{{Color Dialogue|水波玲奈|Rena Minami}}: 回复",
        )
        episodes = importer.parse_wikitext(changed)
        bundle = self.bundle(Path("unused-output"), episodes=episodes)
        self.assertFalse(bundle.passed)
        self.assertTrue(
            any(
                mismatch["type"]
                in {"reader-block-count", "speaker-or-kind"}
                for mismatch in bundle.report["mismatches"]
            )
        )
        self.assertFalse(bundle.report["validation"]["usesLcs"])
        self.assertFalse(bundle.report["validation"]["usesFuzzyMatching"])
        self.assertFalse(bundle.report["validation"]["allowsReordering"])

    def test_section_mismatch_is_refused(self) -> None:
        bundle = self.bundle(
            Path("unused-output"), episodes=self.episodes[:-1]
        )
        self.assertFalse(bundle.passed)
        self.assertIn(
            "section-count",
            {item["type"] for item in bundle.report["mismatches"]},
        )

    def test_unrecognized_wiki_text_is_not_silently_dropped(self) -> None:
        changed = self.wiki_raw.replace(
            "{{BackgroundImage|bg_fixture.png}}",
            "{{BackgroundImage|bg_fixture.png}}\n这不是受支持的剧情标记",
        )
        with self.assertRaises(importer.ImporterError):
            importer.parse_wikitext(changed)
        with self.assertRaises(importer.ImporterError):
            importer.clean_wiki_text("<unsupported>剧情</unsupported>")

    def test_known_control_templates_can_follow_visible_text(self) -> None:
        self.assertEqual(
            importer.clean_wiki_text(
                "（来吧，<ruby>重生<rt>Reborn</rt></ruby>！）"
                "{{BackgroundImage|bg_adv_01_90015_03.png}}"
            ),
            "（来吧，重生！）",
        )
        with self.assertRaises(importer.ImporterError):
            importer.clean_wiki_text("剧情{{UnknownTemplate|仍不可忽略}}")

    def test_known_unlock_notices_are_ignored_without_dropping_story_text(
        self,
    ) -> None:
        for notice in (
            "记忆Lv.1解锁",
            "获取角色第一个记忆时解锁",
            "获取角色首个记忆时解锁",
            "在获得角色的第一个记忆时解锁",
            "在获得角色的第一份记忆时解锁",
            "于获得角色的第一个记忆时解锁",
            "获得角色的第一个记忆后解锁",
            "当角色的第一个记忆被获取时解锁",
            "当角色的第一个记忆被获得时",
            "获得该角色的第一张记忆时解锁",
            "当心之器等级达到Lvl. 2时解锁",
            "在心之器等级2时解锁",
            "于心之器等级2时解锁",
            "心之器等级达到2级时解锁",
            "記憶レベル1解放",
        ):
            parsed = importer.parse_wikitext(
                "=== Episode 0 ===\n"
                f"{notice}\n"
                "{{Color Dialogue|水波玲奈|Rena Minami}}: 台词\n"
            )
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0].events[0].text, "台词")

        with self.assertRaises(importer.ImporterError):
            importer.parse_wikitext(
                "=== Episode 0 ===\n"
                "这是一句没有剧情标记的普通文本\n"
                "{{Color Dialogue|水波玲奈|Rena Minami}}: 台词\n"
            )
        with self.assertRaises(importer.ImporterError):
            importer.parse_wikitext(
                "=== Episode 0 ===\n"
                "那一瞬间，她尘封的记忆终于解锁\n"
                "{{Color Dialogue|水波玲奈|Rena Minami}}: 台词\n"
            )

    def test_empty_bold_markup_is_ignored_as_formatting_artifact(self) -> None:
        parsed = importer.parse_wikitext(
            "=== Episode 0 ===\n"
            "''''''\n"
            "{{Color Dialogue|水波玲奈|Rena Minami}}: 台词\n"
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual([event.text for event in parsed[0].events], ["台词"])

    def test_default_cli_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "Scenarios_full"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = importer.main(
                    [
                        "--jp-file",
                        str(JP_FIXTURE),
                        "--wiki-fixture",
                        str(WIKI_FIXTURE),
                        "--dictionary",
                        str(DICTIONARY),
                        "--cn-root",
                        str(output_root),
                    ]
                )
            self.assertEqual(status, 0)
            self.assertFalse(output_root.exists())
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["mode"], "dry-run")
            self.assertEqual(report["publication"]["report"], "stdout-only")

    def test_publish_stages_full_tree_and_preserves_prior_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "Scenarios_full"
            output_root.mkdir()
            (output_root / "unrelated.txt").write_text(
                "keep me", encoding="utf-8"
            )
            bundle = self.bundle(output_root)

            published, backup, report_path = importer.publish_translation(
                bundle=bundle,
                output_root=output_root,
                jp_path=JP_FIXTURE,
                category="3_Character",
                group_key="character_rena",
            )
            self.assertEqual(
                published.read_text("utf-8"), bundle.rendered_text
            )
            self.assertEqual(
                (output_root / "unrelated.txt").read_text("utf-8"), "keep me"
            )
            self.assertIsNotNone(backup)
            assert backup is not None
            self.assertEqual(
                (backup / "unrelated.txt").read_text("utf-8"), "keep me"
            )
            self.assertEqual(
                json.loads(report_path.read_text("utf-8")), bundle.report
            )

    def test_failed_validation_cannot_publish_or_replace_existing_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "Scenarios_full"
            output_root.mkdir()
            marker = output_root / "marker.txt"
            marker.write_text("untouched", encoding="utf-8")
            changed = self.wiki_raw.replace(
                "{{Color Dialogue|丘比|Kyubey}}: 呼唤",
                "{{Color Dialogue|水波玲奈|Rena Minami}}: 呼唤",
            )
            failed = self.bundle(
                output_root, episodes=importer.parse_wikitext(changed)
            )
            self.assertFalse(failed.passed)
            with self.assertRaises(importer.ImporterError):
                importer.publish_translation(
                    bundle=failed,
                    output_root=output_root,
                    jp_path=JP_FIXTURE,
                    category="3_Character",
                    group_key="character_rena",
                )
            self.assertEqual(marker.read_text("utf-8"), "untouched")
            self.assertEqual(
                list(Path(temporary).glob("Scenarios_full.backup-*")), []
            )

    def test_publish_refuses_path_traversal_components(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "Scenarios_full"
            output_root.mkdir()
            marker = output_root / "marker.txt"
            marker.write_text("untouched", encoding="utf-8")
            bundle = self.bundle(output_root)
            with self.assertRaises(importer.ImporterError):
                importer.publish_translation(
                    bundle=bundle,
                    output_root=output_root,
                    jp_path=JP_FIXTURE,
                    category="..",
                    group_key="character_rena",
                )
            self.assertEqual(marker.read_text("utf-8"), "untouched")

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_publish_rejects_output_beneath_ancestor_junction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside-cn-parent"
            real_output = outside / "Scenarios_full"
            real_output.mkdir(parents=True)
            marker = real_output / "marker.txt"
            outside_sentinel = outside / "outside-sentinel.txt"
            marker.write_text("old output", encoding="utf-8")
            outside_sentinel.write_text("outside must survive", encoding="utf-8")
            alias = root / "alias-to-outside-cn-parent"
            make_windows_junction(alias, outside)
            output_root = alias / "Scenarios_full"
            bundle = self.bundle(output_root)
            try:
                with self.assertRaises(importer.ImporterError):
                    importer.publish_translation(
                        bundle=bundle,
                        output_root=output_root,
                        jp_path=JP_FIXTURE,
                        category="3_Character",
                        group_key="character_rena",
                    )
                self.assertEqual(marker.read_text("utf-8"), "old output")
                self.assertEqual(
                    outside_sentinel.read_text("utf-8"),
                    "outside must survive",
                )
                self.assertFalse(
                    (
                        real_output
                        / "3_Character"
                        / "character_rena"
                        / "character_rena_cn.txt"
                    ).exists()
                )
                self.assertEqual(
                    list(outside.glob("Scenarios_full.backup-*")),
                    [],
                )
            finally:
                if os.path.lexists(alias):
                    os.rmdir(alias)


if __name__ == "__main__":
    unittest.main()
