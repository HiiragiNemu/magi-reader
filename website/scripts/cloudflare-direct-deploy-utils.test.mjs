import assert from 'node:assert/strict';
import test from 'node:test';

import {
  parseNamespaceList,
  rewriteTestConfig,
} from './cloudflare-direct-deploy-utils.mjs';

const TITLE = 'magi-submissions-exedra-cn-test';
const ID = '0123456789abcdef0123456789abcdef';

const config = `{
  "name": "magireader",
  "services": [
    {
      "binding": "WORKER_SELF_REFERENCE",
      "service": "magireader"
    }
  ],
  "kv_namespaces": [
    {
      "binding": "SUBMISSIONS_KV",
      "id": "${ID}"
    }
  ]
}`;

test('namespace parser accepts Wrangler JSON output', () => {
  const output = JSON.stringify([
    { id: 'f'.repeat(32), title: 'magi-submissions' },
    { id: ID, title: TITLE },
  ]);
  assert.equal(parseNamespaceList(output, TITLE), ID);
});

test('namespace parser accepts table output and rejects a longer similar title', () => {
  const output = [
    `│ ${'a'.repeat(32)} │ ${TITLE}-copy │`,
    `│ ${ID} │ ${TITLE} │`,
  ].join('\n');
  assert.equal(parseNamespaceList(output, TITLE), ID);
});

test('namespace parser rejects ambiguous exact matches', () => {
  const output = [
    `│ ${ID} │ ${TITLE} │`,
    `│ ${'b'.repeat(32)} │ ${TITLE} │`,
  ].join('\n');
  assert.throws(
    () => parseNamespaceList(output, TITLE),
    /对应多个 ID/u,
  );
});

test('test config rewrites both Worker and self-reference without changing KV', () => {
  const output = rewriteTestConfig({
    source: config,
    workerName: 'magireader-exedra-cn-test',
    namespaceId: ID,
  });
  assert.match(output, /"name": "magireader-exedra-cn-test"/u);
  assert.match(output, /"service": "magireader-exedra-cn-test"/u);
  assert.match(output, new RegExp(ID, 'u'));
  assert.doesNotMatch(output, /"name": "magireader"/u);
});

test('test config rejects the placeholder KV ID', () => {
  assert.throws(
    () => rewriteTestConfig({
      source: config.replace(ID, '0'.repeat(32)),
      workerName: 'magireader-exedra-cn-test',
      namespaceId: '0'.repeat(32),
    }),
    /全零占位值/u,
  );
});
