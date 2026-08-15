#!/usr/bin/env python3
"""Finish Exedra speaker localization, editable JSON names, and test contracts."""
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
    if source.find(start_marker, start + 1) >= 0:
        raise RuntimeError(f"{path}: block start is not unique")
    write(path, source[:start] + replacement + source[end:])


EXEDRA_EDIT_BLOCK = r'''type ExedraEvent = {
  commentReferences: MutableStringReference[];
  nameReferences: MutableStringReference[];
};

const exedraEvents = (document: JsonRecord): ExedraEvent[] => {
  if (!Array.isArray(document.sheetList)) {
    throw new ScenarioJsonDownloadError('Exedra JSON 缺少 sheetList。');
  }
  const unique: Array<{ fingerprint: string; events: ExedraEvent[] }> = [];
  const fingerprintIndex = new Map<string, number>();

  document.sheetList.forEach((sheetValue, sheetIndex) => {
    if (!isRecord(sheetValue) || !isRecord(sheetValue.headerRow) ||
        !Array.isArray(sheetValue.headerRow.cellList) ||
        !Array.isArray(sheetValue.contentRowList)) {
      return;
    }
    const headers = sheetValue.headerRow.cellList
      .map(value => asString(value).trim().toLowerCase());
    const actionIndex = headers.indexOf('actiontype');
    const commentIndex = headers.indexOf('comment');
    const nameIndex = headers.indexOf('name');
    if (actionIndex < 0 || commentIndex < 0) return;

    const events: ExedraEvent[] = [];
    const fingerprintRows: Array<[string, string, string]> = [];
    sheetValue.contentRowList.forEach((rowValue, rowIndex) => {
      if (!isRecord(rowValue) || !Array.isArray(rowValue.cellList)) return;
      const action = asString(rowValue.cellList[actionIndex]).trim();
      const comment = rowValue.cellList[commentIndex];
      if (!EXEDRA_TEXT_ACTIONS.has(action.toLowerCase()) ||
          typeof comment !== 'string' || !comment.trim()) {
        return;
      }
      const speaker = nameIndex >= 0
        ? asString(rowValue.cellList[nameIndex]).trim()
        : '';
      const cellListPath = appendPath(
        appendPath(
          appendPath(
            appendPath('/sheetList', sheetIndex),
            'contentRowList',
          ),
          rowIndex,
        ),
        'cellList',
      );
      const nameReferences: MutableStringReference[] = [];
      if (
        nameIndex >= 0 &&
        nameIndex < rowValue.cellList.length &&
        typeof rowValue.cellList[nameIndex] === 'string'
      ) {
        nameReferences.push({
          container: rowValue.cellList,
          key: nameIndex,
          path: appendPath(cellListPath, nameIndex),
        });
      }
      events.push({
        commentReferences: [{
          container: rowValue.cellList,
          key: commentIndex,
          path: appendPath(cellListPath, commentIndex),
        }],
        nameReferences,
      });
      fingerprintRows.push([action, speaker, comment.trim()]);
    });
    if (events.length === 0) return;

    const fingerprint = JSON.stringify(fingerprintRows);
    const duplicate = fingerprintIndex.get(fingerprint);
    if (duplicate === undefined) {
      fingerprintIndex.set(fingerprint, unique.length);
      unique.push({ fingerprint, events });
      return;
    }
    const primary = unique[duplicate].events;
    if (primary.length !== events.length) {
      throw new ScenarioJsonDownloadError('Exedra 重复工作表事件数量不同。');
    }
    primary.forEach((event, eventIndex) => {
      event.commentReferences.push(
        ...events[eventIndex].commentReferences,
      );
      event.nameReferences.push(
        ...events[eventIndex].nameReferences,
      );
    });
  });

  return unique.flatMap(item => item.events);
};

const canonicalizeExedraNameCells = (
  document: JsonRecord,
  allowedPaths: Set<string>,
): number => {
  if (!Array.isArray(document.sheetList)) {
    throw new ScenarioJsonDownloadError('Exedra JSON 缺少 sheetList。');
  }
  let changed = 0;
  document.sheetList.forEach((sheetValue, sheetIndex) => {
    if (!isRecord(sheetValue) || !isRecord(sheetValue.headerRow) ||
        !Array.isArray(sheetValue.headerRow.cellList) ||
        !Array.isArray(sheetValue.contentRowList)) {
      return;
    }
    const headers = sheetValue.headerRow.cellList
      .map(value => asString(value).trim().toLowerCase());
    const nameIndex = headers.indexOf('name');
    if (nameIndex < 0) return;
    sheetValue.contentRowList.forEach((rowValue, rowIndex) => {
      if (!isRecord(rowValue) || !Array.isArray(rowValue.cellList) ||
          nameIndex >= rowValue.cellList.length ||
          typeof rowValue.cellList[nameIndex] !== 'string') {
        return;
      }
      const current = rowValue.cellList[nameIndex] as string;
      if (!current.trim()) return;
      changed += setReference(
        {
          container: rowValue.cellList,
          key: nameIndex,
          path: appendPath(
            appendPath(
              appendPath(
                appendPath(
                  appendPath('/sheetList', sheetIndex),
                  'contentRowList',
                ),
                rowIndex,
              ),
              'cellList',
            ),
            nameIndex,
          ),
        },
        translateSpeakerName(current),
        allowedPaths,
      );
    });
  });
  return changed;
};

const canonicalEditableSpeaker = (speaker: string): string =>
  NARRATION_SPEAKERS.has(speaker.trim())
    ? ''
    : translateSpeakerName(speaker.trim());

const applyExedraEdits = (
  document: JsonRecord,
  originalLines: readonly StoryLine[],
  editedLines: readonly StoryLine[],
  allowedPaths: Set<string>,
): number => {
  const events = exedraEvents(document);
  if (events.length !== originalLines.length) {
    throw new ScenarioJsonDownloadError(
      `Exedra 文本事件结构不匹配：JSON=${events.length}，解析=${originalLines.length}。`,
    );
  }
  let changed = canonicalizeExedraNameCells(document, allowedPaths);
  events.forEach((event, index) => {
    const source = originalLines[index];
    const edited = editedLines[index];
    event.commentReferences.forEach(reference => {
      changed += setReference(
        reference,
        edited.text,
        allowedPaths,
      );
    });

    const nextSpeaker = canonicalEditableSpeaker(edited.speaker);
    const baselineSpeaker = canonicalEditableSpeaker(source.speaker);
    if (event.nameReferences.length === 0) {
      if (nextSpeaker !== baselineSpeaker) {
        throw new ScenarioJsonDownloadError(
          `第 ${index + 1} 行 Exedra JSON 没有可写回的 Name 字段。`,
        );
      }
      return;
    }
    event.nameReferences.forEach(reference => {
      changed += setReference(
        reference,
        nextSpeaker,
        allowedPaths,
      );
    });
  });
  if (events.length === 0) {
    throw new ScenarioJsonDownloadError('该 Exedra JSON 没有可编辑文本事件。');
  }
  return changed;
};

'''


EXEDRA_DOWNLOAD_TEST = r'''test('edited Exedra JSON localizes every Name cell and preserves playback columns', () => {
  const filename = 'character_iroha_1.json';
  const originalLines = linesFrom(exedraDocument, filename);
  const edited = cloneLines(originalLines);
  edited[0].speaker = '环彩羽';
  edited[0].text = '你好';
  edited[1].text = '风吹过街道';

  const result = createEditedScenarioJsonDownload({
    sourceJson: JSON.stringify(exedraDocument),
    sourceFilename: filename,
    storyId: 'character_iroha',
    editedLines: edited,
  });
  const output = JSON.parse(result.json) as typeof exedraDocument;
  const rows = output.sheetList[0].contentRowList;

  assert.equal(result.changedTextFields, 4);
  assert.equal(rows[0].cellList[1], '环彩羽');
  assert.equal(rows[1].cellList[1], '环彩羽');
  assert.equal(rows[1].cellList[2], '你好');
  assert.equal(rows[2].cellList[1], '');
  assert.equal(rows[2].cellList[2], '风吹过街道');
  assert.deepEqual(rows[1].cellList.slice(3), ['adv_1001', 'Left', 'Talk', 'cv_1']);
  assert.deepEqual(rows[0].cellList.slice(2), ['', 'adv_1001', 'Left', 'Idle', '']);
  assert.deepEqual(objectKeysShape(output), objectKeysShape(exedraDocument));
});

'''


EVENT_ALIGNMENT_TEST = r'''import assert from 'node:assert/strict';
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
  assert.ok(reader.includes('sourceReady,\n    isExedraStory,\n  ]);'));
});

test('pipeline does not merge authentic Exedra speaker runs', () => {
  assert.ok(
    pipeline.includes(
      'Exedra bilingual alignment is exact JSON text-event order',
    ),
  );
  assert.ok(pipeline.includes('include_speaker = not authentic_tw'));
});
'''


AUDIT_SCRIPT = r'''#!/usr/bin/env python3
"""Prove every JP Exedra speaker that may enter Chinese editing is mapped."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from tw_authentic_scenario import (  # noqa: E402
    contains_japanese_script,
    load_name_translation_map,
    translate_speaker,
)

SOURCE = ROOT / 'magiraexedra-source-master/Scenarios_full'
SEPARATOR = re.compile(r'[:：﹕︰︓]')


def main() -> int:
    mapping = load_name_translation_map()
    failures: dict[str, set[str]] = {}
    txt_labels = 0
    json_labels = 0

    def check(raw: str, location: str) -> None:
        nonlocal txt_labels, json_labels
        speaker = raw.strip()
        if not speaker:
            return
        canonical = translate_speaker(speaker, mapping)
        if location.endswith('.txt'):
            txt_labels += 1
        else:
            json_labels += 1
        if contains_japanese_script(canonical):
            failures.setdefault(speaker, set()).add(location)

    for path in sorted(SOURCE.rglob('*_jp.txt')):
        for number, raw in enumerate(
            path.read_text(encoding='utf-8-sig').splitlines(),
            start=1,
        ):
            line = raw.strip()
            if not line or line.startswith('---'):
                continue
            match = SEPARATOR.search(raw)
            if match is None or match.start() <= 0 or match.start() > 96:
                continue
            check(raw[:match.start()], f'{path.as_posix()}:{number}.txt')

    for path in sorted(SOURCE.rglob('*.json')):
        try:
            value = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        sheets = value.get('sheetList')
        if not isinstance(sheets, list):
            continue
        for sheet_index, sheet in enumerate(sheets):
            if not isinstance(sheet, dict):
                continue
            header = sheet.get('headerRow')
            headers = header.get('cellList') if isinstance(header, dict) else None
            rows = sheet.get('contentRowList')
            if not isinstance(headers, list) or not isinstance(rows, list):
                continue
            folded = [str(item or '').strip().casefold() for item in headers]
            try:
                name_index = folded.index('name')
            except ValueError:
                continue
            for row_index, row in enumerate(rows):
                cells = row.get('cellList') if isinstance(row, dict) else None
                if not isinstance(cells, list) or name_index >= len(cells):
                    continue
                value = cells[name_index]
                if isinstance(value, str) and value.strip():
                    check(
                        value,
                        f'{path.as_posix()}:{sheet_index}:{row_index}.json',
                    )

    if failures:
        for speaker, locations in sorted(failures.items())[:300]:
            canonical = translate_speaker(speaker, mapping)
            print(
                'UNMAPPED_EXEDRA_JP_SPEAKER',
                repr(speaker),
                '->',
                repr(canonical),
                sorted(locations)[:5],
            )
        raise SystemExit(
            'dictionary.ts does not cover every JP Exedra speaker used by '
            f'Chinese editing: {len(failures)} unique labels'
        )

    print(
        'EXEDRA_JP_SPEAKER_DICTIONARY_COMPLETE '
        f'txt_labels={txt_labels} json_labels={json_labels} '
        f'mapping_entries={len(mapping)}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
'''


def patch_scenario_json_download() -> None:
    path = "website/lib/scenario-json-download.ts"
    replace_once(
        path,
        "} from './browser-download.ts';\nimport {\n",
        "} from './browser-download.ts';\n"
        "import { translateSpeakerName } from '../app/config/dictionary.ts';\n"
        "import {\n",
    )
    replace_block(
        path,
        "type ExedraEvent = {",
        "type GeneralVoiceGroup = {",
        EXEDRA_EDIT_BLOCK,
    )


def patch_scenario_json_tests() -> None:
    path = "website/lib/scenario-json-download.test.ts"
    replace_block(
        path,
        "test('edited Exedra JSON changes only Comment cells and preserves playback columns', () => {",
        "test('edited JSON fails closed on count, branch, position and speaker mismatches', () => {",
        EXEDRA_DOWNLOAD_TEST,
    )
    replace_once(
        path,
        "test('edited JSON fails closed on count, branch, position and speaker mismatches', () => {",
        "test('edited JSON fails closed on count, branch and position mismatches', () => {",
    )
    replace_once(
        path,
        """  const exedraFilename = 'character_iroha_1.json';
  const changedSpeaker = cloneLines(linesFrom(exedraDocument, exedraFilename));
  changedSpeaker[0].speaker = '错误角色';
  assert.throws(
    () => createEditedScenarioJsonDownload({
      sourceJson: JSON.stringify(exedraDocument),
      sourceFilename: exedraFilename,
      storyId: 'character_iroha',
      editedLines: changedSpeaker,
    }),
    /Exedra 说话人身份不可修改/u,
  );
""",
        "",
    )


def patch_reader_messages() -> None:
    path = "website/app/reader/[id]/page.tsx"
    source = read(path)
    source = source.replace(
        "个文本字段。",
        "个中文正文/角色名字段。",
    )
    if source == read(path):
        raise RuntimeError("reader JSON field message was not updated")
    write(path, source)


def patch_tests_and_audit() -> None:
    replace_once(
        "website/tests/cloudflare-deployment.test.mjs",
        "  assert.match(workflow, /access-control-allow-origin/u);\n",
        "  assert.match(workflow, /cross-origin-resource-policy: same-origin/u);\n",
    )
    write(
        "website/tests/exedra-event-alignment.test.mjs",
        EVENT_ALIGNMENT_TEST,
    )
    write(
        "tools/audit_exedra_jp_speaker_dictionary.py",
        AUDIT_SCRIPT,
    )


def main() -> int:
    patch_scenario_json_download()
    patch_scenario_json_tests()
    patch_reader_messages()
    patch_tests_and_audit()
    print("AUTHENTIC_TW_REPAIR_V16_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
