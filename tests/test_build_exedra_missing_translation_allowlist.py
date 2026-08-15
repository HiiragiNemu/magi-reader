from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.build_exedra_missing_translation_allowlist import (
    ALLOWLIST_NAME,
    DEFAULT_AUDIT,
    DEFAULT_GLOSSARY,
    DEFAULT_MANIFEST,
    REPORT_NAME,
    ROOT,
    SEALED_INPUT_NAME,
    VERIFICATION_NAME,
    AllowlistError,
    build_outputs,
    output_payloads,
    protected_snapshot,
    sha256_file,
    write_or_check,
)


class ExedraMissingTranslationAllowlistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        required = (DEFAULT_AUDIT, DEFAULT_MANIFEST, DEFAULT_GLOSSARY)
        missing = [path for path in required if not path.is_file()]
        if missing:
            relative = ", ".join(
                path.relative_to(ROOT).as_posix() for path in missing
            )
            raise unittest.SkipTest(
                "local DeepSeek retranslation artifacts are not available: "
                + relative
            )

        cls.allowlist, cls.sealed, cls.verification = build_outputs(
            root=ROOT,
            audit_path=DEFAULT_AUDIT,
            manifest_path=DEFAULT_MANIFEST,
            glossary_path=DEFAULT_GLOSSARY,
            expected_total_groups=443,
            expected_protected_groups=413,
            expected_allowlist_groups=26,
            expected_structural_groups=4,
        )

    def test_exact_partition_and_protected_provenance_close(self) -> None:
        self.assertEqual(
            self.allowlist["counts"],
            {
                "manifest_groups": 443,
                "protected_groups": 413,
                "allowlist_groups": 26,
                "structural_no_text_groups": 4,
                "source_json_files": 176,
                "source_segments": 8877,
                "protection_overlap": 0,
            },
        )
        self.assertEqual(
            self.verification["protection_snapshot"]["provenance_counts"],
            {
                "exedra_wiki_voice_human": 7,
                "official_tw_human": 395,
                "rounddora_0728_human": 11,
            },
        )
        self.assertTrue(all(self.verification["gates"].values()) is False)
        # ``formal_tree_write_allowed`` and ``model_invoked`` are deliberately
        # false; every actual pass/fail gate is true.
        for key, value in self.verification["gates"].items():
            if key in {"formal_tree_write_allowed", "model_invoked"}:
                self.assertFalse(value)
            else:
                self.assertTrue(value, key)

    def test_sealed_entries_have_complete_sources_and_stable_ids(self) -> None:
        self.assertEqual(len(self.sealed["entries"]), 26)
        self.assertEqual(
            {item["source_identity"] for item in self.allowlist["entries"]},
            {item["source_identity"] for item in self.sealed["entries"]},
        )
        item_ids = set()
        segment_ids = set()
        for entry in self.sealed["entries"]:
            self.assertNotIn(entry["item_id"], item_ids)
            item_ids.add(entry["item_id"])
            self.assertFalse(entry["formal_tree_write_allowed"])
            self.assertFalse(entry["protection_overlap"])
            self.assertRegex(entry["jp_sha256"], r"^[0-9a-f]{64}$")
            self.assertFalse((ROOT / entry["target_candidate_txt"]).exists())
            self.assertIsInstance(entry["approved_terms"], list)
            for section in entry["sections"]:
                source = ROOT / section["source_json"]
                self.assertTrue(source.is_file())
                self.assertEqual(sha256_file(source), section["source_json_sha256"])
                self.assertFalse((ROOT / section["target_candidate_json"]).exists())
                self.assertEqual(section["segment_count"], len(section["segments"]))
                for segment in section["segments"]:
                    scoped = (entry["item_id"], segment["segment_id"])
                    self.assertNotIn(scoped, segment_ids)
                    segment_ids.add(scoped)
                    self.assertTrue(segment["source_text"].strip())
        self.assertEqual(len(segment_ids), 8877)

    def test_namae_is_sealed_with_tw_highest_authority_missing_gate(self) -> None:
        namae = [item for item in self.sealed["entries"] if item["category"] == "7_Namae"]
        self.assertEqual(len(namae), 12)
        for entry in namae:
            rule = entry["authority_gate"]["namae_rule"]
            self.assertIn("official TW remains highest authority", rule)
            self.assertIn("currently missing", rule)

    def test_write_check_is_idempotent_and_preserves_protected_tree(self) -> None:
        before = protected_snapshot(ROOT)
        payloads = output_payloads(self.allowlist, self.sealed, self.verification)
        self.assertEqual(
            set(payloads),
            {ALLOWLIST_NAME, SEALED_INPUT_NAME, VERIFICATION_NAME, REPORT_NAME},
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_or_check(output, payloads, check=False)
            first = {name: (output / name).read_bytes() for name in payloads}
            write_or_check(output, payloads, check=False)
            second = {name: (output / name).read_bytes() for name in payloads}
            self.assertEqual(first, second)
            write_or_check(output, payloads, check=True)
        self.assertEqual(before, protected_snapshot(ROOT))

    def test_protected_overlap_fails_closed(self) -> None:
        overlap = copy.deepcopy(protected_snapshot(ROOT))
        identity = self.allowlist["entries"][0]["source_identity"]
        overlap["groups"][identity] = {
            "provenance": "official_tw_human",
            "directory": "fixture",
            "files": [],
        }
        # Keep the expected aggregate count so the test reaches the identity
        # overlap gate rather than stopping on the earlier count gate.
        removed = next(key for key in overlap["groups"] if key != identity)
        overlap["groups"].pop(removed)
        with mock.patch(
            "tools.build_exedra_missing_translation_allowlist.protected_snapshot",
            return_value=overlap,
        ):
            with self.assertRaisesRegex(AllowlistError, "sidecars/audit differ"):
                build_outputs(
                    root=ROOT,
                    audit_path=DEFAULT_AUDIT,
                    manifest_path=DEFAULT_MANIFEST,
                    glossary_path=DEFAULT_GLOSSARY,
                    expected_total_groups=443,
                    expected_protected_groups=413,
                    expected_allowlist_groups=26,
                    expected_structural_groups=4,
                )


if __name__ == "__main__":
    unittest.main()
