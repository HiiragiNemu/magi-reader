import {
  createUtf8DownloadBlob,
  safeDownloadFilename,
  triggerUtf8Download,
} from './browser-download.ts';
import {
  parseStoryContent,
  type StoryFormat,
  type StoryLine,
} from './story-parser.ts';

type JsonRecord = Record<string, unknown>;
type ScenarioFormat = Extract<StoryFormat, 'magireco-json' | 'exedra-json'>;
type OriginalLanguage = 'jp' | 'cn';

export type ScenarioJsonDownload = {
  filename: string;
  json: string;
  blob: Blob;
  format: ScenarioFormat;
  changedTextFields: number;
};

export class ScenarioJsonDownloadError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ScenarioJsonDownloadError';
  }
}

type MutableStringReference = {
  container: JsonRecord | unknown[];
  key: string | number;
  path: string;
  allowInsert?: boolean;
};

const MAGIRECO_CONTROL_RE =
  /\[(?!text(?:Red|Blue|Yellow|Black):|br\])[^\u005b\u005d\r\n]*\]/giu;
const EXEDRA_TEXT_ACTIONS = new Set([
  'talk',
  'narration',
  'charactertalk',
  'onlytext',
]);
const NARRATION_SPEAKERS = new Set(['', '旁白', 'Narration', 'ナレーション']);

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const asString = (value: unknown): string =>
  typeof value === 'string' || typeof value === 'number'
    ? String(value)
    : '';

const stripLeadingBom = (value: string): string =>
  value.replace(/^\uFEFF+/u, '');

const parseJsonDocument = (raw: string): JsonRecord => {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stripLeadingBom(raw));
  } catch (error) {
    const detail = error instanceof Error ? error.message : '未知错误';
    throw new ScenarioJsonDownloadError(`JSON 解析失败：${detail}`);
  }
  if (!isRecord(parsed)) {
    throw new ScenarioJsonDownloadError('剧情 JSON 顶层必须是对象。');
  }
  return parsed;
};

const serializeJsonDocument = (document: JsonRecord): string =>
  `${JSON.stringify(document, null, 2)}\n`;

const formatFromJson = (
  raw: string,
  sourceFilename: string,
): ScenarioFormat => {
  let result;
  try {
    result = parseStoryContent(raw, {
      filename: sourceFilename,
      mergeConsecutiveTextLines: false,
    });
  } catch (error) {
    throw new ScenarioJsonDownloadError(
      error instanceof Error ? error.message : '剧情 JSON 无法解析。',
    );
  }
  if (result.format !== 'magireco-json' && result.format !== 'exedra-json') {
    throw new ScenarioJsonDownloadError('JSON 不是可播放的 Magia Record 或 Exedra 剧情结构。');
  }
  return result.format;
};

const stableStoryStem = (storyId: string, sourceFilename: string): string => {
  const candidate =
    storyId.trim() ||
    sourceFilename.replace(/\.json$/iu, '').trim() ||
    'story';
  const safe = safeDownloadFilename(candidate, 'story')
    .replace(/\.json$/iu, '')
    .replace(/^[. -]+|[. -]+$/gu, '')
    .slice(0, 160);
  return safe || 'story';
};

export const scenarioJsonFilename = (
  storyId: string,
  variant: OriginalLanguage | 'edited_cn',
  sourceFilename = '',
): string =>
  `${stableStoryStem(storyId, sourceFilename)}_${variant}.json`;

const createResult = (
  document: JsonRecord,
  filename: string,
  format: ScenarioFormat,
  changedTextFields: number,
): ScenarioJsonDownload => {
  const json = serializeJsonDocument(document);
  return {
    filename,
    json,
    blob: createUtf8DownloadBlob(json, filename),
    format,
    changedTextFields,
  };
};

export const createOriginalScenarioJsonDownload = (options: {
  sourceJson: string;
  sourceFilename: string;
  storyId: string;
  language: OriginalLanguage;
}): ScenarioJsonDownload => {
  const format = formatFromJson(options.sourceJson, options.sourceFilename);
  const document = parseJsonDocument(options.sourceJson);
  return createResult(
    document,
    scenarioJsonFilename(
      options.storyId,
      options.language,
      options.sourceFilename,
    ),
    format,
    0,
  );
};

const lineStructure = (line: StoryLine): string =>
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
    sourceFormat: line.sourceFormat || '',
    sourceRow: line.sourceRow ?? null,
    sourceSheet: line.sourceSheet || '',
    isScene0: Boolean(line.isScene0),
  });

const requireEditedLineStructure = (
  original: readonly StoryLine[],
  edited: readonly StoryLine[],
): void => {
  if (original.length !== edited.length) {
    throw new ScenarioJsonDownloadError(
      `编辑结构不匹配：JSON=${original.length} 行，编辑稿=${edited.length} 行。`,
    );
  }
  original.forEach((source, index) => {
    const candidate = edited[index];
    if (lineStructure(source) !== lineStructure(candidate)) {
      throw new ScenarioJsonDownloadError(
        `第 ${index + 1} 行的动作、位置、分支或来源结构发生变化。`,
      );
    }
    if (source.isHeader && (
      source.text !== candidate.text ||
      source.speaker !== candidate.speaker
    )) {
      throw new ScenarioJsonDownloadError(
        `第 ${index + 1} 行的 Section/Branch 标题不可修改。`,
      );
    }
    if (!source.isHeader) {
      if (!candidate.text || candidate.text !== candidate.text.trim()) {
        throw new ScenarioJsonDownloadError(
          `第 ${index + 1} 行正文为空或含不可保真的首尾空白。`,
        );
      }
      if (!candidate.speaker || candidate.speaker !== candidate.speaker.trim()) {
        throw new ScenarioJsonDownloadError(
          `第 ${index + 1} 行说话人为空或含首尾空白。`,
        );
      }
    }
  });
};

const cleanMagirecoText = (value: unknown): string => {
  let text = asString(value)
    .replace(/\r\n?/gu, '\n')
    .replace(/@/gu, '\n')
    .replace(/\[br\]/giu, '\n')
    .replace(/[「『]textBlack:/gu, '[textBlack:');
  for (const color of ['Red', 'Blue', 'Yellow', 'Black']) {
    text = text.replace(
      new RegExp(`\\[text${color}:([\\s\\S]*?)\\]`, 'giu'),
      `<${color.toLowerCase()}>$1</${color.toLowerCase()}>`,
    );
  }
  return text
    .replace(/\[(?!\/?(?:red|blue|yellow|black)\b)[^\u005d]*\]/giu, '')
    .trim();
};

const encodeMagirecoColors = (value: string): string => {
  let result = value;
  for (const [tag, source] of [
    ['red', 'Red'],
    ['blue', 'Blue'],
    ['yellow', 'Yellow'],
    ['black', 'Black'],
  ] as const) {
    const pattern = new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`, 'giu');
    while (pattern.test(result)) {
      result = result.replace(pattern, `[text${source}:$1]`);
    }
  }
  if (/<\/?[A-Za-z][^>]*>/u.test(result)) {
    throw new ScenarioJsonDownloadError('编辑正文含不受支持的 HTML/XML 标签。');
  }
  return result;
};

const controlTokens = (value: string): string[] =>
  Array.from(value.matchAll(new RegExp(MAGIRECO_CONTROL_RE.source, 'giu')),
    match => match[0]);

const mergeMagirecoVisibleText = (
  original: string,
  reviewed: string,
): string => {
  if (/[@\r\u0000]/u.test(reviewed)) {
    throw new ScenarioJsonDownloadError('Magia Record 编辑正文不得直接包含 @、回车或 NUL。');
  }
  if (cleanMagirecoText(original) === reviewed) return original;

  const originalSegments = cleanMagirecoText(original).split('\n');
  const desiredSegments = reviewed.split('\n');
  const commandsBySegment = Array.from(
    { length: Math.max(1, desiredSegments.length) },
    () => [] as string[],
  );
  const matcher = new RegExp(MAGIRECO_CONTROL_RE.source, 'giu');
  for (const match of original.matchAll(matcher)) {
    const prefix = cleanMagirecoText(original.slice(0, match.index));
    const sourceSegment = prefix.split('\n').length - 1;
    const targetSegment = originalSegments.length <= 1
      ? 0
      : Math.round(
          sourceSegment *
          (desiredSegments.length - 1) /
          (originalSegments.length - 1),
        );
    commandsBySegment[
      Math.min(targetSegment, commandsBySegment.length - 1)
    ].push(match[0]);
  }

  const result = desiredSegments
    .map((segment, index) =>
      `${commandsBySegment[index].join('')}${encodeMagirecoColors(segment)}`)
    .join('@');
  if (cleanMagirecoText(result) !== reviewed) {
    throw new ScenarioJsonDownloadError('Magia Record 正文编码后无法无损回生。');
  }
  if (JSON.stringify(controlTokens(original)) !== JSON.stringify(controlTokens(result))) {
    throw new ScenarioJsonDownloadError('Magia Record 播放控制指令发生变化。');
  }
  return result;
};

const jsonPointerPart = (value: string | number): string =>
  String(value).replace(/~/gu, '~0').replace(/\//gu, '~1');

const appendPath = (base: string, value: string | number): string =>
  `${base}/${jsonPointerPart(value)}`;

const setReference = (
  reference: MutableStringReference,
  next: string,
  allowedPaths: Set<string>,
): number => {
  const current = reference.container[reference.key as never];
  if (typeof current !== 'string' && !(reference.allowInsert && current === undefined)) {
    throw new ScenarioJsonDownloadError(
      `可编辑 JSON 字段不是字符串：${reference.path}`,
    );
  }
  allowedPaths.add(reference.path);
  if (current === next) return 0;
  (reference.container as Record<string | number, unknown>)[reference.key] = next;
  return 1;
};

const assertOnlyAllowedStringsChanged = (
  before: unknown,
  after: unknown,
  allowedPaths: ReadonlySet<string>,
  path = '',
): void => {
  if (allowedPaths.has(path)) {
    if (
      typeof after !== 'string' ||
      (typeof before !== 'string' && before !== undefined)
    ) {
      throw new ScenarioJsonDownloadError(`可编辑字段类型发生变化：${path}`);
    }
    return;
  }
  if (Array.isArray(before) || Array.isArray(after)) {
    if (!Array.isArray(before) || !Array.isArray(after) || before.length !== after.length) {
      throw new ScenarioJsonDownloadError(`JSON 数组结构发生变化：${path || '/'}`);
    }
    before.forEach((value, index) =>
      assertOnlyAllowedStringsChanged(
        value,
        after[index],
        allowedPaths,
        appendPath(path, index),
      ));
    return;
  }
  if (isRecord(before) || isRecord(after)) {
    if (!isRecord(before) || !isRecord(after)) {
      throw new ScenarioJsonDownloadError(`JSON schema 发生变化：${path || '/'}`);
    }
    const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort();
    keys.forEach(key => {
      const childPath = appendPath(path, key);
      const beforeOwn = Object.hasOwn(before, key);
      const afterOwn = Object.hasOwn(after, key);
      if (!beforeOwn || !afterOwn) {
        if (
          !beforeOwn &&
          afterOwn &&
          allowedPaths.has(childPath) &&
          typeof after[key] === 'string'
        ) {
          return;
        }
        throw new ScenarioJsonDownloadError(`JSON 字段集合发生变化：${path || '/'}`);
      }
      assertOnlyAllowedStringsChanged(
        before[key],
        after[key],
        allowedPaths,
        childPath,
      );
    });
    return;
  }
  if (!Object.is(before, after)) {
    throw new ScenarioJsonDownloadError(`非文本播放字段发生变化：${path || '/'}`);
  }
};

const magirecoStoryGroups = (
  document: JsonRecord,
): Map<string, { group: unknown[]; path: string }> => {
  const story = document.story;
  if (Array.isArray(story)) {
    return new Map([['group_1', { group: story, path: '/story' }]]);
  }
  if (!isRecord(story)) {
    throw new ScenarioJsonDownloadError('Magia Record JSON 缺少 story/group。');
  }
  const groups = new Map<string, { group: unknown[]; path: string }>();
  for (const [key, value] of Object.entries(story)) {
    if (key.startsWith('group_') && Array.isArray(value)) {
      groups.set(key, {
        group: value,
        path: appendPath('/story', key),
      });
    }
  }
  if (groups.size === 0) {
    throw new ScenarioJsonDownloadError('Magia Record JSON 不含可编辑分支。');
  }
  return groups;
};

const exactMagirecoTextKey = (
  item: JsonRecord,
  line: StoryLine,
): string => {
  if (line.sourceCommand === 'fnarration') {
    return ['Fnarration', 'fnarration', 'progressFnarration']
      .find(key => item[key] !== null && item[key] !== undefined) || '';
  }
  if (line.sourceCommand === 'narration') {
    return ['narration', 'progressNarration']
      .find(key => item[key] !== null && item[key] !== undefined) || '';
  }
  return line.sourceCommand || '';
};

const magirecoNameKey = (textKey: string): string => {
  if (['Fnarration', 'fnarration', 'progressFnarration'].includes(textKey)) {
    return 'nameFnarration';
  }
  if (['narration', 'progressNarration'].includes(textKey)) {
    return 'nameNarration';
  }
  if (textKey === 'text') return 'name';
  const match = textKey.match(/^text(Av)?(Left|Center|Right)$/u);
  return match ? `name${match[1] || ''}${match[2]}` : '';
};

const editableChoiceLabel = (line: StoryLine): string => {
  const label = (line.choiceLabel || line.text)
    .replace(/^【|】$/gu, '')
    .trim();
  if (!label) {
    throw new ScenarioJsonDownloadError('选项正文不得为空。');
  }
  return label;
};

const applyMagirecoEdits = (
  document: JsonRecord,
  originalLines: readonly StoryLine[],
  editedLines: readonly StoryLine[],
  allowedPaths: Set<string>,
): number => {
  const groups = magirecoStoryGroups(document);
  let currentGroup: { group: unknown[]; path: string } | undefined;
  let changed = 0;
  let editableCount = 0;

  originalLines.forEach((sourceLine, index) => {
    const editedLine = editedLines[index];
    if (sourceLine.isHeader) {
      const groupName = `group_${sourceLine.headerBranch || '1'}`;
      currentGroup = groups.get(groupName);
      if (!currentGroup) {
        throw new ScenarioJsonDownloadError(`JSON 缺少标题对应分支：${groupName}`);
      }
      return;
    }
    editableCount += 1;
    if (!currentGroup || !sourceLine.sourceRow) {
      throw new ScenarioJsonDownloadError(`第 ${index + 1} 行缺少分支或来源行定位。`);
    }
    const itemIndex = sourceLine.sourceRow - 1;
    const item = currentGroup.group[itemIndex];
    if (!isRecord(item)) {
      throw new ScenarioJsonDownloadError(`第 ${index + 1} 行对应的 JSON 事件无效。`);
    }
    const itemPath = appendPath(currentGroup.path, itemIndex);

    if (sourceLine.isChoice) {
      if (editedLine.speaker !== sourceLine.speaker) {
        throw new ScenarioJsonDownloadError('选项说话人和分支身份不可修改。');
      }
      const selections = item.select;
      if (!Array.isArray(selections)) {
        throw new ScenarioJsonDownloadError('选项行对应 JSON 不含 select。');
      }
      const matches = selections
        .map((value, selectionIndex) => ({ value, selectionIndex }))
        .filter(({ value }) =>
          isRecord(value) &&
          asString(value.group).replace(/^group_?/iu, '') ===
            (sourceLine.choiceTargetId || '') &&
          cleanMagirecoText(value.textSelect) ===
            (sourceLine.choiceLabel || sourceLine.text.replace(/^【|】$/gu, '')));
      if (matches.length !== 1 || !isRecord(matches[0].value)) {
        throw new ScenarioJsonDownloadError('选项无法唯一映射到原始 JSON。');
      }
      const reference: MutableStringReference = {
        container: matches[0].value,
        key: 'textSelect',
        path: appendPath(
          appendPath(appendPath(itemPath, 'select'), matches[0].selectionIndex),
          'textSelect',
        ),
      };
      changed += setReference(
        reference,
        mergeMagirecoVisibleText(
          asString(matches[0].value.textSelect),
          editableChoiceLabel(editedLine),
        ),
        allowedPaths,
      );
      return;
    }

    const textKey = exactMagirecoTextKey(item, sourceLine);
    if (!textKey || typeof item[textKey] !== 'string') {
      throw new ScenarioJsonDownloadError(
        `第 ${index + 1} 行无法映射到原始 Magia Record 文本字段。`,
      );
    }
    changed += setReference(
      {
        container: item,
        key: textKey,
        path: appendPath(itemPath, textKey),
      },
      mergeMagirecoVisibleText(item[textKey], editedLine.text),
      allowedPaths,
    );

    if (editedLine.speaker !== sourceLine.speaker) {
      const nameKey = magirecoNameKey(textKey);
      if (!nameKey || typeof item[nameKey] !== 'string') {
        throw new ScenarioJsonDownloadError(
          `第 ${index + 1} 行说话人来自上下文，不能在不改变 schema 的情况下写回。`,
        );
      }
      const nextSpeaker =
        sourceLine.kind !== 'dialogue' &&
        NARRATION_SPEAKERS.has(editedLine.speaker)
          ? ''
          : editedLine.speaker;
      changed += setReference(
        {
          container: item,
          key: nameKey,
          path: appendPath(itemPath, nameKey),
        },
        nextSpeaker,
        allowedPaths,
      );
    }
  });

  if (editableCount === 0) {
    throw new ScenarioJsonDownloadError('该 Magia Record JSON 没有可编辑文本事件。');
  }
  return changed;
};

type ExedraEvent = {
  references: MutableStringReference[];
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
      events.push({
        references: [{
          container: rowValue.cellList,
          key: commentIndex,
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
            commentIndex,
          ),
        }],
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
      event.references.push(...events[eventIndex].references);
    });
  });

  return unique.flatMap(item => item.events);
};

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
  let changed = 0;
  events.forEach((event, index) => {
    const source = originalLines[index];
    const edited = editedLines[index];
    if (edited.speaker !== source.speaker) {
      throw new ScenarioJsonDownloadError(
        `第 ${index + 1} 行 Exedra 说话人身份不可修改。`,
      );
    }
    event.references.forEach(reference => {
      changed += setReference(
        reference,
        edited.text,
        allowedPaths,
      );
    });
  });
  if (events.length === 0) {
    throw new ScenarioJsonDownloadError('该 Exedra JSON 没有可编辑文本事件。');
  }
  return changed;
};

type GeneralVoiceGroup = {
  groupName: string;
  references: MutableStringReference[][];
};

const naturalGroupNumber = (value: string): number => {
  const match = value.match(/^group_(\d+)$/u);
  return match ? Number(match[1]) : Number.NaN;
};

const generalVoiceGroups = (document: JsonRecord): GeneralVoiceGroup[] => {
  if (!isRecord(document.story)) {
    throw new ScenarioJsonDownloadError('魔法纪录语音 JSON 缺少 story 分组。');
  }
  const groups = Object.entries(document.story)
    .filter(([key, value]) =>
      Number.isFinite(naturalGroupNumber(key)) && Array.isArray(value))
    .sort(([left], [right]) =>
      naturalGroupNumber(left) - naturalGroupNumber(right));
  if (groups.length === 0) {
    throw new ScenarioJsonDownloadError('魔法纪录语音 JSON 不含规范 group 分组。');
  }

  return groups.map(([groupName, turns]) => {
    const voiceReferences: MutableStringReference[] = [];
    const voiceIds = new Set<string>();
    const voiceTexts = new Set<string>();
    const continuationReferences = new Map<string, MutableStringReference[]>();
    (turns as unknown[]).forEach((turnValue, turnIndex) => {
      if (!isRecord(turnValue) || !Array.isArray(turnValue.chara)) return;
      turnValue.chara.forEach((charaValue, charaIndex) => {
        if (!isRecord(charaValue)) return;
        const reference: MutableStringReference = {
          container: charaValue,
          key: 'textHome',
          path: appendPath(
            appendPath(
              appendPath(
                appendPath(
                  appendPath('/story', groupName),
                  turnIndex,
                ),
                'chara',
              ),
              charaIndex,
            ),
            'textHome',
          ),
        };
        const voice = typeof charaValue.voice === 'string'
          ? charaValue.voice.trim()
          : '';
        const textHome = typeof charaValue.textHome === 'string'
          ? charaValue.textHome.trim()
          : '';
        if (voice) {
          voiceIds.add(voice);
          voiceReferences.push({ ...reference, allowInsert: true });
          if (textHome) voiceTexts.add(textHome);
        } else if (textHome) {
          const continuation = continuationReferences.get(textHome) || [];
          continuation.push(reference);
          continuationReferences.set(textHome, continuation);
        }
      });
    });
    if (voiceIds.size > 1) {
      throw new ScenarioJsonDownloadError(
        `${groupName} 同一语音组含多个不同语音资源。`,
      );
    }
    if (voiceTexts.size > 1) {
      throw new ScenarioJsonDownloadError(
        `${groupName} 重复语音角色的 textHome 内容冲突。`,
      );
    }
    const references: MutableStringReference[][] = [];
    // Repeated voice entries drive multiple Live2D mouths but represent one
    // subtitle.  Keep the logical row even when textHome is absent so the
    // editor can insert it into every voice-bearing character atomically.
    if (voiceReferences.length > 0) references.push(voiceReferences);
    references.push(...continuationReferences.values());
    return { groupName, references };
  });
};

const hasGeneralVoicePlaybackShape = (document: JsonRecord): boolean => {
  if (!isRecord(document.story)) return false;
  return Object.values(document.story).some(groupValue =>
    Array.isArray(groupValue) && groupValue.some(turnValue =>
      isRecord(turnValue) && Array.isArray(turnValue.chara) &&
      turnValue.chara.some(charaValue =>
        isRecord(charaValue) &&
        typeof charaValue.voice === 'string' &&
        charaValue.voice.trim().length > 0,
      ),
    ),
  );
};

const voiceLineParts = (
  line: StoryLine,
  options: { allowEmpty?: boolean } = {},
): { prefix: string; body: string } => {
  const match = line.text.match(/^(【[^】\r\n]{1,512}】)(.*)$/u);
  if (!match || (!options.allowEmpty && !match[2].trim())) {
    throw new ScenarioJsonDownloadError('语音资源标签或可编辑正文无效。');
  }
  return { prefix: match[1], body: match[2].trim() };
};

const linesBySection = (
  lines: readonly StoryLine[],
): Array<{ header: StoryLine; body: StoryLine[] }> => {
  const sections: Array<{ header: StoryLine; body: StoryLine[] }> = [];
  for (const line of lines) {
    if (line.isHeader) {
      sections.push({ header: line, body: [] });
      continue;
    }
    const current = sections.at(-1);
    if (!current) {
      throw new ScenarioJsonDownloadError('语音编辑稿在首个 Section 前含正文。');
    }
    current.body.push(line);
  }
  return sections;
};

const applyGeneralVoiceEdits = (
  document: JsonRecord,
  baselineLines: readonly StoryLine[],
  editedLines: readonly StoryLine[],
  allowedPaths: Set<string>,
): number => {
  requireEditedLineStructure(baselineLines, editedLines);
  const groups = generalVoiceGroups(document);
  const baselineSections = linesBySection(baselineLines);
  const editedSections = linesBySection(editedLines);
  if (
    baselineSections.length !== groups.length ||
    editedSections.length !== groups.length
  ) {
    throw new ScenarioJsonDownloadError(
      `语音 JSON/Section 数量不同：JSON=${groups.length}，` +
      `基准=${baselineSections.length}，编辑稿=${editedSections.length}。`,
    );
  }

  let changed = 0;
  groups.forEach((group, sectionIndex) => {
    const baseline = baselineSections[sectionIndex];
    const edited = editedSections[sectionIndex];
    const expectedSection = String(sectionIndex + 1);
    if (
      baseline.header.headerSection !== expectedSection ||
      edited.header.headerSection !== expectedSection
    ) {
      throw new ScenarioJsonDownloadError(
        `语音 Section ${sectionIndex + 1} 编号或顺序发生变化。`,
      );
    }
    if (group.references.length === 0) {
      if (
        baseline.body.length !== edited.body.length ||
        baseline.body.some((line, index) =>
          comparableLine(line) !== comparableLine(edited.body[index]))
      ) {
        throw new ScenarioJsonDownloadError(
          `${group.groupName} 没有 textHome，资源占位行不可修改。`,
        );
      }
      return;
    }
    if (
      baseline.body.length !== group.references.length ||
      edited.body.length !== group.references.length
    ) {
      throw new ScenarioJsonDownloadError(
        `${group.groupName} 的 textHome/TXT 行数不同：` +
        `${group.references.length}/${baseline.body.length}/${edited.body.length}。`,
      );
    }

    group.references.forEach((referenceGroup, lineIndex) => {
      const sourceLine = baseline.body[lineIndex];
      const editedLine = edited.body[lineIndex];
      const sourceParts = voiceLineParts(sourceLine, { allowEmpty: true });
      const editedParts = voiceLineParts(editedLine);
      if (
        sourceLine.speaker !== editedLine.speaker ||
        sourceParts.prefix !== editedParts.prefix
      ) {
        throw new ScenarioJsonDownloadError(
          `${group.groupName} 的角色名、语音资源或时长标签不可修改。`,
        );
      }
      const encoded = editedParts.body
        .replace(/\r\n?|\n/gu, '@')
        .replace(/／/gu, '@');
      if (!encoded.trim()) {
        throw new ScenarioJsonDownloadError(`${group.groupName} 的语音正文为空。`);
      }
      referenceGroup.forEach(reference => {
        changed += setReference(reference, encoded, allowedPaths);
      });
      const rendered = encoded
        .replace(/@/gu, '／')
        .trim();
      if (rendered !== editedParts.body) {
        throw new ScenarioJsonDownloadError(
          `${group.groupName} 的 textHome 无法无损回生。`,
        );
      }
    });
  });
  return changed;
};

const comparableLine = (line: StoryLine): string =>
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

export const createEditedScenarioJsonDownload = (options: {
  sourceJson: string;
  sourceFilename: string;
  storyId: string;
  editedLines: readonly StoryLine[];
  baselineLines?: readonly StoryLine[];
}): ScenarioJsonDownload => {
  const originalDocument = parseJsonDocument(options.sourceJson);
  const document = parseJsonDocument(options.sourceJson);
  const parsed = parseStoryContent(options.sourceJson, {
    filename: options.sourceFilename,
    mergeConsecutiveTextLines: false,
  });
  if (parsed.format !== 'magireco-json' && parsed.format !== 'exedra-json') {
    throw new ScenarioJsonDownloadError('只有可播放剧情 JSON 能生成编辑版本。');
  }
  const allowedPaths = new Set<string>();
  const generalVoice =
    parsed.format === 'magireco-json' &&
    hasGeneralVoicePlaybackShape(document) &&
    (
      options.baselineLines !== undefined ||
      parsed.lines.every(line => line.isHeader)
    );
  if (generalVoice && !options.baselineLines) {
    throw new ScenarioJsonDownloadError(
      '该 Magia Record JSON 没有解析器可定位的普通文本事件；' +
      '语音 JSON 需要提供未合并的 baselineLines。',
    );
  }
  if (!generalVoice) {
    requireEditedLineStructure(parsed.lines, options.editedLines);
  }
  const changedTextFields = generalVoice
    ? applyGeneralVoiceEdits(
        document,
        options.baselineLines || [],
        options.editedLines,
        allowedPaths,
      )
    : parsed.format === 'magireco-json'
      ? applyMagirecoEdits(
          document,
          parsed.lines,
          options.editedLines,
          allowedPaths,
        )
      : applyExedraEdits(
        document,
        parsed.lines,
        options.editedLines,
        allowedPaths,
      );
  assertOnlyAllowedStringsChanged(originalDocument, document, allowedPaths);

  const filename = scenarioJsonFilename(
    options.storyId,
    'edited_cn',
    options.sourceFilename,
  );
  const result = createResult(
    document,
    filename,
    parsed.format,
    changedTextFields,
  );
  if (!generalVoice) {
    assertJsonRoundTrip(result.json, options.sourceFilename, options.editedLines);
  }
  return result;
};

export const triggerScenarioJsonDownload = (
  download: Pick<ScenarioJsonDownload, 'filename' | 'json'>,
): void => {
  triggerUtf8Download(download.json, download.filename);
};
