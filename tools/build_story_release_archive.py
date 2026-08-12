#!/usr/bin/env python3
"""Build and validate a deterministic story/voice data release archive.

The builder deliberately keeps file contents and the file inventory out of
memory.  File metadata is staged in a temporary SQLite database, every payload
is hashed and copied in chunks, and the canonical manifest is emitted one
record at a time.  Publication happens only after the staged archive and its
sidecars have passed a complete streaming validation.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import uuid
import zipfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, TextIO


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

DATA_ROOTS = (
    "magireco-source-master",
    "magireco-translate-data-master",
    "magireco-voice-source-master",
    "magireco-voice-translate-data-master",
    "magiraexedra-source-master",
    "magiraexedra-translate-data-master",
)

MANIFEST_NAME = "STORY_DATA_MANIFEST.v1.json"
REPORT_NAME = "STORY_DATA_RELEASE_REPORT.v1.json"
SHA256SUMS_NAME = "SHA256SUMS.txt"
DEFAULT_ARCHIVE_NAME = "magi-reader-story-data.zip"
DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "story-release"

SCHEMA_VERSION = 1
CHUNK_SIZE = 4 * 1024 * 1024
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }
)
EXCLUDED_FILE_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
EXCLUDED_FILE_SUFFIXES = (
    ".bak",
    ".crdownload",
    ".part",
    ".pyc",
    ".pyo",
    ".swo",
    ".swp",
    ".temp",
    ".tmp",
)


class ArchiveError(RuntimeError):
    """Raised when source data or an archive violates the release contract."""


@dataclass(frozen=True)
class ReleasePaths:
    archive: Path
    sha256sums: Path
    report: Path


def release_paths(output: Path) -> ReleasePaths:
    output = Path(output)
    return ReleasePaths(
        archive=output,
        sha256sums=output.parent / SHA256SUMS_NAME,
        report=output.parent / REPORT_NAME,
    )


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_member_name(value: str) -> str:
    """Return a safe canonical POSIX archive member name.

    Absolute paths, empty paths, Windows separators, drive prefixes and dot
    traversal are rejected rather than normalized.  This prevents a release
    consumer from accidentally extracting outside its destination.
    """

    if not isinstance(value, str) or not value or "\x00" in value:
        raise ArchiveError("archive member path must be a non-empty string")
    if "\\" in value:
        raise ArchiveError(f"archive member path is not POSIX: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ArchiveError(f"absolute archive member path is forbidden: {value!r}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ArchiveError(f"archive member path contains traversal: {value!r}")
    if not path.parts or ":" in path.parts[0]:
        raise ArchiveError(f"archive member path contains a drive prefix: {value!r}")
    canonical = path.as_posix()
    if canonical != value:
        raise ArchiveError(f"archive member path is not canonical: {value!r}")
    return canonical


def _selected_root_names(names: Iterable[str] | None) -> tuple[str, ...]:
    if names is None:
        return DATA_ROOTS
    requested = tuple(names)
    if not requested:
        raise ArchiveError("at least one data root must be selected")
    unknown = sorted(set(requested).difference(DATA_ROOTS))
    if unknown:
        raise ArchiveError(f"unknown data root(s): {', '.join(unknown)}")
    if len(set(requested)) != len(requested):
        raise ArchiveError("a data root may be selected only once")
    requested_set = set(requested)
    # Canonical order makes the archive independent of CLI argument order.
    return tuple(name for name in DATA_ROOTS if name in requested_set)


def _source_roots(repository_root: Path, names: tuple[str, ...]) -> dict[str, Path]:
    repository_root = repository_root.resolve(strict=True)
    result: dict[str, Path] = {}
    for name in names:
        source = (repository_root / name).resolve(strict=True)
        if not _is_relative_to(source, repository_root):
            raise ArchiveError(f"data root escapes the repository: {name}")
        if not source.is_dir():
            raise ArchiveError(f"data root is not a directory: {source}")
        result[name] = source
    return result


def _is_excluded_directory(name: str) -> bool:
    return name in EXCLUDED_DIRECTORY_NAMES


def _is_excluded_file(name: str) -> bool:
    lower = name.lower()
    return (
        name in EXCLUDED_FILE_NAMES
        or name.startswith("~$")
        or name.startswith(".#")
        or lower.endswith(EXCLUDED_FILE_SUFFIXES)
    )


def _is_reparse_point(file_stat: os.stat_result) -> bool:
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _iter_source_files(source_root: Path) -> Iterator[Path]:
    """Yield regular files without following links or holding a tree in memory."""

    pending = [source_root]
    while pending:
        directory = pending.pop()
        try:
            entries = os.scandir(directory)
        except OSError as error:
            raise ArchiveError(f"failed to scan {directory}: {error}") from error
        with entries:
            for entry in entries:
                if entry.name in {".", ".."}:
                    continue
                try:
                    entry_stat = entry.stat(follow_symlinks=False)
                except OSError as error:
                    raise ArchiveError(f"failed to inspect {entry.path}: {error}") from error
                if entry.is_symlink() or _is_reparse_point(entry_stat):
                    raise ArchiveError(f"links and reparse points are forbidden: {entry.path}")
                if stat.S_ISDIR(entry_stat.st_mode):
                    if not _is_excluded_directory(entry.name):
                        pending.append(Path(entry.path))
                    continue
                if not stat.S_ISREG(entry_stat.st_mode):
                    raise ArchiveError(f"non-regular source entry is forbidden: {entry.path}")
                if not _is_excluded_file(entry.name):
                    yield Path(entry.path)


def _hash_binary_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = stream.read(CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _hash_file(path: Path) -> tuple[str, int]:
    with path.open("rb") as stream:
        return _hash_binary_stream(stream)


def _open_inventory(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("PRAGMA temp_store=FILE")
    connection.execute(
        """
        CREATE TABLE inventory (
            archive_path TEXT PRIMARY KEY,
            archive_sort_key BLOB NOT NULL UNIQUE,
            casefold_path TEXT NOT NULL UNIQUE,
            source_root TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            source_path TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL
        )
        """
    )
    return connection


def _inventory_sources(
    connection: sqlite3.Connection,
    source_roots: dict[str, Path],
) -> None:
    for source_name, source_root in source_roots.items():
        count = 0
        for path in _iter_source_files(source_root):
            try:
                resolved = path.resolve(strict=True)
            except OSError as error:
                raise ArchiveError(f"failed to resolve {path}: {error}") from error
            if not _is_relative_to(resolved, source_root):
                raise ArchiveError(f"source file escapes {source_root}: {path}")
            relative_path = path.relative_to(source_root).as_posix()
            validate_member_name(relative_path)
            archive_path = validate_member_name(f"{source_name}/{relative_path}")

            before = path.stat()
            sha256, size = _hash_file(path)
            after = path.stat()
            if (
                before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or size != after.st_size
            ):
                raise ArchiveError(f"source file changed while hashing: {path}")
            try:
                connection.execute(
                    """
                    INSERT INTO inventory (
                        archive_path, archive_sort_key, casefold_path,
                        source_root, relative_path, source_path, bytes, sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        archive_path,
                        archive_path.encode("utf-8"),
                        archive_path.casefold(),
                        source_name,
                        relative_path,
                        str(path),
                        size,
                        sha256,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ArchiveError(
                    f"duplicate or case-colliding archive path: {archive_path}"
                ) from error
            count += 1
        if count == 0:
            raise ArchiveError(f"selected data root contains no eligible files: {source_name}")
        connection.commit()


def _source_summaries(
    connection: sqlite3.Connection,
    selected_roots: tuple[str, ...],
) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for name in selected_roots:
        row = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(bytes), 0) FROM inventory WHERE source_root = ?",
            (name,),
        ).fetchone()
        assert row is not None
        summaries.append({"bytes": int(row[1]), "fileCount": int(row[0]), "name": name})
    return summaries


def _write_manifest(
    path: Path,
    connection: sqlite3.Connection,
    selected_roots: tuple[str, ...],
    compression_name: str,
) -> dict[str, object]:
    summaries = _source_summaries(connection, selected_roots)
    total_files = sum(int(item["fileCount"]) for item in summaries)
    total_bytes = sum(int(item["bytes"]) for item in summaries)

    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("{\n")
        stream.write(f'  "schemaVersion":{SCHEMA_VERSION},\n')
        stream.write('  "manifestType":"magi-reader-story-data",\n')
        stream.write('  "complete":true,\n')
        stream.write(f'  "compression":{_json(compression_name)},\n')
        stream.write('  "sourceRoots":[\n')
        for index, summary in enumerate(summaries):
            suffix = "," if index + 1 < len(summaries) else ""
            stream.write(f"    {_json(summary)}{suffix}\n")
        stream.write("  ],\n")
        stream.write('  "files":[\n')
        cursor = connection.execute(
            """
            SELECT source_root, relative_path, archive_path, bytes, sha256
            FROM inventory ORDER BY archive_sort_key
            """
        )
        for index, row in enumerate(cursor):
            record = {
                "archivePath": row[2],
                "bytes": int(row[3]),
                "path": row[1],
                "sha256": row[4],
                "sourceRoot": row[0],
            }
            suffix = "," if index + 1 < total_files else ""
            stream.write(f"    {_json(record)}{suffix}\n")
        stream.write("  ],\n")
        totals = {"bytes": total_bytes, "fileCount": total_files}
        stream.write(f'  "totals":{_json(totals)}\n')
        stream.write("}\n")
    return {"sourceRoots": summaries, "totals": totals}


def _zip_info(name: str, compression: int, compresslevel: int | None) -> zipfile.ZipInfo:
    validate_member_name(name)
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = compression
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.flag_bits |= 0x800
    info._compresslevel = compresslevel  # type: ignore[attr-defined]
    return info


def _copy_file_into_zip(
    archive: zipfile.ZipFile,
    member_name: str,
    source_path: Path,
    compression: int,
    compresslevel: int | None,
    expected_sha256: str | None = None,
    expected_bytes: int | None = None,
) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    info = _zip_info(member_name, compression, compresslevel)
    with source_path.open("rb") as source, archive.open(
        info, "w", force_zip64=True
    ) as destination:
        while True:
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                break
            destination.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    sha256 = digest.hexdigest()
    if expected_sha256 is not None and sha256 != expected_sha256:
        raise ArchiveError(f"source file changed before ZIP write: {source_path}")
    if expected_bytes is not None and size != expected_bytes:
        raise ArchiveError(f"source file size changed before ZIP write: {source_path}")
    return sha256, size


def _build_zip(
    archive_path: Path,
    manifest_path: Path,
    connection: sqlite3.Connection,
    compression_name: str,
) -> None:
    if compression_name == "deflate":
        compression = zipfile.ZIP_DEFLATED
        compresslevel: int | None = 9
    elif compression_name == "stored":
        compression = zipfile.ZIP_STORED
        compresslevel = None
    else:  # defensive guard for callers that bypass argparse
        raise ArchiveError(f"unsupported compression: {compression_name}")

    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=compression,
        compresslevel=compresslevel,
        allowZip64=True,
        strict_timestamps=True,
    ) as archive:
        archive.comment = b""
        _copy_file_into_zip(
            archive,
            MANIFEST_NAME,
            manifest_path,
            compression,
            compresslevel,
        )
        cursor = connection.execute(
            """
            SELECT archive_path, source_path, bytes, sha256
            FROM inventory ORDER BY archive_sort_key
            """
        )
        for archive_name, source_path, size, sha256 in cursor:
            _copy_file_into_zip(
                archive,
                archive_name,
                Path(source_path),
                compression,
                compresslevel,
                expected_sha256=sha256,
                expected_bytes=int(size),
            )


def _write_sidecars(
    paths: ReleasePaths,
    archive_name: str,
    inventory_summary: dict[str, object],
    compression_name: str,
    manifest_path: Path,
) -> dict[str, object]:
    archive_sha256, archive_bytes = _hash_file(paths.archive)
    manifest_sha256, manifest_bytes = _hash_file(manifest_path)
    paths.sha256sums.write_text(
        f"{archive_sha256}  {archive_name}\n",
        encoding="utf-8",
        newline="\n",
    )
    report = {
        "archive": {
            "bytes": archive_bytes,
            "compression": compression_name,
            "manifestBytes": manifest_bytes,
            "manifestName": MANIFEST_NAME,
            "manifestSha256": manifest_sha256,
            "name": archive_name,
            "sha256": archive_sha256,
        },
        "complete": True,
        "reportType": "magi-reader-story-data-release",
        "schemaVersion": SCHEMA_VERSION,
        "sourceRoots": inventory_summary["sourceRoots"],
        "totals": inventory_summary["totals"],
    }
    paths.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report


def _parse_property_line(line: str, *, trailing_comma: bool) -> tuple[str, object]:
    stripped = line.strip()
    if trailing_comma:
        if not stripped.endswith(","):
            raise ArchiveError("manifest property is missing its separator")
        stripped = stripped[:-1]
    elif stripped.endswith(","):
        raise ArchiveError("manifest property has an unexpected separator")
    try:
        value = json.loads("{" + stripped + "}")
    except json.JSONDecodeError as error:
        raise ArchiveError(f"invalid manifest property: {error}") from error
    if len(value) != 1:
        raise ArchiveError("manifest property must contain exactly one key")
    return next(iter(value.items()))


def _parse_record_line(line: str, *, has_more: bool | None = None) -> dict[str, object]:
    stripped = line.strip()
    has_comma = stripped.endswith(",")
    if has_comma:
        stripped = stripped[:-1]
    if has_more is not None and has_comma != has_more:
        raise ArchiveError("manifest array separator is not canonical")
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise ArchiveError(f"invalid manifest record: {error}") from error
    if not isinstance(value, dict):
        raise ArchiveError("manifest array record must be an object")
    return value


def _read_manifest_header(stream: TextIO) -> dict[str, object]:
    if stream.readline() != "{\n":
        raise ArchiveError("manifest does not start with a canonical object")
    expected = ("schemaVersion", "manifestType", "complete", "compression")
    header: dict[str, object] = {}
    for key in expected:
        parsed_key, value = _parse_property_line(stream.readline(), trailing_comma=True)
        if parsed_key != key:
            raise ArchiveError(f"unexpected manifest property: {parsed_key!r}")
        header[key] = value
    if stream.readline().strip() != '"sourceRoots":[':
        raise ArchiveError("manifest sourceRoots array is missing")
    return header


def _read_manifest_records(
    stream: TextIO,
    on_file: Callable[[dict[str, object]], None],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    header = _read_manifest_header(stream)
    sources: list[dict[str, object]] = []
    while True:
        line = stream.readline()
        if not line:
            raise ArchiveError("manifest ended inside sourceRoots")
        if line.strip() == "],":
            break
        sources.append(_parse_record_line(line))
    if stream.readline().strip() != '"files":[':
        raise ArchiveError("manifest files array is missing")
    while True:
        line = stream.readline()
        if not line:
            raise ArchiveError("manifest ended inside files")
        if line.strip() == "],":
            break
        on_file(_parse_record_line(line))
    key, totals = _parse_property_line(stream.readline(), trailing_comma=False)
    if key != "totals" or not isinstance(totals, dict):
        raise ArchiveError("manifest totals object is missing")
    if stream.readline() != "}\n" or stream.read(1):
        raise ArchiveError("manifest has trailing or malformed content")
    header["totals"] = totals
    return header, sources


def _read_sha256sums(path: Path, archive_name: str) -> str:
    try:
        line = path.read_text(encoding="utf-8").strip("\n")
    except OSError as error:
        raise ArchiveError(f"failed to read {path}: {error}") from error
    parts = line.split("  ", 1)
    if len(parts) != 2 or parts[1] != archive_name:
        raise ArchiveError("SHA256SUMS does not name the expected archive")
    digest = parts[0]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ArchiveError("SHA256SUMS contains an invalid digest")
    return digest


def _validate_source_record(record: dict[str, object]) -> tuple[str, int, int]:
    if set(record) != {"bytes", "fileCount", "name"}:
        raise ArchiveError("manifest source root has unexpected fields")
    name = record["name"]
    count = record["fileCount"]
    size = record["bytes"]
    if name not in DATA_ROOTS or not isinstance(name, str):
        raise ArchiveError("manifest source root name is invalid")
    if not isinstance(count, int) or count <= 0:
        raise ArchiveError(f"manifest source root count is invalid: {name}")
    if not isinstance(size, int) or size < 0:
        raise ArchiveError(f"manifest source root byte count is invalid: {name}")
    return name, count, size


def validate_archive(
    output: Path,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    include_roots: Iterable[str] | None = None,
    verify_sources: bool = True,
    sidecar_paths: ReleasePaths | None = None,
) -> dict[str, object]:
    """Validate sidecars, ZIP members, manifest hashes and optional source data."""

    output = Path(output)
    selected_roots = _selected_root_names(include_roots)
    source_roots = _source_roots(Path(repository_root), selected_roots)
    paths = sidecar_paths or release_paths(output)

    if not paths.archive.is_file() or not paths.sha256sums.is_file() or not paths.report.is_file():
        raise ArchiveError("archive, SHA256SUMS and release report must all exist")
    try:
        report = json.loads(paths.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArchiveError(f"invalid release report: {error}") from error
    if not isinstance(report, dict):
        raise ArchiveError("release report must be an object")
    archive_report = report.get("archive")
    if not isinstance(archive_report, dict):
        raise ArchiveError("release report archive object is missing")
    archive_name = archive_report.get("name")
    if not isinstance(archive_name, str) or not archive_name:
        raise ArchiveError("release report archive name is invalid")

    sidecar_sha256 = _read_sha256sums(paths.sha256sums, archive_name)
    actual_archive_sha256, actual_archive_bytes = _hash_file(paths.archive)
    if sidecar_sha256 != actual_archive_sha256:
        raise ArchiveError("archive SHA-256 does not match SHA256SUMS")
    if archive_report.get("sha256") != actual_archive_sha256:
        raise ArchiveError("archive SHA-256 does not match the release report")
    if archive_report.get("bytes") != actual_archive_bytes:
        raise ArchiveError("archive byte count does not match the release report")
    if archive_report.get("manifestName") != MANIFEST_NAME:
        raise ArchiveError("release report names an unsupported manifest")

    with zipfile.ZipFile(paths.archive, "r", allowZip64=True) as archive:
        infos = archive.infolist()
        if not infos or infos[0].filename != MANIFEST_NAME:
            raise ArchiveError("embedded manifest must be the first ZIP member")
        seen_members: set[str] = set()
        for info in infos:
            validate_member_name(info.filename)
            folded = info.filename.casefold()
            if folded in seen_members:
                raise ArchiveError(f"duplicate or case-colliding ZIP member: {info.filename}")
            seen_members.add(folded)
            if info.is_dir():
                raise ArchiveError(f"directory members are not allowed: {info.filename}")
            if info.date_time != FIXED_ZIP_TIMESTAMP:
                raise ArchiveError(f"non-deterministic ZIP timestamp: {info.filename}")

        manifest_info = infos[0]
        with archive.open(manifest_info, "r") as manifest_binary:
            manifest_sha256, manifest_bytes = _hash_binary_stream(manifest_binary)
        if archive_report.get("manifestSha256") != manifest_sha256:
            raise ArchiveError("embedded manifest SHA-256 does not match the report")
        if archive_report.get("manifestBytes") != manifest_bytes:
            raise ArchiveError("embedded manifest byte count does not match the report")

        info_iterator = iter(itertools.islice(infos, 1, None))
        previous_archive_path: bytes | None = None
        file_count = 0
        total_bytes = 0
        observed_by_root = {name: [0, 0] for name in selected_roots}

        def validate_file(record: dict[str, object]) -> None:
            nonlocal previous_archive_path, file_count, total_bytes
            required = {"archivePath", "bytes", "path", "sha256", "sourceRoot"}
            if set(record) != required:
                raise ArchiveError("manifest file record has unexpected fields")
            archive_path = record["archivePath"]
            relative_path = record["path"]
            source_root = record["sourceRoot"]
            expected_size = record["bytes"]
            expected_sha256 = record["sha256"]
            if not isinstance(archive_path, str) or not isinstance(relative_path, str):
                raise ArchiveError("manifest file paths must be strings")
            validate_member_name(archive_path)
            validate_member_name(relative_path)
            if not isinstance(source_root, str) or source_root not in source_roots:
                raise ArchiveError(f"manifest file has an unknown source root: {source_root!r}")
            if archive_path != f"{source_root}/{relative_path}":
                raise ArchiveError("manifest archivePath does not match sourceRoot/path")
            sort_key = archive_path.encode("utf-8")
            if previous_archive_path is not None and sort_key <= previous_archive_path:
                raise ArchiveError("manifest file records are not in deterministic order")
            previous_archive_path = sort_key
            if not isinstance(expected_size, int) or expected_size < 0:
                raise ArchiveError(f"invalid byte count for {archive_path}")
            if (
                not isinstance(expected_sha256, str)
                or len(expected_sha256) != 64
                or any(char not in "0123456789abcdef" for char in expected_sha256)
            ):
                raise ArchiveError(f"invalid SHA-256 for {archive_path}")
            try:
                info = next(info_iterator)
            except StopIteration as error:
                raise ArchiveError("manifest lists more files than the ZIP contains") from error
            if info.filename != archive_path or info.file_size != expected_size:
                raise ArchiveError(f"ZIP metadata does not match manifest: {archive_path}")
            with archive.open(info, "r") as payload:
                payload_sha256, payload_bytes = _hash_binary_stream(payload)
            if payload_sha256 != expected_sha256 or payload_bytes != expected_size:
                raise ArchiveError(f"ZIP payload does not match manifest: {archive_path}")

            if verify_sources:
                local_path = source_roots[source_root].joinpath(*PurePosixPath(relative_path).parts)
                try:
                    resolved = local_path.resolve(strict=True)
                except OSError as error:
                    raise ArchiveError(f"source file is missing: {local_path}") from error
                if not _is_relative_to(resolved, source_roots[source_root]):
                    raise ArchiveError(f"manifest source path escapes its root: {relative_path}")
                local_sha256, local_bytes = _hash_file(local_path)
                if local_sha256 != expected_sha256 or local_bytes != expected_size:
                    raise ArchiveError(f"local source changed after the archive: {local_path}")

            file_count += 1
            total_bytes += expected_size
            observed_by_root[source_root][0] += 1
            observed_by_root[source_root][1] += expected_size

        with archive.open(manifest_info, "r") as manifest_binary:
            with __import__("io").TextIOWrapper(
                manifest_binary, encoding="utf-8", newline=""
            ) as manifest_text:
                header, source_records = _read_manifest_records(manifest_text, validate_file)

        try:
            extra_info = next(info_iterator)
        except StopIteration:
            extra_info = None
        if extra_info is not None:
            raise ArchiveError(f"ZIP contains an unlisted member: {extra_info.filename}")

    if header.get("schemaVersion") != SCHEMA_VERSION:
        raise ArchiveError("unsupported manifest schema version")
    if header.get("manifestType") != "magi-reader-story-data" or header.get("complete") is not True:
        raise ArchiveError("manifest identity or completion flag is invalid")
    if header.get("compression") not in {"deflate", "stored"}:
        raise ArchiveError("manifest compression is invalid")
    expected_sources = []
    for record in source_records:
        name, count, size = _validate_source_record(record)
        expected_sources.append(name)
        if observed_by_root.get(name) != [count, size]:
            raise ArchiveError(f"source root totals do not match files: {name}")
    if tuple(expected_sources) != selected_roots:
        raise ArchiveError("manifest source root selection/order is incorrect")
    totals = header.get("totals")
    if totals != {"bytes": total_bytes, "fileCount": file_count}:
        raise ArchiveError("manifest totals do not match file records")
    if report.get("schemaVersion") != SCHEMA_VERSION or report.get("complete") is not True:
        raise ArchiveError("release report identity or completion flag is invalid")
    if report.get("sourceRoots") != source_records or report.get("totals") != totals:
        raise ArchiveError("release report does not match the embedded manifest")
    return report


def _publish_transaction(
    staged_to_target: list[tuple[Path, Path]],
    *,
    replace_func: Callable[[str | os.PathLike[str], str | os.PathLike[str]], None] = os.replace,
) -> None:
    """Publish staged files as a rollback-capable group."""

    if not staged_to_target:
        raise ArchiveError("publication set is empty")
    target_parent = staged_to_target[0][1].parent
    if any(target.parent != target_parent for _, target in staged_to_target):
        raise ArchiveError("all release files must share one output directory")
    backup_directory = target_parent / f".story-release-rollback-{uuid.uuid4().hex}"
    backup_directory.mkdir()
    backed_up: list[tuple[Path, Path]] = []
    installed: list[Path] = []
    try:
        for _, target in staged_to_target:
            if target.exists():
                backup = backup_directory / target.name
                replace_func(target, backup)
                backed_up.append((backup, target))
        for staged, target in staged_to_target:
            replace_func(staged, target)
            installed.append(target)
    except BaseException:
        for target in reversed(installed):
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
        for backup, target in reversed(backed_up):
            if backup.exists():
                os.replace(backup, target)
        raise
    finally:
        shutil.rmtree(backup_directory, ignore_errors=True)


def build_release(
    output: Path,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    include_roots: Iterable[str] | None = None,
    compression: str = "deflate",
    replace_func: Callable[[str | os.PathLike[str], str | os.PathLike[str]], None] = os.replace,
) -> dict[str, object]:
    """Build, validate and atomically publish a deterministic release."""

    output = Path(output)
    if output.suffix.lower() != ".zip" or not output.name:
        raise ArchiveError("release output must be a named .zip file")
    selected_roots = _selected_root_names(include_roots)
    repository_root = Path(repository_root).resolve(strict=True)
    source_roots = _source_roots(repository_root, selected_roots)
    output_parent = output.parent.resolve(strict=False)
    output_parent.mkdir(parents=True, exist_ok=True)
    output = output_parent / output.name
    for source_root in source_roots.values():
        if _is_relative_to(output, source_root):
            raise ArchiveError("release output may not be inside a selected data root")
    target_paths = release_paths(output)

    staging_directory = Path(
        tempfile.mkdtemp(prefix=".story-release-staging-", dir=output_parent)
    )
    staging_paths = ReleasePaths(
        archive=staging_directory / output.name,
        sha256sums=staging_directory / SHA256SUMS_NAME,
        report=staging_directory / REPORT_NAME,
    )
    inventory_database = staging_directory / "inventory.sqlite3"
    manifest_path = staging_directory / MANIFEST_NAME
    connection: sqlite3.Connection | None = None
    try:
        connection = _open_inventory(inventory_database)
        _inventory_sources(connection, source_roots)
        inventory_summary = _write_manifest(
            manifest_path,
            connection,
            selected_roots,
            compression,
        )
        _build_zip(
            staging_paths.archive,
            manifest_path,
            connection,
            compression,
        )
        report = _write_sidecars(
            staging_paths,
            output.name,
            inventory_summary,
            compression,
            manifest_path,
        )
        connection.close()
        connection = None
        validate_archive(
            staging_paths.archive,
            repository_root=repository_root,
            include_roots=selected_roots,
            verify_sources=False,
            sidecar_paths=staging_paths,
        )
        _publish_transaction(
            [
                (staging_paths.archive, target_paths.archive),
                (staging_paths.sha256sums, target_paths.sha256sums),
                (staging_paths.report, target_paths.report),
            ],
            replace_func=replace_func,
        )
        return report
    finally:
        if connection is not None:
            connection.close()
        shutil.rmtree(staging_directory, ignore_errors=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="repository containing the six canonical data roots",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY / DEFAULT_ARCHIVE_NAME,
        help="target ZIP (sidecars are written beside it)",
    )
    parser.add_argument(
        "--include-root",
        action="append",
        choices=DATA_ROOTS,
        help="include only this canonical data root; repeat for multiple roots",
    )
    parser.add_argument(
        "--compression",
        choices=("deflate", "stored"),
        default="deflate",
        help="deterministic ZIP compression method",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="stream-validate the existing archive, sidecars and selected source roots",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        selected_roots = _selected_root_names(args.include_root)
        if args.validate_only:
            report = validate_archive(
                args.output,
                repository_root=args.repository_root,
                include_roots=selected_roots,
                verify_sources=True,
            )
            action = "validated"
        else:
            report = build_release(
                args.output,
                repository_root=args.repository_root,
                include_roots=selected_roots,
                compression=args.compression,
            )
            action = "built"
    except (ArchiveError, OSError, sqlite3.Error, zipfile.BadZipFile) as error:
        print(f"story release archive error: {error}", file=sys.stderr)
        return 2
    archive = report["archive"]
    totals = report["totals"]
    assert isinstance(archive, dict) and isinstance(totals, dict)
    print(
        f"{action}: {args.output.resolve()}\n"
        f"files={totals['fileCount']} sourceBytes={totals['bytes']} "
        f"archiveBytes={archive['bytes']} sha256={archive['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
