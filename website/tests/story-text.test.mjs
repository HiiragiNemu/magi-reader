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
