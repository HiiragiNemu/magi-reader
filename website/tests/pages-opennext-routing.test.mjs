import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const preparePages = readFileSync('scripts/prepare-pages.js', 'utf8');

test('Pages wrapper delegates all requests to the OpenNext worker', () => {
  const wrapperSource = preparePages.match(
    /const wrapper = String\.raw`([\s\S]*?)`;/u,
  )?.[1] ?? '';

  assert.match(
    wrapperSource,
    /return appWorker\.fetch\(request, env, ctx\);/u,
  );
  assert.doesNotMatch(wrapperSource, /env\.ASSETS\.fetch/u);
  assert.doesNotMatch(wrapperSource, /request\.method === ["']GET["']/u);
});
