#!/usr/bin/env python3
"""Use event-level Exedra alignment while preserving authentic TW speaker names."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    source = read(path)
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path}: replacement target count={count}; expected exactly 1"
        )
    write(path, source.replace(old, new, 1))


def replace_block(
    path: str,
    start_marker: str,
    end_marker: str,
    replacement: str,
) -> None:
    source = read(path)
    start = source.find(start_marker)
    if start < 0:
        raise RuntimeError(f"{path}: block start not found: {start_marker!r}")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise RuntimeError(f"{path}: block end not found: {end_marker!r}")
    write(path, source[:start] + replacement + source[end:])


BUILD_REPORT = '''def build_report(
    category: str,
    group_key: str,
    jp_path: Path,
    cn_path: Path,
    source_label: str,
    json_meta: list[dict[str, Any]],
) -> dict[str, Any]:
    jp_sections = pipeline._exedra_alignment_sections(jp_path)
    cn_sections = pipeline._exedra_alignment_sections(cn_path)
    if len(jp_sections) != len(cn_sections):
        raise RuntimeError(f"导入后 Section 数量不一致：{group_key}")
    authentic_tw = any(
        item.get("schemaSource") == "official_tw_json"
        for item in json_meta
        if isinstance(item, dict)
    )
    sections = []
    for jp, cn in zip(jp_sections, cn_sections):
        same_event_structure = (
            jp.number == cn.number
            and jp.source_name == cn.source_name
            and jp.reader_block_count == cn.reader_block_count
        )
        speaker_matches = (
            jp.speaker_sequence_sha256 == cn.speaker_sequence_sha256
        )
        if not same_event_structure or (not authentic_tw and not speaker_matches):
            raise RuntimeError(
                "导入后逐事件结构或规范中文说话人证明失败："
                f"{group_key} Section {jp.number}"
            )
        match = EPISODE_RE.search(jp.source_name)
        sections.append(
            {
                "section": jp.number,
                "source": jp.source_name,
                "wikiEpisode": int(match.group(1)) if match else jp.number - 1,
                "readerNormalizedBlocks": {
                    "jp": jp.reader_block_count,
                    "cn": cn.reader_block_count,
                    "matches": True,
                },
                "speakerSequenceSha256": {
                    "jp": jp.speaker_sequence_sha256,
                    "cn": cn.speaker_sequence_sha256,
                },
                "speakerSequenceMatches": speaker_matches,
            }
        )
    speaker_policy = (
        "official_tw_name_column_tw2sp"
        if authentic_tw
        else "dictionary_canonicalized_jp_name"
    )
    return {
        "schemaVersion": 1,
        "status": "validated",
        "provenance": (
            "official_tw_human" if authentic_tw else "trusted_human"
        ),
        "sourceRoot": source_label,
        "group": {"category": category, "groupKey": group_key},
        "validation": {
            "passed": True,
            "mismatchCount": 0,
            "usesLcs": False,
            "usesFuzzyMatching": False,
            "allowsReordering": False,
            "alignmentLevel": "exact-json-text-event-order",
            "structurePolicy": "same-section-source-event-count-action-row",
            "speakerPolicy": speaker_policy,
            "speakerSequencesMayDiffer": authentic_tw,
            "speakerSequencesCanonicalized": True,
            "twSchemaPreserved": authentic_tw,
        },
        "mismatches": [],
        "jp": {
            "contentSha256": pipeline._sha256_utf8_text_file(jp_path),
            "sectionCount": len(jp_sections),
            "readerNormalizedBlockCount": sum(
                item.reader_block_count for item in jp_sections
            ),
        },
        "cn": {
            "renderedSha256": pipeline._sha256_utf8_text_file(cn_path),
            "sectionCount": len(cn_sections),
            "readerNormalizedBlockCount": sum(
                item.reader_block_count for item in cn_sections
            ),
        },
        "sections": sections,
        "sourceJson": json_meta,
    }
'''


def patch_common_report() -> None:
    replace_block(
        "tools/import_exedra_official_tw.py",
        "\ndef build_report(",
        "\ndef commit_staged_group(",
        "\n" + BUILD_REPORT + "\n",
    )


def patch_pipeline() -> None:
    path = "generate_story_index.py"
    replace_once(
        path,
        '''                if canonical_speaker != previous_speaker:
                    signatures.append(
                        (kind, _exedra_speaker_identity(canonical_speaker))
                    )
                    previous_speaker = canonical_speaker
''',
        '''                # Exedra bilingual alignment is exact JSON text-event order.
                # Do not merge adjacent equal speakers: authentic TW Name fields can
                # legitimately split or join runs differently from the JP release.
                signatures.append(
                    (kind, _exedra_speaker_identity(canonical_speaker))
                )
                previous_speaker = canonical_speaker
''',
    )

    old_json_validation = '''        def canonical_structure(rows: Sequence[Mapping[str, Any]]):
            return [
                (
                    int(row.get("sheet_index") or 0),
                    row.get("row_number"),
                    str(row["action"]).casefold(),
                    _canonical_exedra_speaker(
                        str(row.get("speaker") or "旁白")
                    ),
                )
                for row in rows
            ]

        jp_structure = canonical_structure(jp_rows)
        cn_structure = canonical_structure(cn_rows)
        if jp_structure != cn_structure:
            raise PipelineError(
                "Exedra 中日 JSON 的 ActionType/工作表/行位置/"
                "规范中文说话人顺序不一致: "
                f"{group.manifest_id} #{index}"
            )
'''
    new_json_validation = '''        def event_structure(
            rows: Sequence[Mapping[str, Any]],
            *,
            include_speaker: bool,
        ) -> list[tuple[Any, ...]]:
            result: list[tuple[Any, ...]] = []
            for row in rows:
                base: tuple[Any, ...] = (
                    int(row.get("sheet_index") or 0),
                    row.get("row_number"),
                    str(row["action"]).casefold(),
                )
                if include_speaker:
                    base += (
                        _canonical_exedra_speaker(
                            str(row.get("speaker") or "旁白")
                        ),
                    )
                result.append(base)
            return result

        # Authentic TW JSON owns its Chinese Name column. JP is used only to
        # prove exact sheet/row/action event order. Human JP-derived translations
        # must additionally retain the dictionary-canonicalized speaker identity.
        include_speaker = not authentic_tw
        jp_structure = event_structure(
            jp_rows,
            include_speaker=include_speaker,
        )
        cn_structure = event_structure(
            cn_rows,
            include_speaker=include_speaker,
        )
        if jp_structure != cn_structure:
            label = (
                "ActionType/工作表/行位置/规范中文说话人"
                if include_speaker
                else "ActionType/工作表/行位置"
            )
            raise PipelineError(
                f"Exedra 中日 JSON 的 {label} 顺序不一致: "
                f"{group.manifest_id} #{index}"
            )
'''
    replace_once(path, old_json_validation, new_json_validation)


def patch_reader() -> None:
    path = "website/app/reader/[id]/page.tsx"
    replace_once(
        path,
        '''        const nextCnLines = parsedCn?.lines ?? [];
        const nextJpLines = parsedJp?.lines ?? [];
        const nextCnEventLines = parsedCn?.eventLines ?? [];
        const nextJpEventLines = parsedJp?.eventLines ?? [];
''',
        '''        const nextCnEventLines = parsedCn?.eventLines ?? [];
        const nextJpEventLines = parsedJp?.eventLines ?? [];
        // Exedra uses exact JSON text-event alignment. Display the same event
        // sequence used by editing/JSON downloads instead of merging adjacent
        // speakers independently in each language.
        const nextCnLines = isExedraStory
          ? nextCnEventLines
          : parsedCn?.lines ?? [];
        const nextJpLines = isExedraStory
          ? nextJpEventLines
          : parsedJp?.lines ?? [];
''',
    )
    replace_once(
        path,
        '''    sourcePathJp,
    sourceReady,
  ]);
''',
        '''    sourcePathJp,
    sourceReady,
    isExedraStory,
  ]);
''',
    )


def add_test() -> None:
    write(
        "website/tests/exedra-event-alignment.test.mjs",
        """import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const reader = readFileSync(
  new URL('../app/reader/[id]/page.tsx', import.meta.url),
  'utf8',
);
const pipeline = readFileSync(
  new URL('../../generate_story_index.py', import.meta.url),
  'utf8',
);

test('Exedra bilingual rendering uses exact event lines', () => {
  assert.match(
    reader,
    /const nextCnLines = isExedraStory[\s\S]*?nextCnEventLines/u,
  );
  assert.match(
    reader,
    /const nextJpLines = isExedraStory[\s\S]*?nextJpEventLines/u,
  );
  assert.match(reader, /isExedraStory,\n\s*\]\);/u);
});

test('pipeline does not merge authentic Exedra speaker runs', () => {
  assert.match(
    pipeline,
    /Exedra bilingual alignment is exact JSON text-event order/u,
  );
  assert.match(
    pipeline,
    /include_speaker = not authentic_tw/u,
  );
});
""",
    )


def main() -> int:
    patch_common_report()
    patch_pipeline()
    patch_reader()
    add_test()
    print("AUTHENTIC_TW_EVENT_ALIGNMENT_REPAIR_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
