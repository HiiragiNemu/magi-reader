#!/usr/bin/env python3
"""Repair compatibility shims and tests for canonical Chinese speaker Names."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORTER = ROOT / "tools/import_exedra_official_tw.py"
GENERATOR = ROOT / "generate_story_index.py"
VOICE_TEST = ROOT / "tests/test_import_exedra_wiki_voice.py"


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} replacement count={count}; expected 1"
        )
    path.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")


def replace_block(path: Path, start_marker: str, end_marker: str, replacement: str) -> None:
    source = path.read_text(encoding="utf-8")
    start = source.find(start_marker)
    end = source.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} block markers were not found"
        )
    if source.find(start_marker, start + 1) >= 0:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} block start is not unique"
        )
    path.write_text(
        source[:start] + replacement + source[end:],
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    importer = IMPORTER.read_text(encoding="utf-8")
    import_start = importer.find("from tw_authentic_scenario import (")
    import_end = importer.find("\n)", import_start)
    if import_start < 0 or import_end < 0:
        raise RuntimeError("tw_authentic_scenario import block is missing")
    import_block = importer[import_start:import_end]
    if "materialize_human_json" not in import_block:
        if "    materialize_tw_json," not in import_block:
            raise RuntimeError("materialize_tw_json import marker is missing")
        importer = (
            importer[:import_start]
            + import_block.replace(
                "    materialize_tw_json,",
                "    materialize_human_json,\n    materialize_tw_json,",
                1,
            )
            + importer[import_end:]
        )
        IMPORTER.write_text(importer, encoding="utf-8", newline="\n")

    replace_block(
        IMPORTER,
        "\ndef apply_translated_texts(",
        "\ndef render_cn(",
        '''

def apply_translated_texts(
    source_json: Path,
    texts_or_destination,
    destination_or_converter,
) -> str:
    """Support both authentic-TW and retained human/voice materialization.

    Authentic TW calls pass ``(tw_json, destination, converter)``.  Existing
    human and voice importers pass ``(jp_json, translated_texts, destination)``.
    The latter now canonicalizes every Name through dictionary.ts while keeping
    all non-Name/non-Comment playback fields byte-for-byte equivalent.
    """

    if (
        isinstance(texts_or_destination, (list, tuple))
        and isinstance(destination_or_converter, Path)
    ):
        result = materialize_human_json(
            source_json,
            [str(value) for value in texts_or_destination],
            destination_or_converter,
        )
    elif isinstance(texts_or_destination, Path) and callable(
        destination_or_converter
    ):
        result = materialize_tw_json(
            source_json,
            texts_or_destination,
            destination_or_converter,
        )
    else:
        raise TypeError(
            "apply_translated_texts expects either "
            "(source, texts, destination) or (source, destination, converter)"
        )
    return str(result["sha256"])

''',
    )

    importer = IMPORTER.read_text(encoding="utf-8")
    false_marker = '"speakerSequencesMayDiffer": False'
    true_marker = '"speakerSequencesMayDiffer": True'
    if false_marker in importer:
        replace_once(IMPORTER, false_marker, true_marker)
    elif true_marker not in importer:
        raise RuntimeError("speakerSequencesMayDiffer policy is missing")

    generator = GENERATOR.read_text(encoding="utf-8")
    old_error = "ActionType/工作表/行位置/规范中文说话人 顺序不一致"
    new_error = "ActionType/说话人顺序（工作表/行位置/规范中文说话人）不一致"
    if old_error in generator:
        replace_once(GENERATOR, old_error, new_error)
    elif new_error not in generator:
        raise RuntimeError("canonical speaker ordering error marker is missing")

    replace_once(
        VOICE_TEST,
        '        self.assertEqual(after[1], before[1])\n',
        '        self.assertEqual(after[1], "鹿目圆")\n',
    )
    replace_once(
        VOICE_TEST,
        "    def test_playable_json_generation_changes_only_comment_cells(self) -> None:\n",
        "    def test_playable_json_generation_localizes_name_and_comment_cells(self) -> None:\n",
    )

    print("AUTHENTIC_TW_COMPATIBILITY_AND_TEST_REPAIR_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
