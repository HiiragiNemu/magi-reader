from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.stage_deepseek_translation_batch import (
    CANONICAL_TEXT_HASH_MODE,
    GateError,
    MODEL,
    build_prompt,
    canonical_json_bytes,
    claude_command,
    extract_worker_result,
    honorific_violations,
    preflight,
    render_candidate,
    sha256_file,
    snapshot_protection,
    source_segments,
    stage_batch,
    validate_worker_result,
)


class DeepSeekTranslationBatchGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Test Fixture"], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "fixture@example.invalid"],
            check=True,
        )
        baseline_dir = self.root / (
            "magireco-translate-data-master/Scenarios_full/main_story/trusted"
        )
        baseline_dir.mkdir(parents=True)
        self.baseline_txt = baseline_dir / "trusted_cn.txt"
        self.baseline_json = baseline_dir / "trusted.json"
        # Commit transport uses BOM + CRLF; the checked-out copy below uses LF.
        # Both must have the same canonical protection hash.
        self.baseline_txt.write_bytes("\ufeff可信人工文本\r\n".encode("utf-8"))
        self.baseline_json.write_bytes(b'\xef\xbb\xbf{"trusted":true}\r\n')
        subprocess.run(
            ["git", "-C", str(self.root), "add", "magireco-translate-data-master"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-q", "-m", "trusted fixture"],
            check=True,
        )
        self.baseline_commit = subprocess.check_output(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True
        ).strip()
        self.baseline_txt.write_text("可信人工文本\n", encoding="utf-8")
        self.baseline_json.write_text('{"trusted":true}\n', encoding="utf-8")

        self.jp_rel = "magireco-source-master/Scenarios_full/event_story/demo/100001.txt"
        self.cn_rel = "magireco-translate-data-master/Scenarios_full/event_story/demo/100001.txt"
        self.jp = self.root / self.jp_rel
        self.cn = self.root / self.cn_rel
        self.jp.parent.mkdir(parents=True)
        self.cn.parent.mkdir(parents=True)
        self.jp.write_text(
            "--- [Section 1] (Source: 100001.json) ---\n"
            "いろは：こんにちは\\n${player}\n",
            encoding="utf-8",
        )
        self.cn.write_text(
            "--- [Section 1] (Source: 100001.json) ---\n"
            "环彩羽：旧机器译文\\n${player}\n",
            encoding="utf-8",
        )

        self.group_dirs: dict[str, Path] = {}
        for category, group_id, provenance in (
            ("7_Namae", "namae_demo", "official_tw_human"),
            ("6_Reaction", "voice_demo", "exedra_wiki_voice_human"),
            ("4_Portrait", "portrait_demo", "rounddora_0728_human"),
        ):
            group_dir = self.root / (
                f"magiraexedra-translate-data-master/Scenarios_full/{category}/{group_id}"
            )
            group_dir.mkdir(parents=True)
            (group_dir / f"{group_id}_1.json").write_text(
                '{"official":true}\n', encoding="utf-8"
            )
            (group_dir / f"{group_id}_cn.txt").write_text("可信简体文本\n", encoding="utf-8")
            (group_dir / f"{group_id}_cn.import-report.json").write_text(
                '{"validation":"passed"}\n', encoding="utf-8"
            )
            (group_dir / f"{group_id}_cn.provenance.json").write_text(
                json.dumps(
                    {
                        "provenance": provenance,
                        "officialTw": provenance == "official_tw_human",
                        "machineTranslation": False,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            self.group_dirs[provenance] = group_dir

        unknown_dir = self.root / (
            "magiraexedra-translate-data-master/Scenarios_full/2_Sub/unknown_demo"
        )
        unknown_dir.mkdir(parents=True)
        (unknown_dir / "unknown_demo_1.json").write_text("{}\n", encoding="utf-8")
        (unknown_dir / "unknown_demo_cn.provenance.json").write_text(
            '{"provenance":"source_unknown","machineTranslation":false}\n', encoding="utf-8"
        )
        self.inventory = {
            "official_or_human_protected": [],
            "pending_retranslation": [
                {
                    "story_id": "100001",
                    "classification": "pending_retranslation",
                    "jp_txt": self.jp_rel,
                    "cn_txt": self.cn_rel,
                }
            ]
        }
        self.protection = snapshot_protection(
            self.root,
            self.inventory,
            trusted_magia_commit=self.baseline_commit,
            expected_namae_tw_group_count=1,
            expected_namae_tw_json_count=1,
        )
        self.allowlist = {
            "schema_version": 1,
            "entries": [
                {
                    "story_id": "100001",
                    "classification": "pending_retranslation",
                    "jp_txt": self.jp_rel,
                    "target_cn_txt": self.cn_rel,
                    "jp_sha256": sha256_file(self.jp),
                    "target_before_sha256": sha256_file(self.cn),
                }
            ],
        }
        _sections, segments = source_segments(
            self.jp.read_text(encoding="utf-8"), self.jp_rel
        )
        self.package = {
            "schema_version": 1,
            "batch_id": "fixture-001",
            "model": MODEL,
            "glossary_version": "fixture-v1",
            "glossary_sha256": "1" * 64,
            "entries": [
                {
                    **self.allowlist["entries"][0],
                    "title": "测试剧情",
                    "context": "环彩羽向玩家打招呼。",
                    "speaker_relationships": ["环彩羽 -> 玩家：友善"],
                    "approved_terms": [
                        {
                            "term_id": "character-iroha",
                            "source": "いろは",
                            "approved_translation": "环彩羽",
                        }
                    ],
                    "protected_references": ["官方主线称呼：环彩羽"],
                    "segments": segments,
                }
            ],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def checked(self):
        return preflight(
            root=self.root,
            inventory=self.inventory,
            allowlist=self.allowlist,
            package=self.package,
            protection=self.protection,
            trusted_magia_commit=self.baseline_commit,
            expected_namae_tw_group_count=1,
            expected_namae_tw_json_count=1,
        )

    def valid_result(self) -> dict:
        return {
            "batch_id": "fixture-001",
            "results": [
                {
                    "story_id": "100001",
                    "translations": [
                        {
                            "segment_id": "S0001L00001",
                            "text": "你好\\n${player}",
                        }
                    ],
                    "term_hits": [
                        {"term_id": "character-iroha", "segment_ids": ["S0001L00001"]}
                    ],
                    "unresolved": [],
                }
            ],
        }

    def write_inputs(self) -> tuple[Path, Path, Path, Path]:
        paths = []
        for name, value in (
            ("inventory.json", self.inventory),
            ("allowlist.json", self.allowlist),
            ("package.json", self.package),
            ("protection.json", self.protection),
        ):
            path = self.root / name
            path.write_bytes(canonical_json_bytes(value))
            paths.append(path)
        return tuple(paths)  # type: ignore[return-value]

    def test_preflight_closes_allowlist_protected_and_namae_gates(self) -> None:
        checked = self.checked()
        self.assertEqual(checked["summary"]["allowlist_count"], 1)
        self.assertEqual(checked["summary"]["magia_baseline_file_count"], 2)
        self.assertEqual(checked["summary"]["exedra_human_group_count"], 3)
        self.assertEqual(checked["summary"]["exedra_human_file_count"], 12)
        self.assertEqual(checked["summary"]["namae_tw_group_count"], 1)
        self.assertEqual(checked["summary"]["namae_tw_file_count"], 4)
        self.assertEqual(checked["summary"]["namae_tw_json_count"], 1)
        self.assertTrue(checked["summary"]["all_hard_gates_passed"])

    def test_snapshot_protects_complete_baseline_and_all_human_exedra_sources(self) -> None:
        protected = {item["path"]: item for item in self.protection["protected_files"]}
        self.assertIn(self.baseline_txt.relative_to(self.root).as_posix(), protected)
        self.assertIn(self.baseline_json.relative_to(self.root).as_posix(), protected)
        for provenance, group_dir in self.group_dirs.items():
            for path in group_dir.iterdir():
                entry = protected[path.relative_to(self.root).as_posix()]
                self.assertEqual(entry["classification"], provenance)
                self.assertEqual(entry["hash_mode"], CANONICAL_TEXT_HASH_MODE)
        self.assertNotIn(
            "magiraexedra-translate-data-master/Scenarios_full/2_Sub/unknown_demo/unknown_demo_1.json",
            protected,
        )

    def test_canonical_hash_accepts_only_bom_and_eol_transport_changes(self) -> None:
        self.baseline_txt.write_bytes("\ufeff可信人工文本\r\n".encode("utf-8"))
        self.baseline_json.write_bytes(b'\xef\xbb\xbf{"trusted":true}\r\n')
        self.checked()

    def test_claude_command_disables_all_tools_and_pins_model(self) -> None:
        command = claude_command("claude")
        self.assertEqual(command[command.index("--model") + 1], MODEL)
        self.assertEqual(command[command.index("--tools") + 1], "")
        self.assertEqual(command[command.index("--disallowed-tools") + 1], "mcp__*")
        self.assertNotIn("Read", command)
        self.assertNotIn("Bash", command)

    def test_prompt_contains_only_prepared_package_and_translation_boundary(self) -> None:
        prompt = build_prompt(self.package)
        self.assertIn("translation-only worker", prompt)
        self.assertIn("TRANSLATION_PACKAGE_JSON", prompt)
        self.assertIn('"batch_id":"fixture-001"', prompt)
        self.assertNotIn(str(self.root), prompt)

    def test_allowlist_and_package_must_match_exactly(self) -> None:
        changed = copy.deepcopy(self.package)
        changed["entries"][0]["story_id"] = "other"
        with self.assertRaisesRegex(GateError, "absent from the Codex allowlist"):
            preflight(
                root=self.root,
                inventory=self.inventory,
                allowlist=self.allowlist,
                package=changed,
                protection=self.protection,
                trusted_magia_commit=self.baseline_commit,
                expected_namae_tw_group_count=1,
                expected_namae_tw_json_count=1,
            )

    def test_protected_hash_drift_blocks_before_worker(self) -> None:
        self.baseline_txt.write_text("发生语义漂移\n", encoding="utf-8")
        with self.assertRaisesRegex(GateError, "canonical SHA-256 drift"):
            self.checked()

    def test_classification_conflict_blocks_protected_target(self) -> None:
        trusted_rel = self.baseline_txt.relative_to(self.root).as_posix()
        inventory = copy.deepcopy(self.inventory)
        allowlist = copy.deepcopy(self.allowlist)
        package = copy.deepcopy(self.package)
        inventory["pending_retranslation"][0]["cn_txt"] = trusted_rel
        allowlist["entries"][0]["target_cn_txt"] = trusted_rel
        allowlist["entries"][0]["target_before_sha256"] = sha256_file(self.baseline_txt)
        package["entries"][0]["target_cn_txt"] = trusted_rel
        package["entries"][0]["target_before_sha256"] = sha256_file(self.baseline_txt)
        with self.assertRaisesRegex(GateError, "attempts to target a protected"):
            preflight(
                root=self.root,
                inventory=inventory,
                allowlist=allowlist,
                package=package,
                protection=self.protection,
                trusted_magia_commit=self.baseline_commit,
                expected_namae_tw_group_count=1,
                expected_namae_tw_json_count=1,
            )

    def test_unknown_source_cannot_enter_protection_or_deepseek_allowlist(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["source_unknown_blocked"] = [
            {
                "story_id": "unknown-1",
                "classification": "source_unknown_blocked",
                "jp_txt": self.jp_rel,
                "cn_txt": self.cn_rel,
            }
        ]
        allowlist = copy.deepcopy(self.allowlist)
        allowlist["entries"][0]["story_id"] = "unknown-1"
        allowlist["entries"][0]["classification"] = "source_unknown_blocked"
        with self.assertRaisesRegex(GateError, "absent from pending inventory"):
            preflight(
                root=self.root,
                inventory=inventory,
                allowlist=allowlist,
                package=self.package,
                protection=self.protection,
                trusted_magia_commit=self.baseline_commit,
                expected_namae_tw_group_count=1,
                expected_namae_tw_json_count=1,
            )

    def test_namae_unlisted_file_blocks_closed_count(self) -> None:
        extra = self.root / (
            "magiraexedra-translate-data-master/Scenarios_full/7_Namae/namae_demo/extra.json"
        )
        extra.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(GateError, "file inventory is open"):
            self.checked()

    def test_exedra_unlisted_human_group_file_blocks_closed_snapshot(self) -> None:
        extra = self.group_dirs["exedra_wiki_voice_human"] / "unlisted.txt"
        extra.write_text("新增人工文本\n", encoding="utf-8")
        with self.assertRaisesRegex(GateError, "file inventory is open"):
            self.checked()

    def test_exedra_group_hash_must_equal_protected_files_hash(self) -> None:
        protected = copy.deepcopy(self.protection)
        voice_path = (
            self.group_dirs["exedra_wiki_voice_human"] / "voice_demo_cn.txt"
        ).relative_to(self.root).as_posix()
        entry = next(item for item in protected["protected_files"] if item["path"] == voice_path)
        entry["sha256"] = "0" * 64
        with self.assertRaisesRegex(GateError, "hash disagrees with protected_files"):
            preflight(
                root=self.root,
                inventory=self.inventory,
                allowlist=self.allowlist,
                package=self.package,
                protection=protected,
                trusted_magia_commit=self.baseline_commit,
                expected_namae_tw_group_count=1,
                expected_namae_tw_json_count=1,
            )

    def test_result_preserves_structure_placeholders_and_speakers(self) -> None:
        checked = self.checked()
        candidates, unresolved = validate_worker_result(
            self.valid_result(), self.package, checked["prepared_entries"]
        )
        self.assertEqual(unresolved, [])
        rendered = render_candidate(candidates[0])
        self.assertIn("いろは：你好\\n${player}", rendered)
        self.assertNotIn("旧机器译文", rendered)

    def test_result_extra_field_is_rejected(self) -> None:
        checked = self.checked()
        result = self.valid_result()
        result["results"][0]["command"] = "write files"
        with self.assertRaisesRegex(GateError, r"extra=\['command'\]"):
            validate_worker_result(result, self.package, checked["prepared_entries"])

    def test_result_honorific_variants_are_rejected(self) -> None:
        for bad in ("忧ちゃん", "忧chan", "忧-chan", "忧酱"):
            with self.subTest(bad=bad):
                self.assertTrue(honorific_violations(bad))
                checked = self.checked()
                result = self.valid_result()
                result["results"][0]["translations"][0]["text"] = bad + "\\n${player}"
                with self.assertRaisesRegex(GateError, "honorific QA failed"):
                    validate_worker_result(result, self.package, checked["prepared_entries"])

    def test_result_placeholder_change_is_rejected(self) -> None:
        checked = self.checked()
        result = self.valid_result()
        result["results"][0]["translations"][0]["text"] = "你好\\n${other}"
        with self.assertRaisesRegex(GateError, "placeholders/control tokens changed"):
            validate_worker_result(result, self.package, checked["prepared_entries"])

    def test_unresolved_segment_is_accounted_for_but_not_staged(self) -> None:
        checked = self.checked()
        result = self.valid_result()
        result["results"][0]["translations"] = []
        result["results"][0]["term_hits"] = []
        result["results"][0]["unresolved"] = [
            {
                "segment_id": "S0001L00001",
                "source": "こんにちは\\n${player}",
                "reason": "缺少经批准的上下文称呼",
            }
        ]
        candidates, unresolved = validate_worker_result(
            result, self.package, checked["prepared_entries"]
        )
        self.assertEqual(candidates, [])
        self.assertEqual(len(unresolved), 1)

    def test_outer_result_requires_exact_deepseek_model(self) -> None:
        inner = self.valid_result()
        parsed, metadata = extract_worker_result(
            {
                "modelUsage": {MODEL: {"inputTokens": 1}},
                "session_id": "session-test",
                "structured_output": inner,
            }
        )
        self.assertEqual(parsed, inner)
        self.assertEqual(metadata["observed_models"], [MODEL])
        with self.assertRaisesRegex(GateError, "worker model mismatch"):
            extract_worker_result(
                {"modelUsage": {"other-model": {}}, "structured_output": inner}
            )

    def test_stage_writes_only_artifact_candidate_and_checkpoint(self) -> None:
        inventory, allowlist, package, protection = self.write_inputs()
        before = self.cn.read_bytes()
        outer = {
            "modelUsage": {MODEL: {"inputTokens": 1}},
            "session_id": "session-test",
            "structured_output": self.valid_result(),
        }

        def fake_worker(_prompt: str, **_kwargs):
            return outer

        report = {
            "validation": {
                "jsonParsed": True,
                "eventCountsMatch": True,
                "sectionAndBranchOrderMatch": True,
                "jsonToTxtRoundTripMatch": True,
                "preservesNonTextTemplate": True,
            },
            "materializedPaths": [self.cn_rel, self.cn_rel.replace(".txt", ".json")],
        }
        output = self.root / "staging"
        with mock.patch(
            "tools.stage_deepseek_translation_batch.materialize", return_value=report
        ) as materializer:
            checkpoint = stage_batch(
                root=self.root,
                inventory_path=inventory,
                allowlist_path=allowlist,
                package_path=package,
                protection_path=protection,
                output_dir=output,
                worker=fake_worker,
                trusted_magia_commit=self.baseline_commit,
                expected_namae_tw_group_count=1,
                expected_namae_tw_json_count=1,
            )
        self.assertEqual(checkpoint["status"], "staged_validated")
        self.assertEqual(self.cn.read_bytes(), before)
        self.assertTrue((output / "candidates/100001_cn.txt").is_file())
        self.assertTrue((output / "checkpoint.json").is_file())
        self.assertFalse(checkpoint["validation"]["formal_tree_written"])
        materializer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
