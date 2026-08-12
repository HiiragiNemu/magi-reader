from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools import build_story_release_archive as release


class StoryReleaseArchiveTests(unittest.TestCase):
    def make_repository(self, parent: Path) -> Path:
        repository = parent / "repo"
        repository.mkdir()
        for name in release.DATA_ROOTS:
            root = repository / name
            root.mkdir()
            (root / "keep.json").write_text(
                json.dumps({"root": name}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        nested = repository / "magireco-source-master" / "nested"
        nested.mkdir()
        (nested / "story.txt").write_text("剧情\n台词\n", encoding="utf-8")
        # Temporary/editor artifacts are deliberately excluded.
        (nested / "ignored.tmp").write_bytes(b"ignore")
        (nested / "__pycache__").mkdir()
        (nested / "__pycache__" / "ignored.pyc").write_bytes(b"ignore")
        return repository

    def test_build_is_deterministic_and_manifest_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = self.make_repository(base)
            output = base / "out" / "stories.zip"

            first = release.build_release(output, repository_root=repository)
            first_bytes = output.read_bytes()
            first_digest = hashlib.sha256(first_bytes).hexdigest()

            # Source mtimes and an existing release do not affect canonical ZIP bytes.
            story = repository / "magireco-source-master" / "nested" / "story.txt"
            os.utime(story, ns=(2_000_000_000, 2_000_000_000))
            second = release.build_release(output, repository_root=repository)

            self.assertEqual(first_digest, hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(first["archive"]["sha256"], second["archive"]["sha256"])
            self.assertEqual(first["totals"], second["totals"])
            self.assertEqual(first["totals"]["fileCount"], 7)

            validated = release.validate_archive(
                output,
                repository_root=repository,
                verify_sources=True,
            )
            self.assertEqual(validated["archive"]["sha256"], first_digest)
            self.assertEqual(
                release.release_paths(output).sha256sums.read_text(encoding="utf-8"),
                f"{first_digest}  stories.zip\n",
            )

            with zipfile.ZipFile(output, "r") as archive:
                names = archive.namelist()
                self.assertEqual(names[0], release.MANIFEST_NAME)
                self.assertNotIn(
                    "magireco-source-master/nested/ignored.tmp",
                    names,
                )
                self.assertFalse(any("__pycache__" in name for name in names))
                manifest = json.loads(archive.read(release.MANIFEST_NAME))
            self.assertTrue(manifest["complete"])
            self.assertEqual(manifest["schemaVersion"], 1)
            self.assertEqual(
                [item["name"] for item in manifest["sourceRoots"]],
                list(release.DATA_ROOTS),
            )
            archive_paths = [item["archivePath"] for item in manifest["files"]]
            self.assertEqual(
                archive_paths,
                sorted(archive_paths, key=lambda value: value.encode("utf-8")),
            )

    def test_validate_detects_source_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = self.make_repository(base)
            output = base / "out" / "stories.zip"
            release.build_release(
                output,
                repository_root=repository,
                include_roots=["magireco-source-master"],
            )
            (repository / "magireco-source-master" / "keep.json").write_text(
                "changed\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(release.ArchiveError, "local source changed"):
                release.validate_archive(
                    output,
                    repository_root=repository,
                    include_roots=["magireco-source-master"],
                    verify_sources=True,
                )

    def test_transaction_failure_restores_all_previous_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged = root / "staged"
            target = root / "target"
            staged.mkdir()
            target.mkdir()
            pairs: list[tuple[Path, Path]] = []
            for index in range(3):
                staged_path = staged / f"file-{index}.txt"
                target_path = target / f"file-{index}.txt"
                staged_path.write_text(f"new-{index}", encoding="utf-8")
                target_path.write_text(f"old-{index}", encoding="utf-8")
                pairs.append((staged_path, target_path))

            installs = 0

            def fail_second_install(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
                nonlocal installs
                source_path = Path(source)
                if source_path.parent == staged:
                    installs += 1
                    if installs == 2:
                        raise OSError("simulated publication failure")
                os.replace(source, destination)

            with self.assertRaisesRegex(OSError, "simulated publication failure"):
                release._publish_transaction(pairs, replace_func=fail_second_install)

            for index, (_, target_path) in enumerate(pairs):
                self.assertEqual(target_path.read_text(encoding="utf-8"), f"old-{index}")

    def test_member_paths_and_root_selection_are_strict(self) -> None:
        for value in ("", "/absolute", "../escape", "a/../b", "C:/drive", "a\\b"):
            with self.subTest(value=value):
                with self.assertRaises(release.ArchiveError):
                    release.validate_member_name(value)
        self.assertEqual(release.validate_member_name("root/a.json"), "root/a.json")
        with self.assertRaisesRegex(release.ArchiveError, "unknown data root"):
            release._selected_root_names(["not-a-root"])
        with self.assertRaisesRegex(release.ArchiveError, "only once"):
            release._selected_root_names(
                ["magireco-source-master", "magireco-source-master"]
            )


if __name__ == "__main__":
    unittest.main()
