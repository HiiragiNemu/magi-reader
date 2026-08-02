import type { StoryIndexEntry } from './story-index.ts';
import {
  parseStoryContent,
  type StoryFormat,
  type StoryLine,
} from './story-parser.ts';

export type ScenarioJsonSourceOption = {
  key: string;
  filename: string;
  label: string;
  sections: string[];
  jpIndex?: number;
  cnIndex?: number;
};

export type SelectedScenarioJsonEdit = {
  format: Extract<StoryFormat, 'magireco-json' | 'exedra-json'>;
  baselineLines: StoryLine[];
  editedLines: StoryLine[];
};

export class ScenarioJsonSelectionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ScenarioJsonSelectionError';
  }
}

const jsonFilenameFromRepositoryPath = (path: string): string => {
  const filename = path.split('/').at(-1)?.trim() ?? '';
  if (!filename || !/\.json$/iu.test(filename)) {
    throw new ScenarioJsonSelectionError('剧情 JSON 来源文件名无效。');
  }
  return filename;
};

const sourceStem = (filename: string): string =>
  filename.replace(/\.json$/iu, '').toLowerCase();

const headerSectionsForSource = (
  filename: string,
  lines: readonly StoryLine[],
): { sections: string[]; branchCount: number } => {
  const stem = sourceStem(filename);
  const sections: string[] = [];
  let branchCount = 0;
  for (const line of lines) {
    if (!line.isHeader || line.headerSourceId?.toLowerCase() !== stem) {
      continue;
    }
    if (line.headerSection && !sections.includes(line.headerSection)) {
      sections.push(line.headerSection);
    }
    if (line.headerBranch) branchCount += 1;
  }
  return { sections, branchCount };
};

export const buildScenarioJsonSourceOptions = ({
  story,
  cnLines,
  jpLines,
}: {
  story: StoryIndexEntry;
  cnLines: readonly StoryLine[];
  jpLines: readonly StoryLine[];
}): ScenarioJsonSourceOption[] => {
  const options = new Map<string, ScenarioJsonSourceOption>();
  const add = (
    language: 'jp' | 'cn',
    repositoryPath: string,
    index: number,
  ) => {
    const filename = jsonFilenameFromRepositoryPath(repositoryPath);
    const key = filename.toLowerCase();
    const existing = options.get(key);
    if (
      existing &&
      existing[`${language}Index`] !== undefined
    ) {
      throw new ScenarioJsonSelectionError(
        `同一剧情含两个无法区分的 ${filename} 来源。`,
      );
    }
    const candidate = existing ?? {
      key,
      filename,
      label: filename,
      sections: [],
    };
    candidate[`${language}Index`] = index;
    options.set(key, candidate);
  };

  story.json_sources_cn?.forEach((path, index) => add('cn', path, index));
  story.json_sources_jp?.forEach((path, index) => add('jp', path, index));

  const referenceLines = cnLines.length > 0 ? cnLines : jpLines;
  for (const option of options.values()) {
    const { sections, branchCount } = headerSectionsForSource(
      option.filename,
      referenceLines,
    );
    option.sections = sections;
    const sectionLabel = sections.length > 0
      ? `第 ${sections.join('、')} 节`
      : '来源 JSON';
    option.label =
      `${sectionLabel}${branchCount > 0 ? `（${branchCount} 条分支）` : ''}`
      + ` · ${option.filename}`;
  }
  return [...options.values()];
};

const editableStructure = (line: StoryLine): string =>
  JSON.stringify({
    isHeader: Boolean(line.isHeader),
    headerSourceId: line.headerSourceId || '',
    headerSection: line.headerSection || '',
    headerBranch: line.headerBranch || '',
    isChoice: Boolean(line.isChoice),
    choiceTargetId: line.choiceTargetId || '',
    kind: line.kind || '',
    position: line.position || '',
    sourceCommand: line.sourceCommand || '',
    sourceRow: line.sourceRow ?? null,
    sourceSheet: line.sourceSheet || '',
    isScene0: Boolean(line.isScene0),
  });

const assertAggregateEditStructure = (
  baseline: readonly StoryLine[],
  edited: readonly StoryLine[],
): void => {
  if (baseline.length !== edited.length) {
    throw new ScenarioJsonSelectionError(
      `当前编辑稿行数与中文基准不同：${edited.length}/${baseline.length}。`,
    );
  }
  baseline.forEach((line, index) => {
    const candidate = edited[index];
    if (editableStructure(line) !== editableStructure(candidate)) {
      throw new ScenarioJsonSelectionError(
        `当前编辑稿第 ${index + 1} 行的 Section、分支或事件结构发生变化。`,
      );
    }
  });
};

const selectedBodyIndices = (
  lines: readonly StoryLine[],
  sourceFilename: string,
): number[] => {
  const stem = sourceStem(sourceFilename);
  const indices: number[] = [];
  let selected = false;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.isHeader) {
      selected = line.headerSourceId?.toLowerCase() === stem;
      continue;
    }
    if (selected) indices.push(index);
  }
  return indices;
};

const comparableVisibleLine = (line: StoryLine): string =>
  JSON.stringify({
    isChoice: Boolean(line.isChoice),
    speaker: line.speaker,
    text: line.text,
    choiceLabel: line.choiceLabel || '',
    choiceTargetId: line.choiceTargetId || '',
  });

export const mapAggregateEditsToScenarioJson = ({
  sourceJson,
  sourceFilename,
  aggregateSourceBaselineLines,
  aggregateEditingBaselineLines,
  aggregateEditedLines,
}: {
  sourceJson: string;
  sourceFilename: string;
  aggregateSourceBaselineLines: readonly StoryLine[];
  aggregateEditingBaselineLines: readonly StoryLine[];
  aggregateEditedLines: readonly StoryLine[];
}): SelectedScenarioJsonEdit => {
  assertAggregateEditStructure(
    aggregateEditingBaselineLines,
    aggregateEditedLines,
  );
  const parsed = parseStoryContent(sourceJson, {
    filename: sourceFilename,
    mergeConsecutiveTextLines: false,
  });
  if (
    parsed.format !== 'magireco-json' &&
    parsed.format !== 'exedra-json'
  ) {
    throw new ScenarioJsonSelectionError(
      '选中的中文 JSON 不是可播放剧情结构。',
    );
  }

  const sourceBodyIndices = selectedBodyIndices(
    aggregateSourceBaselineLines,
    sourceFilename,
  );
  const editingBodyIndices = selectedBodyIndices(
    aggregateEditingBaselineLines,
    sourceFilename,
  );
  const jsonBodyIndices = parsed.lines.flatMap((line, index) =>
    line.isHeader ? [] : [index]);
  if (sourceBodyIndices.length === 0 || editingBodyIndices.length === 0) {
    throw new ScenarioJsonSelectionError(
      `聚合 TXT 中没有 ${sourceFilename} 对应的 Section。`,
    );
  }
  if (
    sourceBodyIndices.length !== jsonBodyIndices.length ||
    editingBodyIndices.length !== jsonBodyIndices.length
  ) {
    throw new ScenarioJsonSelectionError(
      `聚合 TXT 与 ${sourceFilename} 的未合并事件数量不同：`
      + `${sourceBodyIndices.length}/${editingBodyIndices.length}/`
      + `${jsonBodyIndices.length}。`,
    );
  }

  const editedLines = parsed.lines.map(line => ({ ...line }));
  sourceBodyIndices.forEach((sourceAggregateIndex, offset) => {
    const editingAggregateIndex = editingBodyIndices[offset];
    const jsonIndex = jsonBodyIndices[offset];
    const sourceAggregateBaseline =
      aggregateSourceBaselineLines[sourceAggregateIndex];
    const aggregateEdited =
      aggregateEditedLines[editingAggregateIndex];
    const jsonBaseline = parsed.lines[jsonIndex];
    if (
      comparableVisibleLine(sourceAggregateBaseline) !==
      comparableVisibleLine(jsonBaseline)
    ) {
      throw new ScenarioJsonSelectionError(
        `${sourceFilename} 第 ${offset + 1} 个事件与中文 TXT 基准不一致。`,
      );
    }
    editedLines[jsonIndex] = {
      ...jsonBaseline,
      speaker: aggregateEdited.speaker,
      text: aggregateEdited.text,
      ...(jsonBaseline.isChoice
        ? {
            choiceLabel:
              aggregateEdited.choiceLabel || aggregateEdited.text,
          }
        : {}),
    };
  });

  return {
    format: parsed.format,
    baselineLines: parsed.lines,
    editedLines,
  };
};

export const applyScenarioJsonUploadToAggregate = ({
  sourceJson,
  uploadedJson,
  sourceFilename,
  aggregateEditingBaselineLines,
  aggregateCurrentEditedLines,
}: {
  sourceJson: string;
  uploadedJson: string;
  sourceFilename: string;
  aggregateEditingBaselineLines: readonly StoryLine[];
  aggregateCurrentEditedLines: readonly StoryLine[];
}): StoryLine[] => {
  const source = parseStoryContent(sourceJson, {
    filename: sourceFilename,
    mergeConsecutiveTextLines: false,
  });
  const uploaded = parseStoryContent(uploadedJson, {
    filename: sourceFilename,
    mergeConsecutiveTextLines: false,
  });
  if (
    source.format !== uploaded.format ||
    (source.format !== 'magireco-json' &&
      source.format !== 'exedra-json')
  ) {
    throw new ScenarioJsonSelectionError(
      '上传 JSON 与来源 JSON 的剧情格式不同。',
    );
  }
  if (
    source.lines.length !== uploaded.lines.length ||
    source.lines.some(
      (line, index) =>
        editableStructure(line) !== editableStructure(uploaded.lines[index]),
    )
  ) {
    throw new ScenarioJsonSelectionError(
      '上传 JSON 的事件、动作、位置或分支结构与来源 JSON 不同。',
    );
  }
  const sourceBodyIndices = source.lines.flatMap((line, index) =>
    line.isHeader ? [] : [index]);
  if (sourceBodyIndices.length === 0) {
    throw new ScenarioJsonSelectionError(
      '该 JSON 没有解析器可定位的普通文本事件；语音 JSON 请在网页逐行编辑。',
    );
  }
  const aggregateBodyIndices = selectedBodyIndices(
    aggregateEditingBaselineLines,
    sourceFilename,
  );
  if (aggregateBodyIndices.length !== sourceBodyIndices.length) {
    throw new ScenarioJsonSelectionError(
      `上传 JSON 与聚合 TXT 的未合并事件数量不同：`
      + `${sourceBodyIndices.length}/${aggregateBodyIndices.length}。`,
    );
  }

  const basis =
    aggregateCurrentEditedLines.length ===
    aggregateEditingBaselineLines.length
      ? aggregateCurrentEditedLines
      : aggregateEditingBaselineLines;
  const result = basis.map(line => ({ ...line }));
  aggregateBodyIndices.forEach((aggregateIndex, offset) => {
    const uploadedLine = uploaded.lines[sourceBodyIndices[offset]];
    const current = result[aggregateIndex];
    result[aggregateIndex] = {
      ...current,
      speaker: uploadedLine.speaker,
      text: uploadedLine.text,
      ...(current.isChoice
        ? {
            choiceLabel:
              uploadedLine.choiceLabel || uploadedLine.text,
          }
        : {}),
    };
  });
  return result;
};
