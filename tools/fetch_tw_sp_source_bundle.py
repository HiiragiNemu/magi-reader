#!/usr/bin/env python3
"""Fetch, authenticate, safely extract, and verify the pinned TW SP bundle.

This command is the network/archive boundary for the deterministic TW importer.
It does not import story data, invoke Git, build the site, or deploy anything.
The resulting directory is accepted by ``materialize_tw_official_cn.py`` only
after the v1 SP handoff contract has been verified again.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
import zlib
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from tw_sp_handoff_contract import (  # noqa: E402
    CATALOG_SPECS,
    CONTRACT_FILENAME,
    MAX_CONTRACT_BYTES,
    MAX_JSON_FILE_BYTES,
    ContractError,
    catalog_record_matches_spec,
    parse_contract_bytes,
    verify_contract,
)

DEFAULT_SOURCE_URL = (
    "https://github.com/HiiragiNemu/MagiaExedraTWData/releases/download/"
    "tw-wiki-source-v1-20260806/exedra-tw-wiki-source-v1.zip"
)
DEFAULT_SOURCE_SHA256 = (
    "503c4c9a518d0a992abe800fccde4a97b35b2e4ddaeb2359e63eaa8d572cd1ac"
)
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 200_001
MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1000
DEFAULT_TIMEOUT_SECONDS = 120
USER_AGENT = "magi-reader-tw-sp-source-boundary/1"
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


class SourceBundleError(RuntimeError):
    """Raised when the downloaded archive cannot become a verified bundle."""


@dataclass(frozen=True)
class ArchiveDigest:
    sha256: str
    bytes: int


@dataclass(frozen=True)
class BundleReceipt:
    root: Path
    archive: ArchiveDigest
    source_url: str | None
    contract_sha256: str
    source_revisions: dict[str, str]
    diagnostics: dict[str, int]
    scenario_files: int
    manifest_files: int
    scenario_bytes: int
    manifest_bytes: int
    scenario_tree_sha256: str
    manifest_tree_sha256: str
    scenario_catalog_sha256: str
    manifest_catalog_sha256: str


@dataclass(frozen=True)
class ArchivePlan:
    members: tuple[tuple[ZipInfo, str], ...]
    contract: dict[str, Any]
    contract_sha256: str
    expected_records: dict[str, dict[str, Any]]


def normalize_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if not SHA256_PATTERN.fullmatch(normalized):
        raise SourceBundleError("source SHA-256 must contain exactly 64 hex digits")
    return normalized


def validate_source_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise SourceBundleError(
            "source URL must be an HTTPS URL without credentials or a fragment"
        )
    return value.strip()


def _hash_stream(source: BinaryIO, target: BinaryIO | None = None) -> ArchiveDigest:
    digest = hashlib.sha256()
    byte_count = 0
    while chunk := source.read(DOWNLOAD_CHUNK_BYTES):
        byte_count += len(chunk)
        if byte_count > MAX_ARCHIVE_BYTES:
            raise SourceBundleError(
                f"source archive exceeds {MAX_ARCHIVE_BYTES} bytes"
            )
        digest.update(chunk)
        if target is not None:
            target.write(chunk)
    return ArchiveDigest(digest.hexdigest(), byte_count)


def hash_archive(path: Path) -> ArchiveDigest:
    if path.is_symlink():
        raise SourceBundleError(f"source archive is not a regular file: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise SourceBundleError(f"source archive is not a regular file: {path}")
    with resolved.open("rb") as source:
        return _hash_stream(source)


def _open_url(
    request: Request,
    *,
    timeout: int,
) -> Any:
    return urlopen(request, timeout=timeout)


def download_archive(
    source_url: str,
    target: Path,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    opener: Callable[..., Any] = _open_url,
) -> ArchiveDigest:
    """Stream an HTTPS archive to ``target`` without buffering it in memory."""

    url = validate_source_url(source_url)
    if timeout_seconds <= 0:
        raise SourceBundleError("download timeout must be positive")
    request = Request(url, headers={"User-Agent": USER_AGENT})
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        response_value = opener(request, timeout=timeout_seconds)
        with closing(response_value) as response, target.open("xb") as output:
            final_url = validate_source_url(response.geturl())
            if urlsplit(final_url).scheme != "https":
                raise SourceBundleError("source download redirected away from HTTPS")
            result = _hash_stream(response, output)
            output.flush()
            os.fsync(output.fileno())
        return result
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _normalized_member_path(info: ZipInfo) -> str:
    name = info.filename
    if not name or "\\" in name or "\x00" in name:
        raise SourceBundleError(f"invalid ZIP member path: {name!r}")
    normalized = unicodedata.normalize("NFC", name)
    if normalized != name:
        raise SourceBundleError(f"ZIP member path is not NFC: {name!r}")
    if normalized.endswith("/"):
        normalized = normalized[:-1]
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != normalized
    ):
        raise SourceBundleError(f"invalid ZIP member path: {name!r}")
    for part in path.parts:
        folded_stem = part.split(".", 1)[0].casefold()
        if (
            part.rstrip(" .") != part
            or ":" in part
            or any(ord(character) < 32 for character in part)
            or folded_stem in WINDOWS_RESERVED_NAMES
        ):
            raise SourceBundleError(f"non-portable ZIP member path: {name!r}")
    return path.as_posix()


def _validate_member_type(info: ZipInfo, path: str) -> None:
    if info.flag_bits & 0x1:
        raise SourceBundleError(f"encrypted ZIP member is not allowed: {path}")
    mode = info.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    if stat.S_ISLNK(mode):
        raise SourceBundleError(f"symbolic link is not allowed in ZIP: {path}")
    if info.is_dir():
        if file_type not in {0, stat.S_IFDIR}:
            raise SourceBundleError(f"invalid directory member type: {path}")
        if info.file_size or info.compress_size:
            raise SourceBundleError(f"directory member contains data: {path}")
    elif file_type not in {0, stat.S_IFREG}:
        raise SourceBundleError(f"non-regular ZIP member is not allowed: {path}")
    if info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
        raise SourceBundleError(
            f"unsupported ZIP compression method {info.compress_type}: {path}"
        )
    if (
        not info.is_dir()
        and info.file_size
        and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO
    ):
        raise SourceBundleError(f"ZIP member compression ratio is too high: {path}")


def _validate_member_location(info: ZipInfo, path: str) -> None:
    if info.is_dir():
        allowed = (
            path
            in {
                "bundle",
                "bundle/Resources",
                "bundle/Resources/Scenarios",
                "bundle/Manifests",
            }
            or path.startswith("bundle/Resources/Scenarios/")
        )
        if not allowed:
            raise SourceBundleError(f"directory is outside the v1 bundle roots: {path}")
        return
    if path == CONTRACT_FILENAME:
        if info.file_size > MAX_CONTRACT_BYTES:
            raise SourceBundleError(
                f"root contract exceeds {MAX_CONTRACT_BYTES} bytes"
            )
        return
    for spec in CATALOG_SPECS:
        if catalog_record_matches_spec(spec, path):
            if info.file_size > MAX_JSON_FILE_BYTES:
                raise SourceBundleError(f"{spec.name} JSON is too large: {path}")
            return
    raise SourceBundleError(f"file is outside the v1 bundle contract: {path}")


def _load_root_contract(archive: ZipFile, info: ZipInfo) -> tuple[dict[str, Any], str]:
    with archive.open(info, "r") as source:
        raw = source.read(MAX_CONTRACT_BYTES + 1)
    if len(raw) > MAX_CONTRACT_BYTES:
        raise SourceBundleError(f"root contract exceeds {MAX_CONTRACT_BYTES} bytes")
    return parse_contract_bytes(raw), hashlib.sha256(raw).hexdigest()


def _implicit_parent_directories(paths: set[str]) -> set[str]:
    result: set[str] = set()
    for value in paths:
        parent = PurePosixPath(value).parent
        while parent != PurePosixPath("."):
            result.add(parent.as_posix())
            parent = parent.parent
    return result


def validate_archive_members(archive: ZipFile) -> ArchivePlan:
    infos = archive.infolist()
    if not infos or len(infos) > MAX_ARCHIVE_MEMBERS:
        raise SourceBundleError(
            f"ZIP member count must be in 1..{MAX_ARCHIVE_MEMBERS}: {len(infos)}"
        )
    result: list[tuple[ZipInfo, str]] = []
    seen: dict[str, str] = {}
    total_bytes = 0
    contract_members: list[ZipInfo] = []
    for info in infos:
        path = _normalized_member_path(info)
        folded = path.casefold()
        previous = seen.get(folded)
        if previous is not None:
            raise SourceBundleError(f"duplicate ZIP member path: {previous!r} / {path!r}")
        seen[folded] = path
        _validate_member_type(info, path)
        _validate_member_location(info, path)
        if not info.is_dir():
            total_bytes += info.file_size
            if total_bytes > MAX_UNCOMPRESSED_BYTES:
                raise SourceBundleError(
                    f"ZIP expands beyond {MAX_UNCOMPRESSED_BYTES} bytes"
                )
            if path == CONTRACT_FILENAME:
                contract_members.append(info)
        result.append((info, path))
    if len(contract_members) != 1:
        raise SourceBundleError(
            f"ZIP must contain exactly one root {CONTRACT_FILENAME}"
        )
    contract, contract_sha256 = _load_root_contract(archive, contract_members[0])

    expected_records: dict[str, dict[str, Any]] = {}
    specs = {spec.name: spec for spec in CATALOG_SPECS}
    for catalog_name, catalog in contract["catalogs"].items():
        for item in catalog["files"]:
            path = item["path"]
            if not catalog_record_matches_spec(specs[catalog_name], path):
                raise SourceBundleError(
                    f"contract path is outside {catalog_name} catalog root: {path}"
                )
            if path in expected_records:
                raise SourceBundleError(f"contract path appears in two catalogs: {path}")
            expected_records[path] = item

    expected_files = {CONTRACT_FILENAME, *expected_records}
    actual_files = {path for info, path in result if not info.is_dir()}
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        extra = sorted(actual_files - expected_files)
        raise SourceBundleError(
            "archive members do not exactly match the root contract: "
            f"missing={missing[:3]} extra={extra[:3]}"
        )
    for path in actual_files:
        parent = PurePosixPath(path).parent
        while parent != PurePosixPath("."):
            if parent.as_posix() in actual_files:
                raise SourceBundleError(
                    f"ZIP file member is also a parent path: {parent.as_posix()}"
                )
            parent = parent.parent
    allowed_directories = _implicit_parent_directories(expected_files)
    unexpected_directories = sorted(
        path for info, path in result if info.is_dir() and path not in allowed_directories
    )
    if unexpected_directories:
        raise SourceBundleError(
            f"ZIP contains unlisted directories: {unexpected_directories[:3]}"
        )
    for info, path in result:
        expected_record = expected_records.get(path)
        if expected_record is not None and info.file_size != expected_record["bytes"]:
            raise SourceBundleError(
                f"ZIP member size disagrees with root contract: {path}: "
                f"{info.file_size} != {expected_record['bytes']}"
            )
    return ArchivePlan(
        members=tuple(result),
        contract=contract,
        contract_sha256=contract_sha256,
        expected_records=expected_records,
    )


def _copy_verified_member(
    source: BinaryIO,
    output: BinaryIO,
    *,
    path: str,
    expected_bytes: int,
    expected_sha256: str,
) -> None:
    digest = hashlib.sha256()
    byte_count = 0
    while chunk := source.read(DOWNLOAD_CHUNK_BYTES):
        byte_count += len(chunk)
        if byte_count > expected_bytes:
            raise SourceBundleError(f"ZIP member expanded beyond declared size: {path}")
        digest.update(chunk)
        output.write(chunk)
    actual_sha256 = digest.hexdigest()
    if byte_count != expected_bytes or actual_sha256 != expected_sha256:
        raise SourceBundleError(
            f"ZIP member content disagrees with root contract: {path}: "
            f"bytes={byte_count}/{expected_bytes} "
            f"sha256={actual_sha256}/{expected_sha256}"
        )


def _extract_archive(
    archive_path: Path,
    staging_root: Path,
) -> tuple[dict[str, Any], str]:
    with ZipFile(archive_path, "r") as archive:
        plan = validate_archive_members(archive)
        for info, relative in plan.members:
            target = staging_root.joinpath(*PurePosixPath(relative).parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative == CONTRACT_FILENAME:
                expected_bytes = info.file_size
                expected_sha256 = plan.contract_sha256
            else:
                record = plan.expected_records[relative]
                expected_bytes = record["bytes"]
                expected_sha256 = record["sha256"]
            with archive.open(info, "r") as source, target.open("xb") as output:
                _copy_verified_member(
                    source,
                    output,
                    path=relative,
                    expected_bytes=expected_bytes,
                    expected_sha256=expected_sha256,
                )

    contract = verify_contract(staging_root)
    if contract != plan.contract:
        raise SourceBundleError("verified extracted contract changed during extraction")
    return contract, plan.contract_sha256


def install_archive(
    archive_path: Path,
    output_root: Path,
    expected_sha256: str,
    *,
    source_url: str | None = None,
) -> BundleReceipt:
    """Authenticate and install one archive, preserving an existing destination."""

    expected = normalize_sha256(expected_sha256)
    digest = hash_archive(archive_path)
    archive = archive_path.resolve(strict=True)
    if digest.sha256 != expected:
        raise SourceBundleError(
            "source archive SHA-256 mismatch: "
            f"expected={expected} actual={digest.sha256} bytes={digest.bytes}"
        )

    requested = output_root.absolute()
    requested.parent.mkdir(parents=True, exist_ok=True)
    parent = requested.parent.resolve(strict=True)
    destination = parent / requested.name
    if destination.exists() or destination.is_symlink():
        raise SourceBundleError(f"output root already exists: {destination}")

    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.extract-", dir=parent)
    )
    published = False
    try:
        contract, contract_sha256 = _extract_archive(archive, staging)
        os.replace(staging, destination)
        published = True
        published_contract = verify_contract(destination)
        if published_contract != contract:
            raise SourceBundleError("published bundle changed after atomic installation")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if published:
            if destination.is_symlink():
                destination.unlink(missing_ok=True)
            elif destination.exists():
                shutil.rmtree(destination, ignore_errors=True)
        raise

    scenarios = contract["catalogs"]["scenarios"]
    manifests = contract["catalogs"]["manifests"]
    return BundleReceipt(
        root=destination,
        archive=digest,
        source_url=source_url,
        contract_sha256=contract_sha256,
        source_revisions=dict(contract["sourceRevisions"]),
        diagnostics=dict(contract["diagnostics"]),
        scenario_files=scenarios["fileCount"],
        manifest_files=manifests["fileCount"],
        scenario_bytes=scenarios["byteCount"],
        manifest_bytes=manifests["byteCount"],
        scenario_tree_sha256=scenarios["treeSha256"],
        manifest_tree_sha256=manifests["treeSha256"],
        scenario_catalog_sha256=scenarios["catalogSha256"],
        manifest_catalog_sha256=manifests["catalogSha256"],
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--source-url",
        help=f"HTTPS ZIP URL (default: {DEFAULT_SOURCE_URL})",
    )
    source.add_argument(
        "--archive",
        type=Path,
        help="Existing local ZIP; useful for offline verification",
    )
    parser.add_argument(
        "--source-sha256",
        default=DEFAULT_SOURCE_SHA256,
        help="Required SHA-256 of the entire ZIP",
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    temporary_archive: Path | None = None
    source_url: str | None = None
    try:
        expected = normalize_sha256(args.source_sha256)
        if args.archive is not None:
            archive = args.archive
        else:
            source_url = validate_source_url(args.source_url or DEFAULT_SOURCE_URL)
            args.output_root.parent.mkdir(parents=True, exist_ok=True)
            parent = args.output_root.parent.resolve(strict=True)
            handle, name = tempfile.mkstemp(
                prefix=".tw-sp-source-", suffix=".zip", dir=parent
            )
            os.close(handle)
            temporary_archive = Path(name)
            temporary_archive.unlink()
            print(f"TW_SP_SOURCE_FETCH url={source_url}")
            downloaded = download_archive(
                source_url,
                temporary_archive,
                timeout_seconds=args.timeout_seconds,
            )
            if downloaded.sha256 != expected:
                raise SourceBundleError(
                    "source archive SHA-256 mismatch: "
                    f"expected={expected} actual={downloaded.sha256} "
                    f"bytes={downloaded.bytes}"
                )
            archive = temporary_archive

        receipt = install_archive(
            archive,
            args.output_root,
            expected,
            source_url=source_url,
        )
        print(
            "TW_SP_SOURCE_READY "
            f"root={receipt.root} "
            f"archive_sha256={receipt.archive.sha256} "
            f"archive_bytes={receipt.archive.bytes} "
            f"contract_sha256={receipt.contract_sha256} "
            f"scenarios={receipt.scenario_files} "
            f"scenario_bytes={receipt.scenario_bytes} "
            f"manifests={receipt.manifest_files} "
            f"manifest_bytes={receipt.manifest_bytes} "
            f"scenario_tree_sha256={receipt.scenario_tree_sha256} "
            f"manifest_tree_sha256={receipt.manifest_tree_sha256} "
            f"scenario_catalog_sha256={receipt.scenario_catalog_sha256} "
            f"manifest_catalog_sha256={receipt.manifest_catalog_sha256} "
            f"sp_revision={receipt.source_revisions['sp']} "
            f"scenario_revision={receipt.source_revisions['scenarios']} "
            f"manifest_revision={receipt.source_revisions['manifests']} "
            f"diagnostics={receipt.diagnostics}"
        )
    except (
        SourceBundleError,
        ContractError,
        BadZipFile,
        NotImplementedError,
        OSError,
        ValueError,
        zlib.error,
    ) as exc:
        print(f"TW_SP_SOURCE_ERROR {exc}", file=sys.stderr)
        return 1
    finally:
        if temporary_archive is not None:
            temporary_archive.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
