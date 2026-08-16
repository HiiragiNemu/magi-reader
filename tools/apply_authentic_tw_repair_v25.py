#!/usr/bin/env python3
"""Canonicalize Exedra speakers before JSON edit round-trip validation."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD = ROOT / "website/lib/scenario-json-download.ts"
SELECTION = ROOT / "website/lib/scenario-json-selection.ts"
SELECTION_TEST = ROOT / "website/lib/scenario-json-selection.test.ts"


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} replacement count={count}; expected 1"
        )
    path.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")


def main() -> int:
    replace_once(
        SELECTION,
        "import type { StoryIndexEntry } from './story-index.ts';\n",
        "import type { StoryIndexEntry } from './story-index.ts';\n"
        "import { translateSpeakerName } from '../app/config/dictionary.ts';\n",
    )
    replace_once(
        SELECTION,
        "export class ScenarioJsonSelectionError extends Error {\n"
        "  constructor(message: string) {\n"
        "    super(message);\n"
        "    this.name = 'ScenarioJsonSelectionError';\n"
        "  }\n"
        "}\n\n",
        "export class ScenarioJsonSelectionError extends Error {\n"
        "  constructor(message: string) {\n"
        "    super(message);\n"
        "    this.name = 'ScenarioJsonSelectionError';\n"
        "  }\n"
        "}\n\n"
        "const EXEDRA_NARRATION_SPEAKERS = new Set([\n"
        "  '',\n"
        "  '旁白',\n"
        "  'Narration',\n"
        "  'ナレーション',\n"
        "]);\n\n"
        "const canonicalScenarioSpeaker = (\n"
        "  format: StoryFormat,\n"
        "  speaker: string,\n"
        "): string => {\n"
        "  if (format !== 'exedra-json') return speaker;\n"
        "  const normalized = speaker.trim();\n"
        "  return EXEDRA_NARRATION_SPEAKERS.has(normalized)\n"
        "    ? '旁白'\n"
        "    : translateSpeakerName(normalized);\n"
        "};\n\n",
    )
    replace_once(
        SELECTION,
        "      speaker: aggregateEdited.speaker,\n",
        "      speaker: canonicalScenarioSpeaker(\n"
        "        parsed.format,\n"
        "        aggregateEdited.speaker,\n"
        "      ),\n",
    )
    replace_once(
        SELECTION,
        "      speaker: uploadedLine.speaker,\n",
        "      speaker: canonicalScenarioSpeaker(\n"
        "        uploaded.format,\n"
        "        uploadedLine.speaker,\n"
        "      ),\n",
    )

    old_round_trip = '''const comparableLine = (line: StoryLine): string =>
  JSON.stringify({
    structure: lineStructure(line),
    speaker: line.speaker,
    text: line.text,
    choiceLabel: line.choiceLabel || '',
  });

const assertJsonRoundTrip = (
  json: string,
  sourceFilename: string,
  expected: readonly StoryLine[],
): void => {
  const rendered = parseStoryContent(json, {
    filename: sourceFilename,
    mergeConsecutiveTextLines: false,
  }).lines;
  if (
    rendered.length !== expected.length ||
    rendered.some((line, index) =>
      comparableLine(line) !== comparableLine(expected[index]))
  ) {
    throw new ScenarioJsonDownloadError(
      '编辑 JSON 回生后与校对行不一致，已停止下载。',
    );
  }
};

'''
    new_round_trip = '''const comparableLine = (line: StoryLine): string =>
  JSON.stringify({
    structure: lineStructure(line),
    speaker: line.speaker,
    text: line.text,
    choiceLabel: line.choiceLabel || '',
  });

const canonicalRoundTripSpeaker = (
  line: StoryLine,
  format: ScenarioFormat,
): string => {
  if (format !== 'exedra-json' || line.isHeader) return line.speaker;
  const speaker = line.speaker.trim();
  return NARRATION_SPEAKERS.has(speaker)
    ? '旁白'
    : translateSpeakerName(speaker);
};

const comparableRoundTripLine = (
  line: StoryLine,
  format: ScenarioFormat,
): string =>
  JSON.stringify({
    structure: lineStructure(line),
    speaker: canonicalRoundTripSpeaker(line, format),
    text: line.text,
    choiceLabel: line.choiceLabel || '',
  });

const assertJsonRoundTrip = (
  json: string,
  sourceFilename: string,
  format: ScenarioFormat,
  expected: readonly StoryLine[],
): void => {
  const rendered = parseStoryContent(json, {
    filename: sourceFilename,
    mergeConsecutiveTextLines: false,
  }).lines;
  if (
    rendered.length !== expected.length ||
    rendered.some((line, index) =>
      comparableRoundTripLine(line, format) !==
      comparableRoundTripLine(expected[index], format))
  ) {
    throw new ScenarioJsonDownloadError(
      '编辑 JSON 回生后与校对行不一致，已停止下载。',
    );
  }
};

'''
    replace_once(DOWNLOAD, old_round_trip, new_round_trip)
    replace_once(
        DOWNLOAD,
        "    assertJsonRoundTrip(result.json, options.sourceFilename, options.editedLines);\n",
        "    assertJsonRoundTrip(\n"
        "      result.json,\n"
        "      options.sourceFilename,\n"
        "      parsed.format,\n"
        "      options.editedLines,\n"
        "    );\n",
    )

    replace_once(
        SELECTION_TEST,
        "  const mapped = mapAggregateEditsToScenarioJson({\n"
        "    sourceJson,\n"
        "    sourceFilename: filename,\n"
        "    aggregateSourceBaselineLines: jpLines,\n"
        "    aggregateEditingBaselineLines: cnLines,\n"
        "    aggregateEditedLines: edited,\n"
        "  });\n",
        "  const mapped = mapAggregateEditsToScenarioJson({\n"
        "    sourceJson,\n"
        "    sourceFilename: filename,\n"
        "    aggregateSourceBaselineLines: jpLines,\n"
        "    aggregateEditingBaselineLines: cnLines,\n"
        "    aggregateEditedLines: edited,\n"
        "  });\n"
        "  assert.deepEqual(\n"
        "    mapped.editedLines\n"
        "      .filter(line => !line.isHeader)\n"
        "      .map(line => line.speaker),\n"
        "    ['鹿目圆', '鹿目圆'],\n"
        "  );\n",
    )
    replace_once(
        SELECTION_TEST,
        "  assert.equal(rows[1].cellList[2], '你好');\n"
        "  assert.equal(rows[2].cellList[2], '下次见');\n",
        "  assert.equal(rows[0].cellList[1], '鹿目圆');\n"
        "  assert.equal(rows[1].cellList[1], '鹿目圆');\n"
        "  assert.equal(rows[2].cellList[1], '鹿目圆');\n"
        "  assert.equal(rows[1].cellList[2], '你好');\n"
        "  assert.equal(rows[2].cellList[2], '下次见');\n",
    )
    replace_once(
        SELECTION_TEST,
        "  assert.equal(imported[1].text, '中文一');\n"
        "  assert.equal(imported[2].text, '中文二');\n",
        "  assert.equal(imported[1].speaker, '鹿目圆');\n"
        "  assert.equal(imported[2].speaker, '鹿目圆');\n"
        "  assert.equal(imported[1].text, '中文一');\n"
        "  assert.equal(imported[2].text, '中文二');\n",
    )

    print("EXEDRA_EDIT_SPEAKER_ROUNDTRIP_V25_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
