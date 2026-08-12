from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.build_authoritative_glossary import (
    aligned_speaker_mappings,
    paired_character_directories,
)


class AuthoritativeGlossaryTest(unittest.TestCase):
    def test_paired_character_directory_requires_both_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jp = root / "magireco-source-master/Scenarios_full/character_story"
            cn = root / "magireco-translate-data-master/Scenarios_full/character_story"
            (jp / "1001 - 环彩羽（環 いろは）").mkdir(parents=True)
            (cn / "1001 - 环彩羽（環 いろは）").mkdir(parents=True)
            (jp / "1002 - 七海八千代（七海 やちよ）").mkdir()
            records = paired_character_directories(root)
            self.assertEqual([(item["id"], item["cn"]) for item in records], [("1001", "环彩羽")])

    def test_aligned_speakers_are_approved_only_with_strong_agreement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jp = root / "magireco-source-master/Scenarios_full/main_story/a"
            cn = root / "magireco-translate-data-master/Scenarios_full/main_story/a"
            jp.mkdir(parents=True)
            cn.mkdir(parents=True)
            (jp / "x.txt").write_text("いろは: 一\nいろは: 二\n", encoding="utf-8")
            (cn / "x.txt").write_text("彩羽: 一\n彩羽: 二\n", encoding="utf-8")
            records = aligned_speaker_mappings(root)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["cn"], "彩羽")
            self.assertEqual(records[0]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
