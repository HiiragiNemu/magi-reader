#!/usr/bin/env node

const required = (name) => {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
};

const accountId = required('CLOUDFLARE_ACCOUNT_ID');
const apiToken = required('CLOUDFLARE_API_TOKEN');
const projectName = process.env.PAGES_PROJECT_NAME?.trim() || 'magireader';
const environment = required('PAGES_ENVIRONMENT');
if (environment !== 'preview' && environment !== 'production') {
  throw new Error('PAGES_ENVIRONMENT must be preview or production.');
}

const namespaceId = required('SUBMISSIONS_KV_NAMESPACE_ID');
if (!/^[a-f0-9]{32}$/u.test(namespaceId)) {
  throw new Error('SUBMISSIONS_KV_NAMESPACE_ID is not a 32-character ID.');
}

const plainText = (value) => ({ type: 'plain_text', value });
const secretText = (value) => ({ type: 'secret_text', value });
const envVars = {
  EXEDRA_WIKI_BASE_URL: plainText('https://exedra.wiki'),
  TURNSTILE_SITE_KEY: plainText(required('TURNSTILE_SITE_KEY')),
  TURNSTILE_ALLOWED_HOSTNAMES: plainText(
    required('TURNSTILE_ALLOWED_HOSTNAMES'),
  ),
  PROOFREADING_TARGET_BRANCH: plainText('main'),
  PROOFREADING_SOURCE_COMMIT: plainText(required('GITHUB_SHA')),
  PROOFREADING_ALLOW_GITHUB_ADMIN: plainText('true'),
  PROOFREADING_GITHUB_REPO: plainText('HiiragiNemu/magi-reader'),
  PROOFREADING_TURNSTILE_TEST_MODE: plainText(
    required('TURNSTILE_TEST_MODE'),
  ),
};

for (const [name, value] of [
  ['TURNSTILE_SECRET_KEY', process.env.TURNSTILE_SECRET_KEY],
  ['PROOFREADING_GITHUB_TOKEN', process.env.PROOFREADING_GITHUB_TOKEN],
  ['SUBMISSIONS_ADMIN_TOKEN', process.env.SUBMISSIONS_ADMIN_TOKEN],
]) {
  const normalized = value?.trim();
  if (normalized) envVars[name] = secretText(normalized);
}

const endpoint =
  `https://api.cloudflare.com/client/v4/accounts/${accountId}` +
  `/pages/projects/${encodeURIComponent(projectName)}`;
const response = await fetch(endpoint, {
  method: 'PATCH',
  headers: {
    Authorization: `Bearer ${apiToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    deployment_configs: {
      [environment]: {
        compatibility_date: '2026-02-14',
        compatibility_flags: ['nodejs_compat', 'global_fetch_strictly_public'],
        env_vars: envVars,
        kv_namespaces: {
          SUBMISSIONS_KV: { namespace_id: namespaceId },
        },
      },
    },
  }),
});
const payload = await response.json();
if (!response.ok || payload?.success !== true) {
  const messages = (payload?.errors || [])
    .map((error) => error?.message)
    .filter(Boolean)
    .join('; ');
  throw new Error(
    `Cloudflare Pages project update failed (${response.status}): ${messages}`,
  );
}

const applied = payload.result?.deployment_configs?.[environment];
if (applied?.kv_namespaces?.SUBMISSIONS_KV?.namespace_id !== namespaceId) {
  throw new Error('Cloudflare did not return the expected SUBMISSIONS_KV binding.');
}
console.log(
  JSON.stringify({
    project: projectName,
    environment,
    sharedAdminConfigured: Boolean(process.env.SUBMISSIONS_ADMIN_TOKEN?.trim()),
    serverPrConfigured: Boolean(
      process.env.PROOFREADING_GITHUB_TOKEN?.trim(),
    ),
    turnstileTestMode: process.env.TURNSTILE_TEST_MODE === 'true',
  }),
);
