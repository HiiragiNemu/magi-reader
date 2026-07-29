import assert from 'node:assert/strict';
import test from 'node:test';

import { fetchMagirecoVoiceResponse } from '../lib/audio/voice-player.ts';

const CUE_ID = 'vo_char_3031_00_01';
const DIRECT_URL =
  'https://pub-70a248f1a6fe4ca597e7a10f8b95dfd8.r2.dev/voice/vo_char_3031_00_01_hca.hca';

test('uses the same-origin voice proxy when it succeeds', async () => {
  const requests: string[] = [];
  const response = await fetchMagirecoVoiceResponse(
    CUE_ID,
    new AbortController().signal,
    async input => {
      requests.push(String(input));
      return new Response(new Uint8Array([1, 2, 3]), { status: 200 });
    },
  );

  assert.equal(response.status, 200);
  assert.deepEqual(requests, [
    '/api/audio/magireco-voice/vo_char_3031_00_01',
  ]);
});

test('falls back to the fixed R2 URL after a retryable proxy response', async () => {
  const requests: string[] = [];
  const response = await fetchMagirecoVoiceResponse(
    CUE_ID,
    new AbortController().signal,
    async input => {
      requests.push(String(input));
      return requests.length === 1
        ? Response.json({ error: 'upstream unavailable' }, { status: 502 })
        : new Response(new Uint8Array([1, 2, 3]), { status: 200 });
    },
  );

  assert.equal(response.status, 200);
  assert.deepEqual(requests, [
    '/api/audio/magireco-voice/vo_char_3031_00_01',
    DIRECT_URL,
  ]);
});

test('falls back after a proxy network error but not after a definitive 404', async () => {
  const networkRequests: string[] = [];
  const recovered = await fetchMagirecoVoiceResponse(
    CUE_ID,
    new AbortController().signal,
    async input => {
      networkRequests.push(String(input));
      if (networkRequests.length === 1) throw new TypeError('network error');
      return new Response(new Uint8Array([1]), { status: 200 });
    },
  );
  assert.equal(recovered.status, 200);
  assert.deepEqual(networkRequests, [
    '/api/audio/magireco-voice/vo_char_3031_00_01',
    DIRECT_URL,
  ]);

  let calls = 0;
  await assert.rejects(
    fetchMagirecoVoiceResponse(
      CUE_ID,
      new AbortController().signal,
      async () => {
        calls += 1;
        return new Response(null, { status: 404 });
      },
    ),
    /加载失败 \(404\)/,
  );
  assert.equal(calls, 1);
});

test('does not retry an aborted proxy request', async () => {
  const controller = new AbortController();
  let calls = 0;

  await assert.rejects(
    fetchMagirecoVoiceResponse(
      CUE_ID,
      controller.signal,
      async () => {
        calls += 1;
        controller.abort();
        throw new DOMException('Aborted', 'AbortError');
      },
    ),
    error => error instanceof DOMException && error.name === 'AbortError',
  );
  assert.equal(calls, 1);
});
