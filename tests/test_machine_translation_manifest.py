from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "machine_manifest", ROOT / "generate_machine_translation_manifest.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MachineTranslationManifestTests(unittest.TestCase):
    def test_canonicalize_known_renamed_directories(self) -> None:
        self.assertEqual(
            MODULE.canonicalize_identity(
                "event_story/5216 - 海边的缎带/521610_0-20"
            ),
            "event_story/5216 - 海岸边的缎带/521610_0-20",
        )

    def test_repository_path(self) -> None:
        self.assertEqual(
            MODULE.repository_path_for("event_story/demo/123_1-2"),
            "magireco-translate-data-master/Scenarios_full/event_story/demo/123_1-2.txt",
        )


if __name__ == "__main__":
    unittest.main()
