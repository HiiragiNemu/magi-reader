from __future__ import annotations

import hashlib
import io
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import fetch_tw_sp_source_bundle as source_bundle  # noqa: E402
import tw_sp_handoff_contract as contract  # noqa: E402


class FakeResponse(io.BytesIO):
    def __init__(self, value: bytes, url: str) -> None:
        super().__init__(value)
        self._url = url

    def geturl(self) -> str:
        return self._url


class TwSpSourceBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.handoff = self.root / "handoff"
        self.scenarios = self.handoff / "bundle/Resources/Scenarios/1_Main/example"
        self.manifests = self.handoff / "bundle/Manifests"
        self.scenarios.mkdir(parents=True)
        self.manifests.mkdir(parents=True)
        (self.scenarios / "example.json").write_text(
            json.dumps({"text": "台服正文"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        for index, name in enumerate(contract.REQUIRED_MANIFESTS, 1):
            (self.manifests / name).write_text(
                json.dumps({"payload": {"mstList": [{"id": index}]}}) + "\n",
                encoding="utf-8",
            )
        value = contract.build_contract(
            self.handoff,
            {"sp": "sp-r1", "scenarios": "scenario-r1", "manifests": "manifest-r1"},
        )
        contract.write_contract_atomic(self.handoff, value)
        self.archive = self.root / "source.zip"
        self._write_archive(self.archive)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_archive(self, target: Path) -> None:
        with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(self.handoff.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(self.handoff).as_posix())

    def _sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_pinned_release_defaults_are_exact(self) -> None:
        self.assertEqual(
            source_bundle.DEFAULT_SOURCE_URL,
            "https://github.com/HiiragiNemu/MagiaExedraTWData/releases/download/"
            "tw-wiki-source-v1-20260806/exedra-tw-wiki-source-v1.zip",
        )
        self.assertEqual(
            source_bundle.DEFAULT_SOURCE_SHA256,
            "503c4c9a518d0a992abe800fccde4a97b35b2e4ddaeb2359e63eaa8d572cd1ac",
        )

    def test_offline_archive_is_verified_and_installed(self) -> None:
        output = self.root / "installed"
        with mock.patch.object(
            source_bundle,
            "download_archive",
            side_effect=AssertionError("offline mode attempted network fetch"),
        ):
            result = source_bundle.main(
                [
                    "--archive",
                    str(self.archive),
                    "--source-sha256",
                    self._sha256(self.archive),
                    "--output-root",
                    str(output),
                ]
            )
        self.assertEqual(result, 0)
        verified = contract.verify_contract(output)
        self.assertEqual(verified["diagnostics"], {
            "missing": 0,
            "failure": 0,
            "parseFailure": 0,
        })
        self.assertEqual(verified["catalogs"]["scenarios"]["fileCount"], 1)
        self.assertEqual(verified["catalogs"]["manifests"]["fileCount"], 3)

    def test_download_streams_through_injected_offline_opener(self) -> None:
        payload = b"offline fixture bytes"
        target = self.root / "downloaded.zip"
        calls: list[tuple[str, int]] = []

        def opener(request: object, *, timeout: int) -> FakeResponse:
            calls.append((request.full_url, timeout))  # type: ignore[attr-defined]
            return FakeResponse(payload, "https://fixtures.invalid/source.zip")

        digest = source_bundle.download_archive(
            "https://fixtures.invalid/source.zip",
            target,
            timeout_seconds=7,
            opener=opener,
        )
        self.assertEqual(calls, [("https://fixtures.invalid/source.zip", 7)])
        self.assertEqual(target.read_bytes(), payload)
        self.assertEqual(digest.sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(digest.bytes, len(payload))

    def test_outer_sha256_mismatch_fails_before_extraction(self) -> None:
        output = self.root / "wrong-hash-output"
        with self.assertRaisesRegex(source_bundle.SourceBundleError, "SHA-256 mismatch"):
            source_bundle.install_archive(self.archive, output, "0" * 64)
        self.assertFalse(output.exists())

    def test_contract_hash_mismatch_rejects_tampered_json(self) -> None:
        scenario = self.scenarios / "example.json"
        before = scenario.read_bytes()
        scenario.write_bytes(before.replace("台".encode(), "臺".encode()))
        self.assertEqual(len(scenario.read_bytes()), len(before))
        tampered = self.root / "tampered.zip"
        self._write_archive(tampered)
        output = self.root / "tampered-output"
        with self.assertRaisesRegex(
            source_bundle.SourceBundleError,
            "content disagrees with root contract",
        ):
            source_bundle.install_archive(tampered, output, self._sha256(tampered))
        self.assertFalse(output.exists())

    def test_nonzero_contract_diagnostics_are_rejected(self) -> None:
        path = self.handoff / contract.CONTRACT_FILENAME
        value = json.loads(path.read_text(encoding="utf-8"))
        value["diagnostics"]["failure"] = 1
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        invalid = self.root / "invalid-diagnostics.zip"
        self._write_archive(invalid)
        output = self.root / "invalid-diagnostics-output"
        with self.assertRaisesRegex(contract.ContractError, "必须全部为 0"):
            source_bundle.install_archive(invalid, output, self._sha256(invalid))
        self.assertFalse(output.exists())

    def test_path_traversal_is_rejected_without_writing_outside_root(self) -> None:
        malicious = self.root / "traversal.zip"
        malicious.write_bytes(self.archive.read_bytes())
        with ZipFile(malicious, "a", compression=ZIP_DEFLATED) as archive:
            archive.writestr("../escaped.json", "{}\n")
        output = self.root / "traversal-output"
        escaped = self.root / "escaped.json"
        with self.assertRaisesRegex(source_bundle.SourceBundleError, "invalid ZIP member"):
            source_bundle.install_archive(malicious, output, self._sha256(malicious))
        self.assertFalse(output.exists())
        self.assertFalse(escaped.exists())

    def test_symbolic_link_member_is_rejected(self) -> None:
        malicious = self.root / "symlink.zip"
        malicious.write_bytes(self.archive.read_bytes())
        link = ZipInfo("bundle/Resources/Scenarios/link.json")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with ZipFile(malicious, "a") as archive:
            archive.writestr(link, "../../../../outside.json")
        output = self.root / "symlink-output"
        with self.assertRaisesRegex(source_bundle.SourceBundleError, "symbolic link"):
            source_bundle.install_archive(malicious, output, self._sha256(malicious))
        self.assertFalse(output.exists())

    def test_nested_root_contract_is_rejected(self) -> None:
        nested = self.root / "nested.zip"
        with ZipFile(nested, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(self.handoff.rglob("*")):
                if path.is_file():
                    relative = path.relative_to(self.handoff).as_posix()
                    archive.write(path, f"wrapper/{relative}")
        output = self.root / "nested-output"
        with self.assertRaisesRegex(source_bundle.SourceBundleError, "v1 bundle contract"):
            source_bundle.install_archive(nested, output, self._sha256(nested))
        self.assertFalse(output.exists())

    def test_existing_output_is_preserved(self) -> None:
        output = self.root / "existing"
        output.mkdir()
        marker = output / "marker.txt"
        marker.write_text("keep\n", encoding="utf-8")
        with self.assertRaisesRegex(source_bundle.SourceBundleError, "already exists"):
            source_bundle.install_archive(self.archive, output, self._sha256(self.archive))
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")

    def test_failed_install_does_not_delete_concurrently_created_output(self) -> None:
        output = self.root / "concurrent"
        marker = output / "marker.txt"

        def fail_before_publish(_archive: Path, _staging: Path) -> object:
            output.mkdir()
            marker.write_text("keep\n", encoding="utf-8")
            raise source_bundle.SourceBundleError("fixture failure")

        with mock.patch.object(
            source_bundle,
            "_extract_archive",
            side_effect=fail_before_publish,
        ):
            with self.assertRaisesRegex(source_bundle.SourceBundleError, "fixture failure"):
                source_bundle.install_archive(
                    self.archive,
                    output,
                    self._sha256(self.archive),
                )
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")

    def test_workflow_uses_verified_sp_bundle_contract(self) -> None:
        workflow = (
            ROOT / ".github/workflows/materialize-tw-official-cn.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("tools/fetch_tw_sp_source_bundle.py", workflow)
        self.assertIn('--source-bundle-root "$RUNNER_TEMP/tw-sp-bundle"', workflow)
        self.assertIn("--source-provider exedra-wiki-sp", workflow)
        self.assertIn(source_bundle.DEFAULT_SOURCE_URL, workflow)
        self.assertIn(source_bundle.DEFAULT_SOURCE_SHA256, workflow)
        self.assertNotIn("--scenario-root .tw-official-source/scenarios", workflow)
        self.assertNotIn("tools/extract_tw_compact_sources.py", workflow)


if __name__ == "__main__":
    unittest.main()
