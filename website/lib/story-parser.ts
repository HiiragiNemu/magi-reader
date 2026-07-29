import {
  extractExedraVoiceId,
  extractMagirecoVoiceId,
} from './audio/voice-cue.ts';

export type StoryLineKind = 'dialogue' | 'narration' | 'fnarration';
export type StoryLinePosition = 'left' | 'center' | 'right';
export type StoryFormat =
  | 'plain-text'
  | 'scene0-text'
  | 'magireco-json'
  | 'exedra-json'
  | 'generic-json';

export type StoryLine = {
  speaker: string;
  text: string;
  kind?: StoryLineKind;
  position?: StoryLinePosition;
  sourceCommand?: string;
  sourceFormat?: StoryFormat;
  sourceRow?: number;
  sourceSheet?: string;
  audioCueId?: string;
  isScene0?: boolean;
  isHeader?: boolean;
  headerId?: string;
  headerSourceId?: string;
  headerSection?: string;
  headerBranch?: string;
  isChoice?: boolean;
  choiceLabel?: string;
  choiceTargetId?: string;
};

export type StoryParseResult = {
  lines: StoryLine[];
  format: StoryFormat;
  title?: string;
  warnings: string[];
};

export type StoryParserOptions = {
  filename?: string;
  mergeConsecutiveTextLines?: boolean;
};

export type AlignedStoryLine = {
  cn?: StoryLine;
  jp?: StoryLine;
};

const SCENE0_LINE_PREFIX = '@S0\t';
const SPEAKER_SEPARATORS = /[:：﹕︰︓]/;
const DIALOGUE_ACTIONS = new Set([
  'talk',
  'narration',
  'charactertalk',
  'onlytext',
]);

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const asArray = (value: unknown): unknown[] => Array.isArray(value) ? value : [];

const asString = (value: unknown): string =>
  typeof value === 'string' || typeof value === 'number'
    ? String(value)
    : '';

const normalizeNewlines = (value: string): string =>
  value
    .replace(/^\uFEFF/, '')
    .replace(/\r\n?/g, '\n')
    .replace(/\0/g, '');

const naturalParts = (value: string): Array<string | number> =>
  value.split(/(\d+)/).filter(Boolean).map(part => /^\d+$/.test(part) ? Number(part) : part);

const naturalCompare = (left: string, right: string): number => {
  const leftParts = naturalParts(left);
  const rightParts = naturalParts(right);
  const length = Math.max(leftParts.length, rightParts.length);

  for (let index = 0; index < length; index++) {
    const leftPart = leftParts[index];
    const rightPart = rightParts[index];
    if (leftPart === undefined) return -1;
    if (rightPart === undefined) return 1;
    if (leftPart === rightPart) continue;
    if (typeof leftPart === 'number' && typeof rightPart === 'number') {
      return leftPart - rightPart;
    }
    return String(leftPart).localeCompare(String(rightPart));
  }

  return 0;
};

const stableHash = (value: string): string => {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index++) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(36);
};

const safeAnchorToken = (value: string): string => {
  const trimmed = value.trim();
  const cleaned = trimmed.replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^-+|-+$/g, '');
  if (cleaned && cleaned === trimmed) return cleaned;
  return `${cleaned || 'source'}-${stableHash(trimmed)}`;
};

export const makeSectionAnchorId = (
  sourceId: string,
  section: string,
  branch?: string,
): string => {
  const source = safeAnchorToken(sourceId || 'story');
  const sectionToken = safeAnchorToken(section || 'unknown');
  return `sec-${source}-${sectionToken}${branch ? `-branch-${safeAnchorToken(branch)}` : ''}`;
};

const normalizePosition = (value: unknown): StoryLinePosition | undefined => {
  const normalized = asString(value).trim().toLowerCase();
  if (normalized.includes('left')) return 'left';
  if (normalized.includes('right')) return 'right';
  if (normalized.includes('center') || normalized.includes('centre')) return 'center';
  return undefined;
};

const createHeaderLine = (line: string, index: number): StoryLine => {
  const headerText = line.replace(/---/g, '').trim();
  const sourceFilename =
    headerText.match(/Source:\s*(.+?\.[A-Za-z0-9]+)\s*\)\s*$/i)?.[1] ??
    headerText.match(/(?:Start|End):\s*(.+?\.[A-Za-z0-9]+)(?:\s|$)/i)?.[1] ??
    '';
  const sectionMatch = headerText.match(/Section\s*(\d+)/i);
  const branchMatch = headerText.match(/(?:Branch|group_?)\s*_?\s*(\d+)/i);
  const sourceId = sourceFilename.trim().replace(/\.[A-Za-z0-9]+$/i, '');
  const section = sectionMatch?.[1] ?? '';
  const branch = branchMatch?.[1] ?? '';
  const fallback = `header-${safeAnchorToken(headerText || 'section')}-${index}`;

  return {
    speaker: '',
    text: line,
    isHeader: true,
    headerId: sourceId && section
      ? makeSectionAnchorId(sourceId, section, branch || undefined)
      : fallback,
    headerSourceId: sourceId || undefined,
    headerSection: section || undefined,
    headerBranch: branch || undefined,
    sourceFormat: 'plain-text',
  };
};

const parseScene0Line = (
  line: string,
  warnings: string[],
  lineNumber: number,
): StoryLine | null => {
  if (!line.startsWith(SCENE0_LINE_PREFIX)) return null;

  try {
    const parsed: unknown = JSON.parse(line.slice(SCENE0_LINE_PREFIX.length));
    if (!isRecord(parsed)) throw new Error('payload is not an object');

    const text = normalizeNewlines(asString(parsed.text).replace(/\\n/g, '\n')).trim();
    if (!text) return null;

    const kindValue = asString(parsed.kind).toLowerCase();
    const kind: StoryLineKind =
      kindValue === 'fnarration'
        ? 'fnarration'
        : kindValue === 'narration'
          ? 'narration'
          : 'dialogue';

    return {
      speaker: asString(parsed.speaker).trim() || '旁白',
      text,
      kind,
      position: normalizePosition(parsed.position),
      sourceCommand: asString(parsed.command).trim() || undefined,
      sourceFormat: 'scene0-text',
      sourceRow: lineNumber,
      isScene0: true,
    };
  } catch {
    warnings.push(`第 ${lineNumber} 行的 @S0 数据无效，已按普通文本保留。`);
    return null;
  }
};

const mergeConsecutiveSpeakerLines = (
  lines: StoryLine[],
  preserveScene0Boundaries = false,
): StoryLine[] => {
  const merged: StoryLine[] = [];

  for (const current of lines) {
    const previous = merged.at(-1);
    if (
      previous &&
      !previous.isHeader &&
      !previous.isChoice &&
      !current.isHeader &&
      !current.isChoice &&
      (!preserveScene0Boundaries || (!previous.isScene0 && !current.isScene0)) &&
      previous.speaker === current.speaker
    ) {
      previous.text = previous.text
        ? `${previous.text}\n${current.text}`
        : current.text;
    } else {
      merged.push({ ...current });
    }
  }

  return merged;
};

const applySpeakerBlockMerging = (
  result: StoryParseResult,
  options: StoryParserOptions,
  preserveScene0Boundaries = false,
): StoryParseResult =>
  (options.mergeConsecutiveTextLines ?? true)
    ? {
        ...result,
        lines: mergeConsecutiveSpeakerLines(
          result.lines,
          preserveScene0Boundaries,
        ),
      }
    : result;

const parsePlainText = (
  raw: string,
  options: StoryParserOptions,
): StoryParseResult => {
  const warnings: string[] = [];
  const parsed: StoryLine[] = [];
  let sawScene0 = false;
  let currentHeaderAudioCueId: string | undefined;

  normalizeNewlines(raw).split('\n').forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (!line) return;

    if (line.startsWith('---')) {
      const header = createHeaderLine(line, index);
      currentHeaderAudioCueId =
        extractExedraVoiceId(header.headerSourceId || '') || undefined;
      parsed.push(header);
      return;
    }

    const choiceMatch = line.match(/^(?:选项|選択肢|Choice)\s*[:：]\s*【?(.+?)】?\s*(?:→|->)\s*(\S+)/i);
    if (choiceMatch) {
      const target = choiceMatch[2];
      parsed.push({
        speaker: '选项',
        text: `【${choiceMatch[1]}】`,
        isChoice: true,
        choiceLabel: choiceMatch[1],
        choiceTargetId: target.replace(/^group_?/i, ''),
        sourceFormat: 'plain-text',
        sourceRow: index + 1,
      });
      return;
    }

    const scene0Line = parseScene0Line(line, warnings, index + 1);
    if (scene0Line) {
      sawScene0 = true;
      const audioCueId =
        extractMagirecoVoiceId(line) || currentHeaderAudioCueId;
      currentHeaderAudioCueId = undefined;
      parsed.push({
        ...scene0Line,
        audioCueId,
      });
      return;
    }

    const audioCueId =
      extractMagirecoVoiceId(line) || currentHeaderAudioCueId;
    currentHeaderAudioCueId = undefined;

    const separatorIndex = line.search(SPEAKER_SEPARATORS);
    const possibleSpeaker = separatorIndex > 0 ? line.slice(0, separatorIndex).trim() : '';
    const isSpeakerLine =
      separatorIndex > 0 &&
      separatorIndex <= 64 &&
      !line.startsWith('[') &&
      !/^(?:https?|file|data)$/i.test(possibleSpeaker) &&
      !/^\d+$/.test(possibleSpeaker) &&
      !/^(?:第\s*\d+\s*[话話章章节節回幕]|(?:chapter|episode)\s*\d+)$/i.test(possibleSpeaker) &&
      !/[<>{}]/.test(possibleSpeaker);

    if (isSpeakerLine) {
      const parsedSpeaker = possibleSpeaker.replace(/\s+/g, '') || '旁白';
      const isNarration =
        /^(?:Narration|ナレーション|旁白)$/i.test(parsedSpeaker);
      parsed.push({
        speaker: isNarration ? '旁白' : parsedSpeaker,
        text: line.slice(separatorIndex + 1).trim().replace(/\\n/g, '\n'),
        kind: isNarration ? 'narration' : 'dialogue',
        sourceFormat: 'plain-text',
        sourceRow: index + 1,
        audioCueId,
      });
    } else {
      parsed.push({
        speaker: '旁白',
        text: line.replace(/\\n/g, '\n'),
        kind: 'narration',
        sourceFormat: 'plain-text',
        sourceRow: index + 1,
        audioCueId,
      });
    }
  });

  return applySpeakerBlockMerging({
    lines: parsed,
    format: sawScene0 ? 'scene0-text' : 'plain-text',
    warnings,
  }, options, true);
};

const cleanMagirecoText = (value: unknown): string => {
  let text = normalizeNewlines(asString(value))
    .replace(/@/g, '\n')
    .replace(/\[br\]/gi, '\n')
    .replace(/[「『]textBlack:/g, '[textBlack:');

  for (const color of ['Red', 'Blue', 'Yellow', 'Black']) {
    text = text.replace(
      new RegExp(`\\[text${color}:([\\s\\S]*?)\\]`, 'gi'),
      `<${color.toLowerCase()}>$1</${color.toLowerCase()}>`,
    );
  }

  return text.replace(/\[(?!\/?(?:red|blue|yellow|black)\b)[^\]]*]/gi, '').trim();
};

const getMagirecoSection = (filename: string): string => {
  const match = filename.match(/[-_](\d+)(?:[_\-.]|$)/);
  return match?.[1] ?? '1';
};

const parseMagirecoJson = (
  value: UnknownRecord,
  options: StoryParserOptions,
): StoryParseResult => {
  const warnings: string[] = [];
  const story = value.story;
  const groups: Array<[string, unknown[]]> = [];

  if (Array.isArray(story)) {
    groups.push(['group_1', story]);
  } else if (isRecord(story)) {
    Object.entries(story)
      .filter(([key, group]) => key.startsWith('group_') && Array.isArray(group))
      .sort(([left], [right]) => naturalCompare(left, right))
      .forEach(([key, group]) => groups.push([key, group as unknown[]]));
  }

  if (groups.length === 0) {
    throw new Error('Magia Record JSON 中没有可读取的 story/group 数据。');
  }

  const filename = options.filename || 'scenario.json';
  const section = getMagirecoSection(filename);
  const globalIdNames = new Map<string, string>();
  const lines: StoryLine[] = [];

  for (const [groupName, group] of groups) {
    const branch = groupName === 'group_1' ? '' : groupName.replace(/^group_?/, '');
    const headerText =
      `--- [Section ${section}${branch ? ` - Branch ${branch}` : ''}] (Source: ${filename}) ---`;
    lines.push({
      ...createHeaderLine(headerText, lines.length),
      sourceFormat: 'magireco-json',
    });

    const positionIds = new Map<StoryLinePosition, string>();
    const positionNames = new Map<StoryLinePosition, string>();
    let narrationName = '旁白';
    let fnarrationName = '旁白';

    group.forEach((itemValue, itemIndex) => {
      if (!isRecord(itemValue)) return;
      const item = itemValue;

      for (const characterValue of asArray(item.chara)) {
        if (!isRecord(characterValue)) continue;
        const id = asString(characterValue.id).trim();
        const numericPosition = Number(characterValue.pos);
        const position: StoryLinePosition | undefined =
          numericPosition === 0 ? 'left' : numericPosition === 1 ? 'center' : numericPosition === 2 ? 'right' : undefined;
        if (id && position) positionIds.set(position, id);
      }

      for (const [suffix, position] of [
        ['Left', 'left'],
        ['Center', 'center'],
        ['Right', 'right'],
      ] as const) {
        const nameKey = `name${suffix}`;
        if (nameKey in item) {
          const name = asString(item[nameKey]).trim();
          if (name) {
            positionNames.set(position, name);
            const characterId = positionIds.get(position);
            if (characterId) globalIdNames.set(characterId, name);
          } else {
            positionNames.delete(position);
          }
        }
      }

      if (Array.isArray(item.select)) {
        for (const optionValue of item.select) {
          if (!isRecord(optionValue)) continue;
          const label = cleanMagirecoText(optionValue.textSelect);
          const target = asString(optionValue.group).replace(/^group_?/, '');
          if (!label) continue;
          lines.push({
            speaker: '选项',
            text: `【${label}】`,
            isChoice: true,
            choiceLabel: label,
            choiceTargetId: target,
            sourceCommand: 'select',
            sourceFormat: 'magireco-json',
            sourceRow: itemIndex + 1,
          });
        }
        return;
      }

      const fnarration =
        item.Fnarration ??
        item.fnarration ??
        item.progressFnarration;
      const narration =
        item.narration ??
        item.progressNarration;

      const pushLine = (
        rawText: unknown,
        speaker: string,
        kind: StoryLineKind,
        command: string,
        position?: StoryLinePosition,
      ) => {
        const text = cleanMagirecoText(rawText);
        if (!text) return;
        lines.push({
          speaker: speaker || '旁白',
          text,
          kind,
          position,
          sourceCommand: command,
          sourceFormat: 'magireco-json',
          sourceRow: itemIndex + 1,
          isScene0: true,
        });
      };

      if (fnarration !== undefined && asString(fnarration)) {
        if ('nameFnarration' in item) {
          fnarrationName = asString(item.nameFnarration).trim() || '旁白';
        }
        pushLine(fnarration, fnarrationName, 'fnarration', 'fnarration');
      } else if (narration !== undefined && asString(narration)) {
        if ('nameNarration' in item) {
          narrationName = asString(item.nameNarration).trim() || '旁白';
        }
        pushLine(narration, narrationName, 'narration', 'narration');
      } else {
        let pushedPositionText = false;
        for (const [suffix, candidatePosition] of [
          ['Left', 'left'],
          ['Center', 'center'],
          ['Right', 'right'],
        ] as const) {
          const key = `text${suffix}`;
          const avKey = `textAv${suffix}`;
          const candidate = item[key] ?? item[avKey];
          if (candidate === undefined || !asString(candidate)) continue;

          const explicitName = asString(item[`name${suffix}`]).trim();
          const characterId = positionIds.get(candidatePosition);
          const speaker =
            explicitName ||
            positionNames.get(candidatePosition) ||
            (characterId ? globalIdNames.get(characterId) : '') ||
            '旁白';
          pushLine(
            candidate,
            speaker,
            'dialogue',
            key in item ? key : avKey,
            candidatePosition,
          );
          pushedPositionText = true;
        }
        if (!pushedPositionText && asString(item.text)) {
          pushLine(
            item.text,
            asString(item.name).trim() || '旁白',
            'dialogue',
            'text',
            'center',
          );
        }
      }
    });
  }

  if (lines.every(line => line.isHeader)) {
    warnings.push('该 Magia Record JSON 没有可显示的对白。');
  }

  return { lines, format: 'magireco-json', warnings };
};

const headerIndex = (headers: string[], name: string): number =>
  headers.findIndex(header => header.trim().toLowerCase() === name.toLowerCase());

const inferExedraDefaultSpeaker = (filename: string, title: string): string => {
  if (!/^cv_/i.test(filename) || !title.includes('_')) return '';
  const candidate = title.split('_')[0]?.trim();
  return candidate && candidate.length <= 40 ? candidate : '';
};

const isPlausibleAssetSpeaker = (value: string): boolean =>
  Boolean(value) &&
  value.length <= 40 &&
  !/\d/.test(value) &&
  !/[_\\/]/.test(value) &&
  !/^(?:adv|bg|cv|spine|asset|chara|character|npc|mob|effect|eff|voice|se|bgm)[-_.]/i.test(value) &&
  !/\.(?:png|jpg|json|asset)$/i.test(value);

const parseExedraJson = (
  value: UnknownRecord,
  options: StoryParserOptions,
): StoryParseResult => {
  const warnings: string[] = [];
  const lines: StoryLine[] = [];
  const title = asString(value.bookTitle).trim();
  const filename = options.filename || 'scenario.json';
  const defaultSpeaker = inferExedraDefaultSpeaker(filename, title);
  const sheets = asArray(value.sheetList);
  const seenSheets = new Set<string>();

  sheets.forEach((sheetValue, sheetIndex) => {
    if (!isRecord(sheetValue)) return;
    const sheetName = asString(sheetValue.sheetName).trim() || `sheet-${sheetIndex + 1}`;
    const headerRow = isRecord(sheetValue.headerRow) ? sheetValue.headerRow : {};
    const headers = asArray(headerRow.cellList).map(cell => asString(cell).trim());
    const contentRows = asArray(sheetValue.contentRowList);
    const sheetFingerprint = JSON.stringify([
      headers,
      contentRows.map(row => isRecord(row) ? asArray(row.cellList) : row),
    ]);
    if (seenSheets.has(sheetFingerprint)) {
      warnings.push(`${sheetName} 与前一个工作表内容重复，已去重。`);
      return;
    }
    seenSheets.add(sheetFingerprint);

    const actionIndex = headerIndex(headers, 'ActionType');
    const commentIndex = headerIndex(headers, 'Comment');
    const nameIndex = headerIndex(headers, 'Name');
    const assetIndex = headerIndex(headers, 'AssetID');
    const positionIndex = headerIndex(headers, 'PositionID');

    if (actionIndex < 0 || commentIndex < 0) {
      warnings.push(`${sheetName} 缺少 ActionType 或 Comment 列，已跳过。`);
      return;
    }

    const positionSpeakers = new Map<StoryLinePosition, string>();
    const assetSpeakers = new Map<string, string>();
    for (const rowValue of contentRows) {
      if (!isRecord(rowValue)) continue;
      const cells = asArray(rowValue.cellList);
      const action = asString(cells[actionIndex]).trim();
      const normalizedAction = action.toLowerCase();
      const name = nameIndex >= 0 ? asString(cells[nameIndex]).trim() : '';
      const asset = assetIndex >= 0 ? asString(cells[assetIndex]).trim() : '';
      const position = positionIndex >= 0 ? normalizePosition(cells[positionIndex]) : undefined;
      const rowNumberValue = Number(rowValue.rowNumber);
      const rowNumber = Number.isFinite(rowNumberValue) ? rowNumberValue : undefined;

      if (normalizedAction === 'put' && name && asset) {
        assetSpeakers.set(asset, name);
      }
      if (normalizedAction === 'put' && position) {
        const putSpeaker = name || (isPlausibleAssetSpeaker(asset) ? asset : '');
        if (putSpeaker) {
          positionSpeakers.set(position, putSpeaker);
        } else {
          positionSpeakers.delete(position);
        }
      }

      if (!DIALOGUE_ACTIONS.has(normalizedAction)) continue;
      const text = normalizeNewlines(asString(cells[commentIndex])).trim();
      if (!text) continue;

      const assetSpeaker = isPlausibleAssetSpeaker(asset) ? asset : '';
      const inferredSpeaker =
        name ||
        assetSpeakers.get(asset) ||
        (position ? positionSpeakers.get(position) : '') ||
        assetSpeaker ||
        defaultSpeaker;
      const isNarration =
        normalizedAction === 'narration' ||
        (normalizedAction === 'onlytext' && !name) ||
        !inferredSpeaker;
      const resolvedSpeaker =
        normalizedAction === 'narration'
          ? name || '旁白'
          : inferredSpeaker || '旁白';
      const kind: StoryLineKind = isNarration ? 'narration' : 'dialogue';

      lines.push({
        speaker: resolvedSpeaker,
        text,
        kind,
        position,
        sourceCommand: action,
        sourceFormat: 'exedra-json',
        sourceRow: rowNumber,
        sourceSheet: sheetName,
      });
    }
  });

  if (lines.length === 0) {
    warnings.push('该 Exedra JSON 没有 Talk、Narration、CharacterTalk 或 OnlyText 文本。');
  }

  return {
    lines,
    format: 'exedra-json',
    title: title || undefined,
    warnings,
  };
};

const parseGenericJson = (value: unknown): StoryParseResult | null => {
  const candidateLines =
    Array.isArray(value)
      ? value
      : isRecord(value)
        ? value.lines ?? value.dialogues ?? value.messages
        : null;

  if (!Array.isArray(candidateLines)) return null;

  const lines: StoryLine[] = [];
  candidateLines.forEach((entry, index) => {
    if (typeof entry === 'string') {
      const text = normalizeNewlines(entry).trim();
      if (text) {
        lines.push({
          speaker: '旁白',
          text,
          kind: 'narration',
          sourceFormat: 'generic-json',
          sourceRow: index + 1,
        });
      }
      return;
    }

    if (!isRecord(entry)) return;
    const text = normalizeNewlines(asString(entry.text ?? entry.content ?? entry.dialogue)).trim();
    if (!text) return;
    const speaker = asString(entry.speaker ?? entry.name ?? entry.character).trim() || '旁白';
    lines.push({
      speaker,
      text,
      kind: speaker === '旁白' ? 'narration' : 'dialogue',
      sourceFormat: 'generic-json',
      sourceRow: index + 1,
    });
  });

  return lines.length > 0
    ? { lines, format: 'generic-json', warnings: [] }
    : null;
};

export const parseStoryContent = (
  raw: string,
  options: StoryParserOptions = {},
): StoryParseResult => {
  const normalized = normalizeNewlines(raw);
  if (!normalized.trim()) {
    return { lines: [], format: 'plain-text', warnings: [] };
  }

  const filenameLooksJson = /\.json$/i.test(options.filename || '');
  const contentLooksJson = /^[\[{]/.test(normalized.trimStart());

  if (filenameLooksJson || contentLooksJson) {
    let value: unknown;
    try {
      value = JSON.parse(normalized);
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误';
      throw new Error(`JSON 解析失败：${detail}`);
    }

    if (isRecord(value) && Array.isArray(value.sheetList)) {
      return applySpeakerBlockMerging(parseExedraJson(value, options), options);
    }
    if (isRecord(value) && ('story' in value)) {
      return applySpeakerBlockMerging(parseMagirecoJson(value, options), options);
    }

    const generic = parseGenericJson(value);
    if (generic) return applySpeakerBlockMerging(generic, options);
    throw new Error('无法识别该 JSON 的剧情结构。');
  }

  return parsePlainText(normalized, options);
};

export const serializeStoryLine = (line: StoryLine): string => {
  if (line.isHeader) return line.text;
  if (line.isChoice) {
    const target = line.choiceTargetId ? `group_${line.choiceTargetId}` : '';
    return `选项: 【${line.choiceLabel || line.text}】→ ${target}`;
  }
  if (line.isScene0 && line.sourceFormat === 'scene0-text' && line.sourceCommand) {
    return SCENE0_LINE_PREFIX + JSON.stringify({
      kind: line.kind || 'dialogue',
      speaker: line.speaker || '旁白',
      text: line.text || '',
      command: line.sourceCommand,
      ...(line.position ? { position: line.position } : {}),
    });
  }
  const escapedText = (line.text || '').replace(/\r?\n/g, '\\n');
  return `${line.speaker || '旁白'}: ${escapedText}`;
};

export const alignStoryLines = (
  cn: StoryLine[],
  jp: StoryLine[],
): AlignedStoryLine[] =>
  Array.from(
    { length: Math.max(cn.length, jp.length) },
    (_, index) => ({ cn: cn[index], jp: jp[index] }),
  );
