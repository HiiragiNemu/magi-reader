from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import certify_tw_materialization as tw_cert  # noqa: E402
import materialize_exedra_jp_source as jp_source  # noqa: E402
import organize_exedra_scenarios as organizer  # noqa: E402
import resolve_reader_update_event as event  # noqa: E402
import stage_reader_automation_update as stage_update  # noqa: E402
import tw_sp_handoff_contract as contract  # noqa: E402
import tw_official_import_core as tw_import  # noqa: E402
import verify_tw_source_pin as tw_pin  # noqa: E402


def scenario_bytes(title: str = "Fixture") -> bytes:
    return json.dumps(
        {
            "bookTitle": title,
            "sheetList": [
                {
                    "sheetName": "script",
                    "headerRow": {
                        "cellList": ["ActionType", "Name", "Comment"]
                    },
                    "contentRowList": [
                        {"cellList": ["Talk", "まどか", "official JP text"]}
                    ],
                }
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")


class ReaderUpdateEventTests(unittest.TestCase):
    def test_tw_payload_is_content_addressed_and_exact(self) -> None:
        digest = "a" * 64
        tag = f"tw-wiki-source-v1-{digest}"
        base = "https://github.com/madoka-exedra-wiki/ma-ex-data/releases"
        resolved = event.resolve_tw_payload(
            {
                "schemaVersion": 1,
                "releaseUrl": f"{base}/tag/{tag}",
                "archiveUrl": (
                    f"{base}/download/{tag}/exedra-tw-wiki-source-v1.zip"
                ),
                "archiveSha256": digest,
                "contractUrl": (
                    f"{base}/download/{tag}/exedra-tw-sp-handoff.v1.json"
                ),
                "contractSha256": "b" * 64,
                "sourceRevisions": {
                    "sp": "sp-r1",
                    "scenarios": "scenario-r1",
                    "manifests": "manifest-r1",
                },
            }
        )
        self.assertEqual(resolved["source_repository"], event.TRUSTED_PRODUCER)
        self.assertEqual(resolved["release_tag"], tag)

    def test_tw_payload_rejects_repository_drift(self) -> None:
        digest = "a" * 64
        tag = f"tw-wiki-source-v1-{digest}"
        payload = {
            "schemaVersion": 1,
            "releaseUrl": f"https://github.com/other/data/releases/tag/{tag}",
            "archiveUrl": (
                "https://github.com/other/data/releases/download/"
                f"{tag}/exedra-tw-wiki-source-v1.zip"
            ),
            "archiveSha256": digest,
            "contractUrl": (
                "https://github.com/other/data/releases/download/"
                f"{tag}/exedra-tw-sp-handoff.v1.json"
            ),
            "contractSha256": "b" * 64,
            "sourceRevisions": {
                "sp": "sp-r1",
                "scenarios": "scenario-r1",
                "manifests": "manifest-r1",
            },
        }
        with self.assertRaises(event.UpdateEventError):
            event.resolve_tw_payload(payload)

    def test_jp_payload_pins_one_exact_commit(self) -> None:
        commit = "c" * 40
        resolved = event.resolve_jp_payload(
            {
                "schemaVersion": 1,
                "commitUrl": (
                    f"https://github.com/{event.TRUSTED_PRODUCER}/commit/{commit}"
                ),
                "archiveUrl": (
                    f"https://github.com/{event.TRUSTED_PRODUCER}/archive/{commit}.zip"
                ),
                "commitSha": commit,
                "sourceRevision": commit,
            }
        )
        self.assertEqual(resolved["source_commit"], commit)

    def test_uppercase_revision_is_rejected(self) -> None:
        commit = "c" * 40
        with self.assertRaises(event.UpdateEventError):
            event.resolve_jp_payload(
                {
                    "schemaVersion": 1,
                    "commitUrl": (
                        f"https://github.com/{event.TRUSTED_PRODUCER}/commit/{commit}"
                    ),
                    "archiveUrl": (
                        f"https://github.com/{event.TRUSTED_PRODUCER}/archive/{commit}.zip"
                    ),
                    "commitSha": commit.upper(),
                    "sourceRevision": commit,
                }
            )


class TwCertificationTests(unittest.TestCase):
    def test_dynamic_counts_are_certified_without_historical_constants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            report = root / "report.json"
            story_index = root / "story_index.json"
            scenario = root / "bundle/Resources/Scenarios/1_Main/example"
            manifests = root / "bundle/Manifests"
            scenario.mkdir(parents=True)
            manifests.mkdir(parents=True)
            (scenario / "example.json").write_text("{}\n", encoding="utf-8")
            for name in contract.REQUIRED_MANIFESTS:
                (manifests / name).write_text("{}\n", encoding="utf-8")
            revisions = {
                "sp": "sp-r2",
                "scenarios": "scenario-r2",
                "manifests": "manifest-r2",
            }
            source_contract = contract.build_contract(root, revisions)
            contract_evidence = tw_import.build_source_contract_evidence(
                source_contract,
                scenario_count=1,
                manifest_count=len(contract.REQUIRED_MANIFESTS),
            )
            report.write_text(
                json.dumps(
                    {
                        "status": "materialized",
                        "sourceProvider": "exedra-wiki-sp",
                        "sourceContract": contract_evidence,
                        "sourceInventory": {"scenarioFiles": 1},
                        "stats": {
                            "official_tw_groups": 1,
                            "official_tw_json_files": 1,
                            "official_tw_text_events": 3,
                            "tw_source_files": 1,
                            "tw_source_files_used": 1,
                            "tw_source_files_unused": 0,
                            "tw_source_files_deferred_partial": 0,
                            "tw_source_files_tw_only_without_jp": 0,
                            "tw_source_files_no_text": 0,
                            "tw_source_files_unexpected_unused": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            story_index.write_text(
                json.dumps(
                    [
                        {
                            "official_tw": True,
                            "official_tw_chapter_title": "主线",
                            "official_tw_section_titles": ["第一节"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            values = tw_cert.certify(report, story_index)
            self.assertEqual(values["tw_source_files"], 1)
            self.assertTrue(contract_evidence["complete"])
            self.assertEqual(
                contract_evidence["diagnostics"],
                {"missing": 0, "failure": 0, "parseFailure": 0},
            )
            invalid_contract = dict(source_contract)
            invalid_contract["diagnostics"] = {
                "missing": 0,
                "failure": 1,
                "parseFailure": 0,
            }
            with self.assertRaisesRegex(RuntimeError, "diagnostics"):
                tw_import.build_source_contract_evidence(
                    invalid_contract,
                    scenario_count=1,
                    manifest_count=len(contract.REQUIRED_MANIFESTS),
                )


class TwNonRegressionTests(unittest.TestCase):
    def test_coverage_growth_is_accepted(self) -> None:
        previous = {
            "status": "materialized",
            "stats": {field: 10 for field in tw_import.TW_NON_REGRESSION_FIELDS},
        }
        current = {field: 11 for field in tw_import.TW_NON_REGRESSION_FIELDS}
        tw_import.enforce_tw_non_regression(current, previous)

    def test_coverage_shrink_is_rejected(self) -> None:
        previous = {
            "status": "materialized",
            "stats": {field: 10 for field in tw_import.TW_NON_REGRESSION_FIELDS},
        }
        current = {field: 10 for field in tw_import.TW_NON_REGRESSION_FIELDS}
        current["official_tw_text_events"] = 9
        with self.assertRaisesRegex(
            RuntimeError,
            r"official_tw_text_events 9 < 10",
        ):
            tw_import.enforce_tw_non_regression(current, previous)


class TwPinTests(unittest.TestCase):
    def test_contract_and_source_revisions_must_match_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            scenario = root / "bundle/Resources/Scenarios/1_Main/example"
            manifests = root / "bundle/Manifests"
            scenario.mkdir(parents=True)
            manifests.mkdir(parents=True)
            (scenario / "example.json").write_text("{}\n", encoding="utf-8")
            for name in contract.REQUIRED_MANIFESTS:
                (manifests / name).write_text("{}\n", encoding="utf-8")
            revisions = {
                "sp": "sp-r1",
                "scenarios": "scenario-r1",
                "manifests": "manifest-r1",
            }
            path = contract.write_contract_atomic(
                root, contract.build_contract(root, revisions)
            )
            digest, _ = contract._hash_file(path)
            result = tw_pin.verify_pins(
                root,
                contract_sha256=digest,
                sp_revision=revisions["sp"],
                scenario_revision=revisions["scenarios"],
                manifest_revision=revisions["manifests"],
            )
            self.assertEqual(result["contract_sha256"], digest)
            with self.assertRaises(tw_pin.PinError):
                tw_pin.verify_pins(
                    root,
                    contract_sha256=digest,
                    sp_revision="wrong",
                    scenario_revision=revisions["scenarios"],
                    manifest_revision=revisions["manifests"],
                )


class JpMaterializationTests(unittest.TestCase):
    def test_unsuffixed_jp_is_selected_and_localized_copy_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            source = root / "source"
            for category in organizer.CATEGORY_ORDER:
                (source / category).mkdir(parents=True)
            group = source / "1_Main/main_fixture1_1"
            group.mkdir()
            (group / "main_fixture1_1.json").write_bytes(scenario_bytes())
            (group / "main_fixture1_1_zh-Hant.json").write_bytes(
                scenario_bytes("localized copy")
            )
            (group / "main_fixture1_1_zh-Hant-TW.json").write_bytes(
                scenario_bytes("localized region copy")
            )
            (group / "main_fixture1_1_sub.json").write_bytes(
                scenario_bytes("legitimate JP suffix")
            )
            output = root / "organized"
            receipt_path = root / "receipt.json"
            receipt = jp_source.materialize(
                source,
                output,
                receipt_path,
                source_repository=jp_source.TRUSTED_SOURCE_REPOSITORY,
                source_commit="d" * 40,
                current_root=None,
            )
            self.assertEqual(receipt["sourceFileCount"], 4)
            self.assertEqual(receipt["selectedFileCount"], 2)
            self.assertFalse(any(output.rglob("*_zh-Hant*.json")))
            self.assertTrue(any(output.rglob("*_sub.json")))


class StageAllowlistTests(unittest.TestCase):
    def _repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(
            ["git", "-C", str(root), "config", "user.name", "Fixture"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "fixture@example.invalid"],
            check=True,
        )
        path = root / "website/public/story_index.json"
        path.parent.mkdir(parents=True)
        path.write_text("[]\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "--", "."], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-qm", "fixture"], check=True
        )
        return temporary, root

    def test_only_machine_owned_paths_are_staged(self) -> None:
        temporary, root = self._repo()
        previous = Path.cwd()
        try:
            os.chdir(root)
            (root / "website/public/story_index.json").write_text(
                '[{"id":"new"}]\n', encoding="utf-8"
            )
            staged = stage_update.stage("tw")
            self.assertEqual(staged, ["website/public/story_index.json"])
        finally:
            os.chdir(previous)
            temporary.cleanup()

    def test_unrelated_ui_change_is_rejected(self) -> None:
        temporary, root = self._repo()
        previous = Path.cwd()
        try:
            os.chdir(root)
            forbidden = root / "website/src/app/page.tsx"
            forbidden.parent.mkdir(parents=True)
            forbidden.write_text("export default 1;\n", encoding="utf-8")
            with self.assertRaises(stage_update.StageError):
                stage_update.stage("jp")
        finally:
            os.chdir(previous)
            temporary.cleanup()


class WorkflowContractTests(unittest.TestCase):
    def test_workflows_are_fail_closed_and_deploy_explicitly(self) -> None:
        tw = (ROOT / ".github/workflows/materialize-tw-official-cn.yml").read_text(
            encoding="utf-8"
        )
        jp = (ROOT / ".github/workflows/materialize-exedra-jp-source.yml").read_text(
            encoding="utf-8"
        )
        deploy = (ROOT / ".github/workflows/deploy.yml").read_text(
            encoding="utf-8"
        )
        for workflow in (tw, jp):
            self.assertIn("EXEDRA_READER_AUTOMATION_ENABLED == 'true'", workflow)
            self.assertIn("EXEDRA_WIKI_SOURCE_TOKEN is required", workflow)
            self.assertIn("uses: ./.github/workflows/deploy.yml", workflow)
            self.assertIn("python tools/stage_reader_automation_update.py", workflow)
            self.assertNotIn("git add -A\n", workflow)
        self.assertNotIn("tw-wiki-source-v1-20260806", tw)
        self.assertIn("sparse-checkout set", jp)
        self.assertIn("--filter=blob:none --no-tags --depth=1", jp)
        self.assertNotIn("repository: ${{ steps.source.outputs.source_repository }}", jp)
        self.assertIn("workflow_call:", deploy)
        self.assertIn("[tw-materialized]", deploy)
        self.assertIn("[jp-materialized]", deploy)


if __name__ == "__main__":
    unittest.main()
