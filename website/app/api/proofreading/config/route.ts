import { NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import { getUsableAdminToken } from '@/lib/submission-security';

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };

export async function GET() {
  const { env } = await getCloudflareContext({ async: true });
  const siteKey = env.TURNSTILE_SITE_KEY?.trim() || '';
  return NextResponse.json(
    {
      submissions_enabled: Boolean(
        env.SUBMISSIONS_KV && siteKey && env.TURNSTILE_SECRET_KEY?.trim(),
      ),
      turnstile_site_key: siteKey,
      target_branch: env.PROOFREADING_TARGET_BRANCH?.trim() || 'main',
      source_revision: env.PROOFREADING_SOURCE_COMMIT?.trim() || 'unknown',
      github_admin_auth:
        env.PROOFREADING_ALLOW_GITHUB_ADMIN?.trim().toLowerCase() === 'true',
      shared_admin_auth: Boolean(
        getUsableAdminToken(env.SUBMISSIONS_ADMIN_TOKEN),
      ),
      server_pr_creation: Boolean(
        env.PROOFREADING_GITHUB_TOKEN?.trim(),
      ),
      turnstile_test_mode:
        env.PROOFREADING_TURNSTILE_TEST_MODE?.trim().toLowerCase() === 'true',
    },
    { headers: NO_STORE_HEADERS },
  );
}
