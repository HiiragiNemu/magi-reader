import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const configVerifier = path.resolve('scripts/verify-cloudflare-config.mjs');
const outputVerifier = path.resolve('scripts/verify-cloudflare-output.mjs');
const deploymentWorkflow = path.resolve('..', '.github', 'workflows', 'deploy.yml');
const testDeploymentWorkflow = path.resolve(
  '..',
  '.github',
  'workflows',
  'deploy-exedra-proofreading-test.yml',
);
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
    const storyIndex = '[{"id":"fixture"}]\n';
    writeFileSync(path.join(publicDirectory, 'story_index.json'), storyIndex);
    const storyIndexSha256 = createHash('sha256')
      .update(storyIndex)
      .digest('hex');
    const writeManifest = (scope, manifest) => {
      const name = `search_index_manifest.${scope}.json`;
      const source = JSON.stringify(manifest);
      writeFileSync(path.join(assets, name), source);
      writeFileSync(path.join(publicDirectory, name), source);
    };
    const manifestFor = (scope, sha256) => ({
      version: 1,
      sha256,
      bytes: 123,
      entries: 1,
      object_key: `search/${scope}/${sha256}.json`,
      story_index_sha256: storyIndexSha256,
    });
    writeManifest('magireco', manifestFor('magireco', 'a'.repeat(64)));
    writeManifest('exedra', manifestFor('exedra', 'c'.repeat(64)));

    const valid = spawnSync(process.execPath, [outputVerifier], {
      cwd: directory,
      encoding: 'utf8',
    });
    assert.equal(valid.status, 0, valid.stderr);

    const v2Manifest = {
      version: 2,
      sha256: 'd'.repeat(64),
      bytes: 1024 * 1024 + 17,
      entries: 2,
      object_key: `search/magireco/${'d'.repeat(64)}.json`,
      story_index_sha256: storyIndexSha256,
      chunk_bytes: 1024 * 1024,
      chunks: [
        { bytes: 1024 * 1024, sha256: 'e'.repeat(64) },
        { bytes: 17, sha256: 'f'.repeat(64) },
      ],
    };
    writeManifest('magireco', v2Manifest);
    const validV2 = spawnSync(process.execPath, [outputVerifier], {
      cwd: directory,
      encoding: 'utf8',
    });
    assert.equal(validV2.status, 0, validV2.stderr);

    const malformedV2 = {
      ...v2Manifest,
      chunks: [
        { bytes: 1024 * 1024, sha256: 'not-a-hash' },
        { bytes: 17, sha256: 'f'.repeat(64) },
      ],
    };
    writeManifest('magireco', malformedV2);
    const invalidManifest = spawnSync(process.execPath, [outputVerifier], {
      cwd: directory,
      encoding: 'utf8',
    });
    assert.notEqual(invalidManifest.status, 0);
    assert.match(invalidManifest.stderr, /内容寻址键无效/u);

    writeManifest('magireco', v2Manifest);
    writeFileSync(path.join(assets, 'search_content.exedra.json'), '[]');
    const invalid = spawnSync(process.execPath, [outputVerifier], {
      cwd: directory,
      encoding: 'utf8',
    });
    assert.notEqual(invalid.status, 0);
    assert.match(invalid.stderr, /不能打包/u);
  });
});

test('production workflow safely deploys the current app to Cloudflare Pages', () => {
  const workflow = readFileSync(deploymentWorkflow, 'utf8');
  assert.match(workflow, /branches:\s*\[main\]/u);
  assert.match(workflow, /fetch-depth:\s*0/u);
  assert.match(workflow, /wrangler pages deploy \.pages-deploy/u);
  assert.doesNotMatch(workflow, /secrets\.KV_NAMESPACE_ID/u);
  assert.match(workflow, /secrets\.SUBMISSIONS_KV_NAMESPACE_ID/u);
  assert.match(workflow, /PROOFREADING_KV_TITLE:\s*magi-submissions/u);
  assert.match(workflow, /proofreading_queue\.py namespace/u);
  assert.match(workflow, /steps\.kv\.outputs\.namespace_id/u);
  assert.match(workflow, /npm ci/u);
  assert.match(workflow, /npm run check/u);
  assert.match(workflow, /generate_machine_translation_manifest\.py/u);
  assert.ok(
    workflow.indexOf('python generate_story_index.py') <
      workflow.indexOf('python generate_machine_translation_manifest.py'),
  );
  assert.ok(
    workflow.indexOf('python generate_machine_translation_manifest.py') <
      workflow.indexOf('npm run build:pages'),
  );
  assert.match(workflow, /npm run build:pages/u);
  assert.match(workflow, /configure-pages-project\.mjs/u);
  assert.match(workflow, /Verify server implementation is not exposed/u);
  assert.match(workflow, /magireader\.pages\.dev/u);
  assert.match(workflow, /api\/proofreading\/machine-status/u);
  assert.doesNotMatch(workflow, /wrangler r2 object put/u);
  assert.doesNotMatch(workflow, /opennextjs-cloudflare deploy/u);
});

test('Pages binding configuration uses the runtime GitHub repository variable', () => {
  const script = readFileSync(
    path.resolve('scripts', 'configure-pages-project.mjs'),
    'utf8',
  );
  assert.match(script, /PROOFREADING_GITHUB_REPO:/u);
  assert.doesNotMatch(script, /PROOFREADING_GITHUB_REPOSITORY:/u);
});

test('isolated Exedra V4 deployment verifies search chunks, revision, voice systems and decoder', () => {
  const workflow = readFileSync(testDeploymentWorkflow, 'utf8');
  assert.match(workflow, /AUTHENTIC_TW_CANONICAL_CN_DEPLOY_V1/u);
  assert.match(workflow, /startsWith\(github\.event\.head_commit\.message, '\[tw-materialized\]'\)/u);
  assert.match(workflow, /\?__revision=\$\{GITHUB_SHA\}-\$\{attempt\}/u);
  assert.match(workflow, /search_chunk_delivery\.py verify-http --base-url/u);
  assert.match(workflow, /TW_DEPLOY_BYTES_OK/u);
  assert.match(workflow, /pub-70a248f1a6fe4ca597e7a10f8b95dfd8\.r2\.dev/u);
  assert.match(workflow, /discover-cloudflare-r2-bucket\.mjs/u);
  assert.match(workflow, /"binding": "MAGIRECO_VOICE_R2"/u);
  assert.match(workflow, /"bucket_name": "\$VOICE_R2_BUCKET_NAME"/u);
  assert.match(
    workflow,
    /VOICE_R2_BUCKET_NAME: \$\{\{ steps\.voice_r2\.outputs\.bucket_name \}\}/u,
  );
  assert.doesNotMatch(workflow, /steps\.voice_r2\.outputs\.bucket_name \|\|/u);
  assert.match(workflow, /HTTP fallback/u);
  assert.doesNotMatch(workflow, /wrangler r2 object put/u);
  assert.match(workflow, /Smoke-test bounded voice playback assets/u);
  assert.match(workflow, /api\/audio\/magireco-voice\/vo_char_3031_00_01/u);
  assert.match(workflow, /Origin: \$site_url/u);
  assert.match(workflow, /cross-origin-resource-policy: same-origin/u);
  assert.match(workflow, /audio\/exedra-local\/cv_namae_call_01\.ogg/u);
  assert.match(workflow, /audio\/hca_wasm_bg\.wasm/u);
  assert.match(workflow, /VOICE_ASSETS_OK/u);
});
