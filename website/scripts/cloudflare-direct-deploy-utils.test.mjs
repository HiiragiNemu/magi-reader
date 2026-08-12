import assert from 'node:assert/strict';
import test from 'node:test';

import {
  parseNamespaceList,
  resolveNpmInvocation,
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
  ],
  "vars": {
    "EXEDRA_WIKI_BASE_URL": "https://exedra.wiki"
  }
}`;

const rewriteOptions = {
  source: config,
  workerName: 'magireader-exedra-cn-test',
  namespaceId: ID,
  hostname: 'magireader-exedra-cn-test.example.workers.dev',
  targetBranch: 'EXEDRA-TEST',
  sourceCommit: '1'.repeat(40),
  githubRepo: 'HiiragiNemu/magi-reader',
  turnstileSiteKey: '1x00000000000000000000AA',
};

test('namespace parser accepts Wrangler JSON output', () => {
  const output = JSON.stringify([
    { id: 'f'.repeat(32), title: 'magi-submissions' },
    { id: ID, title: TITLE },
  ]);
  assert.equal(parseNamespaceList(output, TITLE), ID);
});

test('namespace parser ignores a bracketed warning after multiline JSON', () => {
  const output = `${JSON.stringify([
    { id: 'f'.repeat(32), title: 'magi-submissions' },
    { id: ID, title: TITLE },
  ], null, 2)}\n\n▲ [WARNING] Proxy environment variables detected.`;
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
  const output = rewriteTestConfig(rewriteOptions);
  assert.match(output, /"name": "magireader-exedra-cn-test"/u);
  assert.match(output, /"service": "magireader-exedra-cn-test"/u);
  assert.match(output, new RegExp(ID, 'u'));
  assert.doesNotMatch(output, /"name": "magireader"/u);
  assert.match(
    output,
    /"PROOFREADING_TARGET_BRANCH": "EXEDRA-TEST"/u,
  );
  assert.match(
    output,
    /"PROOFREADING_SOURCE_COMMIT": "1111111111111111111111111111111111111111"/u,
  );
  assert.match(
    output,
    /"TURNSTILE_ALLOWED_HOSTNAMES": "magireader-exedra-cn-test\.example\.workers\.dev"/u,
  );
});

test('Windows npm invocation uses the current Node process without cmd.exe', () => {
  const invocation = resolveNpmInvocation({
    platform: 'win32',
    nodeExecutable: 'C:\\node\\node.exe',
    npmExecPath: 'C:\\node\\node_modules\\npm\\bin\\npm-cli.js',
  });
  assert.deepEqual(invocation, {
    command: 'C:\\node\\node.exe',
    prefixArgs: ['C:\\node\\node_modules\\npm\\bin\\npm-cli.js'],
  });
});

test('POSIX npm invocation validates paths with POSIX semantics', () => {
  const invocation = resolveNpmInvocation({
    platform: 'linux',
    nodeExecutable: '/usr/local/bin/node',
    npmExecPath: '/usr/local/lib/node_modules/npm/bin/npm-cli.js',
  });
  assert.deepEqual(invocation, {
    command: '/usr/local/bin/node',
    prefixArgs: ['/usr/local/lib/node_modules/npm/bin/npm-cli.js'],
  });
});

test('Windows npm invocation rejects missing or relative npm CLI paths', () => {
  assert.throws(
    () => resolveNpmInvocation({
      platform: 'win32',
      nodeExecutable: 'C:\\node\\node.exe',
      npmExecPath: '',
    }),
    /必须通过 npm run 启动/u,
  );
  assert.throws(
    () => resolveNpmInvocation({
      platform: 'win32',
      nodeExecutable: 'C:\\node\\node.exe',
      npmExecPath: 'npm-cli.js',
    }),
    /绝对路径/u,
  );
});

test('test config rejects the placeholder KV ID', () => {
  assert.throws(
    () => rewriteTestConfig({
      ...rewriteOptions,
      source: config.replace(ID, '0'.repeat(32)),
      namespaceId: '0'.repeat(32),
    }),
    /全零占位值/u,
  );
});
