import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import test from 'node:test';

import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import typescript from 'typescript';

import { splitHighlightSegments } from '../lib/search.ts';

const require = createRequire(import.meta.url);
const source = await readFile(
  new URL('../components/StoryText.tsx', import.meta.url),
  'utf8',
);
const compiled = typescript.transpileModule(source, {
  compilerOptions: {
    esModuleInterop: true,
    jsx: typescript.JsxEmit.ReactJSX,
    module: typescript.ModuleKind.CommonJS,
    target: typescript.ScriptTarget.ES2020,
  },
  fileName: 'StoryText.tsx',
}).outputText;

const storyTextModule = { exports: {} };
const localRequire = (specifier) => {
  if (specifier === '@/lib/search') return { splitHighlightSegments };
  return require(specifier);
};
new Function('require', 'module', 'exports', compiled)(
  localRequire,
  storyTextModule,
  storyTextModule.exports,
);
const StoryText = storyTextModule.exports.default;
const LineBreakMarkerText = storyTextModule.exports.LineBreakMarkerText;
const MAX_VISIBLE_LINE_BREAK_MARKERS =
  storyTextModule.exports.MAX_VISIBLE_LINE_BREAK_MARKERS;

test('StoryText safely degrades 10,000 sequential rich-text tags without overflowing', () => {
  assert.equal(typeof StoryText, 'function');
  const hostileButSmallText = '<red>x</red>'.repeat(10_000);
  assert.ok(hostileButSmallText.length < 8 * 1024 * 1024);

  assert.doesNotThrow(() => {
    const html = renderToStaticMarkup(
      createElement(StoryText, { text: hostileButSmallText }),
    );
    assert.ok(html.includes('x'));
  });
});

test('StoryText shows optional line-break markers while preserving real newlines', () => {
  const text = '第一行\n第二行';
  const normal = renderToStaticMarkup(
    createElement(StoryText, { text }),
  );
  const visible = renderToStaticMarkup(
    createElement(StoryText, { text, showLineBreaks: true }),
  );

  assert.doesNotMatch(normal, /data-line-break-marker/u);
  assert.match(visible, /data-line-break-marker="true"/u);
  assert.match(visible, /aria-hidden="true"/u);
  assert.match(visible, /↵<\/span>\n/u);
  assert.equal(text, '第一行\n第二行');
});

test('line-break markers remain compatible with rich text and search highlighting', () => {
  const html = renderToStaticMarkup(
    createElement(StoryText, {
      text: '<red>第一行\n第二行</red>',
      query: '第二',
      showLineBreaks: true,
    }),
  );
  assert.match(html, /text-red-500/u);
  assert.match(html, /<mark/u);
  assert.match(html, /data-line-break-marker="true"/u);
});

test('line-break marker DOM is strictly bounded for abnormal input', () => {
  const html = renderToStaticMarkup(
    createElement(LineBreakMarkerText, {
      text: 'x\n'.repeat(MAX_VISIBLE_LINE_BREAK_MARKERS + 50),
      markerOnly: true,
    }),
  );
  assert.equal(
    html.match(/data-line-break-marker="true"/gu)?.length,
    MAX_VISIBLE_LINE_BREAK_MARKERS,
  );
  assert.match(html, /text-transparent/u);
});
