#!/usr/bin/env python3
"""Safely organize Magia Exedra scenario JSON into website-ready story groups.

The source JSON files are never modified. A normal run builds a complete sibling
staging directory, validates it against a deterministic ownership manifest, and
only then renames it into place. An existing output is renamed to a timestamped
backup; it is never deleted by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = Path(
    r"D:\magia\Madoka Magica Magia Exedra JP_GL\Resources\Scenarios"
)
DEFAULT_OUTPUT = (
    REPO_ROOT / "magiraexedra-source-master" / "Scenarios_full"
)

CATEGORY_ORDER = (
    "1_Main",
    "2_Sub",
    "3_Character",
    "4_Portrait",
    "6_Reaction",
    "7_Namae",
    "8_Dungeon",
    "10_Battle",
)
MANIFEST_NAME = "exedra_manifest.json"
TEXT_ACTIONS = frozenset({"Talk", "Narration", "CharacterTalk", "OnlyText"})
EXCLUDED_TEXT_ACTIONS = frozenset({"PlayVoice"})
MANIFEST_SCHEMA_VERSION = 1


class OrganizerError(RuntimeError):
    """Raised when a source plan or generated output is not safe to publish."""


def _is_link_like(path: Path) -> bool:
    """Return True for symbolic links and Windows directory junctions."""

    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction and is_junction())
    except OSError as error:
        raise OrganizerError(
            f"Cannot inspect path reparse state: {path}: {error}"
        ) from error


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _assert_no_link_ancestors(path: Path, *, label: str) -> None:
    current = _absolute_lexical(path)
    while True:
        if _is_link_like(current):
            raise OrganizerError(
                f"{label} contains a symbolic-link or junction ancestor: {current}"
            )
        if current.parent == current:
            break
        current = current.parent


def _plain_tree_entries(
    root: Path,
) -> list[tuple[Path, Path, bool]]:
    """Enumerate a tree without following symbolic links or junctions."""

    root = _absolute_lexical(root)
    _assert_no_link_ancestors(root, label="Tree root")
    if not root.is_dir():
        raise OrganizerError(f"Tree root does not exist: {root}")
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as error:
        raise OrganizerError(f"Cannot resolve tree root {root}: {error}") from error

    result: list[tuple[Path, Path, bool]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as scan:
                entries = sorted(scan, key=lambda item: item.name.casefold())
        except OSError as error:
            raise OrganizerError(f"Cannot enumerate {current}: {error}") from error

        child_directories: list[Path] = []
        for entry in entries:
            path = Path(entry.path)
            if _is_link_like(path):
                raise OrganizerError(
                    f"Tree contains a symbolic link or junction: {path}"
                )
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
                resolved = path.resolve(strict=True)
                resolved.relative_to(resolved_root)
            except ValueError as error:
                raise OrganizerError(f"Tree entry escapes root: {path}") from error
            except OSError as error:
                raise OrganizerError(
                    f"Cannot inspect tree entry {path}: {error}"
                ) from error
            if not is_directory and not is_file:
                raise OrganizerError(f"Tree contains a special entry: {path}")
            relative = path.relative_to(root)
            result.append((path, relative, is_directory))
            if is_directory:
                child_directories.append(path)
        stack.extend(reversed(child_directories))
    return result


@dataclass(frozen=True)
class Dialogue:
    speaker: str
    text: str
    action_type: str
    sheet: int
    row: int


@dataclass
class SourceRecord:
    path: Path
    source_path: str
    category: str
    source_dir: str
    source_name: str
    group_key: str
    group_id: str
    sort_key: tuple[Any, ...]
    sha256: str
    book_title: str
    dialogues: list[Dialogue]
    section: int = 0
    output_json: str = ""
    excluded_playvoice: int = 0
    deduplicated_sheets: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class GroupPlan:
    category: str
    group_key: str
    group_id: str
    sources: list[SourceRecord]
    output_dir: str
    text_file: str
    text: str = ""
    text_sha256: str = ""

    @property
    def dialogue_count(self) -> int:
        return sum(len(source.dialogues) for source in self.sources)


@dataclass
class OrganizationPlan:
    source_root: Path
    sources: list[SourceRecord]
    groups: list[GroupPlan]
    warnings: list[str]


def natural_sort_key(value: str) -> tuple[tuple[int, Any], ...]:
    """Return a dependency-free, deterministic natural-sort key."""

    parts: list[tuple[int, Any]] = []
    for part in re.split(r"(\d+)", value):
        if not part:
            continue
        if part.isdigit():
            parts.append((1, int(part)))
        else:
            parts.append((0, part.casefold()))
    return tuple(parts)


def posix_path(*parts: str) -> str:
    return "/".join(part.strip("/\\") for part in parts if part)


def stable_group_id(category: str, group_key: str) -> str:
    return f"exedra:{category}:{group_key.casefold()}"


def _safe_group_component(value: str, source_dir: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\0" in value
    ):
        raise OrganizerError(
            f"Unsafe group name derived from {source_dir!r}: {value!r}"
        )
    return value


def normalize_namae_key(source_dir: str) -> str:
    """7_Namae groups by the same alphabetic name after removing digits."""

    without_digits = re.sub(r"\d+", "", source_dir)
    collapsed = re.sub(r"_+", "_", without_digits).strip("_")
    if not collapsed:
        raise OrganizerError(
            f"7_Namae source directory has no non-numeric group name: {source_dir}"
        )
    return _safe_group_component(collapsed, source_dir)


def group_key_for(category: str, source_dir: str) -> str:
    """Map one original script directory to exactly one logical story group."""

    if category == "6_Reaction":
        match = re.match(r"^cv_(\d+)(?:_|$)", source_dir, flags=re.IGNORECASE)
        if not match:
            raise OrganizerError(
                f"Unrecognized 6_Reaction directory name: {source_dir}"
            )
        return _safe_group_component(f"cv_{match.group(1)}", source_dir)

    if category == "7_Namae":
        return normalize_namae_key(source_dir)

    # Strip exactly one part number. This deliberately keeps the preceding
    # chapter number: main_embryoeve1_2 -> main_embryoeve1.
    stripped = re.sub(r"_\d+$", "", source_dir)
    if stripped != source_dir:
        return _safe_group_component(stripped, source_dir)

    # A few source families encode the part without an underscore, such as
    # main_baraen1_prologue1 and main_scene0_film02_movie1.
    stripped = re.sub(r"\d+$", "", source_dir).rstrip("_")
    return _safe_group_component(stripped or source_dir, source_dir)


def reaction_sort_key(source_dir: str, source_name: str) -> tuple[Any, ...]:
    """Match process_scripts.py ordering: number, evo_fee, then story."""

    filename_key = (
        0
        if Path(source_name).stem.casefold() == source_dir.casefold()
        else 1,
        natural_sort_key(source_name),
    )
    detailed = re.match(
        r"^cv_(\d+)_other_(evo_fee|story)_(\d+)$",
        source_dir,
        flags=re.IGNORECASE,
    )
    if detailed:
        kind_order = 0 if detailed.group(2).casefold() == "evo_fee" else 1
        return (
            0,
            int(detailed.group(3)),
            kind_order,
            filename_key,
        )

    compact = re.match(
        r"^cv_(\d+)_(\d+)$", source_dir, flags=re.IGNORECASE
    )
    if compact:
        return (1, int(compact.group(2)), filename_key)

    return (2, natural_sort_key(source_dir), filename_key)


def source_sort_key(
    category: str, source_dir: str, source_name: str
) -> tuple[Any, ...]:
    if category == "6_Reaction":
        return reaction_sort_key(source_dir, source_name)
    filename_key = (
        0
        if Path(source_name).stem.casefold() == source_dir.casefold()
        else 1,
        natural_sort_key(source_name),
    )
    return (natural_sort_key(source_dir), filename_key)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def escape_comment_linebreaks(text: str) -> str:
    """Match the reader's boundary trim and preserve internal line breaks."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return normalized.replace("\n", "\\n")


def is_plausible_asset_speaker(value: str) -> bool:
    value = value.strip()
    return (
        bool(value)
        and len(value) <= 40
        and not re.search(r"\d", value)
        and not re.search(r"[_\\/]", value)
        and not re.match(
            r"^(?:adv|bg|cv|spine|asset|chara|character|npc|mob|effect|"
            r"eff|voice|se|bgm)[-_.]",
            value,
            flags=re.IGNORECASE,
        )
        and not re.search(
            r"\.(?:png|jpg|json|asset)$",
            value,
            flags=re.IGNORECASE,
        )
    )


def _cell(cells: Sequence[Any], index: int | None) -> Any:
    if index is None or index < 0 or index >= len(cells):
        return None
    return cells[index]


def extract_dialogues(
    document: dict[str, Any],
    *,
    is_reaction: bool,
) -> tuple[list[Dialogue], int, int, list[str]]:
    """Extract reader-compatible lines using each sheet's named columns."""

    dialogues: list[Dialogue] = []
    excluded_playvoice = 0
    deduplicated_sheets = 0
    warnings: list[str] = []
    sheet_list = document.get("sheetList")
    if not isinstance(sheet_list, list):
        return [], 0, 0, ["missing-or-invalid-sheetList"]
    book_title = str(document.get("bookTitle") or "").strip()
    default_speaker = ""
    if is_reaction and "_" in book_title:
        candidate = book_title.split("_", 1)[0].strip()
        if 0 < len(candidate) <= 40:
            default_speaker = candidate

    seen_sheet_fingerprints: dict[str, int] = {}
    for sheet_index, sheet in enumerate(sheet_list, start=1):
        if not isinstance(sheet, dict):
            warnings.append(f"sheet-{sheet_index}:invalid-sheet")
            continue
        fingerprint = json.dumps(
            sheet,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        duplicate_of = seen_sheet_fingerprints.get(fingerprint)
        if duplicate_of is not None:
            deduplicated_sheets += 1
            warnings.append(
                f"sheet-{sheet_index}:duplicate-of-sheet-{duplicate_of}"
            )
            continue
        seen_sheet_fingerprints[fingerprint] = sheet_index

        header_row = sheet.get("headerRow")
        header_cells = (
            header_row.get("cellList")
            if isinstance(header_row, dict)
            else None
        )
        if not isinstance(header_cells, list):
            warnings.append(f"sheet-{sheet_index}:missing-header")
            continue

        headers = [str(value or "").strip() for value in header_cells]
        indices = {
            header: headers.index(header)
            for header in (
                "ActionType",
                "Name",
                "Comment",
                "AssetID",
                "PositionID",
            )
            if header in headers
        }
        if "ActionType" not in indices or "Comment" not in indices:
            warnings.append(
                f"sheet-{sheet_index}:missing-ActionType-or-Comment"
            )
            continue

        content_rows = sheet.get("contentRowList")
        if not isinstance(content_rows, list):
            warnings.append(f"sheet-{sheet_index}:missing-contentRowList")
            continue

        position_speakers: dict[str, str] = {}
        asset_speakers: dict[str, str] = {}
        for row_index, row in enumerate(content_rows, start=1):
            if not isinstance(row, dict):
                continue
            cells = row.get("cellList")
            if not isinstance(cells, list):
                continue

            action_value = _cell(cells, indices.get("ActionType"))
            action_type = str(action_value or "").strip()
            comment_value = _cell(cells, indices.get("Comment"))
            name_value = _cell(cells, indices.get("Name"))
            name = str(name_value or "").strip()
            asset_value = _cell(cells, indices.get("AssetID"))
            asset = str(asset_value or "").strip()
            position_value = _cell(cells, indices.get("PositionID"))
            position = str(position_value or "").strip()

            if action_type == "Put" and name and asset:
                asset_speakers[asset] = name

            if action_type == "Put" and position:
                put_speaker = (
                    name
                    or (asset if is_plausible_asset_speaker(asset) else "")
                )
                if put_speaker:
                    position_speakers[position] = put_speaker
                else:
                    position_speakers.pop(position, None)

            if action_type in EXCLUDED_TEXT_ACTIONS:
                if isinstance(comment_value, str) and comment_value.strip():
                    excluded_playvoice += 1
                continue
            if action_type not in TEXT_ACTIONS:
                continue
            if not isinstance(comment_value, str) or not comment_value.strip():
                continue

            speaker = name
            if not speaker:
                if action_type == "Narration":
                    speaker = "Narration"
                else:
                    speaker = (
                        asset_speakers.get(asset, "")
                        or
                        position_speakers.get(position, "")
                        or (
                            asset
                            if is_plausible_asset_speaker(asset)
                            else ""
                        )
                        or default_speaker
                    )
                    if not speaker:
                        if is_reaction or action_type == "CharacterTalk":
                            speaker = ""
                        else:
                            speaker = "Narration"

            dialogues.append(
                Dialogue(
                    speaker=speaker,
                    text=escape_comment_linebreaks(comment_value),
                    action_type=action_type,
                    sheet=sheet_index,
                    row=row_index,
                )
            )

    return dialogues, excluded_playvoice, deduplicated_sheets, warnings


def _load_source(
    source_root: Path,
    category: str,
    path: Path,
) -> SourceRecord:
    raw = path.read_bytes()
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        relative = path.relative_to(source_root).as_posix()
        raise OrganizerError(f"Unreadable JSON {relative}: {error}") from error
    if not isinstance(document, dict):
        relative = path.relative_to(source_root).as_posix()
        raise OrganizerError(f"JSON root must be an object: {relative}")

    relative = path.relative_to(source_root)
    if len(relative.parts) < 3:
        raise OrganizerError(
            f"JSON must be inside a source directory: {relative.as_posix()}"
        )
    source_dir = relative.parts[1]
    group_key = group_key_for(category, source_dir)
    (
        dialogues,
        excluded_playvoice,
        deduplicated_sheets,
        warnings,
    ) = extract_dialogues(document, is_reaction=category == "6_Reaction")

    return SourceRecord(
        path=path,
        source_path=relative.as_posix(),
        category=category,
        source_dir=source_dir,
        source_name=path.name,
        group_key=group_key,
        group_id=stable_group_id(category, group_key),
        sort_key=source_sort_key(category, source_dir, path.name),
        sha256=sha256_bytes(raw),
        book_title=str(document.get("bookTitle") or ""),
        dialogues=dialogues,
        excluded_playvoice=excluded_playvoice,
        deduplicated_sheets=deduplicated_sheets,
        warnings=warnings,
    )


def render_group_text(group: GroupPlan) -> str:
    sections: list[str] = []
    for index, source in enumerate(group.sources, start=1):
        source.section = index
        lines = [
            f"--- [Section {index}] (Source: {source.source_name}) ---"
        ]
        lines.extend(
            f"{dialogue.speaker}: {dialogue.text}"
            if dialogue.speaker
            else dialogue.text
            for dialogue in source.dialogues
        )
        sections.append("\n".join(lines))
    return "\n\n".join(sections).rstrip() + "\n"


def build_plan(source_root: Path) -> OrganizationPlan:
    """Read all eight original categories and build a deterministic plan."""

    source_root = _absolute_lexical(source_root)
    _assert_no_link_ancestors(source_root, label="Source root")
    if not source_root.is_dir():
        raise OrganizerError(f"Source root does not exist: {source_root}")

    records: list[SourceRecord] = []
    warnings: list[str] = []
    for category in CATEGORY_ORDER:
        category_dir = source_root / category
        _assert_no_link_ancestors(category_dir, label="Category")
        if not category_dir.is_dir():
            raise OrganizerError(f"Missing required category: {category_dir}")

        paths = sorted(
            (
                path
                for path, _, is_directory in _plain_tree_entries(category_dir)
                if not is_directory and path.suffix.casefold() == ".json"
            ),
            key=lambda path: natural_sort_key(
                path.relative_to(category_dir).as_posix()
            ),
        )
        for path in paths:
            record = _load_source(source_root, category, path)
            records.append(record)
            warnings.extend(
                f"{record.source_path}:{warning}"
                for warning in record.warnings
            )

    grouped: dict[tuple[str, str], list[SourceRecord]] = defaultdict(list)
    canonical_keys: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in records:
        identity = (record.category, record.group_key.casefold())
        grouped[identity].append(record)
        canonical_keys[identity].add(record.group_key)

    category_rank = {name: index for index, name in enumerate(CATEGORY_ORDER)}
    groups: list[GroupPlan] = []
    for identity, group_sources in grouped.items():
        category, _ = identity
        group_key = min(
            canonical_keys[identity], key=lambda value: natural_sort_key(value)
        )
        group_id = stable_group_id(category, group_key)
        group_sources.sort(key=lambda record: record.sort_key)
        output_dir = posix_path(category, group_key)
        text_file = posix_path(
            output_dir, f"{group_key}_jp.txt"
        )

        for record in group_sources:
            record.group_key = group_key
            record.group_id = group_id
            record.output_json = posix_path(output_dir, record.source_name)

        group = GroupPlan(
            category=category,
            group_key=group_key,
            group_id=group_id,
            sources=group_sources,
            output_dir=output_dir,
            text_file=text_file,
        )
        group.text = render_group_text(group)
        group.text_sha256 = sha256_bytes(group.text.encode("utf-8"))
        groups.append(group)

    groups.sort(
        key=lambda group: (
            category_rank[group.category],
            natural_sort_key(group.group_key),
        )
    )
    records.sort(
        key=lambda record: (
            category_rank[record.category],
            natural_sort_key(record.group_key),
            record.section,
            natural_sort_key(record.source_name),
        )
    )

    plan = OrganizationPlan(
        source_root=source_root,
        sources=records,
        groups=groups,
        warnings=sorted(warnings, key=natural_sort_key),
    )
    validate_plan(plan)
    return plan


def validate_plan(plan: OrganizationPlan) -> None:
    """Prove one-to-one source ownership and collision-free output paths."""

    scanned_paths = [record.source_path.casefold() for record in plan.sources]
    if len(scanned_paths) != len(set(scanned_paths)):
        raise OrganizerError("Duplicate source ownership paths in plan")

    owned_sources = [
        record.source_path.casefold()
        for group in plan.groups
        for record in group.sources
    ]
    if len(owned_sources) != len(set(owned_sources)):
        raise OrganizerError("One or more JSON sources belong to multiple groups")
    if set(owned_sources) != set(scanned_paths):
        missing = sorted(set(scanned_paths) - set(owned_sources))
        extra = sorted(set(owned_sources) - set(scanned_paths))
        raise OrganizerError(
            f"Ownership mismatch; missing={missing[:5]}, extra={extra[:5]}"
        )

    group_ids = [group.group_id for group in plan.groups]
    if len(group_ids) != len(set(group_ids)):
        raise OrganizerError("Duplicate group IDs in plan")

    output_paths: list[str] = []
    for group in plan.groups:
        output_paths.append(group.text_file.casefold())
        if not group.sources:
            raise OrganizerError(f"Empty group: {group.group_id}")
        for source in group.sources:
            if source.group_id != group.group_id:
                raise OrganizerError(
                    f"Incorrect owner for {source.source_path}"
                )
            output_paths.append(source.output_json.casefold())
    if len(output_paths) != len(set(output_paths)):
        raise OrganizerError("Case-insensitive output path collision in plan")


def _category_summary(plan: OrganizationPlan) -> list[dict[str, Any]]:
    return [
        {
            "category": category,
            "groupCount": sum(
                group.category == category for group in plan.groups
            ),
            "sourceCount": sum(
                source.category == category for source in plan.sources
            ),
            "dialogueCount": sum(
                group.dialogue_count
                for group in plan.groups
                if group.category == category
            ),
        }
        for category in CATEGORY_ORDER
    ]


def manifest_for(plan: OrganizationPlan) -> dict[str, Any]:
    """Return a timestamp-free manifest so identical input is reproducible."""

    excluded_playvoice = sum(
        source.excluded_playvoice for source in plan.sources
    )
    deduplicated_sheets = sum(
        source.deduplicated_sheets for source in plan.sources
    )
    return {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "categoryOrder": list(CATEGORY_ORDER),
        "summary": {
            "categoryCount": len(CATEGORY_ORDER),
            "groupCount": len(plan.groups),
            "sourceCount": len(plan.sources),
            "dialogueCount": sum(
                group.dialogue_count for group in plan.groups
            ),
            "excludedPlayVoiceCount": excluded_playvoice,
            "deduplicatedSheetCount": deduplicated_sheets,
            "warningCount": len(plan.warnings),
            "duplicateOwnershipCount": 0,
            "omittedSourceCount": 0,
        },
        "categories": _category_summary(plan),
        "groups": [
            {
                "id": group.group_id,
                "category": group.category,
                "groupKey": group.group_key,
                "outputDir": group.output_dir,
                "textFile": group.text_file,
                "textSha256": group.text_sha256,
                "sourceCount": len(group.sources),
                "dialogueCount": group.dialogue_count,
                "sources": [
                    source.source_path for source in group.sources
                ],
            }
            for group in plan.groups
        ],
        "sources": [
            {
                "sourcePath": source.source_path,
                "category": source.category,
                "groupId": source.group_id,
                "groupKey": source.group_key,
                "outputJson": source.output_json,
                "sha256": source.sha256,
                "section": source.section,
                "dialogueCount": len(source.dialogues),
                "excludedPlayVoiceCount": source.excluded_playvoice,
                "deduplicatedSheetCount": source.deduplicated_sheets,
                "bookTitle": source.book_title,
            }
            for source in plan.sources
        ],
        "warnings": plan.warnings,
    }


def _manifest_bytes(plan: OrganizationPlan) -> bytes:
    text = json.dumps(
        manifest_for(plan),
        ensure_ascii=False,
        indent=2,
    )
    return (text + "\n").encode("utf-8")


def write_stage(plan: OrganizationPlan, stage_root: Path) -> None:
    if stage_root.exists():
        raise OrganizerError(f"Refusing to reuse staging path: {stage_root}")
    stage_root.mkdir(parents=True)
    for category in CATEGORY_ORDER:
        (stage_root / category).mkdir()

    for group in plan.groups:
        group_dir = stage_root.joinpath(*group.output_dir.split("/"))
        group_dir.mkdir(parents=True)
        for source in group.sources:
            output_json = stage_root.joinpath(
                *source.output_json.split("/")
            )
            shutil.copy2(source.path, output_json)
        text_path = stage_root.joinpath(*group.text_file.split("/"))
        text_path.write_text(group.text, encoding="utf-8", newline="\n")

    (stage_root / MANIFEST_NAME).write_bytes(_manifest_bytes(plan))


def validate_output(plan: OrganizationPlan, output_root: Path) -> dict[str, int]:
    """Validate bytes, manifest, ownership, omissions, and unexpected outputs."""

    output_root = _absolute_lexical(output_root)
    _assert_no_link_ancestors(output_root, label="Output root")
    if not output_root.is_dir():
        raise OrganizerError(f"Output root does not exist: {output_root}")

    manifest_path = output_root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise OrganizerError(f"Missing manifest: {manifest_path}")
    try:
        actual_manifest = json.loads(manifest_path.read_text("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OrganizerError(f"Unreadable manifest: {error}") from error
    expected_manifest = manifest_for(plan)
    if actual_manifest != expected_manifest:
        raise OrganizerError("Manifest does not match the current source plan")

    expected_json = {
        source.output_json.casefold(): source for source in plan.sources
    }
    for category in CATEGORY_ORDER:
        category_root = output_root / category
        if not category_root.is_dir():
            raise OrganizerError(f"Missing output category: {category}")

    expected_text = {
        group.text_file.casefold(): group for group in plan.groups
    }
    expected_files: dict[str, str] = {
        MANIFEST_NAME.casefold(): MANIFEST_NAME
    }
    for relative in (
        *(source.output_json for source in plan.sources),
        *(group.text_file for group in plan.groups),
    ):
        key = relative.casefold()
        if key in expected_files:
            raise OrganizerError(
                f"Planned case-insensitive output collision: {relative}"
            )
        expected_files[key] = relative

    actual_files: dict[str, Path] = {}
    for path, relative_path, is_directory in _plain_tree_entries(output_root):
        if is_directory:
            continue
        relative = relative_path.as_posix()
        key = relative.casefold()
        if key in actual_files:
            raise OrganizerError(
                f"Duplicate case-insensitive output file: {relative}"
            )
        actual_files[key] = path

    if set(actual_files) != set(expected_files):
        missing = sorted(set(expected_files) - set(actual_files))
        extra = sorted(set(actual_files) - set(expected_files))
        raise OrganizerError(
            f"Output file mismatch; missing={missing[:5]}, extra={extra[:5]}"
        )
    for key, expected_relative in expected_files.items():
        actual_relative = actual_files[key].relative_to(output_root).as_posix()
        if actual_relative != expected_relative:
            raise OrganizerError(
                "Output path casing differs from the plan: "
                f"expected={expected_relative}, actual={actual_relative}"
            )

    actual_json = {
        key: actual_files[key] for key in expected_json
    }
    for key, source in expected_json.items():
        if sha256_file(actual_json[key]) != source.sha256:
            raise OrganizerError(
                f"Copied JSON differs from source: {source.output_json}"
            )

    actual_text = {
        key: actual_files[key] for key in expected_text
    }
    for key, group in expected_text.items():
        actual_bytes = actual_text[key].read_bytes()
        if sha256_bytes(actual_bytes) != group.text_sha256:
            raise OrganizerError(
                f"JP TXT differs from plan: {group.text_file}"
            )

    return {
        "sources": len(plan.sources),
        "groups": len(plan.groups),
        "duplicateOwnership": 0,
        "omittedSources": 0,
    }


def _unique_sibling(path: Path, label: str) -> Path:
    token = uuid.uuid4().hex[:12]
    return path.parent / f".{path.name}.{label}-{token}"


def publish_plan(
    plan: OrganizationPlan,
    output_root: Path,
) -> tuple[Path, Path | None]:
    """Build, validate, then atomically swap while preserving old output."""

    output_root = _absolute_lexical(output_root)
    _assert_no_link_ancestors(output_root, label="Output root")
    source_root = plan.source_root.resolve()
    resolved_output = output_root.resolve(strict=False)
    if (
        resolved_output == source_root
        or resolved_output in source_root.parents
        or source_root in resolved_output.parents
    ):
        raise OrganizerError(
            "Output and source roots must not overlap: "
            f"source={source_root}, output={resolved_output}"
        )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    stage_root = _unique_sibling(output_root, "staging")
    write_stage(plan, stage_root)
    validate_output(plan, stage_root)

    backup_root: Path | None = None
    if output_root.exists():
        # Reject nested reparse points before preserving or replacing the tree.
        _plain_tree_entries(output_root)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_root = output_root.parent / (
            f"{output_root.name}.backup-{stamp}-{uuid.uuid4().hex[:8]}"
        )
        output_root.rename(backup_root)

    try:
        stage_root.rename(output_root)
        validate_output(plan, output_root)
    except BaseException:
        if output_root.exists():
            failed_root = _unique_sibling(output_root, "failed")
            output_root.rename(failed_root)
        if backup_root is not None and not output_root.exists():
            backup_root.rename(output_root)
        raise

    return output_root, backup_root


def report_for(plan: OrganizationPlan) -> dict[str, Any]:
    largest = sorted(
        plan.groups,
        key=lambda group: (
            -len(group.sources),
            -group.dialogue_count,
            group.group_id,
        ),
    )[:10]
    return {
        "sourceCount": len(plan.sources),
        "groupCount": len(plan.groups),
        "dialogueCount": sum(
            group.dialogue_count for group in plan.groups
        ),
        "warningCount": len(plan.warnings),
        "excludedPlayVoiceCount": sum(
            source.excluded_playvoice for source in plan.sources
        ),
        "deduplicatedSheetCount": sum(
            source.deduplicated_sheets for source in plan.sources
        ),
        "duplicateOwnershipCount": 0,
        "omittedSourceCount": 0,
        "categories": _category_summary(plan),
        "largestGroups": [
            {
                "id": group.group_id,
                "sources": len(group.sources),
                "dialogues": group.dialogue_count,
            }
            for group in largest
        ],
    }


def _print_report(plan: OrganizationPlan) -> None:
    report = report_for(plan)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Original Scenarios root (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Organized Scenarios_full target (default: {DEFAULT_OUTPUT})",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate the complete plan without writing files",
    )
    mode.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the existing --output against current source files",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        plan = build_plan(args.source)
        if args.dry_run:
            _print_report(plan)
            return 0
        if args.validate_only:
            result = validate_output(plan, args.output)
            _print_report(plan)
            print(
                "Validation succeeded: "
                f"{result['sources']} sources, {result['groups']} groups, "
                "0 duplicates, 0 omissions."
            )
            return 0

        output, backup = publish_plan(plan, args.output)
        _print_report(plan)
        print(f"Published validated output: {output}")
        if backup is not None:
            print(f"Previous output preserved as: {backup}")
        return 0
    except (OSError, OrganizerError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
