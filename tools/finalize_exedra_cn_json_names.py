#!/usr/bin/env python3
"""Persist canonical Chinese Name cells in the actual Exedra CN corpus.

The regular canonicalizer also rebuilds reports and TXT.  This final pass is
intentionally rooted at magiraexedra-translate-data-master/Scenarios_full so
non-playable Put/Disp Name cells in retained human groups cannot be missed or
written into the JP source tree by mistake.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tw_authentic_scenario import (
    contains_japanese_script,
    json_bytes,
    load_name_translation_map,
    translate_speaker,
)

ROOT = Path(__file__).resolve().parents[1]
CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
REPORT_SUFFIXES = (
    "_cn.import-report.json",
    "_cn.provenance.json",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def header_indices(sheet: dict[str, Any]) -> dict[str, int]:
    header = sheet.get("headerRow")
    cells = header.get("cellList") if isinstance(header, dict) else None
    if not isinstance(cells, list):
        return {}
    return {
        str(value or "").strip().casefold(): index
        for index, value in enumerate(cells)
        if str(value or "").strip()
    }


def canonicalize_file(
    path: Path,
    mapping: dict[str, str],
) -> tuple[int, list[str]]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        return 0, []
    sheets = value.get("sheetList")
    if not isinstance(sheets, list):
        return 0, []

    changes = 0
    unresolved: list[str] = []
    for sheet_index, sheet in enumerate(sheets):
        if not isinstance(sheet, dict):
            continue
        name_index = header_indices(sheet).get("name")
        rows = sheet.get("contentRowList")
        if name_index is None or not isinstance(rows, list):
            continue
        for row_index, row in enumerate(rows):
            cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(cells, list) or name_index >= len(cells):
                continue
            raw = cells[name_index]
            if not isinstance(raw, str) or not raw.strip():
                continue
            canonical = translate_speaker(raw, mapping)
            if canonical != raw:
                cells[name_index] = canonical
                changes += 1
            if contains_japanese_script(canonical):
                unresolved.append(
                    f"{path.relative_to(ROOT).as_posix()}:"
                    f"{sheet_index}:{row_index}:{canonical}"
                )

    if changes:
        path.write_bytes(json_bytes(value))
    return changes, unresolved


def update_source_entries(value: Any, directory: Path) -> int:
    updates = 0
    if isinstance(value, list):
        for item in value:
            updates += update_source_entries(item, directory)
        return updates
    if not isinstance(value, dict):
        return 0

    source = value.get("source")
    if isinstance(source, str) and source and not Path(source).is_absolute():
        source_path = directory / source
        if source_path.is_file() and source_path.suffix.casefold() == ".json":
            digest = sha256_file(source_path)
            for key in ("cnSha256", "simplifiedJsonSha256"):
                if key in value and value.get(key) != digest:
                    value[key] = digest
                    updates += 1

    for key, item in value.items():
        if key in {"source", "cnSha256", "simplifiedJsonSha256"}:
            continue
        if isinstance(item, (dict, list)):
            updates += update_source_entries(item, directory)
    return updates


def update_metadata(path: Path, json_changes: int) -> int:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Exedra metadata root is not an object: {path}")
    updates = update_source_entries(value, path.parent)
    marker = value.get("speakerCanonicalization")
    if isinstance(marker, dict):
        previous = int(marker.get("jsonNameCellsChanged") or 0)
        marker["jsonNameCellsChanged"] = previous + json_changes
        marker["allJsonNameColumnsCanonicalized"] = True
        updates += 1
    else:
        value["speakerCanonicalization"] = {
            "policy": "dictionary.ts-canonical-Chinese-all-Name-columns",
            "jsonNameCellsChanged": json_changes,
            "allJsonNameColumnsCanonicalized": True,
        }
        updates += 1
    if updates:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return updates


def main() -> int:
    if not CN_ROOT.is_dir():
        raise RuntimeError(f"Exedra CN corpus is missing: {CN_ROOT}")
    mapping = load_name_translation_map()
    changed_by_directory: dict[Path, int] = {}
    unresolved: list[str] = []
    files = 0
    changes = 0

    for path in sorted(CN_ROOT.rglob("*.json")):
        folded = path.name.casefold()
        if folded.endswith(REPORT_SUFFIXES):
            continue
        file_changes, file_unresolved = canonicalize_file(path, mapping)
        files += 1
        changes += file_changes
        unresolved.extend(file_unresolved)
        if file_changes:
            changed_by_directory[path.parent] = (
                changed_by_directory.get(path.parent, 0) + file_changes
            )

    if unresolved:
        print("EXEDRA_FINAL_JSON_NAME_UNRESOLVED", unresolved[:500])
        raise RuntimeError(
            f"{len(unresolved)} Japanese speaker labels remain after finalization"
        )

    metadata_updates = 0
    for path in sorted(CN_ROOT.rglob("*.json")):
        if not path.name.casefold().endswith(REPORT_SUFFIXES):
            continue
        metadata_updates += update_metadata(
            path,
            changed_by_directory.get(path.parent, 0),
        )

    print(
        "EXEDRA_FINAL_JSON_NAMES_OK "
        f"files={files} changes={changes} metadata_updates={metadata_updates}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
