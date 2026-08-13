#!/usr/bin/env python3
"""Build a sealed, lowest-authority Exedra translation input.

The builder is deterministic and read-only with respect to both scenario trees.
It consumes the completed Exedra localization audit, then admits only the 26
groups that have readable Japanese dialogue and no protected Chinese group.
It never calls a model and never creates Chinese scenario JSON/TXT files.

Generated files intentionally use names distinct from the earlier hand-written
``allowlist.v1.json`` so a rerun cannot overwrite another agent's checkpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
JP_ROOT_REL = PurePosixPath("magiraexedra-source-master/Scenarios_full")
CN_ROOT_REL = PurePosixPath("magiraexedra-translate-data-master/Scenarios_full")
DEFAULT_AUDIT = ROOT / "artifacts/exedra_localization_audit.generated.json"
DEFAULT_MANIFEST = ROOT / JP_ROOT_REL / "exedra_manifest.json"
DEFAULT_GLOSSARY = (
    ROOT / "artifacts/deepseek-retranslation/authoritative-glossary.v1.json"
)
DEFAULT_OUTPUT_DIR = (
    ROOT / "artifacts/deepseek-retranslation/exedra-missing-allowlist-v1"
)
ALLOWLIST_NAME = "allowlist.generated.v1.json"
SEALED_INPUT_NAME = "sealed-input.v1.json"
VERIFICATION_NAME = "verification.v1.json"
REPORT_NAME = "report.v1.md"
SCHEMA_VERSION = 1
PROTECTED_PROVENANCE = frozenset(
    {"official_tw_human", "exedra_wiki_voice_human", "rounddora_0728_human"}
)
TEXT_ACTIONS = frozenset({"talk", "narration", "charactertalk", "onlytext"})


class AllowlistError(RuntimeError):
    """A fail-closed source/protection gate failed."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AllowlistError(f"{label} is not valid UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AllowlistError(f"{label} must be a JSON object: {path}")
    return value


def safe_relative(value: str, label: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in value
    ):
        raise AllowlistError(f"unsafe {label}: {value!r}")
    return path


def root_path(root: Path, relative: PurePosixPath) -> Path:
    return root.joinpath(*relative.parts)


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


def _cell(cells: Sequence[Any], index: int) -> Any:
    return cells[index] if 0 <= index < len(cells) else ""


def extract_dialogue_rows(data: Mapping[str, Any], label: str) -> list[dict[str, Any]]:
    sheet_list = data.get("sheetList")
    if not isinstance(sheet_list, list):
        raise AllowlistError(f"Japanese source lacks sheetList: {label}")
    rows: list[dict[str, Any]] = []
    seen_sheets: set[str] = set()
    for sheet_index, sheet in enumerate(sheet_list):
        if not isinstance(sheet, dict):
            raise AllowlistError(f"Japanese sheet is not an object: {label}[{sheet_index}]")
        header = sheet.get("headerRow")
        content = sheet.get("contentRowList")
        header_cells = header.get("cellList") if isinstance(header, dict) else None
        if not isinstance(header_cells, list) or not isinstance(content, list):
            raise AllowlistError(f"Japanese sheet lacks header/content rows: {label}[{sheet_index}]")
        headers = [str(value or "").strip() for value in header_cells]
        try:
            action_index = headers.index("ActionType")
            comment_index = headers.index("Comment")
        except ValueError as exc:
            raise AllowlistError(f"Japanese sheet lacks ActionType/Comment: {label}") from exc
        name_index = headers.index("Name") if "Name" in headers else -1
        sheet_rows: list[dict[str, Any]] = []
        for fallback_row, row in enumerate(content, start=2):
            if not isinstance(row, dict) or not isinstance(row.get("cellList"), list):
                raise AllowlistError(f"Japanese content row is invalid: {label}:{fallback_row}")
            cells = row["cellList"]
            action = str(_cell(cells, action_index) or "").strip()
            text = _cell(cells, comment_index)
            if action.casefold() not in TEXT_ACTIONS or not isinstance(text, str):
                continue
            text = text.strip()
            if not text:
                continue
            speaker = str(_cell(cells, name_index) or "").strip() if name_index >= 0 else ""
            sheet_rows.append(
                {
                    "row_number": int(row.get("rowNumber") or fallback_row),
                    "action": action,
                    "speaker": speaker,
                    "source_text": text,
                }
            )
        fingerprint = sha256_bytes(canonical_json_bytes(sheet_rows))
        if fingerprint in seen_sheets:
            continue
        seen_sheets.add(fingerprint)
        rows.extend(sheet_rows)
    return rows


def _group_identity(record: Mapping[str, Any], label: str) -> str:
    identity = record.get("sourceIdentity")
    if not isinstance(identity, str) or not identity.startswith("exedra:"):
        raise AllowlistError(f"{label} lacks a valid sourceIdentity")
    return identity


def protected_snapshot(root: Path) -> dict[str, Any]:
    base = root_path(root, CN_ROOT_REL)
    groups: dict[str, dict[str, Any]] = {}
    file_records: list[tuple[str, str]] = []
    provenance_counts: Counter[str] = Counter()
    if not base.is_dir():
        raise AllowlistError(f"Exedra Chinese root is missing: {base}")
    for sidecar in sorted(base.rglob("*_cn.provenance.json")):
        record = load_object(sidecar, "Exedra provenance sidecar")
        provenance = str(record.get("provenance") or record.get("sourceType") or "")
        if provenance not in PROTECTED_PROVENANCE:
            continue
        identity = _group_identity(record, str(sidecar))
        if identity in groups:
            raise AllowlistError(f"duplicate protected sourceIdentity: {identity}")
        relative_dir = sidecar.parent.relative_to(root).as_posix()
        files: list[str] = []
        for path in sorted(item for item in sidecar.parent.iterdir() if item.is_file()):
            relative = path.relative_to(root).as_posix()
            files.append(relative)
            file_records.append((relative, sha256_file(path)))
        groups[identity] = {
            "provenance": provenance,
            "directory": relative_dir,
            "files": files,
        }
        provenance_counts[provenance] += 1
    digest = hashlib.sha256()
    for relative, file_sha256 in sorted(file_records):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256.encode("ascii"))
        digest.update(b"\0")
    return {
        "groups": groups,
        "group_count": len(groups),
        "file_count": len(file_records),
        "provenance_counts": dict(sorted(provenance_counts.items())),
        "tree_sha256": digest.hexdigest(),
    }


def _approved_terms(glossary: Mapping[str, Any], corpus: str) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for key in ("static_terms", "paired_character_names", "speaker_mappings"):
        values = glossary.get(key)
        if not isinstance(values, list):
            raise AllowlistError(f"glossary field must be a list: {key}")
        for raw in values:
            if not isinstance(raw, dict):
                raise AllowlistError(f"glossary {key} contains a non-object")
            jp = raw.get("jp")
            cn = raw.get("cn")
            if not isinstance(jp, str) or not jp or not isinstance(cn, str) or not cn:
                continue
            if jp not in corpus or raw.get("status", "approved") != "approved":
                continue
            if "Source" in jp or len(jp) > 80:
                continue
            term = {
                "term_id": "term-" + sha256_bytes(f"{jp}\0{cn}".encode("utf-8"))[:16],
                "source": jp,
                "approved_translation": cn,
                "kind": str(raw.get("kind") or key),
                "context": str(raw.get("context") or ""),
                "confidence": str(raw.get("confidence") or "approved"),
                "conflict": str(raw.get("conflict") or ""),
                "evidence": raw.get("evidence") if isinstance(raw.get("evidence"), list) else [],
            }
            selected[(jp, cn)] = term
    return sorted(selected.values(), key=lambda item: (item["source"], item["approved_translation"]))


def _target_group_dir(group: Mapping[str, Any]) -> PurePosixPath:
    output_dir = group.get("outputDir")
    if not isinstance(output_dir, str):
        raise AllowlistError("manifest group lacks outputDir")
    return CN_ROOT_REL / safe_relative(output_dir, "manifest outputDir")


def build_outputs(
    *,
    root: Path,
    audit_path: Path,
    manifest_path: Path,
    glossary_path: Path,
    expected_total_groups: int,
    expected_protected_groups: int,
    expected_allowlist_groups: int,
    expected_structural_groups: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = root.resolve()
    audit = load_object(audit_path, "Exedra localization audit")
    manifest = load_object(manifest_path, "Exedra source manifest")
    glossary = load_object(glossary_path, "authoritative glossary")
    if audit.get("status") != "complete":
        raise AllowlistError("Exedra localization audit is not complete")
    groups_raw = manifest.get("groups")
    if not isinstance(groups_raw, list):
        raise AllowlistError("Exedra manifest groups is not a list")
    groups: dict[str, dict[str, Any]] = {}
    for raw in groups_raw:
        if not isinstance(raw, dict):
            raise AllowlistError("Exedra manifest contains a non-object group")
        identity = str(raw.get("id") or "")
        if not identity or identity in groups:
            raise AllowlistError(f"invalid/duplicate manifest group identity: {identity!r}")
        groups[identity] = raw
    if len(groups) != expected_total_groups:
        raise AllowlistError(
            f"manifest group count drift: expected={expected_total_groups}, actual={len(groups)}"
        )

    remaining = audit.get("remainingTranslatableGroups")
    structural = audit.get("structuralNoTextGroups")
    official = audit.get("officialTwGroups")
    retained = audit.get("retainedHumanGroups")
    if not all(isinstance(value, list) for value in (remaining, structural, official, retained)):
        raise AllowlistError("audit classification arrays are missing")
    if len(remaining) != expected_allowlist_groups or len(structural) != expected_structural_groups:
        raise AllowlistError(
            "audit remaining/structural counts drift: "
            f"remaining={len(remaining)}, structural={len(structural)}"
        )
    audit_protected = {
        _group_identity(item, "audit protected group") for item in [*official, *retained]
    }
    if len(audit_protected) != expected_protected_groups:
        raise AllowlistError(
            f"audit protected count drift: expected={expected_protected_groups}, actual={len(audit_protected)}"
        )
    remaining_ids = {_group_identity(item, "audit remaining group") for item in remaining}
    structural_ids = {_group_identity(item, "audit structural group") for item in structural}
    if audit_protected & remaining_ids or audit_protected & structural_ids or remaining_ids & structural_ids:
        raise AllowlistError("audit classifications overlap")
    if audit_protected | remaining_ids | structural_ids != set(groups):
        raise AllowlistError("audit classifications do not close exactly over the manifest")

    protection = protected_snapshot(root)
    if protection["group_count"] != expected_protected_groups:
        raise AllowlistError(
            "protected sidecar count drift: "
            f"expected={expected_protected_groups}, actual={protection['group_count']}"
        )
    if set(protection["groups"]) != audit_protected:
        missing = sorted(audit_protected - set(protection["groups"]))
        extra = sorted(set(protection["groups"]) - audit_protected)
        raise AllowlistError(f"protected sidecars/audit differ: missing={missing}, extra={extra}")

    # Prove the four structural groups truly contain no readable text events.
    for identity in sorted(structural_ids):
        group = groups[identity]
        dialogue_count = 0
        for source in group.get("sources", []):
            source_name = PurePosixPath(str(source)).name
            source_path = root_path(root, JP_ROOT_REL / safe_relative(str(group["outputDir"]), "outputDir") / source_name)
            dialogue_count += len(extract_dialogue_rows(load_object(source_path, "Japanese source"), str(source_path)))
        if dialogue_count != 0 or int(group.get("dialogueCount") or 0) != 0:
            raise AllowlistError(f"audit structural group contains readable dialogue: {identity}")

    allow_entries: list[dict[str, Any]] = []
    sealed_entries: list[dict[str, Any]] = []
    source_file_count = 0
    segment_count = 0
    for audit_entry in sorted(remaining, key=lambda item: str(item["sourceIdentity"])):
        identity = _group_identity(audit_entry, "audit remaining group")
        if identity in protection["groups"]:
            raise AllowlistError(f"remaining group overlaps protected provenance: {identity}")
        group = groups.get(identity)
        if group is None:
            raise AllowlistError(f"remaining group absent from manifest: {identity}")
        target_dir_rel = _target_group_dir(group)
        target_dir = root_path(root, target_dir_rel)
        if target_dir.exists() and any(target_dir.iterdir()):
            raise AllowlistError(f"remaining group already has Chinese/protection files: {identity}: {target_dir}")

        text_rel = JP_ROOT_REL / safe_relative(str(group["textFile"]), "manifest textFile")
        text_path = root_path(root, text_rel)
        jp_txt_sha256 = sha256_file(text_path)
        if jp_txt_sha256 != group.get("textSha256"):
            raise AllowlistError(f"Japanese TXT hash drift: {identity}")
        sections: list[dict[str, Any]] = []
        group_segments = 0
        book_titles: list[str] = []
        seen_source_names: set[str] = set()
        for section_index, source in enumerate(group.get("sources", []), start=1):
            source_name = PurePosixPath(str(source)).name
            if source_name in seen_source_names:
                raise AllowlistError(f"duplicate source basename within group: {identity}: {source_name}")
            seen_source_names.add(source_name)
            source_rel = JP_ROOT_REL / safe_relative(str(group["outputDir"]), "outputDir") / source_name
            source_path = root_path(root, source_rel)
            source_data = load_object(source_path, "Japanese source")
            rows = extract_dialogue_rows(source_data, str(source_path))
            title = str(source_data.get("bookTitle") or "").strip()
            if title and title not in book_titles:
                book_titles.append(title)
            segments: list[dict[str, Any]] = []
            for row_index, row in enumerate(rows, start=1):
                segment = {
                    "segment_id": f"S{section_index:04d}R{row_index:05d}",
                    **row,
                }
                segments.append(segment)
            group_segments += len(segments)
            source_file_count += 1
            sections.append(
                {
                    "section_index": section_index,
                    "source_name": source_name,
                    "source_json": source_rel.as_posix(),
                    "source_json_sha256": sha256_file(source_path),
                    "target_candidate_json": (target_dir_rel / source_name).as_posix(),
                    "book_title": title,
                    "segment_count": len(segments),
                    "segments": segments,
                }
            )
        if group_segments <= 0:
            raise AllowlistError(f"remaining group has no readable Japanese text: {identity}")
        if group_segments != int(group.get("dialogueCount") or -1):
            raise AllowlistError(
                f"manifest dialogue count drift: {identity}: manifest={group.get('dialogueCount')}, parsed={group_segments}"
            )
        segment_count += group_segments
        corpus = "\n".join(
            [str(audit_entry.get("title") or ""), *book_titles]
            + [f"{row['speaker']}\n{row['source_text']}" for section in sections for row in section["segments"]]
        )
        approved_terms = _approved_terms(glossary, corpus)
        item_id = "exedra-missing-v1-" + sha256_bytes(
            f"{identity}\0{jp_txt_sha256}".encode("utf-8")
        )[:24]
        target_txt = target_dir_rel / f"{group['groupKey']}_cn.txt"
        category = str(group.get("category") or audit_entry.get("category") or "")
        common = {
            "item_id": item_id,
            "story_id": str(audit_entry.get("storyId") or ""),
            "source_identity": identity,
            "classification": "missing_protected_chinese_translation",
            "category": category,
            "title": str(audit_entry.get("title") or ""),
            "context": {
                "book_titles": book_titles,
                "source_count": len(sections),
                "segment_count": group_segments,
                "audit_failures": audit_entry.get("failures", []),
                "human_source_rejections": audit_entry.get("humanSourceRejections", []),
            },
            "jp_txt": text_rel.as_posix(),
            "jp_sha256": jp_txt_sha256,
            "target_candidate_txt": target_txt.as_posix(),
            "formal_tree_write_allowed": False,
            "protection_overlap": False,
            "authority_gate": {
                "official_tw_human": "highest_authority_missing_or_unusable_in_completed_audit",
                "exedra_wiki_voice_human": "protected_if_present_but_absent",
                "rounddora_0728_human": "protected_if_present_but_absent",
                "deepseek_v4_flash": "lowest_weight_staging_only",
                "namae_rule": (
                    "7_Namae official TW remains highest authority; this source is currently missing; "
                    "recheck official TW before any later formal application"
                    if category == "7_Namae"
                    else "not_applicable"
                ),
            },
        }
        allow_entries.append(
            {
                **common,
                "source_json": [
                    {
                        key: section[key]
                        for key in (
                            "section_index",
                            "source_name",
                            "source_json",
                            "source_json_sha256",
                            "target_candidate_json",
                            "segment_count",
                        )
                    }
                    for section in sections
                ],
                "approved_term_ids": [term["term_id"] for term in approved_terms],
            }
        )
        sealed_entries.append(
            {
                **common,
                "sections": sections,
                "approved_terms": approved_terms,
            }
        )

    if len(allow_entries) != expected_allowlist_groups:
        raise AllowlistError("allowlist did not close exactly over all remaining groups")
    if {entry["source_identity"] for entry in allow_entries} != remaining_ids:
        raise AllowlistError("allowlist identities differ from audit remaining groups")

    input_hashes = {
        "audit": {"path": audit_path.relative_to(root).as_posix(), "sha256": sha256_file(audit_path)},
        "manifest": {"path": manifest_path.relative_to(root).as_posix(), "sha256": sha256_file(manifest_path)},
        "glossary": {"path": glossary_path.relative_to(root).as_posix(), "sha256": sha256_file(glossary_path)},
    }
    policy = {
        "authority_order": [
            "official_tw_human",
            "exedra_wiki_voice_human",
            "rounddora_0728_human",
            "deepseek_v4_flash_lowest_weight_staging",
        ],
        "protected_provenance": sorted(PROTECTED_PROVENANCE),
        "formal_tree_write_allowed": False,
        "model_invoked": False,
        "scenario_tree_modified": False,
    }
    allowlist = {
        "schema_version": SCHEMA_VERSION,
        "system": "exedra",
        "classification": "missing_protected_chinese_translation",
        "inputs": input_hashes,
        "policy": policy,
        "counts": {
            "manifest_groups": len(groups),
            "protected_groups": protection["group_count"],
            "allowlist_groups": len(allow_entries),
            "structural_no_text_groups": len(structural_ids),
            "source_json_files": source_file_count,
            "source_segments": segment_count,
            "protection_overlap": 0,
        },
        "entries": allow_entries,
    }
    sealed_input = {
        "schema_version": SCHEMA_VERSION,
        "package_id": "exedra-missing-protected-cn-v1",
        "system": "exedra",
        "model_target": "deepseek-v4-flash",
        "inputs": input_hashes,
        "policy": policy,
        "translation_instructions": {
            "scope": "translate_only_the_sealed_segments",
            "preserve": [
                "segment_count",
                "segment_id",
                "speaker",
                "variables",
                "control_codes",
                "escaped_newlines",
            ],
            "unknown_terms": "return_unresolved_without_guessing",
            "output": "lowest_weight_staging_only",
        },
        "entries": sealed_entries,
    }
    allow_sha256 = sha256_bytes(canonical_json_bytes(allowlist))
    sealed_sha256 = sha256_bytes(canonical_json_bytes(sealed_input))
    verification = {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "inputs": input_hashes,
        "outputs": {
            ALLOWLIST_NAME: {"sha256": allow_sha256},
            SEALED_INPUT_NAME: {"sha256": sealed_sha256},
        },
        "gates": {
            "manifest_groups_exact": len(groups) == expected_total_groups,
            "protected_groups_exact": protection["group_count"] == expected_protected_groups,
            "remaining_groups_exact": len(allow_entries) == expected_allowlist_groups,
            "structural_no_text_groups_exact": len(structural_ids) == expected_structural_groups,
            "classification_partition_exact": True,
            "protected_overlap_zero": True,
            "all_groups_have_readable_japanese": True,
            "all_target_directories_empty_or_absent": True,
            "formal_tree_write_allowed": False,
            "model_invoked": False,
        },
        "counts": allowlist["counts"],
        "protection_snapshot": {
            "protected_group_count": protection["group_count"],
            "protected_file_count": protection["file_count"],
            "provenance_counts": protection["provenance_counts"],
            "protected_tree_sha256": protection["tree_sha256"],
        },
    }
    return allowlist, sealed_input, verification


def output_payloads(
    allowlist: Mapping[str, Any], sealed_input: Mapping[str, Any], verification: Mapping[str, Any]
) -> dict[str, bytes]:
    rows = []
    for entry in allowlist["entries"]:
        rows.append(
            "| {source_identity} | {category} | {sources} | {segments} | {terms} |".format(
                source_identity=entry["source_identity"],
                category=entry["category"],
                sources=len(entry["source_json"]),
                segments=sum(item["segment_count"] for item in entry["source_json"]),
                terms=len(entry["approved_term_ids"]),
            )
        )
    provenance = verification["protection_snapshot"]["provenance_counts"]
    report = "\n".join(
        [
            "# Exedra missing protected-Chinese allowlist v1",
            "",
            "This is a deterministic, lowest-authority staging input. It does not call a model, "
            "does not write the formal scenario trees, and cannot override official TW, Exedra Wiki, "
            "or rounddora 0728 human text.",
            "",
            "## Closed inventory",
            "",
            f"- Manifest groups: {allowlist['counts']['manifest_groups']}",
            f"- Protected groups: {allowlist['counts']['protected_groups']} "
            f"(official TW {provenance['official_tw_human']}; Wiki voice "
            f"{provenance['exedra_wiki_voice_human']}; rounddora 0728 "
            f"{provenance['rounddora_0728_human']})",
            f"- Allowlisted missing groups: {allowlist['counts']['allowlist_groups']}",
            f"- Structural/no-text groups excluded: {allowlist['counts']['structural_no_text_groups']}",
            f"- Japanese source JSON: {allowlist['counts']['source_json_files']}",
            f"- Sealed text segments: {allowlist['counts']['source_segments']}",
            "- Protected overlap: 0",
            "- Formal-tree write allowed: false",
            "- Model invoked: false",
            "",
            "Every 7_Namae entry carries a recheck gate stating that official TW remains the "
            "highest authority and is currently missing for that source group.",
            "",
            "## Entries",
            "",
            "| source_identity | category | JSON | segments | approved terms |",
            "|---|---:|---:|---:|---:|",
            *rows,
            "",
        ]
    ).encode("utf-8")
    return {
        ALLOWLIST_NAME: canonical_json_bytes(allowlist),
        SEALED_INPUT_NAME: canonical_json_bytes(sealed_input),
        VERIFICATION_NAME: canonical_json_bytes(verification),
        REPORT_NAME: report,
    }


def write_or_check(output_dir: Path, payloads: Mapping[str, bytes], *, check: bool) -> None:
    if check:
        for name, expected in payloads.items():
            path = output_dir / name
            try:
                actual = path.read_bytes()
            except OSError as exc:
                raise AllowlistError(f"generated output is missing: {path}: {exc}") from exc
            if actual != expected:
                raise AllowlistError(f"generated output is stale: {path}")
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        atomic_write(output_dir / name, payload)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--expected-total-groups", type=int, default=443)
    parser.add_argument("--expected-protected-groups", type=int, default=413)
    parser.add_argument("--expected-allowlist-groups", type=int, default=26)
    parser.add_argument("--expected-structural-groups", type=int, default=4)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        outputs = build_outputs(
            root=args.root,
            audit_path=args.audit,
            manifest_path=args.manifest,
            glossary_path=args.glossary,
            expected_total_groups=args.expected_total_groups,
            expected_protected_groups=args.expected_protected_groups,
            expected_allowlist_groups=args.expected_allowlist_groups,
            expected_structural_groups=args.expected_structural_groups,
        )
        payloads = output_payloads(*outputs)
        write_or_check(args.output_dir, payloads, check=args.check)
    except AllowlistError as exc:
        print(f"Exedra missing-translation allowlist failed: {exc}")
        return 1
    action = "verified" if args.check else "generated"
    print(
        f"Exedra missing-translation allowlist {action}: "
        f"groups={outputs[0]['counts']['allowlist_groups']}, "
        f"segments={outputs[0]['counts']['source_segments']}, "
        f"protected={outputs[0]['counts']['protected_groups']}, overlap=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
