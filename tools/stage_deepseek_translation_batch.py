#!/usr/bin/env python3
"""Validate and stage one DeepSeek story-translation batch.

This module is deliberately fail-closed.  Codex must prepare a batch-specific
allowlist, a translation package containing the complete Japanese TXT rows and
an immutable protection snapshot before this program is run.  The model cannot
read the repository: Claude Code is launched with ``--tools ""`` and receives
only the prepared JSON package on stdin.

There is intentionally no command that writes into either scenario tree.
``stage`` produces candidate TXT files and a checkpoint below an artifact
directory.  A later, separately reviewed transaction may consume those files.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.materialize_proofreading_assets import (
    ReviewedLine,
    ReviewedSection,
    canonical_txt,
    materialize,
    parse_reviewed_text,
)


MODEL = "deepseek-v4-flash"
SCHEMA_VERSION = 1
TRUSTED_MAGIA_BASELINE_COMMIT = "65f221f2aaa5a9fe161ed32e03e4dfbb93d4746d"
TRUSTED_MAGIA_ROOT = PurePosixPath(
    "magireco-translate-data-master/Scenarios_full"
)
DEFAULT_INVENTORY = (
    ROOT / "artifacts/deepseek-retranslation/retranslation-inventory.v1.json"
)
DEFAULT_NAMAE_ROOT = PurePosixPath(
    "magiraexedra-translate-data-master/Scenarios_full/7_Namae"
)
EXEDRA_TRANSLATION_ROOT = PurePosixPath(
    "magiraexedra-translate-data-master/Scenarios_full"
)
PROTECTED_EXEDRA_PROVENANCE = frozenset(
    {"official_tw_human", "exedra_wiki_voice_human", "rounddora_0728_human"}
)
EXPECTED_NAMAE_TW_GROUP_COUNT = 92
EXPECTED_NAMAE_TW_JSON_COUNT = 215
CANONICAL_TEXT_HASH_MODE = "utf8-bom-stripped-lf-v1"
TEXT_FILE_SUFFIXES = frozenset({".json", ".txt"})
ALLOWED_CLASSIFICATIONS = frozenset(
    {"pending_retranslation", "missing_protected_chinese_translation"}
)

HONORIFIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("japanese_chan", re.compile(r"ちゃん")),
    ("romanized_chan", re.compile(r"(?i)(?<![A-Za-z])(?:-\s*)?chan(?![A-Za-z])")),
    ("transliterated_jiang", re.compile(r"酱")),
)
PLACEHOLDER_RE = re.compile(
    r"(?:"
    r"\\n|\\[rt]|"
    r"\$\{[^{}\r\n]+\}|"
    r"\{\{[^{}\r\n]+\}\}|"
    r"\{[^{}\r\n]+\}|"
    r"%(?:\d+\$)?[-+#0 ]*\d*(?:\.\d+)?[a-zA-Z%]|"
    r"</?[A-Za-z][^<>\r\n]*>|"
    r"\[(?:text(?:Red|Blue|Yellow|Black):|/?(?:red|blue|yellow|black)\b)[^\]\r\n]*\]"
    r")"
)


class GateError(RuntimeError):
    """A hard gate failed; no candidate is eligible for publication."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_text_bytes(value: bytes, label: str) -> bytes:
    """Return the auditable UTF-8/BOM/EOL-normalized representation.

    Protected story assets are text files.  Git/autocrlf and Windows editors
    may change only their transport encoding (UTF-8 BOM or line endings), so
    the protection gate hashes decoded text after stripping one UTF-8 BOM and
    normalizing CRLF/CR to LF.  No JSON parsing or whitespace rewriting occurs.
    """

    try:
        text = value.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise GateError(f"protected text is not valid UTF-8: {label}: {exc}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def canonical_text_sha256_bytes(value: bytes, label: str) -> str:
    return sha256_bytes(canonical_text_bytes(value, label))


def canonical_text_sha256_file(path: Path) -> str:
    if path.suffix.lower() not in TEXT_FILE_SUFFIXES:
        raise GateError(f"protected asset is not a JSON/TXT text file: {path}")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise GateError(f"protected text cannot be read: {path}: {exc}") from exc
    return canonical_text_sha256_bytes(payload, str(path))


def protected_tree_sha256(entries: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for path, canonical_sha256 in sorted(entries.items()):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(canonical_sha256.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"{label} is not valid UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GateError(f"{label} must be a JSON object: {path}")
    return value


def _git_output(root: Path, args: Sequence[str], label: str) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        raise GateError(f"{label} failed ({process.returncode}): {detail}")
    return process.stdout


def resolve_commit(root: Path, commit: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise GateError(f"trusted Magia baseline is not a full commit ID: {commit!r}")
    resolved = _git_output(
        root, ["rev-parse", "--verify", f"{commit}^{{commit}}"], "resolve trusted baseline"
    ).decode("ascii", errors="strict").strip().lower()
    if resolved != commit.lower():
        raise GateError(f"trusted Magia baseline resolved unexpectedly: {resolved}")
    return resolved


def trusted_magia_baseline_files(
    root: Path, commit: str
) -> dict[str, str]:
    """Stream canonical hashes for every runtime JSON/TXT in the trusted commit."""

    resolved = resolve_commit(root, commit)
    listing = _git_output(
        root,
        ["ls-tree", "-r", "-z", resolved, "--", TRUSTED_MAGIA_ROOT.as_posix()],
        "list trusted Magia baseline",
    )
    objects: list[tuple[str, str]] = []
    for raw_entry in listing.split(b"\0"):
        if not raw_entry:
            continue
        try:
            raw_meta, raw_path = raw_entry.split(b"\t", 1)
            mode, object_type, object_id = raw_meta.decode("ascii").split()
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GateError("trusted Magia git tree contains an invalid entry") from exc
        if object_type != "blob" or mode == "120000":
            continue
        relative = safe_relative(path, "trusted Magia baseline path")
        if not relative.is_relative_to(TRUSTED_MAGIA_ROOT):
            raise GateError(f"trusted Magia entry escaped its root: {path}")
        if relative.suffix.lower() not in TEXT_FILE_SUFFIXES:
            continue
        objects.append((relative.as_posix(), object_id))
    if not objects:
        raise GateError("trusted Magia baseline contains no runtime JSON/TXT files")

    result: dict[str, str] = {}
    requests = b"".join(object_id.encode("ascii") + b"\n" for _path, object_id in objects)
    # A flush/read round trip for every blob is prohibitively slow for the
    # 10k+ file pinned tree on Windows.  Let Git service the complete batch in
    # one process and spool its output to a temporary file.  This stays bounded
    # in memory, avoids pipe deadlocks, and preserves one header/payload record
    # per listed path.
    with tempfile.TemporaryFile() as batch_output:
        process = subprocess.run(
            ["git", "-C", str(root), "cat-file", "--batch"],
            input=requests,
            stdout=batch_output,
            stderr=subprocess.PIPE,
            check=False,
        )
        stderr = process.stderr.decode("utf-8", errors="replace").strip()
        if process.returncode != 0:
            raise GateError(f"git cat-file failed ({process.returncode}): {stderr}")
        batch_output.seek(0)
        for path, object_id in objects:
            header = batch_output.readline()
            parts = header.rstrip(b"\n").split()
            if (
                len(parts) != 3
                or parts[0].decode("ascii", errors="replace") != object_id
                or parts[1] != b"blob"
            ):
                raise GateError(f"git cat-file returned an invalid header for {path}: {header!r}")
            try:
                size = int(parts[2])
            except ValueError as exc:
                raise GateError(f"git cat-file returned an invalid size for {path}") from exc
            payload = batch_output.read(size)
            terminator = batch_output.read(1)
            if len(payload) != size or terminator != b"\n":
                raise GateError(f"git cat-file returned a truncated blob for {path}")
            result[path] = canonical_text_sha256_bytes(payload, f"{resolved}:{path}")
        if batch_output.read(1):
            raise GateError("git cat-file returned unexpected trailing output")
        if len(result) != len(objects):
            raise GateError("trusted Magia baseline path inventory is not unique")
        return result


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def require_exact_keys(
    value: Mapping[str, Any], *, required: Iterable[str], optional: Iterable[str] = (), label: str
) -> None:
    required_set = set(required)
    allowed = required_set | set(optional)
    missing = sorted(required_set - set(value))
    extra = sorted(set(value) - allowed)
    if missing or extra:
        raise GateError(f"{label} keys invalid; missing={missing}, extra={extra}")


def safe_relative(value: str, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise GateError(f"{label} must be a non-empty POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in value
    ):
        raise GateError(f"unsafe {label}: {value!r}")
    return path


def repo_path(root: Path, value: str, label: str) -> Path:
    return root.joinpath(*safe_relative(value, label).parts)


def verify_digest(path: Path, expected: str, label: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
        raise GateError(f"{label} has an invalid SHA-256: {expected!r}")
    if not path.is_file() or path.is_symlink():
        raise GateError(f"{label} is missing or is a symlink: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise GateError(f"{label} SHA-256 drift: expected={expected}, actual={actual}")


def _protected_entry(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise GateError(f"{label} must be an object")
    require_exact_keys(
        value, required=("path", "sha256", "hash_mode", "classification"), label=label
    )
    path = safe_relative(value["path"], f"{label}.path").as_posix()
    classification = value["classification"]
    if classification not in {"official", "human", *PROTECTED_EXEDRA_PROVENANCE}:
        raise GateError(f"{label}.classification is not protected: {classification!r}")
    if value["hash_mode"] != CANONICAL_TEXT_HASH_MODE:
        raise GateError(f"{label}.hash_mode is not the canonical text policy")
    return {
        "path": path,
        "sha256": str(value["sha256"]),
        "hash_mode": CANONICAL_TEXT_HASH_MODE,
        "classification": str(classification),
    }


def verify_protected_digest(path: Path, expected: str, label: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
        raise GateError(f"{label} has an invalid canonical SHA-256: {expected!r}")
    if not path.is_file() or path.is_symlink():
        raise GateError(f"{label} is missing or is a symlink: {path}")
    actual = canonical_text_sha256_file(path)
    if actual != expected:
        raise GateError(
            f"{label} canonical SHA-256 drift: expected={expected}, actual={actual}"
        )


def _group_text_paths(group_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in group_dir.iterdir()
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in TEXT_FILE_SUFFIXES
    )


def _is_runtime_story_json(path: PurePosixPath | Path) -> bool:
    name = path.name
    return (
        path.suffix.lower() == ".json"
        and not name.endswith("_cn.provenance.json")
        and not name.endswith("_cn.import-report.json")
    )


def _load_protected_exedra_sidecars(root: Path) -> dict[str, dict[str, Any]]:
    exedra_root = root.joinpath(*EXEDRA_TRANSLATION_ROOT.parts)
    if not exedra_root.is_dir() or exedra_root.is_symlink():
        raise GateError(f"Exedra translated root is unavailable: {exedra_root}")
    result: dict[str, dict[str, Any]] = {}
    for provenance_path in sorted(exedra_root.rglob("*_cn.provenance.json")):
        if not provenance_path.is_file() or provenance_path.is_symlink():
            continue
        provenance = load_object(provenance_path, "Exedra provenance")
        classification = provenance.get("provenance")
        if classification not in PROTECTED_EXEDRA_PROVENANCE:
            continue
        group_rel = provenance_path.parent.relative_to(root).as_posix()
        if group_rel in result:
            raise GateError(f"Exedra group has duplicate protected provenance: {group_rel}")
        if provenance.get("machineTranslation") is not False:
            raise GateError(f"protected Exedra provenance is marked machine translated: {provenance_path}")
        if classification == "official_tw_human" and provenance.get("officialTw") is not True:
            raise GateError(f"official TW provenance lacks officialTw=true: {provenance_path}")
        result[group_rel] = {
            "path": provenance_path,
            "value": provenance,
            "classification": classification,
        }
    return result


def _verify_group_record(
    root: Path,
    raw_group: Any,
    *,
    label: str,
    protected_by_path: Mapping[str, Mapping[str, str]],
) -> tuple[str, str, set[str], int]:
    if not isinstance(raw_group, dict):
        raise GateError(f"{label} must be an object")
    require_exact_keys(
        raw_group,
        required=(
            "group_id", "group_path", "provenance", "provenance_path",
            "provenance_sha256", "provenance_hash_mode", "files",
        ),
        label=label,
    )
    group_path_rel = safe_relative(raw_group["group_path"], f"{label}.group_path")
    if not group_path_rel.is_relative_to(EXEDRA_TRANSLATION_ROOT):
        raise GateError(f"{label} is outside the Exedra translated root")
    group_dir = root.joinpath(*group_path_rel.parts)
    if not group_dir.is_dir() or group_dir.is_symlink():
        raise GateError(f"{label} group directory is unavailable: {group_dir}")
    if raw_group["group_id"] != group_dir.name:
        raise GateError(f"{label}.group_id does not match its directory")
    classification = raw_group["provenance"]
    if classification not in PROTECTED_EXEDRA_PROVENANCE:
        raise GateError(f"{label}.provenance is not protected: {classification!r}")
    provenance_rel = safe_relative(raw_group["provenance_path"], f"{label}.provenance_path")
    provenance_path = root.joinpath(*provenance_rel.parts)
    if provenance_path.parent != group_dir:
        raise GateError(f"{label} provenance is outside its group")
    if raw_group["provenance_hash_mode"] != CANONICAL_TEXT_HASH_MODE:
        raise GateError(f"{label}.provenance_hash_mode is invalid")
    verify_protected_digest(provenance_path, str(raw_group["provenance_sha256"]), f"{label} provenance")
    provenance = load_object(provenance_path, f"{label} provenance")
    if provenance.get("provenance") != classification or provenance.get("machineTranslation") is not False:
        raise GateError(f"{label} live provenance classification drifted")
    if classification == "official_tw_human" and provenance.get("officialTw") is not True:
        raise GateError(f"{label} official TW provenance lost officialTw=true")

    raw_files = raw_group["files"]
    if not isinstance(raw_files, list) or not raw_files:
        raise GateError(f"{label}.files must be non-empty")
    listed: set[str] = set()
    runtime_json_count = 0
    for file_index, raw_file in enumerate(raw_files):
        file_label = f"{label}.files[{file_index}]"
        if not isinstance(raw_file, dict):
            raise GateError(f"{file_label} must be an object")
        require_exact_keys(raw_file, required=("path", "sha256", "hash_mode"), label=file_label)
        if raw_file["hash_mode"] != CANONICAL_TEXT_HASH_MODE:
            raise GateError(f"{file_label}.hash_mode is invalid")
        relative = safe_relative(raw_file["path"], f"{file_label}.path")
        candidate = root.joinpath(*relative.parts)
        if candidate.parent != group_dir:
            raise GateError(f"{file_label} is outside its protected group")
        text = relative.as_posix()
        if text in listed:
            raise GateError(f"{file_label} duplicates a group file")
        listed.add(text)
        verify_protected_digest(candidate, str(raw_file["sha256"]), file_label)
        protected = protected_by_path.get(text)
        if (
            protected is None
            or protected["classification"] != classification
            or protected["hash_mode"] != CANONICAL_TEXT_HASH_MODE
            or protected["sha256"] != str(raw_file["sha256"])
        ):
            raise GateError(
                f"{file_label} is absent/misclassified or its hash disagrees with protected_files"
            )
        if _is_runtime_story_json(relative):
            runtime_json_count += 1
    actual = {path.relative_to(root).as_posix() for path in _group_text_paths(group_dir)}
    if listed != actual:
        raise GateError(
            f"{label} file inventory is open: missing={sorted(actual-listed)}, "
            f"extra={sorted(listed-actual)}"
        )
    return group_path_rel.as_posix(), provenance_rel.as_posix(), listed, runtime_json_count


def verify_protection_snapshot(
    root: Path,
    snapshot: Mapping[str, Any],
    *,
    trusted_magia_commit: str = TRUSTED_MAGIA_BASELINE_COMMIT,
    expected_namae_tw_group_count: int = EXPECTED_NAMAE_TW_GROUP_COUNT,
    expected_namae_tw_json_count: int = EXPECTED_NAMAE_TW_JSON_COUNT,
) -> dict[str, Any]:
    require_exact_keys(
        snapshot,
        required=(
            "schema_version", "hash_policy", "protected_files", "magia_trusted_baseline",
            "exedra_human_authority", "namae_tw_authority",
        ),
        label="protection snapshot",
    )
    if snapshot["schema_version"] != SCHEMA_VERSION:
        raise GateError("unsupported protection snapshot schema")
    hash_policy = snapshot["hash_policy"]
    if not isinstance(hash_policy, dict):
        raise GateError("hash_policy must be an object")
    require_exact_keys(hash_policy, required=("mode", "normalization"), label="hash_policy")
    if hash_policy != {
        "mode": CANONICAL_TEXT_HASH_MODE,
        "normalization": "decode UTF-8-sig; CRLF/CR to LF; encode UTF-8; no semantic rewrite",
    }:
        raise GateError("protection snapshot hash policy is not canonical")

    raw_protected = snapshot["protected_files"]
    if not isinstance(raw_protected, list):
        raise GateError("protected_files must be a list")
    protected = [
        _protected_entry(item, f"protected_files[{index}]")
        for index, item in enumerate(raw_protected)
    ]
    protected_by_path = {item["path"]: item for item in protected}
    if len(protected_by_path) != len(protected):
        raise GateError("protected_files contains duplicate paths")

    magia = snapshot["magia_trusted_baseline"]
    if not isinstance(magia, dict):
        raise GateError("magia_trusted_baseline must be an object")
    require_exact_keys(
        magia,
        required=("commit", "root", "expected_file_count", "tree_sha256"),
        label="magia_trusted_baseline",
    )
    if magia["commit"] != trusted_magia_commit or magia["root"] != TRUSTED_MAGIA_ROOT.as_posix():
        raise GateError("Magia trusted baseline commit/root is not the pinned authority")
    baseline = trusted_magia_baseline_files(root, trusted_magia_commit)
    if magia["expected_file_count"] != len(baseline) or magia["tree_sha256"] != protected_tree_sha256(baseline):
        raise GateError("Magia trusted baseline count/tree digest is open or drifted")
    expected_protected_paths: set[str] = set()
    for path, baseline_hash in baseline.items():
        entry = protected_by_path.get(path)
        if (
            entry is None
            or entry["classification"] != "human"
            or entry["hash_mode"] != CANONICAL_TEXT_HASH_MODE
            or entry["sha256"] != baseline_hash
        ):
            raise GateError(f"trusted Magia runtime file is absent/misclassified: {path}")
        verify_protected_digest(repo_path(root, path, "trusted Magia file"), baseline_hash, path)
        expected_protected_paths.add(path)

    exedra = snapshot["exedra_human_authority"]
    if not isinstance(exedra, dict):
        raise GateError("exedra_human_authority must be an object")
    require_exact_keys(
        exedra,
        required=("root", "allowed_provenance", "expected_group_count", "groups"),
        label="exedra_human_authority",
    )
    if exedra["root"] != EXEDRA_TRANSLATION_ROOT.as_posix() or exedra["allowed_provenance"] != sorted(PROTECTED_EXEDRA_PROVENANCE):
        raise GateError("Exedra protected provenance policy drifted")
    groups = exedra["groups"]
    if not isinstance(groups, list) or exedra["expected_group_count"] != len(groups):
        raise GateError("Exedra protected group count/list is open")
    live_sidecars = _load_protected_exedra_sidecars(root)
    if len(groups) != len(live_sidecars):
        raise GateError(
            f"Exedra protected group count is open: expected={len(live_sidecars)}, listed={len(groups)}"
        )
    group_by_path: dict[str, Mapping[str, Any]] = {}
    exedra_file_count = 0
    for index, raw_group in enumerate(groups):
        group_path, provenance_path, files, _json_count = _verify_group_record(
            root,
            raw_group,
            label=f"exedra_human_authority.groups[{index}]",
            protected_by_path=protected_by_path,
        )
        if group_path in group_by_path:
            raise GateError(f"Exedra authority duplicates group path: {group_path}")
        live = live_sidecars.get(group_path)
        if live is None or live["path"].relative_to(root).as_posix() != provenance_path:
            raise GateError(f"Exedra protected live group/sidecar is absent: {group_path}")
        group_by_path[group_path] = raw_group
        expected_protected_paths.update(files)
        exedra_file_count += len(files)
    if set(group_by_path) != set(live_sidecars):
        raise GateError("Exedra protected group path set is open")

    namae = snapshot["namae_tw_authority"]
    if not isinstance(namae, dict):
        raise GateError("namae_tw_authority must be an object")
    require_exact_keys(
        namae,
        required=("root", "expected_group_count", "expected_json_count", "groups"),
        label="namae_tw_authority",
    )
    if namae["root"] != DEFAULT_NAMAE_ROOT.as_posix():
        raise GateError("7_Namae authority root drifted")
    namae_groups = namae["groups"]
    if (
        not isinstance(namae_groups, list)
        or namae["expected_group_count"] != expected_namae_tw_group_count
        or len(namae_groups) != expected_namae_tw_group_count
        or namae["expected_json_count"] != expected_namae_tw_json_count
    ):
        raise GateError("7_Namae official TW declared counts are not closed")
    actual_namae_paths = {
        path
        for path, live in live_sidecars.items()
        if PurePosixPath(path).is_relative_to(DEFAULT_NAMAE_ROOT)
        and live["classification"] == "official_tw_human"
    }
    listed_namae_paths: set[str] = set()
    namae_files: set[str] = set()
    namae_json_count = 0
    for index, raw_group in enumerate(namae_groups):
        group_path, _provenance_path, files, json_count = _verify_group_record(
            root,
            raw_group,
            label=f"namae_tw_authority.groups[{index}]",
            protected_by_path=protected_by_path,
        )
        if not PurePosixPath(group_path).is_relative_to(DEFAULT_NAMAE_ROOT):
            raise GateError(f"7_Namae group escaped its authority root: {group_path}")
        if raw_group["provenance"] != "official_tw_human":
            raise GateError(f"7_Namae authority is not official TW: {group_path}")
        if group_path in listed_namae_paths or group_by_path.get(group_path) != raw_group:
            raise GateError(f"7_Namae group is duplicated or differs from Exedra authority: {group_path}")
        listed_namae_paths.add(group_path)
        namae_files.update(files)
        namae_json_count += json_count
    if listed_namae_paths != actual_namae_paths or namae_json_count != expected_namae_tw_json_count:
        raise GateError(
            "7_Namae TW protection count/set is open: "
            f"groups_expected={sorted(actual_namae_paths)}, groups_listed={sorted(listed_namae_paths)}, "
            f"json_expected={expected_namae_tw_json_count}, json_listed={namae_json_count}"
        )

    if set(protected_by_path) != expected_protected_paths:
        raise GateError(
            "protected_files contains an unclassified or missing path: "
            f"missing={sorted(expected_protected_paths-set(protected_by_path))}, "
            f"extra={sorted(set(protected_by_path)-expected_protected_paths)}"
        )
    return {
        "protected_file_count": len(protected_by_path),
        "protected_paths": frozenset(protected_by_path),
        "magia_baseline_file_count": len(baseline),
        "exedra_human_group_count": len(group_by_path),
        "exedra_human_file_count": exedra_file_count,
        "namae_tw_group_count": len(namae_groups),
        "namae_tw_file_count": len(namae_files),
        "namae_tw_json_count": namae_json_count,
    }


def snapshot_protection(
    root: Path,
    inventory: Mapping[str, Any],
    *,
    trusted_magia_commit: str = TRUSTED_MAGIA_BASELINE_COMMIT,
    expected_namae_tw_group_count: int = EXPECTED_NAMAE_TW_GROUP_COUNT,
    expected_namae_tw_json_count: int = EXPECTED_NAMAE_TW_JSON_COUNT,
) -> dict[str, Any]:
    """Build a closed snapshot from pinned Git baseline and explicit provenance."""

    # The translation inventory remains a required classification input, but it
    # cannot narrow the protection boundary.  Unknown/blocked records therefore
    # never become protected merely because they appear in the public index.
    if not isinstance(inventory.get("official_or_human_protected"), list):
        raise GateError("inventory lacks official_or_human_protected")
    baseline = trusted_magia_baseline_files(root, trusted_magia_commit)
    protected_by_path: dict[str, dict[str, str]] = {}
    for relative, baseline_hash in baseline.items():
        current = repo_path(root, relative, "trusted Magia runtime file")
        verify_protected_digest(current, baseline_hash, relative)
        protected_by_path[relative] = {
            "path": relative,
            "sha256": baseline_hash,
            "hash_mode": CANONICAL_TEXT_HASH_MODE,
            "classification": "human",
        }

    live_sidecars = _load_protected_exedra_sidecars(root)
    groups: list[dict[str, Any]] = []
    for group_path, live in sorted(live_sidecars.items()):
        provenance_path: Path = live["path"]
        classification = str(live["classification"])
        files: list[dict[str, str]] = []
        for path in _group_text_paths(provenance_path.parent):
            relative = path.relative_to(root).as_posix()
            digest = canonical_text_sha256_file(path)
            files.append(
                {"path": relative, "sha256": digest, "hash_mode": CANONICAL_TEXT_HASH_MODE}
            )
            if relative in protected_by_path:
                raise GateError(f"protected path belongs to two authorities: {relative}")
            protected_by_path[relative] = {
                "path": relative,
                "sha256": digest,
                "hash_mode": CANONICAL_TEXT_HASH_MODE,
                "classification": classification,
            }
        group = {
            "group_id": provenance_path.parent.name,
            "group_path": group_path,
            "provenance": classification,
            "provenance_path": provenance_path.relative_to(root).as_posix(),
            "provenance_sha256": canonical_text_sha256_file(provenance_path),
            "provenance_hash_mode": CANONICAL_TEXT_HASH_MODE,
            "files": files,
        }
        groups.append(group)

    namae_groups = [
        group
        for group in groups
        if PurePosixPath(group["group_path"]).is_relative_to(DEFAULT_NAMAE_ROOT)
        and group["provenance"] == "official_tw_human"
    ]
    namae_json_count = sum(
        1
        for group in namae_groups
        for item in group["files"]
        if _is_runtime_story_json(PurePosixPath(item["path"]))
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "hash_policy": {
            "mode": CANONICAL_TEXT_HASH_MODE,
            "normalization": "decode UTF-8-sig; CRLF/CR to LF; encode UTF-8; no semantic rewrite",
        },
        "protected_files": sorted(protected_by_path.values(), key=lambda item: item["path"]),
        "magia_trusted_baseline": {
            "commit": trusted_magia_commit,
            "root": TRUSTED_MAGIA_ROOT.as_posix(),
            "expected_file_count": len(baseline),
            "tree_sha256": protected_tree_sha256(baseline),
        },
        "exedra_human_authority": {
            "root": EXEDRA_TRANSLATION_ROOT.as_posix(),
            "allowed_provenance": sorted(PROTECTED_EXEDRA_PROVENANCE),
            "expected_group_count": len(groups),
            "groups": groups,
        },
        "namae_tw_authority": {
            "root": DEFAULT_NAMAE_ROOT.as_posix(),
            "expected_group_count": len(namae_groups),
            "expected_json_count": namae_json_count,
            "groups": namae_groups,
        },
    }
    verify_protection_snapshot(
        root,
        result,
        trusted_magia_commit=trusted_magia_commit,
        expected_namae_tw_group_count=expected_namae_tw_group_count,
        expected_namae_tw_json_count=expected_namae_tw_json_count,
    )
    return result


def _inventory_queue(inventory: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    entries = inventory.get("pending_retranslation")
    if not isinstance(entries, list):
        raise GateError("inventory lacks pending_retranslation")
    queue: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or entry.get("classification") != "pending_retranslation":
            raise GateError(f"inventory pending entry {index} is invalid")
        story_id = str(entry.get("story_id") or "")
        if not story_id or story_id in queue:
            raise GateError("inventory contains empty or duplicate pending story IDs")
        queue[story_id] = entry
    return queue


def validate_allowlist(
    root: Path, allowlist: Mapping[str, Any], inventory: Mapping[str, Any]
) -> list[dict[str, Any]]:
    require_exact_keys(allowlist, required=("schema_version", "entries"), label="allowlist")
    if allowlist["schema_version"] != SCHEMA_VERSION or not isinstance(allowlist["entries"], list):
        raise GateError("allowlist schema/entries is invalid")
    queue = _inventory_queue(inventory)
    normalized: list[dict[str, Any]] = []
    story_ids: set[str] = set()
    for index, raw in enumerate(allowlist["entries"]):
        label = f"allowlist.entries[{index}]"
        if not isinstance(raw, dict):
            raise GateError(f"{label} must be an object")
        require_exact_keys(
            raw,
            required=(
                "story_id", "classification", "jp_txt", "target_cn_txt",
                "jp_sha256", "target_before_sha256",
            ),
            label=label,
        )
        story_id = str(raw["story_id"])
        if story_id in story_ids or story_id not in queue:
            raise GateError(f"{label} is duplicate or absent from pending inventory: {story_id}")
        story_ids.add(story_id)
        if raw["classification"] not in ALLOWED_CLASSIFICATIONS:
            raise GateError(f"{label} classification is not translatable")
        inventory_entry = queue[story_id]
        if (
            raw["classification"] != inventory_entry["classification"]
            or raw["jp_txt"] != inventory_entry["jp_txt"]
            or raw["target_cn_txt"] != inventory_entry["cn_txt"]
        ):
            raise GateError(f"{label} does not exactly match the classified inventory")
        jp_path = repo_path(root, raw["jp_txt"], f"{label}.jp_txt")
        target_path = repo_path(root, raw["target_cn_txt"], f"{label}.target_cn_txt")
        verify_digest(jp_path, str(raw["jp_sha256"]), f"{label} Japanese source")
        verify_digest(target_path, str(raw["target_before_sha256"]), f"{label} target baseline")
        normalized.append(dict(raw))
    if not normalized:
        raise GateError("allowlist must select at least one story")
    return normalized


def source_segments(text: str, label: str) -> tuple[tuple[ReviewedSection, ...], list[dict[str, Any]]]:
    try:
        sections = parse_reviewed_text(text, label)
    except Exception as exc:
        raise GateError(f"Japanese TXT cannot be structurally parsed: {label}: {exc}") from exc
    segments: list[dict[str, Any]] = []
    for section_index, section in enumerate(sections):
        for line_index, line in enumerate(section.lines):
            if line.kind == "interview_marker":
                continue
            segments.append(
                {
                    "segment_id": f"S{section_index+1:04d}L{line_index+1:05d}",
                    "section_index": section_index,
                    "line_index": line_index,
                    "kind": line.kind,
                    "speaker": line.speaker,
                    "source_text": line.text,
                }
            )
    return sections, segments


def validate_package(
    root: Path,
    package: Mapping[str, Any],
    allow_entries: Sequence[Mapping[str, Any]],
    protected_paths: frozenset[str],
) -> list[dict[str, Any]]:
    require_exact_keys(
        package,
        required=(
            "schema_version", "batch_id", "model", "glossary_version",
            "glossary_sha256", "entries",
        ),
        label="translation package",
    )
    if package["schema_version"] != SCHEMA_VERSION or package["model"] != MODEL:
        raise GateError("translation package schema/model is invalid")
    if not isinstance(package["batch_id"], str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", package["batch_id"]):
        raise GateError("batch_id is invalid")
    if not isinstance(package["glossary_version"], str) or not package["glossary_version"]:
        raise GateError("glossary_version is empty")
    if not re.fullmatch(r"[0-9a-f]{64}", str(package["glossary_sha256"])):
        raise GateError("glossary_sha256 is invalid")
    raw_entries = package["entries"]
    if not isinstance(raw_entries, list) or len(raw_entries) != len(allow_entries):
        raise GateError("DS input entry count is not identical to the Codex allowlist")
    normalized: list[dict[str, Any]] = []
    allow_by_id = {str(item["story_id"]): item for item in allow_entries}
    package_ids: list[str] = []
    for index, raw in enumerate(raw_entries):
        label = f"translation package entries[{index}]"
        if not isinstance(raw, dict):
            raise GateError(f"{label} must be an object")
        require_exact_keys(
            raw,
            required=(
                "story_id", "classification", "jp_txt", "target_cn_txt", "jp_sha256",
                "target_before_sha256", "title", "context", "speaker_relationships",
                "approved_terms", "protected_references", "segments",
            ),
            label=label,
        )
        story_id = str(raw["story_id"])
        package_ids.append(story_id)
        allow = allow_by_id.get(story_id)
        if allow is None:
            raise GateError(f"{label} is absent from the Codex allowlist")
        for field in (
            "story_id", "classification", "jp_txt", "target_cn_txt", "jp_sha256", "target_before_sha256"
        ):
            if raw[field] != allow[field]:
                raise GateError(f"{label}.{field} differs from the Codex allowlist")
        if raw["target_cn_txt"] in protected_paths:
            raise GateError(f"{label} attempts to target a protected official/human file")
        for text_field in ("title", "context"):
            if not isinstance(raw[text_field], str) or not raw[text_field].strip():
                raise GateError(f"{label}.{text_field} must be non-empty")
        for list_field in ("speaker_relationships", "approved_terms", "protected_references"):
            if not isinstance(raw[list_field], list):
                raise GateError(f"{label}.{list_field} must be a list")
        jp_path = repo_path(root, raw["jp_txt"], f"{label}.jp_txt")
        sections, derived = source_segments(jp_path.read_text(encoding="utf-8-sig"), raw["jp_txt"])
        if raw["segments"] != derived:
            raise GateError(f"{label}.segments is not the complete, exact Japanese TXT row sequence")
        normalized.append({"raw": raw, "sections": sections, "segments": derived})
    if package_ids != [str(item["story_id"]) for item in allow_entries]:
        raise GateError("DS input order/list is not identical to the Codex allowlist")
    return normalized


RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["batch_id", "results"],
    "properties": {
        "batch_id": {"type": "string"},
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["story_id", "translations", "term_hits", "unresolved"],
                "properties": {
                    "story_id": {"type": "string"},
                    "translations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["segment_id", "text"],
                            "properties": {
                                "segment_id": {"type": "string"},
                                "text": {"type": "string"},
                            },
                        },
                    },
                    "term_hits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["term_id", "segment_ids"],
                            "properties": {
                                "term_id": {"type": "string"},
                                "segment_ids": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                    "unresolved": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["segment_id", "source", "reason"],
                            "properties": {
                                "segment_id": {"type": "string"},
                                "source": {"type": "string"},
                                "reason": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
}


def build_prompt(package: Mapping[str, Any]) -> str:
    payload = json.dumps(package, ensure_ascii=False, separators=(",", ":"))
    return (
        "You are a translation-only worker. Translate the supplied Japanese story rows into natural "
        "Simplified Chinese using only the supplied context, approved terms and protected references. "
        "Do not research, inspect files, infer provenance, plan engineering work, run tools, or add facts. "
        "If a name/term or context is insufficient, add an unresolved item instead of guessing. Preserve "
        "every segment ID, information, placeholder, control token, and literal \\n count. Do not output "
        "speakers or structure. For Japanese personal-name/nickname suffix ちゃん, use 小 + the approved "
        "Chinese address; never output ちゃん, chan, -chan, or 酱. Translate lexical uses such as 赤ちゃん "
        "by meaning, never by character replacement. Return only the JSON object required by the schema.\n"
        "TRANSLATION_PACKAGE_JSON:\n" + payload
    )


def claude_command(claude_binary: str = "claude") -> list[str]:
    executable = shutil.which(claude_binary) or claude_binary
    return [
        executable,
        "-p",
        "--model",
        MODEL,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(RESULT_SCHEMA, ensure_ascii=False, separators=(",", ":")),
        "--tools",
        "",
        "--disallowed-tools",
        "mcp__*",
    ]


def _terminate_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.kill()


def invoke_claude(prompt: str, *, claude_binary: str, timeout_seconds: int, cwd: Path) -> dict[str, Any]:
    command = claude_command(claude_binary)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_tree(process)
        stdout, stderr = process.communicate()
        raise GateError(f"Claude translation worker timed out after {timeout_seconds}s") from exc
    if process.returncode != 0:
        tail = stderr[-2000:].replace("\r", " ").replace("\n", " ")
        raise GateError(f"Claude translation worker failed ({process.returncode}): {tail}")
    try:
        outer = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise GateError("Claude worker did not return outer JSON") from exc
    if not isinstance(outer, dict) or outer.get("is_error") is True or outer.get("subtype") == "error":
        raise GateError("Claude worker returned an error result")
    return outer


def extract_worker_result(outer: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    observed_models: set[str] = set()
    for key in ("modelUsage", "model_usage"):
        value = outer.get(key)
        if isinstance(value, dict):
            observed_models.update(str(model) for model in value)
    if isinstance(outer.get("model"), str):
        observed_models.add(str(outer["model"]))
    if observed_models != {MODEL}:
        raise GateError(f"worker model mismatch: observed={sorted(observed_models)}")
    inner: Any = outer.get("structured_output")
    if inner is None:
        raw = outer.get("result")
        if not isinstance(raw, str):
            raise GateError("Claude outer JSON lacks a structured translation result")
        try:
            inner = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GateError("Claude result is not a bare JSON object") from exc
    if not isinstance(inner, dict):
        raise GateError("worker translation result must be an object")
    metadata = {
        "session_id": str(outer.get("session_id") or outer.get("sessionId") or ""),
        "observed_models": sorted(observed_models),
        "outer_sha256": sha256_bytes(canonical_json_bytes(outer)),
    }
    return inner, metadata


def _require_result_shape(result: Mapping[str, Any], package: Mapping[str, Any]) -> None:
    require_exact_keys(result, required=("batch_id", "results"), label="worker result")
    if result["batch_id"] != package["batch_id"] or not isinstance(result["results"], list):
        raise GateError("worker result batch ID/list is invalid")


def placeholder_counts(value: str) -> collections.Counter[str]:
    return collections.Counter(PLACEHOLDER_RE.findall(value))


def honorific_violations(value: str) -> list[str]:
    return [code for code, pattern in HONORIFIC_PATTERNS if pattern.search(value)]


def validate_worker_result(
    result: Mapping[str, Any],
    package: Mapping[str, Any],
    prepared_entries: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _require_result_shape(result, package)
    raw_results = result["results"]
    expected_ids = [str(entry["raw"]["story_id"]) for entry in prepared_entries]
    actual_ids: list[str] = []
    candidates: list[dict[str, Any]] = []
    unresolved_all: list[dict[str, Any]] = []
    for index, (raw_result, prepared) in enumerate(zip(raw_results, prepared_entries, strict=False)):
        label = f"worker results[{index}]"
        if not isinstance(raw_result, dict):
            raise GateError(f"{label} must be an object")
        require_exact_keys(
            raw_result,
            required=("story_id", "translations", "term_hits", "unresolved"),
            label=label,
        )
        story_id = str(raw_result["story_id"])
        actual_ids.append(story_id)
        if story_id != prepared["raw"]["story_id"]:
            raise GateError(f"{label} story order differs from the Codex package")
        segments = prepared["segments"]
        segment_by_id = {item["segment_id"]: item for item in segments}
        translations = raw_result["translations"]
        unresolved = raw_result["unresolved"]
        term_hits = raw_result["term_hits"]
        if not all(isinstance(value, list) for value in (translations, unresolved, term_hits)):
            raise GateError(f"{label} translation fields must be lists")
        unresolved_ids: set[str] = set()
        for unresolved_index, item in enumerate(unresolved):
            item_label = f"{label}.unresolved[{unresolved_index}]"
            if not isinstance(item, dict):
                raise GateError(f"{item_label} must be an object")
            require_exact_keys(item, required=("segment_id", "source", "reason"), label=item_label)
            segment_id = item["segment_id"]
            if segment_id not in segment_by_id or segment_id in unresolved_ids:
                raise GateError(f"{item_label} has an unknown/duplicate segment")
            if item["source"] != segment_by_id[segment_id]["source_text"] or not str(item["reason"]).strip():
                raise GateError(f"{item_label} source/reason is invalid")
            unresolved_ids.add(segment_id)
            unresolved_all.append({"story_id": story_id, **item})

        translation_by_id: dict[str, str] = {}
        for translation_index, item in enumerate(translations):
            item_label = f"{label}.translations[{translation_index}]"
            if not isinstance(item, dict):
                raise GateError(f"{item_label} must be an object")
            require_exact_keys(item, required=("segment_id", "text"), label=item_label)
            segment_id = item["segment_id"]
            text = item["text"]
            if (
                segment_id not in segment_by_id
                or segment_id in translation_by_id
                or segment_id in unresolved_ids
                or not isinstance(text, str)
                or not text.strip()
            ):
                raise GateError(f"{item_label} has an unknown/duplicate/empty segment")
            source = segment_by_id[segment_id]["source_text"]
            if source.count("\n") != text.count("\n"):
                raise GateError(f"{item_label} literal newline count changed")
            if placeholder_counts(source) != placeholder_counts(text):
                raise GateError(f"{item_label} placeholders/control tokens changed")
            violations = honorific_violations(text)
            if violations:
                raise GateError(f"{item_label} honorific QA failed: {violations}")
            translation_by_id[segment_id] = text

        if set(translation_by_id) | unresolved_ids != set(segment_by_id):
            missing = sorted(set(segment_by_id) - set(translation_by_id) - unresolved_ids)
            raise GateError(f"{label} does not account for every segment: missing={missing}")
        approved_term_ids = {
            str(term.get("term_id"))
            for term in prepared["raw"]["approved_terms"]
            if isinstance(term, dict) and term.get("term_id")
        }
        seen_hits: set[str] = set()
        for hit_index, hit in enumerate(term_hits):
            hit_label = f"{label}.term_hits[{hit_index}]"
            if not isinstance(hit, dict):
                raise GateError(f"{hit_label} must be an object")
            require_exact_keys(hit, required=("term_id", "segment_ids"), label=hit_label)
            term_id = str(hit["term_id"])
            if term_id not in approved_term_ids or term_id in seen_hits or not isinstance(hit["segment_ids"], list):
                raise GateError(f"{hit_label} cites an unknown/duplicate approved term")
            if any(segment_id not in segment_by_id for segment_id in hit["segment_ids"]):
                raise GateError(f"{hit_label} cites an unknown segment")
            seen_hits.add(term_id)

        if not unresolved_ids:
            candidates.append(
                {
                    "story_id": story_id,
                    "sections": prepared["sections"],
                    "segments": segments,
                    "translations": translation_by_id,
                    "target_cn_txt": prepared["raw"]["target_cn_txt"],
                }
            )
    if len(raw_results) != len(prepared_entries) or actual_ids != expected_ids:
        raise GateError("worker result list is not identical to the Codex package")
    return candidates, unresolved_all


def render_candidate(candidate: Mapping[str, Any]) -> str:
    translations: Mapping[str, str] = candidate["translations"]
    updated_sections: list[ReviewedSection] = []
    for section_index, section in enumerate(candidate["sections"]):
        updated_lines: list[ReviewedLine] = []
        for line_index, line in enumerate(section.lines):
            segment_id = f"S{section_index+1:04d}L{line_index+1:05d}"
            if line.kind == "interview_marker":
                updated_lines.append(line)
            else:
                updated_lines.append(dataclasses.replace(line, text=translations[segment_id]))
        updated_sections.append(dataclasses.replace(section, lines=tuple(updated_lines)))
    return canonical_txt(updated_sections)


def preflight(
    *, root: Path, inventory: Mapping[str, Any], allowlist: Mapping[str, Any],
    package: Mapping[str, Any], protection: Mapping[str, Any],
    trusted_magia_commit: str = TRUSTED_MAGIA_BASELINE_COMMIT,
    expected_namae_tw_group_count: int = EXPECTED_NAMAE_TW_GROUP_COUNT,
    expected_namae_tw_json_count: int = EXPECTED_NAMAE_TW_JSON_COUNT,
) -> dict[str, Any]:
    protection_result = verify_protection_snapshot(
        root,
        protection,
        trusted_magia_commit=trusted_magia_commit,
        expected_namae_tw_group_count=expected_namae_tw_group_count,
        expected_namae_tw_json_count=expected_namae_tw_json_count,
    )
    allow_entries = validate_allowlist(root, allowlist, inventory)
    prepared = validate_package(root, package, allow_entries, protection_result["protected_paths"])
    return {
        "protection": protection_result,
        "allow_entries": allow_entries,
        "prepared_entries": prepared,
        "summary": {
            "batch_id": package["batch_id"],
            "allowlist_count": len(allow_entries),
            "protected_file_count": protection_result["protected_file_count"],
            "magia_baseline_file_count": protection_result["magia_baseline_file_count"],
            "exedra_human_group_count": protection_result["exedra_human_group_count"],
            "exedra_human_file_count": protection_result["exedra_human_file_count"],
            "namae_tw_group_count": protection_result["namae_tw_group_count"],
            "namae_tw_file_count": protection_result["namae_tw_file_count"],
            "namae_tw_json_count": protection_result["namae_tw_json_count"],
            "all_hard_gates_passed": True,
        },
    }


def stage_batch(
    *,
    root: Path,
    inventory_path: Path,
    allowlist_path: Path,
    package_path: Path,
    protection_path: Path,
    output_dir: Path,
    claude_binary: str = "claude",
    timeout_seconds: int = 1800,
    worker: Callable[..., Mapping[str, Any]] = invoke_claude,
    preflight_only: bool = False,
    trusted_magia_commit: str = TRUSTED_MAGIA_BASELINE_COMMIT,
    expected_namae_tw_group_count: int = EXPECTED_NAMAE_TW_GROUP_COUNT,
    expected_namae_tw_json_count: int = EXPECTED_NAMAE_TW_JSON_COUNT,
) -> dict[str, Any]:
    inventory = load_object(inventory_path, "inventory")
    allowlist = load_object(allowlist_path, "allowlist")
    package = load_object(package_path, "translation package")
    protection = load_object(protection_path, "protection snapshot")
    checked = preflight(
        root=root,
        inventory=inventory,
        allowlist=allowlist,
        package=package,
        protection=protection,
        trusted_magia_commit=trusted_magia_commit,
        expected_namae_tw_group_count=expected_namae_tw_group_count,
        expected_namae_tw_json_count=expected_namae_tw_json_count,
    )
    file_hashes = {
        "inventory": sha256_file(inventory_path),
        "allowlist": sha256_file(allowlist_path),
        "package": sha256_file(package_path),
        "protection": sha256_file(protection_path),
    }
    checkpoint: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "preflight_passed" if preflight_only else "worker_pending",
        "batch_id": package["batch_id"],
        "model": MODEL,
        "glossary_version": package["glossary_version"],
        "glossary_sha256": package["glossary_sha256"],
        "input_hashes": file_hashes,
        "input_range": [
            {
                "story_id": item["story_id"],
                "jp_txt": item["jp_txt"],
                "jp_sha256": item["jp_sha256"],
                "target_cn_txt": item["target_cn_txt"],
                "target_before_sha256": item["target_before_sha256"],
            }
            for item in checked["allow_entries"]
        ],
        "counts": checked["summary"],
        "candidate_files": [],
        "unresolved": [],
        "validation": {
            "allowlist_exact": True,
            "protected_hashes_unchanged": True,
            "namae_tw_protection_closed": True,
            "model_tools_disabled": True,
            "formal_tree_written": False,
        },
    }
    output_dir = output_dir.resolve()
    if preflight_only:
        atomic_write(output_dir / "checkpoint.json", canonical_json_bytes(checkpoint))
        return checkpoint

    prompt = build_prompt(package)
    checkpoint["prompt_sha256"] = sha256_bytes(prompt.encode("utf-8"))
    outer = worker(
        prompt,
        claude_binary=claude_binary,
        timeout_seconds=timeout_seconds,
        cwd=root,
    )
    result, metadata = extract_worker_result(outer)
    candidates, unresolved = validate_worker_result(
        result, package, checked["prepared_entries"]
    )
    staged: list[dict[str, Any]] = []
    candidate_payloads: list[tuple[Path, bytes]] = []
    for candidate in candidates:
        rendered = render_candidate(candidate)
        target = repo_path(root, candidate["target_cn_txt"], "candidate target")
        report = materialize(target, repo_root=root, write=False, reviewed_text=rendered)
        payload = rendered.encode("utf-8")
        destination = output_dir / "candidates" / f"{candidate['story_id']}_cn.txt"
        candidate_payloads.append((destination, payload))
        staged.append(
            {
                "story_id": candidate["story_id"],
                "path": destination.relative_to(output_dir).as_posix(),
                "sha256": sha256_bytes(payload),
                "bytes": len(payload),
                "materialize_validation": report["validation"],
                "materialized_paths": report["materializedPaths"],
            }
        )

    # Prove no protected/baseline input moved while the external worker ran.
    verify_protection_snapshot(
        root,
        protection,
        trusted_magia_commit=trusted_magia_commit,
        expected_namae_tw_group_count=expected_namae_tw_group_count,
        expected_namae_tw_json_count=expected_namae_tw_json_count,
    )
    for allow in checked["allow_entries"]:
        verify_digest(
            repo_path(root, allow["target_cn_txt"], "target baseline"),
            allow["target_before_sha256"],
            f"target baseline {allow['story_id']}",
        )
    # Nothing is exposed in the staging directory until every candidate has
    # passed playable JSON/TXT regeneration and both immutable hash gates.
    for destination, payload in candidate_payloads:
        atomic_write(destination, payload)
    checkpoint.update(
        {
            "status": "blocked_unresolved" if unresolved else "staged_validated",
            "worker": metadata,
            "result_sha256": sha256_bytes(canonical_json_bytes(result)),
            "candidate_files": staged,
            "unresolved": unresolved,
        }
    )
    checkpoint["validation"].update(
        {
            "worker_output_schema_exact": True,
            "segment_count_and_order_match": True,
            "speaker_structure_preserved": True,
            "placeholders_and_newlines_match": True,
            "honorific_violations": 0,
            "playable_json_txt_dry_run": not unresolved,
        }
    )
    atomic_write(output_dir / "worker-result.json", canonical_json_bytes(result))
    atomic_write(output_dir / "checkpoint.json", canonical_json_bytes(checkpoint))
    return checkpoint


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot-protection")
    snapshot.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    snapshot.add_argument("--output", type=Path, required=True)

    for command in ("preflight", "stage"):
        child = subparsers.add_parser(command)
        child.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
        child.add_argument("--allowlist", type=Path, required=True)
        child.add_argument("--package", type=Path, required=True)
        child.add_argument("--protection", type=Path, required=True)
        child.add_argument("--output-dir", type=Path, required=True)
        child.add_argument("--claude-binary", default="claude")
        child.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    try:
        if args.command == "snapshot-protection":
            result = snapshot_protection(root, load_object(args.inventory, "inventory"))
            atomic_write(args.output.resolve(), canonical_json_bytes(result))
            print(
                "DEEPSEEK_PROTECTION_SNAPSHOT_OK "
                f"protected={len(result['protected_files'])} "
                f"namae_tw_groups={result['namae_tw_authority']['expected_group_count']}"
            )
            return 0
        checkpoint = stage_batch(
            root=root,
            inventory_path=args.inventory.resolve(),
            allowlist_path=args.allowlist.resolve(),
            package_path=args.package.resolve(),
            protection_path=args.protection.resolve(),
            output_dir=args.output_dir,
            claude_binary=args.claude_binary,
            timeout_seconds=args.timeout_seconds,
            preflight_only=args.command == "preflight",
        )
        print(
            "DEEPSEEK_BATCH_GATE_OK "
            f"status={checkpoint['status']} batch={checkpoint['batch_id']} "
            f"allowlist={checkpoint['counts']['allowlist_count']}"
        )
        return 0
    except GateError as exc:
        print(f"DEEPSEEK_BATCH_GATE_FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
