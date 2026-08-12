from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.build_deepseek_retranslation_inventory import (
    InventoryError,
    safe_repo_path,
    text_metrics,
)


class DeepSeekRetranslationInventoryTests(unittest.TestCase):
    def test_text_metrics_keeps_source_order_and_finds_quality_signals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "story.txt"
            path.write_text(
                "--- [Section 1] (Source: a.json) ---\n"
                "莎奈: 忧-chan，你好。\n"
                "--- [Section 2] (Source: b.json) ---\n"
                "旁白: 日本語の残留\n",
                encoding="utf-8",
            )
            metrics = text_metrics(path)
        self.assertEqual(metrics["source_names"], ["a.json", "b.json"])
        self.assertEqual(metrics["content_row_count"], 2)
        self.assertEqual(metrics["quality_issue_counts"]["ui_chan_literal"], 1)
        self.assertGreaterEqual(metrics["quality_issue_counts"]["japanese_kana"], 1)

    def test_safe_repo_path_rejects_traversal_and_backslash(self) -> None:
        for candidate in ("../x", "/absolute", "a\\b", "a/../b"):
            with self.subTest(candidate=candidate), self.assertRaises(InventoryError):
                safe_repo_path(candidate)

    def test_safe_repo_path_accepts_unicode_repository_path(self) -> None:
        path = safe_repo_path("root/角色/剧情.txt")
        self.assertEqual(path.as_posix(), "root/角色/剧情.txt")


if __name__ == "__main__":
    unittest.main()
