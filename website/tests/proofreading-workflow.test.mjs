import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const read = (relative) => readFileSync(path.resolve(relative), 'utf8');

test('public proofreading submissions require Turnstile and version hashes', () => {
  const route = read('app/api/submit/route.ts');
  assert.match(route, /verifyTurnstileToken/u);
  assert.match(route, /base_sha256/u);
  assert.match(route, /base_content_sha256/u);
  assert.match(route, /catalog_sha256/u);
  assert.match(route, /source_identity/u);
  assert.match(route, /DUPLICATE_SUBMISSION/u);
});

test('admin detail strips receipt and internal KV index metadata', () => {
  const model = read('lib/proofreading.ts');
  const detailRoute = read('app/api/admin/submissions/[id]/route.ts');
  assert.match(model, /ProofreadingAdminDetail/u);
  assert.match(model, /'receipt_sha256'\s*\|\s*'index_key'/u);
  assert.match(detailRoute, /toProofreadingAdminDetail/u);
  assert.doesNotMatch(detailRoute, /submission:\s*context\.record/u);
});

test('approved reviews create a scoped GitHub pull request', () => {
  const route = read('app/api/admin/submissions/[id]/route.ts');
  const github = read('lib/github-proofreading.ts');
  assert.match(route, /createProofreadingPullRequest/u);
  assert.match(github, /community-proofreading\//u);
  assert.match(github, /base_sha256/u);
  assert.match(github, /Section\/Branch 结构/u);
  assert.match(github, /const generalVoice/u);
  assert.match(github, /magireco-voice-translate-data-master/u);
  assert.match(github, /\/pulls/u);
});

test('community proofreading PR CI materializes playable JSON before TXT', () => {
  const workflow = read('../.github/workflows/community-proofreading-pr.yml');
  assert.match(workflow, /branches:\s*\[EXEDRA-TEST\]/u);
  assert.match(workflow, /exactly one canonical TXT/u);
  assert.match(workflow, /magireco-translate-data-master/u);
  assert.match(workflow, /magireco-voice-translate-data-master/u);
  assert.match(workflow, /magireco-voice-source-master/u);
  assert.match(workflow, /voice_source_manifest/u);
  assert.match(workflow, /voice_cn_manifest/u);
  assert.match(workflow, /Disallowed general-voice proofreading path/u);
  assert.match(workflow, /magiraexedra-translate-data-master/u);
  assert.match(workflow, /materialize_proofreading_assets\.py/u);
  assert.match(workflow, /Materialize playable JSON before canonical TXT/u);
  assert.match(workflow, /PROOFREADING_GITHUB_TOKEN/u);
  assert.match(workflow, /TARGET_REPO_TOKEN/u);
  assert.match(workflow, /npm run build:worker/u);
});

test('TW simplified test deployment is isolated, deterministic and chunk-verified', () => {
  const workflow = read('../.github/workflows/deploy-exedra-proofreading-test.yml');
  assert.match(workflow, /AUTHENTIC_TW_CANONICAL_CN_DEPLOY_V1/u);
  assert.match(workflow, /branches:\s*\[EXEDRA-TEST\]/u);
  assert.match(workflow, /startsWith\(github\.event\.head_commit\.message, '\[tw-materialized\]'\)/u);
  assert.match(workflow, /magi-submissions-exedra-cn-test/u);
  assert.match(workflow, /TURNSTILE_SITE_KEY/u);
  assert.match(workflow, /TURNSTILE_SECRET_KEY/u);
  assert.match(workflow, /PROOFREADING_TARGET_BRANCH/u);
  assert.match(workflow, /PROOFREADING_SOURCE_COMMIT/u);
  assert.match(workflow, /npm run check/u);
  assert.match(workflow, /build_split_search_indexes\.py/u);
  assert.match(workflow, /search_chunk_delivery\.py materialize/u);
  assert.match(workflow, /search_chunk_delivery\.py verify-tree/u);
  assert.match(workflow, /search_chunk_delivery\.py verify-http --base-url/u);
  assert.match(workflow, /opennextjs-cloudflare deploy/u);
  assert.match(workflow, /TW_DEPLOY_BYTES_OK/u);
  assert.doesNotMatch(workflow, /wrangler r2 object put/u);
});

test('review login presents shared team token as the simple default', () => {
  const page = read('app/review/submissions/page.tsx');
  const configRoute = read('app/api/proofreading/config/route.ts');
  const auth = read('lib/admin-auth.ts');
  assert.match(page, /团队审核口令/u);
  assert.match(page, /普通审核员无需创建 GitHub 令牌/u);
  assert.match(page, /仓库维护者高级登录/u);
  assert.match(configRoute, /shared_admin_auth/u);
  assert.match(configRoute, /server_pr_creation/u);
  assert.doesNotMatch(configRoute, /SUBMISSIONS_ADMIN_TOKEN\s*[,}]/u);
  assert.doesNotMatch(configRoute, /PROOFREADING_GITHUB_TOKEN\s*[,}]/u);
  assert.match(
    auth,
    /githubToken:\s*env\.PROOFREADING_GITHUB_TOKEN\?\.trim\(\)\s*\|\|\s*undefined/u,
  );
  assert.ok(
    auth.indexOf('constantTimeEquals(token, sharedSecret)') <
      auth.indexOf('const githubAllowed'),
    'fixed team token must be checked before the advanced GitHub fallback',
  );
});
