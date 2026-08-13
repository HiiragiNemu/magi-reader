from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "close_deepseek_translation_to_manual",
    ROOT / "tools/close_deepseek_translation_to_manual.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class CloseDeepSeekTranslationToManualTests(unittest.TestCase):
    def test_real_handoff_partition_and_protection(self) -> None:
        staging = ROOT / MODULE.DEFAULT_STAGING
        exedra = ROOT / MODULE.DEFAULT_EXEDRA
        protected = ROOT / MODULE.DEFAULT_PROTECTED
        before = MODULE.sha256_file(protected)
        handoff = MODULE.build_handoff(staging, exedra, protected, MODULE.DS_JOB_ROOT)
        after = MODULE.sha256_file(protected)

        self.assertEqual(before, after)
        self.assertEqual(handoff["counts"]["magireco_queue_total"], 507)
        self.assertEqual(handoff["counts"]["magireco_ds_terminal_references"], 168)
        self.assertEqual(handoff["counts"]["magireco_verified_ok"], 31)
        self.assertEqual(handoff["counts"]["magireco_unresolved"], 20)
        self.assertEqual(handoff["counts"]["magireco_pending_human_translation"], 339)
        self.assertEqual(handoff["counts"]["magireco_malformed_result_json"], 3)
        self.assertEqual(handoff["counts"]["exedra_pending_human_translation"], 26)
        self.assertEqual(handoff["counts"]["exedra_protected_groups_excluded"], 413)
        self.assertEqual(
            handoff["inputs"]["protected_baseline"]["file_verification"][
                "missing_file_count"
            ],
            0,
        )
        self.assertEqual(
            handoff["inputs"]["protected_baseline"]["file_verification"][
                "mismatch_file_count"
            ],
            0,
        )
        self.assertEqual(len(handoff["entries"]), 533)
        self.assertFalse(handoff["policy"]["formal_tree_write_allowed"])
        self.assertTrue(
            all(entry["formal_tree_write_allowed"] is False for entry in handoff["entries"])
        )

    def test_generator_outputs_are_reopenable_and_idempotent(self) -> None:
        staging = ROOT / MODULE.DEFAULT_STAGING
        exedra = ROOT / MODULE.DEFAULT_EXEDRA
        protected = ROOT / MODULE.DEFAULT_PROTECTED
        handoff = MODULE.build_handoff(staging, exedra, protected, MODULE.DS_JOB_ROOT)
        first = MODULE.stable_json_bytes(handoff)
        second = MODULE.stable_json_bytes(handoff)
        self.assertEqual(first, second)
        json.loads(first.decode("utf-8"))

        with tempfile.TemporaryDirectory() as temporary:
            csv_path = Path(temporary) / "manual-review.csv"
            MODULE.write_csv(csv_path, handoff["entries"])
            data = csv_path.read_bytes()
            self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
            self.assertIn("pending_human_translation".encode(), data)

    def test_honorific_gate_does_not_flag_food_sauce(self) -> None:
        self.assertIsNone(MODULE.FORBIDDEN_HONORIFIC.search("酱油和番茄酱"))
        self.assertIsNotNone(MODULE.FORBIDDEN_HONORIFIC.search("忧-chan"))
        self.assertIsNotNone(MODULE.FORBIDDEN_HONORIFIC.search("ういちゃん"))
        self.assertIsNotNone(MODULE.FORBIDDEN_HONORIFIC.search("Yacchan"))


if __name__ == "__main__":
    unittest.main()
