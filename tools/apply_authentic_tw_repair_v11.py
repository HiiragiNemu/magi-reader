#!/usr/bin/env python3
"""Permit and prove dictionary-canonical Name changes in human Exedra JSON."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORTER = ROOT / "tools/import_exedra_human_text.py"
TEST = ROOT / "tests/test_import_exedra_human_text.py"

VALIDATOR = r'''
def validate_only_comment_changed(
    jp_json: Path,
    cn_json: Path,
    expected_texts: list[str],
) -> dict[str, Any]:
    """Prove that only Name and playable Comment cells were localized.

    Every non-empty Name cell, including Put/Disp rows, must equal the exact
    dictionary.ts canonical Chinese form of the corresponding JP Name.  Every
    other playback field remains identical.
    """

    jp_document = common.load_json(jp_json)
    cn_document = common.load_json(cn_json)
    if not isinstance(jp_document, dict) or not isinstance(cn_document, dict):
        raise RuntimeError(f"Exedra JSON 顶层不是对象：{jp_json.name}")
    mapping = common.load_name_translation_map()

    jp_sheets = jp_document.get("sheetList")
    cn_sheets = cn_document.get("sheetList")
    if not isinstance(jp_sheets, list) or not isinstance(cn_sheets, list):
        raise RuntimeError(f"Exedra JSON 缺少 sheetList：{jp_json.name}")
    if len(jp_sheets) != len(cn_sheets):
        raise RuntimeError(f"本地化前后 sheetList 数量不同：{jp_json.name}")

    mutable_comment_cells = 0
    canonical_name_cells = 0
    for sheet_index, (jp_sheet, cn_sheet) in enumerate(
        zip(jp_sheets, cn_sheets),
        start=1,
    ):
        if not isinstance(jp_sheet, dict) or not isinstance(cn_sheet, dict):
            if jp_sheet != cn_sheet:
                raise RuntimeError(
                    f"本地化前后 Sheet 结构不同：{jp_json.name} #{sheet_index}"
                )
            continue
        jp_header = jp_sheet.get("headerRow")
        cn_header = cn_sheet.get("headerRow")
        jp_rows = jp_sheet.get("contentRowList")
        cn_rows = cn_sheet.get("contentRowList")
        if (
            not isinstance(jp_header, dict)
            or not isinstance(cn_header, dict)
            or not isinstance(jp_rows, list)
            or not isinstance(cn_rows, list)
        ):
            if jp_sheet != cn_sheet:
                raise RuntimeError(
                    f"本地化前后 Sheet 元数据不同：{jp_json.name} #{sheet_index}"
                )
            continue
        jp_headers = jp_header.get("cellList")
        cn_headers = cn_header.get("cellList")
        if not isinstance(jp_headers, list) or not isinstance(cn_headers, list):
            raise RuntimeError(f"Exedra JSON Header 无效：{jp_json.name}")
        if jp_headers != cn_headers or len(jp_rows) != len(cn_rows):
            raise RuntimeError(
                f"本地化前后 Header/Row 数量不同：{jp_json.name} #{sheet_index}"
            )
        names = [str(value).strip().casefold() for value in jp_headers]
        action_index = names.index("actiontype") if "actiontype" in names else None
        comment_index = names.index("comment") if "comment" in names else None
        name_index = names.index("name") if "name" in names else None

        for row_index, (jp_row, cn_row) in enumerate(
            zip(jp_rows, cn_rows),
            start=1,
        ):
            jp_cells = jp_row.get("cellList") if isinstance(jp_row, dict) else None
            cn_cells = cn_row.get("cellList") if isinstance(cn_row, dict) else None
            if not isinstance(jp_cells, list) or not isinstance(cn_cells, list):
                if jp_row != cn_row:
                    raise RuntimeError(
                        f"本地化前后 Row 结构不同：{jp_json.name} "
                        f"#{sheet_index}:{row_index}"
                    )
                continue
            if len(jp_cells) != len(cn_cells):
                raise RuntimeError(
                    f"本地化前后 cellList 长度不同：{jp_json.name} "
                    f"#{sheet_index}:{row_index}"
                )

            if name_index is not None and name_index < len(jp_cells):
                jp_name = jp_cells[name_index]
                cn_name = cn_cells[name_index]
                if isinstance(jp_name, str):
                    expected_name = (
                        common.translate_speaker(jp_name, mapping)
                        if jp_name.strip()
                        else jp_name
                    )
                    if cn_name != expected_name:
                        raise RuntimeError(
                            "本地化 JSON 的 Name 未按 dictionary.ts 规范中文化："
                            f"{jp_json.name} #{sheet_index}:{row_index}: "
                            f"{jp_name!r} -> {cn_name!r}, expected {expected_name!r}"
                        )
                    if jp_name.strip():
                        canonical_name_cells += 1
                    jp_cells[name_index] = "__MAGIREADER_CANONICAL_NAME__"
                    cn_cells[name_index] = "__MAGIREADER_CANONICAL_NAME__"
                elif jp_name != cn_name:
                    raise RuntimeError(
                        f"本地化 JSON 修改了非字符串 Name：{jp_json.name}"
                    )

            if (
                action_index is not None
                and comment_index is not None
                and max(action_index, comment_index) < len(jp_cells)
            ):
                action = str(jp_cells[action_index] or "").strip().casefold()
                comment = jp_cells[comment_index]
                if (
                    action in common.TEXT_ACTIONS
                    and isinstance(comment, str)
                    and comment.strip()
                ):
                    if comment_index >= len(cn_cells):
                        raise RuntimeError(
                            f"本地化 JSON 缺少 Comment：{jp_json.name}"
                        )
                    jp_cells[comment_index] = "__MAGIREADER_LOCALIZED_COMMENT__"
                    cn_cells[comment_index] = "__MAGIREADER_LOCALIZED_COMMENT__"
                    mutable_comment_cells += 1

    if jp_document != cn_document:
        raise RuntimeError(
            f"本地化 JSON 修改了 Name/Comment 以外的字段：{jp_json.name}"
        )

    cn_rows = common.extract_rows(cn_json)
    actual_texts = [str(row.get("text") or "") for row in cn_rows]
    if actual_texts != expected_texts:
        raise RuntimeError(
            f"本地化 JSON 的可播放 Comment 顺序错误：{jp_json.name}"
        )
    return {
        # Compatibility key: means all fields outside the declared localized
        # Name/Comment contract match.
        "nonCommentFieldsMatch": True,
        "nonLocalizedFieldsMatch": True,
        "canonicalNameSequenceMatches": True,
        "playableCommentSequenceMatches": True,
        "canonicalNameCellCount": canonical_name_cells,
        "mutableCommentCellCount": mutable_comment_cells,
        "canonicalEventCount": len(actual_texts),
    }
'''


def replace_block(path: Path, start_marker: str, end_marker: str, replacement: str) -> None:
    source = path.read_text(encoding="utf-8")
    start = source.find(start_marker)
    end = source.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0:
        raise RuntimeError(f"{path.relative_to(ROOT)} block markers were not found")
    if source.find(start_marker, start + 1) >= 0:
        raise RuntimeError(f"{path.relative_to(ROOT)} block start is not unique")
    path.write_text(
        source[:start] + "\n" + replacement.strip() + "\n" + source[end:],
        encoding="utf-8",
        newline="\n",
    )


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} replacement count={count}; expected 1"
        )
    path.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")


def main() -> int:
    replace_block(
        IMPORTER,
        "\ndef validate_only_comment_changed(",
        "\ndef import_group(",
        VALIDATOR,
    )
    replace_once(
        TEST,
        "    def test_localized_json_changes_only_playable_comment_cells(self) -> None:\n",
        "    def test_localized_json_changes_canonical_name_and_comment_cells(self) -> None:\n",
    )
    replace_once(
        TEST,
        '                            "cellList": ["Talk", "角色", "日本語", "voice_1"],\n',
        '                            "cellList": ["Talk", "鹿目まどか", "日本語", "voice_1"],\n',
    )
    replace_once(
        TEST,
        '            self.assertTrue(proof["nonCommentFieldsMatch"])\n',
        '            self.assertTrue(proof["nonLocalizedFieldsMatch"])\n'
        '            self.assertTrue(proof["canonicalNameSequenceMatches"])\n'
        '            localized = json.loads(cn_path.read_text(encoding="utf-8"))\n'
        '            self.assertEqual(\n'
        '                localized["sheetList"][0]["contentRowList"][0]["cellList"][1],\n'
        '                "鹿目圆",\n'
        '            )\n',
    )
    print("EXEDRA_HUMAN_NAME_COMMENT_VALIDATION_REPAIR_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
