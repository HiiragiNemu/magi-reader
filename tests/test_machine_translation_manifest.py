from __future__ import annotations

import importlib.util
import tempfile
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

    def test_identity_comes_from_deployed_cn_path(self) -> None:
        identity = MODULE.identity_from_public_cn_path(
            "/data/event_story/5129 - Dependence Blue/512901_0-5_cn.txt"
        )
        self.assertEqual(
            identity,
            "event_story/5129 - Dependence Blue/512901_0-5",
        )
        self.assertEqual(
            MODULE.repository_path_for(identity),
            "magireco-translate-data-master/Scenarios_full/"
            "event_story/5129 - Dependence Blue/512901_0-5.txt",
        )

    def test_referenced_json_sources_are_resolved_in_txt_directory(self) -> None:
        identity = "event_story/5129 - Dependence Blue/512901_0-5"
        with tempfile.TemporaryDirectory() as raw_directory:
            path = Path(raw_directory) / "story.txt"
            path.write_text(
                "---[Section 0] (Source: 512901-0.json) ---\n"
                "角色: 文本\n"
                "---[Section 1] (Source: nested/512901-1.json) ---\n",
                encoding="utf-8",
            )
            self.assertEqual(
                MODULE.referenced_json_sources(identity, path),
                {
                    "event_story/5129 - Dependence Blue/512901-0.json",
                    "event_story/5129 - Dependence Blue/nested/512901-1.json",
                },
            )

    def test_invalid_public_cn_path_is_rejected(self) -> None:
        with self.assertRaises(MODULE.ManifestError):
            MODULE.identity_from_public_cn_path("/outside/story_cn.txt")

    def test_only_paths_absent_from_trusted_main_are_added(self) -> None:
        baseline = {
            "human-main.txt": "aaa",
            "human-event.txt": "bbb",
        }
        current = {
            "human-main.txt": "aaa",
            "human-event.txt": "bbb",
            "new-machine.txt": "ccc",
        }
        added, overwritten, deleted = MODULE.classify_trust_boundary(
            baseline, current
        )
        self.assertEqual(added, {"new-machine.txt"})
        self.assertEqual(overwritten, set())
        self.assertEqual(deleted, set())

    def test_modified_or_deleted_trusted_files_are_detected(self) -> None:
        baseline = {
            "main_story/official.txt": "aaa",
            "event_story/human.txt": "bbb",
        }
        current = {
            "main_story/official.txt": "machine-overwrite",
            "new-machine.txt": "ccc",
        }
        added, overwritten, deleted = MODULE.classify_trust_boundary(
            baseline, current
        )
        self.assertEqual(added, {"new-machine.txt"})
        self.assertEqual(overwritten, {"main_story/official.txt"})
        self.assertEqual(deleted, {"event_story/human.txt"})


if __name__ == "__main__":
    unittest.main()
