from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

import github_api_checkout as api_checkout  # noqa: E402
import import_exedra_cache_export as wiki_import  # noqa: E402
import import_exedra_official_tw as tw_import  # noqa: E402


class TwSourceIndexTests(unittest.TestCase):
    def test_exact_relative_path_wins_over_duplicate_basenames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "1_Main/chapter_a/shared.json"
            second = root / "2_Sub/chapter_b/shared.json"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_text("{}", encoding="utf-8")
            second.write_text("{}", encoding="utf-8")
            index = tw_import.TwSourceIndex(root)
            self.assertEqual(
                index.resolve("1_Main/chapter_a/shared.json"),
                first.resolve(),
            )
            with self.assertRaisesRegex(RuntimeError, "basename 匹配不唯一"):
                index.resolve("missing/shared.json")

    def test_unsafe_manifest_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "safe.json").write_text("{}", encoding="utf-8")
            index = tw_import.TwSourceIndex(root)
            for value in ("../safe.json", "/safe.json", "a\\safe.json", ""):
                with self.subTest(value=value):
                    with self.assertRaises(RuntimeError):
                        index.resolve(value)


class TextStructureTests(unittest.TestCase):
    def test_section_parser_keeps_speaker_and_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "group_jp.txt"
            path.write_text(
                "\n".join(
                    [
                        "--- [Section 1] (Source: story_1.json) ---",
                        "環 いろは：こんにちは",
                        "ナレーション：夜が明ける",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            sections = tw_import.parse_txt(path)
            self.assertEqual(len(sections), 1)
            self.assertEqual(sections[0].source, "story_1.json")
            self.assertEqual(
                [line.kind for line in sections[0].lines],
                ["dialogue", "narration"],
            )

    def test_row_alignment_rejects_reordered_rows(self) -> None:
        section = tw_import.Section(
            number=1,
            source="story_1.json",
            lines=(tw_import.Line("環 いろは", "こんにちは", "dialogue"),),
        )
        jp_rows = [
            {
                "sheet_index": 0,
                "row_number": 10,
                "action": "Talk",
                "speaker": "環 いろは",
                "text": "こんにちは",
            }
        ]
        tw_rows = [
            {
                "sheet_index": 0,
                "row_number": 11,
                "action": "Talk",
                "speaker": "環 いろは",
                "text": "你好",
            }
        ]
        with self.assertRaisesRegex(RuntimeError, "行位置不同"):
            tw_import.validate_row_alignment(
                "story_1.json",
                jp_rows,
                tw_rows,
                section,
            )


class WikiExportTests(unittest.TestCase):
    def test_wiki_url_is_restricted_to_exact_https_domain_and_story_path(self) -> None:
        valid = "https://exedra.wiki/wiki/:Iroha_Tamaki/Story/Chinese"
        self.assertEqual(wiki_import.validate_wiki_url(valid), valid)
        invalid = (
            "http://exedra.wiki/wiki/:Iroha_Tamaki/Story/Chinese",
            "https://evil.example/wiki/:Iroha_Tamaki/Story/Chinese",
            "https://exedra.wiki/wiki/:Iroha_Tamaki/Story/Japanese",
            "https://user@exedra.wiki/wiki/:Iroha_Tamaki/Story/Chinese",
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    wiki_import.validate_wiki_url(value)

    def test_export_policy_and_machine_provenance_are_rejected(self) -> None:
        base_record = {
            "story_id": "exedra_character_character_iroha_1234567890",
            "source_identity": "exedra:3_Character:character_iroha",
            "source_url": "https://exedra.wiki/wiki/:Iroha_Tamaki/Story/Chinese",
            "generated_at": "2026-07-28T00:00:00+00:00",
            "jp_sha256": "a" * 64,
            "cn_sha256": "b" * 64,
            "text": (
                "--- [Section 1] (Source: a.json) ---\n"
                "環 いろは：你好\n"
            ),
        }
        base_record["cn_sha256"] = __import__("hashlib").sha256(
            base_record["text"].encode("utf-8")
        ).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "export.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "policy": "trusted_exedra_sources_only",
                        "records": [
                            {**base_record, "provenance": "machine_translation"}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "非 Wiki 人工来源"):
                wiki_import.load_export(path)


class TransactionTests(unittest.TestCase):
    def test_commit_staged_group_refuses_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            target = root / "target"
            stage.mkdir()
            target.mkdir()
            (stage / "a.txt").write_text("new", encoding="utf-8")
            (target / "a.txt").write_text("old", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "拒绝覆盖"):
                tw_import.commit_staged_group(stage, target)
            self.assertEqual(
                (target / "a.txt").read_text(encoding="utf-8"),
                "old",
            )
            self.assertEqual(
                (stage / "a.txt").read_text(encoding="utf-8"),
                "new",
            )


class GitHubApiCheckoutTests(unittest.TestCase):
    def test_api_root_requires_https_without_credentials(self) -> None:
        self.assertEqual(
            api_checkout.validate_api_root("https://api.github.com/"),
            "https://api.github.com",
        )
        for value in (
            "http://api.github.com",
            "https://user@api.github.com",
            "https://api.github.com:8443",
            "https://api.github.com?token=secret",
        ):
            with self.subTest(value=value):
                with self.assertRaises(api_checkout.CheckoutError):
                    api_checkout.validate_api_root(value)

    def test_windows_preflight_rejects_reserved_and_case_colliding_paths(self) -> None:
        sha = "a" * 40
        with self.assertRaisesRegex(
            api_checkout.CheckoutError,
            "Windows reserved",
        ):
            api_checkout.preflight_entries(
                [api_checkout.TreeEntry("CON.txt", "100644", "blob", sha, 1)],
                "windows",
            )
        with self.assertRaisesRegex(
            api_checkout.CheckoutError,
            "path collision",
        ):
            api_checkout.preflight_entries(
                [
                    api_checkout.TreeEntry("Readme.md", "100644", "blob", sha, 1),
                    api_checkout.TreeEntry("README.md", "100644", "blob", "b" * 40, 1),
                ],
                "windows",
            )

    def test_symlink_backslash_target_is_rejected_before_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "link"
            with self.assertRaisesRegex(
                api_checkout.CheckoutError,
                "Unsafe symlink target",
            ):
                api_checkout.write_symlink(
                    path,
                    b"..\\outside",
                    "windows",
                )
            self.assertFalse(path.exists())

    def test_zip_output_cannot_be_inside_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "checkout"
            root.mkdir()
            (root / "a.txt").write_text("a", encoding="utf-8")
            with self.assertRaisesRegex(
                api_checkout.CheckoutError,
                "must not be inside",
            ):
                api_checkout.zip_tree(root, root / "checkout.zip")


if __name__ == "__main__":
    unittest.main()
