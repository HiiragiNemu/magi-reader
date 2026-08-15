#!/usr/bin/env python3
"""Canonicalize every non-empty Name cell, not only playable dialogue rows."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools/tw_authentic_scenario.py"

REPLACEMENT = r'''
def canonicalize_json_names_path(
    path: Path,
    mapping: dict[str, str],
) -> tuple[int, int]:
    """Canonicalize every Name column cell and report unresolved kana.

    Exedra uses Name on Put/Disp and other non-dialogue rows as well as on
    playable Talk/Narration rows.  Those cells are part of the published
    Chinese scenario JSON and must follow the same dictionary contract.
    """

    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict):
        raise RuntimeError(f"Exedra JSON root is not an object: {path}")

    changes = 0
    remaining = 0
    sheets = document.get("sheetList")
    if not isinstance(sheets, list):
        raise RuntimeError(f"Exedra JSON is missing sheetList: {path}")

    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        name_index = _header_indices(sheet).get("name")
        rows = sheet.get("contentRowList")
        if name_index is None or not isinstance(rows, list):
            continue
        for row in rows:
            cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(cells, list) or name_index >= len(cells):
                continue
            value = cells[name_index]
            if not isinstance(value, str) or not value.strip():
                continue
            canonical = translate_speaker(value, mapping)
            if canonical != value:
                cells[name_index] = canonical
                changes += 1
            if contains_japanese_script(canonical):
                remaining += 1

    if changes:
        path.write_bytes(json_bytes(document))
    return changes, remaining
'''


def main() -> int:
    source = MODULE.read_text(encoding="utf-8")
    start_marker = "\ndef canonicalize_json_names_path("
    end_marker = "\ndef dictionary_sha256("
    start = source.find(start_marker)
    end = source.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0:
        raise RuntimeError(
            "tw_authentic_scenario.py canonicalize_json_names_path block not found"
        )
    if source.find(start_marker, start + 1) >= 0:
        raise RuntimeError("canonicalize_json_names_path is not unique")
    MODULE.write_text(
        source[:start] + "\n" + REPLACEMENT.strip() + "\n" + source[end:],
        encoding="utf-8",
        newline="\n",
    )
    print("EXEDRA_ALL_JSON_NAME_CANONICALIZATION_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
