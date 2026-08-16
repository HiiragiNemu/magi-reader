#!/usr/bin/env python3
"""Separate Exedra JSON event structure proof from speaker localization proof.

JP and CN Exedra JSON files must retain the exact sheet/row/action event order.
Speaker strings are language data, however, and are validated independently:
all non-empty CN Name cells must already be the canonical dictionary form and
must contain no kana. This permits legitimate blank/contextual Name placement
differences in retained human translations without weakening action ordering,
file hashes, report binding, or Name/Comment-only mutation proofs.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "generate_story_index.py"
PIPELINE_TEST = ROOT / "tests/test_data_pipeline.py"
WEB_TEST = ROOT / "website/tests/exedra-event-alignment.test.mjs"

OLD_VALIDATION = '''        def event_structure(
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

NEW_VALIDATION = '''        def event_structure(
            rows: Sequence[Mapping[str, Any]],
        ) -> list[tuple[Any, ...]]:
            return [
                (
                    int(row.get("sheet_index") or 0),
                    row.get("row_number"),
                    str(row["action"]).casefold(),
                )
                for row in rows
            ]

        # Language-specific Name placement is not event structure. Authentic TW
        # owns its Chinese Name column, while retained human translations can
        # legitimately use a Chinese Name where the JP row relied on contextual
        # Put/position state. Exact source/report hashes and the importers prove
        # Name/Comment-only localization; here we prove sheet/row/action order.
        jp_structure = event_structure(jp_rows)
        cn_structure = event_structure(cn_rows)
        if jp_structure != cn_structure:
            raise PipelineError(
                "Exedra 中日 JSON 的 ActionType/工作表/行位置顺序不一致: "
                f"{group.manifest_id} #{index}"
            )

        # Every visible CN Name must nevertheless be the exact canonical form.
        # Blank cells remain meaningful playback structure and are left blank.
        for event_index, row in enumerate(cn_rows, start=1):
            speaker = str(row.get("speaker") or "").strip()
            if not speaker:
                continue
            canonical = _canonical_exedra_speaker(speaker)
            if speaker != canonical or re.search(r"[\u3040-\u30ff]", speaker):
                raise PipelineError(
                    "Exedra 中文 JSON 的 Name 未规范中文化: "
                    f"{group.manifest_id} #{index} event {event_index}: "
                    f"{speaker!r} -> {canonical!r}"
                )
'''

NEW_WEB_TEST = """import assert from 'node:assert/strict';
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
  assert.ok(reader.includes('const nextCnLines = isExedraStory'));
  assert.ok(reader.includes('? nextCnEventLines'));
  assert.ok(reader.includes('const nextJpLines = isExedraStory'));
  assert.ok(reader.includes('? nextJpEventLines'));
  assert.ok(reader.includes('sourceReady,\\n    isExedraStory,\\n  ]);'));
});

test('pipeline separates event structure from localized speaker proof', () => {
  assert.ok(
    pipeline.includes(
      'Exedra bilingual alignment is exact JSON text-event order',
    ),
  );
  assert.ok(
    pipeline.includes(
      'Exedra 中日 JSON 的 ActionType/工作表/行位置顺序不一致',
    ),
  );
  assert.ok(
    pipeline.includes('Exedra 中文 JSON 的 Name 未规范中文化'),
  );
  assert.doesNotMatch(pipeline, /include_speaker = not authentic_tw/u);
});
"""

NEW_PIPELINE_TEST = '''    def test_noncanonical_cn_json_name_is_rejected(self) -> None:
        self._make_sources()
        cn_json = self._write_main_cn_json()
        data = json.loads(cn_json.read_text(encoding="utf-8"))
        data["sheetList"][0]["contentRowList"][0]["cellList"][1] = (
            "鹿目まどか"
        )
        write_json(cn_json, data)
        report_path = (
            self.exedra_cn
            / "1_Main"
            / "main_demo"
            / "main_demo_cn.import-report.json"
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["sourceJson"][0]["cnSha256"] = generate._sha256_file(
            cn_json
        )
        write_json(report_path, report)

        with self.assertRaisesRegex(
            generate.PipelineError,
            "Name 未规范中文化",
        ):
            generate.build_story_catalog(
                staging_public_dir=self.stage,
                jp_dir=self.jp,
                cn_dir=self.cn,
                exedra_jp_dir=self.exedra,
                exedra_cn_dir=self.exedra_cn,
                titles_path=self.titles,
            )

'''


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} replacement count={count}; expected 1"
        )
    path.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")


def main() -> int:
    replace_once(PIPELINE, OLD_VALIDATION, NEW_VALIDATION)

    # The fixture represents a published CN JSON and therefore must itself use
    # the canonical Chinese Name rather than relying on validation-time mapping.
    replace_once(
        PIPELINE_TEST,
        '                [["Talk", "鹿目まどか", "秀恩爱", "", ""]]\n',
        '                [["Talk", "鹿目圆", "秀恩爱", "", ""]]\n',
    )
    replace_once(
        PIPELINE_TEST,
        '            "ActionType/.*说话人",\n',
        '            "ActionType/工作表/行位置",\n',
    )
    marker = '    def test_tampered_cn_file_is_rejected_by_report_hash(self) -> None:\n'
    source = PIPELINE_TEST.read_text(encoding="utf-8")
    if source.count(marker) != 1:
        raise RuntimeError("test_data_pipeline insertion marker is not unique")
    PIPELINE_TEST.write_text(
        source.replace(marker, NEW_PIPELINE_TEST + marker, 1),
        encoding="utf-8",
        newline="\n",
    )

    if not WEB_TEST.is_file():
        raise RuntimeError("generated Exedra event-alignment web test is missing")
    WEB_TEST.write_text(NEW_WEB_TEST, encoding="utf-8", newline="\n")

    print("EXEDRA_EVENT_STRUCTURE_AND_SPEAKER_PROOF_V24_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
