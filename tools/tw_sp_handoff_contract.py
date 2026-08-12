#!/usr/bin/env python3
"""Build and verify the deterministic Exedra Wiki SP handoff contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

CONTRACT_FILENAME = "exedra-tw-sp-handoff.v1.json"
SCHEMA_VERSION = 1
CONTRACT_NAME = "exedra-tw-sp-handoff"
TREE_HASH_ALGORITHM = "sha256-path-nul-size-nul-content-v1"
CATALOG_HASH_ALGORITHM = "sha256-canonical-json-files-v1"
HASH_CHUNK_BYTES = 1024 * 1024
MAX_CONTRACT_BYTES = 64 * 1024 * 1024
MAX_JSON_FILE_BYTES = 256 * 1024 * 1024
MAX_CATALOG_FILES = 100_000
REQUIRED_MANIFESTS = (
    "getAdvMstList.json",
    "getCollectionConditionMstList.json",
    "getFieldStageMstList.json",
)
SOURCE_REVISION_KEYS = ("sp", "scenarios", "manifests")
PROVENANCE = {
    "provider": "exedra-wiki-sp",
    "locale": "zh-Hant-TW",
    "authority": "official-tw-client",
    "originalTextUnmodified": True,
    "textTransformation": "reader-tw2sp",
}


class ContractError(RuntimeError):
    """Raised when a handoff package cannot satisfy the v1 contract."""


@dataclass(frozen=True)
class FileRecord:
    path: str
    bytes: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "bytes": self.bytes, "sha256": self.sha256}


@dataclass(frozen=True)
class CatalogSpec:
    name: str
    root: str
    pattern: str
    recursive: bool


CATALOG_SPECS = (
    CatalogSpec(
        name="scenarios",
        root="bundle/Resources/Scenarios",
        pattern="**/*.json",
        recursive=True,
    ),
    CatalogSpec(
        name="manifests",
        root="bundle/Manifests",
        pattern="*.json",
        recursive=False,
    ),
)


def catalog_record_matches_spec(spec: CatalogSpec, value: str) -> bool:
    """Return whether one normalized file path belongs to its fixed v1 catalog."""

    path = PurePosixPath(_nfc_posix(value))
    root = PurePosixPath(spec.root)
    root_parts = root.parts
    if path.parts[: len(root_parts)] != root_parts:
        return False
    relative_parts = path.parts[len(root_parts) :]
    if not relative_parts or path.suffix.casefold() != ".json":
        return False
    return spec.recursive or len(relative_parts) == 1


def _nfc_posix(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized != value
        or "\\" in normalized
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != normalized
    ):
        raise ContractError(f"非法合同相对路径：{value!r}")
    return path.as_posix()


def _resolve_under(root: Path, relative: str, *, directory: bool = False) -> Path:
    root_resolved = root.resolve(strict=True)
    candidate = root_resolved.joinpath(*PurePosixPath(_nfc_posix(relative)).parts)
    if candidate.is_symlink():
        raise ContractError(f"交接路径类型无效：{relative}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ContractError(f"路径越出交接根目录：{relative}") from exc
    if resolved.is_symlink() or (directory and not resolved.is_dir()):
        raise ContractError(f"交接路径类型无效：{relative}")
    return resolved


def _walk_catalog(root: Path, *, recursive: bool) -> list[Path]:
    """Return regular JSON files while rejecting symlinks and nested manifests."""

    files: list[Path] = []
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for directory in directories:
            child = current_path / directory
            if child.is_symlink():
                raise ContractError(f"来源目录含符号链接：{child}")
        if not recursive and current_path == root:
            for directory in directories:
                child = current_path / directory
                if next(child.rglob("*.json"), None) is not None:
                    raise ContractError(f"Manifest 目录含嵌套 JSON：{child}")
        if not recursive and current_path != root:
            if any(name.casefold().endswith(".json") for name in names):
                raise ContractError(f"Manifest 目录含嵌套 JSON：{current_path}")
            directories[:] = []
            continue
        for name in names:
            path = current_path / name
            if path.is_symlink():
                raise ContractError(f"来源目录含符号链接：{path}")
            if path.is_file() and path.suffix.casefold() == ".json":
                files.append(path)
                if len(files) > MAX_CATALOG_FILES:
                    raise ContractError(
                        f"单个目录超过文件上限 {MAX_CATALOG_FILES}：{root}"
                    )
        if not recursive:
            directories[:] = []
    return sorted(files, key=lambda path: unicodedata.normalize("NFC", path.as_posix()))


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = path.stat().st_size
    with path.open("rb") as source:
        while chunk := source.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest(), size


def _validate_json_file(path: Path, size: int) -> None:
    if size > MAX_JSON_FILE_BYTES:
        raise ContractError(
            f"单个 JSON 超过解析上限 {MAX_JSON_FILE_BYTES} bytes：{path}"
        )
    try:
        with path.open("r", encoding="utf-8-sig") as source:
            json.load(source)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"JSON 解析失败：{path}: {exc}") from exc


def _tree_hash(records: Iterable[FileRecord], handoff_root: Path) -> str:
    """Hash sorted contract paths, decimal sizes, and file bytes in 1 MiB chunks."""

    digest = hashlib.sha256()
    for record in records:
        digest.update(record.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record.bytes).encode("ascii"))
        digest.update(b"\0")
        path = _resolve_under(handoff_root, record.path)
        with path.open("rb") as source:
            while chunk := source.read(HASH_CHUNK_BYTES):
                digest.update(chunk)
    return digest.hexdigest()


def _catalog_hash(records: Iterable[FileRecord]) -> str:
    payload = json.dumps(
        [record.as_dict() for record in records],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def scan_catalog(handoff_root: Path, spec: CatalogSpec) -> dict[str, Any]:
    catalog_root = _resolve_under(handoff_root, spec.root, directory=True)
    paths = _walk_catalog(catalog_root, recursive=spec.recursive)
    if not paths:
        raise ContractError(f"目录没有 JSON：{spec.root}")

    records: list[FileRecord] = []
    casefold_paths: dict[str, str] = {}
    parse_failures: list[str] = []
    handoff_resolved = handoff_root.resolve(strict=True)
    for path in paths:
        resolved = path.resolve(strict=True)
        try:
            relative = _nfc_posix(resolved.relative_to(handoff_resolved).as_posix())
        except ValueError as exc:
            raise ContractError(f"来源文件越出交接根目录：{path}") from exc
        folded = relative.casefold()
        previous = casefold_paths.get(folded)
        if previous is not None and previous != relative:
            raise ContractError(f"来源路径大小写冲突：{previous!r} / {relative!r}")
        casefold_paths[folded] = relative
        digest, size = _hash_file(resolved)
        try:
            _validate_json_file(resolved, size)
        except ContractError as exc:
            parse_failures.append(str(exc))
        records.append(FileRecord(relative, size, digest))

    if parse_failures:
        raise ContractError(
            f"{spec.name} 存在 {len(parse_failures)} 个 JSON 解析失败；"
            f"首个：{parse_failures[0]}"
        )
    records.sort(key=lambda item: item.path)
    return {
        "root": spec.root,
        "pattern": spec.pattern,
        "treeHashAlgorithm": TREE_HASH_ALGORITHM,
        "treeSha256": _tree_hash(records, handoff_root),
        "catalogHashAlgorithm": CATALOG_HASH_ALGORITHM,
        "catalogSha256": _catalog_hash(records),
        "fileCount": len(records),
        "byteCount": sum(record.bytes for record in records),
        "files": [record.as_dict() for record in records],
    }


def _validate_revisions(revisions: dict[str, str]) -> dict[str, str]:
    if set(revisions) != set(SOURCE_REVISION_KEYS):
        raise ContractError(
            f"sourceRevisions 必须且只能包含：{', '.join(SOURCE_REVISION_KEYS)}"
        )
    result: dict[str, str] = {}
    for key in SOURCE_REVISION_KEYS:
        value = revisions.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise ContractError(f"来源版本无效：{key}")
        result[key] = value.strip()
    return result


def build_contract(handoff_root: Path, revisions: dict[str, str]) -> dict[str, Any]:
    if handoff_root.is_symlink():
        raise ContractError(f"交接根目录无效：{handoff_root}")
    root = handoff_root.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ContractError(f"交接根目录无效：{handoff_root}")
    normalized_revisions = _validate_revisions(revisions)
    catalogs = {spec.name: scan_catalog(root, spec) for spec in CATALOG_SPECS}
    manifest_names = {
        PurePosixPath(item["path"]).name
        for item in catalogs["manifests"]["files"]
    }
    missing = sorted(set(REQUIRED_MANIFESTS) - manifest_names)
    if missing:
        raise ContractError(f"缺少必需 Manifest：{missing}")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "contractName": CONTRACT_NAME,
        "complete": True,
        "provenance": dict(PROVENANCE),
        "sourceRevisions": normalized_revisions,
        "diagnostics": {"missing": 0, "failure": 0, "parseFailure": 0},
        "requiredManifests": list(REQUIRED_MANIFESTS),
        "catalogs": catalogs,
    }


def _require_sha256(value: Any, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ContractError(f"{field} 不是小写 SHA-256")


def validate_contract_shape(contract: Any) -> dict[str, Any]:
    if not isinstance(contract, dict):
        raise ContractError("合同顶层必须是对象")
    expected_top = {
        "schemaVersion",
        "contractName",
        "complete",
        "provenance",
        "sourceRevisions",
        "diagnostics",
        "requiredManifests",
        "catalogs",
    }
    if set(contract) != expected_top:
        raise ContractError(f"合同顶层字段不匹配：{sorted(contract)}")
    if (
        type(contract.get("schemaVersion")) is not int
        or contract.get("schemaVersion") != SCHEMA_VERSION
    ):
        raise ContractError("schemaVersion 必须为 1")
    if contract.get("contractName") != CONTRACT_NAME:
        raise ContractError("contractName 无效")
    if contract.get("complete") is not True:
        raise ContractError("complete 必须为 true")
    provenance = contract.get("provenance")
    if (
        not isinstance(provenance, dict)
        or set(provenance) != set(PROVENANCE)
        or any(
            type(provenance[key]) is not type(expected)
            or provenance[key] != expected
            for key, expected in PROVENANCE.items()
        )
    ):
        raise ContractError("provenance 与 v1 来源政策不一致")
    revisions = contract.get("sourceRevisions")
    if not isinstance(revisions, dict):
        raise ContractError("sourceRevisions 必须是对象")
    _validate_revisions(revisions)
    diagnostics = contract.get("diagnostics")
    if (
        not isinstance(diagnostics, dict)
        or set(diagnostics) != {"missing", "failure", "parseFailure"}
        or any(
            type(diagnostics[key]) is not int or diagnostics[key] != 0
            for key in diagnostics
        )
    ):
        raise ContractError("missing/failure/parseFailure 必须全部为 0")
    if contract.get("requiredManifests") != list(REQUIRED_MANIFESTS):
        raise ContractError("requiredManifests 与 v1 合同不一致")

    catalogs = contract.get("catalogs")
    if not isinstance(catalogs, dict) or set(catalogs) != {
        spec.name for spec in CATALOG_SPECS
    }:
        raise ContractError("catalogs 必须包含 scenarios 和 manifests")
    for spec in CATALOG_SPECS:
        value = catalogs.get(spec.name)
        if not isinstance(value, dict):
            raise ContractError(f"catalog 无效：{spec.name}")
        expected_fields = {
            "root",
            "pattern",
            "treeHashAlgorithm",
            "treeSha256",
            "catalogHashAlgorithm",
            "catalogSha256",
            "fileCount",
            "byteCount",
            "files",
        }
        if set(value) != expected_fields:
            raise ContractError(f"catalog 字段无效：{spec.name}")
        if value.get("root") != spec.root or value.get("pattern") != spec.pattern:
            raise ContractError(f"catalog 路径约定无效：{spec.name}")
        if value.get("treeHashAlgorithm") != TREE_HASH_ALGORITHM:
            raise ContractError(f"树哈希算法无效：{spec.name}")
        if value.get("catalogHashAlgorithm") != CATALOG_HASH_ALGORITHM:
            raise ContractError(f"目录哈希算法无效：{spec.name}")
        _require_sha256(value.get("treeSha256"), f"{spec.name}.treeSha256")
        _require_sha256(value.get("catalogSha256"), f"{spec.name}.catalogSha256")
        files = value.get("files")
        if not isinstance(files, list) or not files:
            raise ContractError(f"catalog files 无效：{spec.name}")
        if len(files) > MAX_CATALOG_FILES:
            raise ContractError(
                f"catalog files 超过上限 {MAX_CATALOG_FILES}：{spec.name}"
            )
        if (
            type(value.get("fileCount")) is not int
            or value.get("fileCount") != len(files)
        ):
            raise ContractError(f"catalog fileCount 不匹配：{spec.name}")
        byte_total = 0
        previous = ""
        seen: set[str] = set()
        records: list[FileRecord] = []
        for item in files:
            if (
                not isinstance(item, dict)
                or set(item) != {"path", "bytes", "sha256"}
            ):
                raise ContractError(f"catalog file 记录无效：{spec.name}")
            raw_path = item.get("path") if isinstance(item.get("path"), str) else ""
            path = _nfc_posix(raw_path)
            if not catalog_record_matches_spec(spec, path):
                raise ContractError(
                    f"catalog 路径越出固定根目录：{spec.name}: {path}"
                )
            if path <= previous:
                raise ContractError(f"catalog files 未严格按路径排序：{spec.name}")
            previous = path
            if path.casefold() in seen:
                raise ContractError(f"catalog 路径重复：{path}")
            seen.add(path.casefold())
            size = item.get("bytes")
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise ContractError(f"catalog 文件大小无效：{path}")
            _require_sha256(item.get("sha256"), f"{path}.sha256")
            byte_total += size
            records.append(FileRecord(path, size, item["sha256"]))
        if (
            type(value.get("byteCount")) is not int
            or value.get("byteCount") != byte_total
        ):
            raise ContractError(f"catalog byteCount 不匹配：{spec.name}")
        if value.get("catalogSha256") != _catalog_hash(records):
            raise ContractError(f"catalog 目录清单哈希不匹配：{spec.name}")
        if spec.name == "manifests":
            manifest_names = {PurePosixPath(record.path).name for record in records}
            missing = sorted(set(REQUIRED_MANIFESTS) - manifest_names)
            if missing:
                raise ContractError(f"缺少必需 Manifest：{missing}")
    return contract


def canonical_contract_bytes(contract: dict[str, Any]) -> bytes:
    return (
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"合同 JSON 含重复字段：{key}")
        result[key] = value
    return result


def parse_contract_bytes(payload: bytes) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8-sig")
        value = json.loads(text, object_pairs_hook=_strict_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"合同 JSON 无法读取：{exc}") from exc
    return validate_contract_shape(value)


def write_contract_atomic(handoff_root: Path, contract: dict[str, Any]) -> Path:
    target = handoff_root.resolve(strict=True) / CONTRACT_FILENAME
    payload = canonical_contract_bytes(validate_contract_shape(contract))
    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{CONTRACT_FILENAME}.",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    ) as temporary:
        temporary.write(payload)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)
    return target


def load_contract(path: Path) -> dict[str, Any]:
    if path.name != CONTRACT_FILENAME:
        raise ContractError(f"合同文件名必须是 {CONTRACT_FILENAME}")
    if path.is_symlink() or not path.is_file():
        raise ContractError(f"合同文件类型无效：{path}")
    size = path.stat().st_size
    if size > MAX_CONTRACT_BYTES:
        raise ContractError(f"合同文件超过 {MAX_CONTRACT_BYTES} bytes")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ContractError(f"合同 JSON 无法读取：{path}: {exc}") from exc
    return parse_contract_bytes(payload)


def verify_contract(handoff_root: Path, contract_path: Path | None = None) -> dict[str, Any]:
    if handoff_root.is_symlink():
        raise ContractError(f"交接根目录无效：{handoff_root}")
    root = handoff_root.resolve(strict=True)
    if not root.is_dir():
        raise ContractError(f"交接根目录无效：{handoff_root}")
    expected_path = root / CONTRACT_FILENAME
    if expected_path.is_symlink():
        raise ContractError(f"合同文件类型无效：{expected_path}")
    expected_resolved = expected_path.resolve(strict=True)
    requested_path = contract_path or expected_path
    if requested_path.is_symlink():
        raise ContractError(f"合同文件类型无效：{requested_path}")
    requested_resolved = requested_path.resolve(strict=True)
    if requested_resolved != expected_resolved:
        raise ContractError(f"合同必须位于交接根目录：{expected_path}")
    contract = load_contract(expected_resolved)
    rebuilt = build_contract(root, dict(contract["sourceRevisions"]))
    if contract != rebuilt:
        for name in ("scenarios", "manifests"):
            expected = contract["catalogs"][name]
            actual = rebuilt["catalogs"][name]
            if expected != actual:
                raise ContractError(
                    f"{name} 目录与合同不一致："
                    f"files {expected['fileCount']}->{actual['fileCount']}, "
                    f"bytes {expected['byteCount']}->{actual['byteCount']}, "
                    f"tree {expected['treeSha256']}->{actual['treeSha256']}"
                )
        raise ContractError("合同与重新计算结果不一致")
    return contract


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="生成并原子写入 v1 合同")
    build.add_argument("--handoff-root", type=Path, required=True)
    build.add_argument("--sp-revision", required=True)
    build.add_argument("--scenario-revision", required=True)
    build.add_argument("--manifest-revision", required=True)
    verify = commands.add_parser("verify", help="重算全部目录并核验 v1 合同")
    verify.add_argument("--handoff-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            contract = build_contract(
                args.handoff_root,
                {
                    "sp": args.sp_revision,
                    "scenarios": args.scenario_revision,
                    "manifests": args.manifest_revision,
                },
            )
            path = write_contract_atomic(args.handoff_root, contract)
            print(
                "TW_SP_HANDOFF_BUILT "
                f"path={path} "
                f"scenarios={contract['catalogs']['scenarios']['fileCount']} "
                f"manifests={contract['catalogs']['manifests']['fileCount']}"
            )
        else:
            contract = verify_contract(args.handoff_root)
            print(
                "TW_SP_HANDOFF_OK "
                f"scenarios={contract['catalogs']['scenarios']['fileCount']} "
                f"manifests={contract['catalogs']['manifests']['fileCount']}"
            )
    except (ContractError, OSError) as exc:
        print(f"TW_SP_HANDOFF_ERROR {exc}", file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
