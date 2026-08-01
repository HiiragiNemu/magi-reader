import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  discoverR2VoiceBucket,
  runDiscoveryCli,
} from './discover-cloudflare-r2-bucket.mjs';

const ACCOUNT_ID = 'a'.repeat(32);
const TARGET_DOMAIN = `pub-${'7'.repeat(32)}.r2.dev`;
const TOKEN = 'test-token-never-log-this';

const jsonResponse = (body, status = 200) => new Response(
  JSON.stringify(body),
  {
    status,
    headers: { 'content-type': 'application/json' },
  },
);

const listResponse = (buckets, cursor = undefined) => ({
  success: true,
  result: { buckets },
  result_info: cursor == null ? {} : { cursor },
});

const domainResponse = (domain, enabled = true) => ({
  success: true,
  result: {
    bucketId: 'b'.repeat(32),
    domain,
    enabled,
  },
});

test('R2 discovery requires an exact managed-domain match', async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url: String(url), options });
    if (String(url).includes('/r2/buckets?')) {
      return jsonResponse(listResponse([
        { name: 'wrong-voice', jurisdiction: 'default' },
        { name: 'right-voice', jurisdiction: 'eu' },
      ]));
    }
    if (String(url).includes('/wrong-voice/')) {
      return jsonResponse(domainResponse(`prefix.${TARGET_DOMAIN}`));
    }
    return jsonResponse(domainResponse(TARGET_DOMAIN));
  };

  const result = await discoverR2VoiceBucket({
    accountId: ACCOUNT_ID,
    apiToken: TOKEN,
    targetDomain: TARGET_DOMAIN,
    fetchImpl,
  });

  assert.deepEqual(result, {
    bucketName: 'right-voice',
    domain: TARGET_DOMAIN,
    publicAccessEnabled: true,
    listWasTruncated: false,
  });
  assert.equal(calls.length, 3);
  assert.match(calls[0].url, /per_page=1000/u);
  assert.equal(calls[2].options.headers['cf-r2-jurisdiction'], 'eu');
  assert.equal(calls[2].options.headers.Authorization, `Bearer ${TOKEN}`);
  assert.doesNotMatch(calls[2].url, new RegExp(TOKEN, 'u'));
});

test('permission failure produces an empty binding output and keeps fallback enabled', async () => {
  const directory = mkdtempSync(path.join(os.tmpdir(), 'r2-discovery-test-'));
  const output = path.join(directory, 'github-output.txt');
  const originalOutput = process.env.GITHUB_OUTPUT;
  process.env.GITHUB_OUTPUT = output;
  const messages = [];
  const originalLog = console.log;
  console.log = (message) => messages.push(String(message));
  try {
    const result = await runDiscoveryCli({
      argv: ['--target-domain', TARGET_DOMAIN],
      env: {
        CLOUDFLARE_ACCOUNT_ID: ACCOUNT_ID,
        CLOUDFLARE_API_TOKEN: TOKEN,
      },
      fetchImpl: async () => jsonResponse(
        { success: false, errors: [{ message: 'forbidden' }] },
        403,
      ),
    });

    assert.equal(result, null);
    assert.equal(
      readFileSync(output, 'utf8'),
      'bucket_name=\ndiscovery_status=fallback\n',
    );
    assert.ok(messages.some((message) => (
      message.startsWith('::warning::')
      && message.includes('R2 Storage Read')
    )));
    assert.ok(messages.every((message) => !message.includes(TOKEN)));
  } finally {
    console.log = originalLog;
    if (originalOutput == null) {
      delete process.env.GITHUB_OUTPUT;
    } else {
      process.env.GITHUB_OUTPUT = originalOutput;
    }
    rmSync(directory, { recursive: true, force: true });
  }
});

test('a missing exact match does not accept a suffix or disabled unrelated domain', async () => {
  const fetchImpl = async (url) => {
    if (String(url).includes('/r2/buckets?')) {
      return jsonResponse(listResponse([
        { name: 'suffix-match', jurisdiction: 'default' },
        { name: 'unrelated', jurisdiction: 'default' },
      ]));
    }
    if (String(url).includes('/suffix-match/')) {
      return jsonResponse(domainResponse(`${TARGET_DOMAIN}.example`, false));
    }
    return jsonResponse(domainResponse(`pub-${'8'.repeat(32)}.r2.dev`));
  };

  const result = await discoverR2VoiceBucket({
    accountId: ACCOUNT_ID,
    apiToken: TOKEN,
    targetDomain: TARGET_DOMAIN,
    fetchImpl,
  });
  assert.equal(result, null);
});

test('discovery rejects malformed account IDs before making a request', async () => {
  let called = false;
  await assert.rejects(
    discoverR2VoiceBucket({
      accountId: '../account',
      apiToken: TOKEN,
      targetDomain: TARGET_DOMAIN,
      fetchImpl: async () => {
        called = true;
        return jsonResponse({});
      },
    }),
    /CF_ACCOUNT_ID/u,
  );
  assert.equal(called, false);
});
