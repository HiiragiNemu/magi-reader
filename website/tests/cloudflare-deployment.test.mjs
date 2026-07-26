import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const configVerifier = path.resolve('scripts/verify-cloudflare-config.mjs');
const outputVerifier = path.resolve('scripts/verify-cloudflare-output.mjs');
const placeholder = '00000000000000000000000000000000';
const realNamespaceId = '0123456789abcdef0123456789abcdef';

const withTempDirectory = (callback) => {
  const directory = mkdtempSync(path.join(os.tmpdir(), 'magireader-deploy-test-'));
  try {
    return callback(directory);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
};

const configFixture = (namespaceId, extra = '') => `{
  "name": "magireader",
  "main": ".open-next/worker.js",
  "kv_namespaces": [
    { "binding": "SUBMISSIONS_KV", "id": "${namespaceId}" }
  ]${extra}
}
`;

test('deployment config refuses the committed placeholder without an override', () => {
  withTempDirectory((directory) => {
    const config = path.join(directory, 'wrangler.jsonc');
    writeFileSync(config, configFixture(placeholder));
    const result = spawnSync(
      process.execPath,
      [configVerifier, '--config', config],
      { cwd: directory, encoding: 'utf8' },
    );

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /全零占位/u);
  });
});

test('deployment config resolves the namespace from CI without modifying the template', () => {
  withTempDirectory((directory) => {
    const config = path.join(directory, 'wrangler.jsonc');
    const output = path.join(directory, 'wrangler.deploy.jsonc');
    const original = configFixture(placeholder);
    writeFileSync(config, original);
    const result = spawnSync(
      process.execPath,
      [configVerifier, '--config', config, '--output', output],
      {
        cwd: directory,
        encoding: 'utf8',
        env: {
          ...process.env,
          SUBMISSIONS_KV_NAMESPACE_ID: realNamespaceId,
        },
      },
    );

    assert.equal(result.status, 0, result.stderr);
    assert.equal(readFileSync(config, 'utf8'), original);
    assert.match(readFileSync(output, 'utf8'), new RegExp(realNamespaceId, 'u'));
  });
});

test('deployment config rejects an embedded administrator token', () => {
  withTempDirectory((directory) => {
    const config = path.join(directory, 'wrangler.jsonc');
    writeFileSync(
      config,
      configFixture(realNamespaceId, ', "SUBMISSIONS_ADMIN_TOKEN": "leaked"'),
    );
    const result = spawnSync(
      process.execPath,
      [configVerifier, '--config', config],
      { cwd: directory, encoding: 'utf8' },
    );

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /Worker secret/u);
  });
});

test('Cloudflare output requires a valid manifest and excludes the large payload', () => {
  withTempDirectory((directory) => {
    const assets = path.join(directory, '.open-next', 'assets');
    const publicDirectory = path.join(directory, 'public');
    mkdirSync(assets, { recursive: true });
    mkdirSync(publicDirectory, { recursive: true });
    writeFileSync(path.join(directory, '.open-next', 'worker.js'), 'export {};');
    const manifest = JSON.stringify({
      version: 1,
      sha256: 'a'.repeat(64),
      bytes: 123,
      entries: 1,
      object_key: `search/${'a'.repeat(64)}.json`,
      story_index_sha256: 'b'.repeat(64),
    });
    writeFileSync(path.join(assets, 'search_index_manifest.json'), manifest);
    writeFileSync(
      path.join(publicDirectory, 'search_index_manifest.json'),
      manifest,
    );

    const valid = spawnSync(process.execPath, [outputVerifier], {
      cwd: directory,
      encoding: 'utf8',
    });
    assert.equal(valid.status, 0, valid.stderr);

    writeFileSync(path.join(assets, 'search_content.json'), '[]');
    const invalid = spawnSync(process.execPath, [outputVerifier], {
      cwd: directory,
      encoding: 'utf8',
    });
    assert.notEqual(invalid.status, 0);
    assert.match(invalid.stderr, /不能打包/u);
  });
});
