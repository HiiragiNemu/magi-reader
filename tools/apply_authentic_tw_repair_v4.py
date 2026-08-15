#!/usr/bin/env python3
"""Harden authentic TW field validation against duplicate-sheet normalization."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/tw_authentic_scenario.py"

OLD = '''    localized_events = extract_text_events(document)
    if len(localized_events) != len(original_events):
        raise RuntimeError(
            f"TW event count changed while localizing {source.name}: "
            f"{len(original_events)} -> {len(localized_events)}"
        )
    for index, (before, after) in enumerate(
        zip(original_events, localized_events), start=1
    ):
        before_structure = (
            before["sheet_index"],
            before["row_number"],
            str(before["action"]).casefold(),
        )
        after_structure = (
            after["sheet_index"],
            after["row_number"],
            str(after["action"]).casefold(),
        )
        if before_structure != after_structure:
            raise RuntimeError(
                f"TW event structure changed at {source.name} event {index}"
            )
        if after["text"] != convert(str(before["text"])):
            raise RuntimeError(
                f"TW Comment was not simplified exactly at {source.name} event {index}"
            )
        expected_speaker = (
            translate_speaker(convert(str(before["speaker"])), speaker_map)
            if str(before["speaker"]).strip()
            else ""
        )
        if after["speaker"] != expected_speaker:
            raise RuntimeError(
                f"TW Name was not canonicalized exactly at {source.name} event {index}"
            )

    encoded = json_bytes(document)
'''

NEW = '''    localized_events = extract_text_events(document)
    if len(localized_events) != len(original_events):
        raise RuntimeError(
            f"TW event count changed while localizing {source.name}: "
            f"{len(original_events)} -> {len(localized_events)}"
        )

    original_sheets = original.get("sheetList")
    localized_sheets = document.get("sheetList")
    if (
        not isinstance(original_sheets, list)
        or not isinstance(localized_sheets, list)
        or len(original_sheets) != len(localized_sheets)
    ):
        raise RuntimeError(f"TW sheetList changed while localizing {source.name}")
    for sheet_index, (before_sheet, after_sheet) in enumerate(
        zip(original_sheets, localized_sheets),
        start=1,
    ):
        if not isinstance(before_sheet, dict) or not isinstance(after_sheet, dict):
            if before_sheet != after_sheet:
                raise RuntimeError(
                    f"TW sheet changed at {source.name} sheet {sheet_index}"
                )
            continue
        before_indices = _header_indices(before_sheet)
        after_indices = _header_indices(after_sheet)
        if before_indices != after_indices:
            raise RuntimeError(
                f"TW headers changed at {source.name} sheet {sheet_index}"
            )
        before_rows = before_sheet.get("contentRowList")
        after_rows = after_sheet.get("contentRowList")
        if (
            not isinstance(before_rows, list)
            or not isinstance(after_rows, list)
            or len(before_rows) != len(after_rows)
        ):
            raise RuntimeError(
                f"TW row count changed at {source.name} sheet {sheet_index}"
            )
        name_index = before_indices.get("name")
        action_index = before_indices.get("actiontype")
        comment_index = before_indices.get("comment")
        for row_index, (before_row, after_row) in enumerate(
            zip(before_rows, after_rows),
            start=1,
        ):
            before_cells = (
                before_row.get("cellList")
                if isinstance(before_row, dict)
                else None
            )
            after_cells = (
                after_row.get("cellList")
                if isinstance(after_row, dict)
                else None
            )
            if not isinstance(before_cells, list) or not isinstance(after_cells, list):
                if before_row != after_row:
                    raise RuntimeError(
                        f"TW row changed at {source.name} "
                        f"sheet {sheet_index} row {row_index}"
                    )
                continue
            if len(before_cells) != len(after_cells):
                raise RuntimeError(
                    f"TW cell count changed at {source.name} "
                    f"sheet {sheet_index} row {row_index}"
                )
            if name_index is not None and name_index < len(before_cells):
                before_name = before_cells[name_index]
                after_name = after_cells[name_index]
                expected_name = (
                    translate_speaker(convert(before_name), speaker_map)
                    if isinstance(before_name, str) and before_name
                    else before_name
                )
                if after_name != expected_name:
                    raise RuntimeError(
                        "TW Name was not canonicalized exactly at "
                        f"{source.name} sheet {sheet_index} row {row_index}: "
                        f"before={before_name!r} expected={expected_name!r} "
                        f"after={after_name!r}"
                    )
            action = (
                str(before_cells[action_index] or "").strip().casefold()
                if action_index is not None and action_index < len(before_cells)
                else ""
            )
            if (
                action in TEXT_ACTIONS
                and comment_index is not None
                and comment_index < len(before_cells)
            ):
                before_comment = before_cells[comment_index]
                after_comment = after_cells[comment_index]
                expected_comment = (
                    convert(before_comment)
                    if isinstance(before_comment, str) and before_comment
                    else before_comment
                )
                if after_comment != expected_comment:
                    raise RuntimeError(
                        "TW playable Comment was not simplified exactly at "
                        f"{source.name} sheet {sheet_index} row {row_index}"
                    )

    before_redacted = copy.deepcopy(original)
    after_redacted = copy.deepcopy(document)
    _redact_localized_fields(before_redacted)
    _redact_localized_fields(after_redacted)
    if before_redacted != after_redacted:
        raise RuntimeError(
            f"TW localization changed fields outside Name/playable Comment: {source.name}"
        )

    encoded = json_bytes(document)
'''


def main() -> int:
    source = PATH.read_text(encoding="utf-8")
    count = source.count(OLD)
    if count != 1:
        raise RuntimeError(
            f"tw_authentic_scenario.py validation block count={count}; expected 1"
        )
    PATH.write_text(source.replace(OLD, NEW, 1), encoding="utf-8", newline="\n")
    print("AUTHENTIC_TW_FIELD_VALIDATION_REPAIR_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
