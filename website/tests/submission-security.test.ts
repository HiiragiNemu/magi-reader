import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  getAdminAccessConfiguration,
  getRateLimitIdentity,
  getUsableAdminToken,
  MIN_ADMIN_TOKEN_LENGTH,
} from '../lib/submission-security.ts';

test('admin access stays disabled for missing or short runtime tokens', () => {
  assert.equal(getUsableAdminToken(undefined), null);
  assert.equal(getUsableAdminToken('x'.repeat(MIN_ADMIN_TOKEN_LENGTH - 1)), null);
  assert.equal(
    getUsableAdminToken(`  ${'x'.repeat(MIN_ADMIN_TOKEN_LENGTH)}  `),
    'x'.repeat(MIN_ADMIN_TOKEN_LENGTH),
  );
});

test('admin GET policy returns 503 when the runtime token is shorter than 32 characters', () => {
  assert.deepEqual(
    getAdminAccessConfiguration(
      true,
      'x'.repeat(MIN_ADMIN_TOKEN_LENGTH - 1),
    ),
    { ok: false, status: 503 },
  );
  assert.deepEqual(
    getAdminAccessConfiguration(false, 'x'.repeat(MIN_ADMIN_TOKEN_LENGTH)),
    { ok: false, status: 503 },
  );
  assert.deepEqual(
    getAdminAccessConfiguration(true, 'x'.repeat(MIN_ADMIN_TOKEN_LENGTH)),
    { ok: true, token: 'x'.repeat(MIN_ADMIN_TOKEN_LENGTH) },
  );
});

test('rate limiting prefers the Cloudflare-provided client IP', () => {
  const headers = new Headers({
    'cf-connecting-ip': '203.0.113.5',
    'x-forwarded-for': '198.51.100.8',
  });

  assert.equal(
    getRateLimitIdentity(headers, () => 'unused'),
    'cloudflare-ip:203.0.113.5',
  );
});

test('rate limiting never shares one unknown key when no client headers exist', () => {
  const first = getRateLimitIdentity(new Headers(), () => 'request-a');
  const second = getRateLimitIdentity(new Headers(), () => 'request-b');

  assert.equal(first, 'request:request-a');
  assert.equal(second, 'request:request-b');
  assert.notEqual(first, second);
});

test('invalid submissions are rejected before consuming shared-IP quota', () => {
  const routeSource = readFileSync(
    new URL('../app/api/submit/route.ts', import.meta.url),
    'utf8',
  );
  const validationIndex = routeSource.indexOf(
    'const validation = validateSubmission(bodyResult.value);',
  );
  const quotaIndex = routeSource.indexOf(
    'const rateLimit = await consumeRateLimit(kv, request);',
  );

  assert.notEqual(validationIndex, -1);
  assert.notEqual(quotaIndex, -1);
  assert.ok(validationIndex < quotaIndex);
});
