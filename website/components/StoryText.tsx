"use client";

import { Fragment, type ReactNode } from 'react';

import { splitHighlightSegments } from '@/lib/search';

type StoryTextProps = {
  text: string;
  query?: string;
  theme?: string;
  showLineBreaks?: boolean;
};

type RichMatch = {
  index: number;
  full: string;
  inner: string;
  kind: 'color' | 'size' | 'ruby';
  value: string;
};

const MAX_RICH_TEXT_RECURSION = 96;
export const MAX_VISIBLE_LINE_BREAK_MARKERS = 200;

type LineBreakMarkerBudget = {
  remaining: number;
};

const COLOR_CLASSES: Record<string, string> = {
  red: 'text-red-500 font-bold',
  blue: 'text-blue-500 font-bold',
  yellow: 'text-yellow-500 font-bold',
};

const safeColor = (value: string): string | undefined => {
  const normalized = value.trim().replace(/^["']|["']$/g, '').toLowerCase();
  if (/^#[0-9a-f]{3,4}(?:[0-9a-f]{3,4})?$/i.test(normalized)) return normalized;
  if (['black', 'red', 'blue', 'yellow'].includes(normalized)) return normalized;
  return undefined;
};

const findFirstRichMatch = (text: string): RichMatch | null => {
  const candidates: RichMatch[] = [];

  const exedraColor = /<color\s*=\s*(?:"([^"]+)"|'([^']+)'|([^>\s]+))\s*>([\s\S]*?)<\/color>/i.exec(text)
    ?? /<color\s*=\s*(?:"([^"]+)"|'([^']+)'|([^>\s]+))\s*>([\s\S]*)$/i.exec(text);
  if (exedraColor) {
    candidates.push({
      index: exedraColor.index,
      full: exedraColor[0],
      inner: exedraColor[4],
      kind: 'color',
      value: exedraColor[1] ?? exedraColor[2] ?? exedraColor[3] ?? '',
    });
  }

  const simpleColor = /<(red|blue|yellow|black)>([\s\S]*?)<\/\1>/i.exec(text);
  if (simpleColor) {
    candidates.push({
      index: simpleColor.index,
      full: simpleColor[0],
      inner: simpleColor[2],
      kind: 'color',
      value: simpleColor[1],
    });
  }

  const bracketColor = /\[text(Red|Blue|Yellow|Black):([\s\S]*?)\]/i.exec(text);
  if (bracketColor) {
    candidates.push({
      index: bracketColor.index,
      full: bracketColor[0],
      inner: bracketColor[2],
      kind: 'color',
      value: bracketColor[1],
    });
  }

  const size = /<size\s*=\s*(?:"?)(\d{1,3})(%|px)?(?:"?)\s*>([\s\S]*?)<\/size>/i.exec(text);
  if (size) {
    candidates.push({
      index: size.index,
      full: size[0],
      inner: size[3],
      kind: 'size',
      value: `${size[1]}${size[2] || '%'}`,
    });
  }

  const ruby = /<r\s*=\s*(?:"([^"]*)"|'([^']*)'|([^>]*))>([\s\S]*?)<\/r>/i.exec(text);
  if (ruby) {
    candidates.push({
      index: ruby.index,
      full: ruby[0],
      inner: ruby[4],
      kind: 'ruby',
      value: ruby[1] ?? ruby[2] ?? ruby[3] ?? '',
    });
  }

  return candidates.sort((left, right) => left.index - right.index)[0] ?? null;
};

const renderTextWithLineBreakMarkers = (
  text: string,
  keyPrefix: string,
  markerBudget?: LineBreakMarkerBudget,
  markerOnly = false,
): ReactNode => {
  const wrapText = (value: string, key: string): ReactNode =>
    markerOnly
      ? <span key={key} className="text-transparent">{value}</span>
      : value;

  if (!markerBudget || markerBudget.remaining <= 0 || !text.includes('\n')) {
    return wrapText(text, `${keyPrefix}-plain`);
  }

  const nodes: ReactNode[] = [];
  let cursor = 0;
  let markerIndex = 0;
  while (markerBudget.remaining > 0) {
    const lineBreak = text.indexOf('\n', cursor);
    if (lineBreak < 0) break;
    nodes.push(
      wrapText(
        text.slice(cursor, lineBreak),
        `${keyPrefix}-text-${markerIndex}`,
      ),
    );
    nodes.push(
      <Fragment key={`${keyPrefix}-break-${markerIndex}`}>
        <span
          aria-hidden="true"
          data-line-break-marker="true"
          className="pointer-events-none inline-block w-0 select-none overflow-visible text-[0.72em] font-black text-fuchsia-500/80"
        >
          ↵
        </span>
        {'\n'}
      </Fragment>,
    );
    markerBudget.remaining -= 1;
    markerIndex += 1;
    cursor = lineBreak + 1;
  }
  nodes.push(
    wrapText(text.slice(cursor), `${keyPrefix}-tail-${markerIndex}`),
  );
  return nodes;
};

export function LineBreakMarkerText({
  text,
  markerOnly = false,
}: {
  text: string;
  markerOnly?: boolean;
}) {
  return (
    <>
      {renderTextWithLineBreakMarkers(
        text,
        'line-break-preview',
        { remaining: MAX_VISIBLE_LINE_BREAK_MARKERS },
        markerOnly,
      )}
    </>
  );
}

const renderPlainText = (
  text: string,
  query: string,
  keyPrefix: string,
  markerBudget?: LineBreakMarkerBudget,
): ReactNode =>
  splitHighlightSegments(text, query).map((segment, index) =>
    segment.highlight
      ? (
          <mark
            key={`${keyPrefix}-highlight-${index}`}
            className="bg-yellow-200 text-black outline outline-1 outline-yellow-400 rounded px-0.5 shadow-sm mx-0.5"
          >
            {renderTextWithLineBreakMarkers(
              segment.text,
              `${keyPrefix}-highlight-${index}`,
              markerBudget,
            )}
          </mark>
        )
      : (
          <Fragment key={`${keyPrefix}-text-${index}`}>
            {renderTextWithLineBreakMarkers(
              segment.text,
              `${keyPrefix}-text-${index}`,
              markerBudget,
            )}
          </Fragment>
        ),
  );

const renderRichText = (
  text: string,
  query: string,
  keyPrefix: string,
  theme: string,
  markerBudget?: LineBreakMarkerBudget,
  recursionDepth = 0,
): ReactNode => {
  if (recursionDepth >= MAX_RICH_TEXT_RECURSION) {
    return renderPlainText(
      text,
      query,
      `${keyPrefix}-fallback`,
      markerBudget,
    );
  }
  const match = findFirstRichMatch(text);
  if (!match) return renderPlainText(text, query, keyPrefix, markerBudget);

  const before = text.slice(0, match.index);
  const after = text.slice(match.index + match.full.length);
  const nextDepth = recursionDepth + 1;
  const content = renderRichText(
    match.inner,
    query,
    `${keyPrefix}-inner`,
    theme,
    markerBudget,
    nextDepth,
  );
  let wrapped: ReactNode;

  if (match.kind === 'color') {
    const color = safeColor(match.value);
    const className = color === 'black'
      ? theme === 'dark'
        ? 'font-black text-gray-100 drop-shadow-sm'
        : 'font-black text-gray-900 drop-shadow-sm'
      : color
        ? COLOR_CLASSES[color]
        : undefined;
    wrapped = (
      <span
        key={`${keyPrefix}-color`}
        className={className}
        style={!className && color ? { color } : undefined}
      >
        {content}
      </span>
    );
  } else if (match.kind === 'size') {
    const unit = match.value.toLowerCase().endsWith('px') ? 'px' : '%';
    const rawSize = Number.parseInt(match.value, 10);
    const size = unit === 'px'
      ? Math.min(96, Math.max(8, rawSize))
      : Math.min(400, Math.max(25, rawSize));
    wrapped = (
      <span key={`${keyPrefix}-size`} style={{ fontSize: `${size}${unit}` }}>
        {content}
      </span>
    );
  } else {
    wrapped = (
      <ruby key={`${keyPrefix}-ruby`} className="ruby-text">
        {content}
        <rp>（</rp>
        <rt>{match.value.trim()}</rt>
        <rp>）</rp>
      </ruby>
    );
  }

  return (
    <>
      {renderRichText(
        before,
        query,
        `${keyPrefix}-before`,
        theme,
        markerBudget,
        nextDepth,
      )}
      {wrapped}
      {renderRichText(
        after,
        query,
        `${keyPrefix}-after`,
        theme,
        markerBudget,
        nextDepth,
      )}
    </>
  );
};

export default function StoryText({
  text,
  query = '',
  theme = 'light',
  showLineBreaks = false,
}: StoryTextProps) {
  const markerBudget = showLineBreaks
    ? { remaining: MAX_VISIBLE_LINE_BREAK_MARKERS }
    : undefined;
  return <>{renderRichText(text, query, 'story', theme, markerBudget)}</>;
}
