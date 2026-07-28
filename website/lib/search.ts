const SEARCH_CHARACTER_RE = /[\p{L}\p{N}]/u;

type IndexedCharacter = {
  normalized: string;
  start: number;
  end: number;
};

export type HighlightSegment = {
  text: string;
  highlight: boolean;
};

const indexSearchCharacters = (value: string): IndexedCharacter[] => {
  const indexed: IndexedCharacter[] = [];

  for (let offset = 0; offset < value.length;) {
    const codePoint = value.codePointAt(offset);
    if (codePoint === undefined) break;

    const character = String.fromCodePoint(codePoint);
    const end = offset + character.length;
    const normalizedCharacter = character.normalize('NFKC').toLocaleLowerCase();

    for (const normalized of normalizedCharacter) {
      if (SEARCH_CHARACTER_RE.test(normalized)) {
        indexed.push({ normalized, start: offset, end });
      }
    }

    offset = end;
  }

  return indexed;
};

export const normalizeSearchText = (value: string): string =>
  indexSearchCharacters(value).map(character => character.normalized).join('');

export const findNormalizedRanges = (
  value: string,
  query: string,
): Array<{ start: number; end: number }> => {
  const indexed = indexSearchCharacters(value);
  const normalizedValue = indexed.map(character => character.normalized).join('');
  const normalizedQuery = normalizeSearchText(query);

  if (!normalizedQuery || !normalizedValue) return [];

  const ranges: Array<{ start: number; end: number }> = [];
  let fromIndex = 0;

  while (fromIndex <= normalizedValue.length - normalizedQuery.length) {
    const matchIndex = normalizedValue.indexOf(normalizedQuery, fromIndex);
    if (matchIndex < 0) break;

    const first = indexed[matchIndex];
    const last = indexed[matchIndex + normalizedQuery.length - 1];
    if (first && last) ranges.push({ start: first.start, end: last.end });

    fromIndex = matchIndex + Math.max(normalizedQuery.length, 1);
  }

  return ranges;
};

export const splitHighlightSegments = (
  value: string,
  query: string,
): HighlightSegment[] => {
  const ranges = findNormalizedRanges(value, query);
  if (ranges.length === 0) return [{ text: value, highlight: false }];

  const segments: HighlightSegment[] = [];
  let offset = 0;

  for (const range of ranges) {
    if (range.start > offset) {
      segments.push({ text: value.slice(offset, range.start), highlight: false });
    }
    segments.push({ text: value.slice(range.start, range.end), highlight: true });
    offset = range.end;
  }

  if (offset < value.length) {
    segments.push({ text: value.slice(offset), highlight: false });
  }

  return segments;
};

export const extractSearchSnippet = (
  value: string,
  query: string,
  contextLength = 30,
): string | null => {
  const firstRange = findNormalizedRanges(value, query)[0];
  if (!firstRange) return null;

  const start = Math.max(0, firstRange.start - contextLength);
  const end = Math.min(value.length, firstRange.end + contextLength);
  return value
    .slice(start, end)
    .replace(/\s+/g, ' ')
    .trim();
};
