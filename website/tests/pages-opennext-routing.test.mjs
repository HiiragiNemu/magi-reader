import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const preparePages = readFileSync('scripts/prepare-pages.js', 'utf8');
const wrapperSource = preparePages.match(
  /const wrapper = String\.raw`([\s\S]*?)`;/u,
)?.[1] ?? '';

test('Pages wrapper serves public assets without routing them through OpenNext', () => {
  assert.match(wrapperSource, /env\.ASSETS\.fetch\(request\)/u);
  assert.match(wrapperSource, /pathname\.startsWith\(\"\/data\/\"\)/u);
  assert.match(wrapperSource, /pathname\.startsWith\(\"\/_next\/\"\)/u);
  assert.match(wrapperSource, /\/\\\.\[A-Za-z0-9\]\{1,16\}\$/u);
});

test('Pages wrapper sends dynamic and RSC requests to OpenNext', () => {
  assert.match(wrapperSource, /url\.searchParams\.has\(\"_rsc\"\)/u);
  assert.match(wrapperSource, /request\.headers\.get\(\"rsc\"\) === \"1\"/u);
  assert.match(wrapperSource, /next-router-state-tree/u);
  assert.match(wrapperSource, /pathname\.startsWith\(\"\/reader\/\"\)/u);
  assert.match(wrapperSource, /pathname\.startsWith\(\"\/api\/\"\)/u);
  assert.match(
    wrapperSource,
    /return appWorker\.fetch\(request, env, ctx\);/u,
  );
});
