from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "machine_manifest", ROOT / "generate_machine_translation_manifest.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def run_git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def raw_blob_hash(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data
    ).hexdigest()


class MachineTranslationManifestTests(unittest.TestCase):
    def test_generated_manifest_uses_fail_closed_source_classification(self) -> None:
        manifest_path = (
            ROOT
            / "website"
            / "public"
            / "data"
            / "machine_translation_manifest.generated.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["version"], 4)
        self.assertEqual(manifest["classification"], "SOURCE_UNVERIFIED")
        self.assertIn("source_unverified", manifest["definition"])
        self.assertEqual(manifest["total"], len(manifest["entries"]))
        self.assertTrue(manifest["entries"])
        manual_ids = manifest["manual_human_verified_ids"]
        self.assertEqual(manifest["manual_human_verified_total"], len(manual_ids))
        self.assertEqual(
            manifest["review_remaining"],
            manifest["total"] - len(manual_ids),
        )
        self.assertEqual(len(manual_ids), len(set(manual_ids)))
        for entry in manifest["entries"]:
            self.assertEqual(entry["classification"], "SOURCE_UNVERIFIED")
            self.assertEqual(
                entry["provenance"],
                "source_unverified_added_after_trusted_main",
            )
            self.assertEqual(
                entry["review_reason"],
                "cn_txt_absent_from_trusted_main",
            )
            self.assertEqual(
                entry["added_source_json_count"],
                entry["machine_source_json_count"],
            )
            self.assertEqual(
                entry["manual_human_verified"],
                entry["story_id"] in manual_ids,
            )

    def test_closed_manual_ledger_uses_only_the_cumulative_section(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            path = Path(raw_directory) / "PROCESSED_STORY_TITLES.md"
            path.write_text(
                "# 已处理剧情标题清单\n\n"
                "- 当前已写入并通过现有 JSON 结构校验：**2 / 507**\n"
                "- 当前剩余：**505**\n\n"
                "## 本轮新增\n\n"
                "- [x] `claim-only` — 此处不授予权限\n\n"
                "## 累计已处理\n\n"
                "- [x] `310001` — 已闭环一\n"
                "- [x] `event_story_demo` — 已闭环二\n\n"
                "## 问题文件与异常记录\n",
                encoding="utf-8",
            )
            self.assertEqual(
                MODULE.load_manual_retranslation_verified_ids(path),
                {"310001", "event_story_demo"},
            )

    def test_closed_manual_ledger_count_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            path = Path(raw_directory) / "PROCESSED_STORY_TITLES.md"
            path.write_text(
                "- 当前已写入并通过现有 JSON 结构校验：**2 / 507**\n"
                "- 当前剩余：**505**\n"
                "## 累计已处理\n"
                "- [x] `310001` — 只有一项\n"
                "## 问题文件与异常记录\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MODULE.ManifestError, "count mismatch"):
                MODULE.load_manual_retranslation_verified_ids(path)

    def test_only_closed_story_source_paths_may_overwrite_baseline(self) -> None:
        allowed = {"source/closed.json"}
        self.assertEqual(
            MODULE.validate_manual_overwrite_boundary(
                {"source/closed.json"},
                allowed,
            ),
            {"source/closed.json"},
        )
        with self.assertRaisesRegex(MODULE.ManifestError, "without a closed"):
            MODULE.validate_manual_overwrite_boundary(
                {"source/closed.json", "source/claim-only.json"},
                allowed,
            )

    def test_generated_artifacts_are_written_as_utf8_lf_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            path = Path(raw_directory) / "generated.json"
            MODULE.write_utf8_lf(path, "{\n  \"ok\": true\n}\n")
            self.assertEqual(path.read_bytes(), b'{\n  "ok": true\n}\n')
            with self.assertRaisesRegex(
                MODULE.ManifestError,
                "contains a carriage return",
            ):
                MODULE.write_utf8_lf(path, "bad\r\n")

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

    def test_worktree_hashes_apply_git_eol_and_clean_filter_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            repository = Path(raw_directory)
            run_git(repository, "init", "--quiet")
            run_git(repository, "config", "user.name", "Manifest Test")
            run_git(repository, "config", "user.email", "manifest@example.invalid")
            run_git(
                repository,
                "config",
                "filter.normalize-story.clean",
                "git stripspace",
            )
            (repository / ".gitattributes").write_text(
                "*.txt text eol=lf\n"
                "*.story text eol=lf filter=normalize-story\n",
                encoding="utf-8",
            )
            tracked_path = "数据 目录/人工 剧情.txt"
            filtered_path = "数据 目录/过滤 剧情.story"
            added_path = "数据 目录/新增 机翻.txt"
            tracked_file = repository / Path(*tracked_path.split("/"))
            filtered_file = repository / Path(*filtered_path.split("/"))
            added_file = repository / Path(*added_path.split("/"))
            tracked_file.parent.mkdir(parents=True)
            tracked_file.write_bytes("人工文本\r\n第二行\r\n".encode("utf-8"))
            filtered_file.write_bytes(
                "需要过滤的文本  \r\n第二行\t\r\n".encode("utf-8")
            )
            run_git(
                repository,
                "add",
                "--",
                ".gitattributes",
                tracked_path,
                filtered_path,
            )
            baseline = {
                tracked_path: run_git(repository, "rev-parse", f":{tracked_path}"),
                filtered_path: run_git(repository, "rev-parse", f":{filtered_path}"),
            }

            # Leave the added file outside the index: it must remain classified as
            # added while all baseline hashes use Git's clean-filter semantics.
            added_file.write_bytes("新增文本\r\n".encode("utf-8"))
            current = MODULE.git_worktree_blob_hashes(
                [tracked_path, filtered_path, added_path],
                repository_root=repository,
            )

            self.assertEqual(current[tracked_path], baseline[tracked_path])
            self.assertEqual(current[filtered_path], baseline[filtered_path])
            self.assertNotEqual(current[tracked_path], raw_blob_hash(tracked_file))
            self.assertNotEqual(current[filtered_path], raw_blob_hash(filtered_file))
            added, overwritten, deleted = MODULE.classify_trust_boundary(
                baseline,
                current,
            )
            self.assertEqual(added, {added_path})
            self.assertEqual(overwritten, set())
            self.assertEqual(deleted, set())

    def test_worktree_hashes_reject_unsafe_or_missing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            repository = Path(raw_directory)
            run_git(repository, "init", "--quiet")
            with self.assertRaisesRegex(MODULE.ManifestError, "unsafe worktree path"):
                MODULE.git_worktree_blob_hashes(
                    ["目录/换行\n剧情.txt"],
                    repository_root=repository,
                )
            with self.assertRaisesRegex(MODULE.ManifestError, "worktree file is missing"):
                MODULE.git_worktree_blob_hashes(
                    ["目录/不存在.txt"],
                    repository_root=repository,
                )

    def test_worktree_hashes_reject_result_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            repository = Path(raw_directory)
            (repository / "a.txt").write_text("a", encoding="utf-8")
            (repository / "b.txt").write_text("b", encoding="utf-8")
            one_hash = "a" * 40 + "\n"
            with mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=SimpleNamespace(
                    returncode=0,
                    stdout=one_hash,
                    stderr="",
                ),
            ):
                with self.assertRaisesRegex(
                    MODULE.ManifestError,
                    "result count does not match",
                ):
                    MODULE.git_worktree_blob_hashes(
                        ["a.txt", "b.txt"],
                        repository_root=repository,
                    )


if __name__ == "__main__":
    unittest.main()
