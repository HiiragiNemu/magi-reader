from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tw_sp_handoff_contract as contract  # noqa: E402


class TwSpHandoffContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.scenarios = self.root / "bundle/Resources/Scenarios"
        self.manifests = self.root / "bundle/Manifests"
        self.scenarios.mkdir(parents=True)
        self.manifests.mkdir(parents=True)
        (self.scenarios / "1_Main/example").mkdir(parents=True)
        (self.scenarios / "1_Main/example/example.json").write_text(
            json.dumps({"text": "台服正文"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        for index, name in enumerate(contract.REQUIRED_MANIFESTS, 1):
            (self.manifests / name).write_text(
                json.dumps({"payload": {"mstList": [{"id": index}]}}) + "\n",
                encoding="utf-8",
            )
        self.revisions = {
            "sp": "wiki-sp-release-2026-08-04",
            "scenarios": "scenario-catalog-r1",
            "manifests": "manifest-catalog-r1",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_build_write_and_verify(self) -> None:
        value = contract.build_contract(self.root, self.revisions)
        path = contract.write_contract_atomic(self.root, value)
        self.assertEqual(path.name, contract.CONTRACT_FILENAME)
        verified = contract.verify_contract(self.root)
        self.assertEqual(verified, value)
        self.assertTrue(verified["complete"])
        self.assertEqual(verified["provenance"], contract.PROVENANCE)
        self.assertEqual(
            verified["diagnostics"],
            {"missing": 0, "failure": 0, "parseFailure": 0},
        )
        self.assertEqual(verified["catalogs"]["scenarios"]["fileCount"], 1)
        self.assertEqual(verified["catalogs"]["manifests"]["fileCount"], 3)

    def test_output_is_byte_deterministic(self) -> None:
        first = contract.build_contract(self.root, self.revisions)
        target = contract.write_contract_atomic(self.root, first)
        first_bytes = target.read_bytes()
        second = contract.build_contract(self.root, self.revisions)
        contract.write_contract_atomic(self.root, second)
        self.assertEqual(target.read_bytes(), first_bytes)
        self.assertEqual(first, second)

    def test_tree_hash_matches_documented_sequence(self) -> None:
        value = contract.build_contract(self.root, self.revisions)
        record = value["catalogs"]["scenarios"]["files"][0]
        path = self.root.joinpath(*Path(record["path"]).parts)
        expected = hashlib.sha256()
        expected.update(record["path"].encode("utf-8"))
        expected.update(b"\0")
        expected.update(str(record["bytes"]).encode("ascii"))
        expected.update(b"\0")
        expected.update(path.read_bytes())
        self.assertEqual(
            value["catalogs"]["scenarios"]["treeSha256"], expected.hexdigest()
        )

    def test_tampered_file_is_rejected(self) -> None:
        contract.write_contract_atomic(
            self.root, contract.build_contract(self.root, self.revisions)
        )
        scenario = self.scenarios / "1_Main/example/example.json"
        scenario.write_text('{"text":"已改变"}\n', encoding="utf-8")
        with self.assertRaisesRegex(contract.ContractError, "scenarios 目录与合同不一致"):
            contract.verify_contract(self.root)

    def test_missing_required_manifest_is_rejected(self) -> None:
        (self.manifests / contract.REQUIRED_MANIFESTS[0]).unlink()
        with self.assertRaisesRegex(contract.ContractError, "缺少必需 Manifest"):
            contract.build_contract(self.root, self.revisions)

    def test_invalid_json_is_rejected_without_overwriting_contract(self) -> None:
        target = contract.write_contract_atomic(
            self.root, contract.build_contract(self.root, self.revisions)
        )
        before = target.read_bytes()
        (self.scenarios / "broken.json").write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(contract.ContractError, "JSON 解析失败"):
            contract.build_contract(self.root, self.revisions)
        self.assertEqual(target.read_bytes(), before)

    def test_nested_manifest_json_is_rejected(self) -> None:
        nested = self.manifests / "unexpected"
        nested.mkdir()
        (nested / "hidden.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(contract.ContractError, "Manifest 目录含嵌套 JSON"):
            contract.build_contract(self.root, self.revisions)

    def test_source_revisions_are_all_required(self) -> None:
        with self.assertRaisesRegex(contract.ContractError, "必须且只能包含"):
            contract.build_contract(self.root, {"sp": "r1", "scenarios": "r2"})

    def test_shape_rejects_incomplete_and_diagnostics(self) -> None:
        value = contract.build_contract(self.root, self.revisions)
        value["complete"] = False
        with self.assertRaisesRegex(contract.ContractError, "complete 必须为 true"):
            contract.validate_contract_shape(value)
        value["complete"] = True
        value["diagnostics"]["missing"] = 1
        with self.assertRaisesRegex(contract.ContractError, "必须全部为 0"):
            contract.validate_contract_shape(value)

    def test_shape_rejects_changed_provenance(self) -> None:
        value = contract.build_contract(self.root, self.revisions)
        value["provenance"]["authority"] = "unknown"
        with self.assertRaisesRegex(contract.ContractError, "provenance"):
            contract.validate_contract_shape(value)

    def test_shape_rejects_catalog_path_and_catalog_hash_drift(self) -> None:
        value = contract.build_contract(self.root, self.revisions)
        value["catalogs"]["scenarios"]["files"][0]["path"] = "outside/example.json"
        with self.assertRaisesRegex(contract.ContractError, "固定根目录"):
            contract.validate_contract_shape(value)

        value = contract.build_contract(self.root, self.revisions)
        value["catalogs"]["scenarios"]["files"][0]["path"] = (
            value["catalogs"]["scenarios"]["files"][0]["path"].replace("/", "\\")
        )
        with self.assertRaisesRegex(contract.ContractError, "非法合同相对路径"):
            contract.validate_contract_shape(value)

        value = contract.build_contract(self.root, self.revisions)
        value["catalogs"]["scenarios"]["catalogSha256"] = "0" * 64
        with self.assertRaisesRegex(contract.ContractError, "目录清单哈希"):
            contract.validate_contract_shape(value)

    def test_shape_rejects_boolean_integer_fields(self) -> None:
        value = contract.build_contract(self.root, self.revisions)
        value["schemaVersion"] = True
        with self.assertRaisesRegex(contract.ContractError, "schemaVersion"):
            contract.validate_contract_shape(value)

        value = contract.build_contract(self.root, self.revisions)
        value["diagnostics"]["missing"] = False
        with self.assertRaisesRegex(contract.ContractError, "必须全部为 0"):
            contract.validate_contract_shape(value)

        value = contract.build_contract(self.root, self.revisions)
        value["catalogs"]["scenarios"]["fileCount"] = True
        with self.assertRaisesRegex(contract.ContractError, "fileCount"):
            contract.validate_contract_shape(value)

        value = contract.build_contract(self.root, self.revisions)
        value["provenance"]["originalTextUnmodified"] = 1
        with self.assertRaisesRegex(contract.ContractError, "provenance"):
            contract.validate_contract_shape(value)

    def test_contract_json_rejects_duplicate_fields(self) -> None:
        target = contract.write_contract_atomic(
            self.root, contract.build_contract(self.root, self.revisions)
        )
        value = target.read_text(encoding="utf-8")
        target.write_text(
            value.replace(
                '  "schemaVersion": 1,',
                '  "schemaVersion": 1,\n  "schemaVersion": 1,',
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(contract.ContractError, "重复字段"):
            contract.verify_contract(self.root)

    def test_verify_requires_contract_at_handoff_root(self) -> None:
        root_contract = contract.write_contract_atomic(
            self.root, contract.build_contract(self.root, self.revisions)
        )
        outside = self.root / "outside" / contract.CONTRACT_FILENAME
        outside.parent.mkdir()
        outside.write_bytes(root_contract.read_bytes())
        with self.assertRaisesRegex(contract.ContractError, "必须位于交接根目录"):
            contract.verify_contract(self.root, outside)


if __name__ == "__main__":
    unittest.main()
