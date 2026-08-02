import assert from 'node:assert/strict';
import test from 'node:test';

import {
  fetchBoundedResponseBytes,
  readBoundedResponseBytes,
} from './bounded-response.ts';

test('bounded response stops a chunked body before retaining beyond its limit', async () => {
  let cancelled = false;
  const response = new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new Uint8Array([1, 2]));
      controller.enqueue(new Uint8Array([3, 4]));
    },
    cancel() {
      cancelled = true;
    },
  }));
  await assert.rejects(
    readBoundedResponseBytes(response, 3, '测试响应'),
    /测试响应超过大小限制/u,
  );
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(cancelled, true);
});

test('bounded fetch cancels a declared oversized or failed response body', async () => {
  let oversizedCancelled = false;
  const oversized = new Response(new ReadableStream<Uint8Array>({
    cancel() {
      oversizedCancelled = true;
    },
  }), { headers: { 'Content-Length': '9' } });
  await assert.rejects(
    fetchBoundedResponseBytes(
      async () => oversized,
      { label: '大响应', maxBytes: 8, timeoutMs: 1_000 },
    ),
    /大响应超过大小限制/u,
  );
  assert.equal(oversizedCancelled, true);

  let failedCancelled = false;
  const failed = new Response(new ReadableStream<Uint8Array>({
    cancel() {
      failedCancelled = true;
    },
  }), { status: 503 });
  await assert.rejects(
    fetchBoundedResponseBytes(
      async () => failed,
      { label: '失败响应', maxBytes: 8, timeoutMs: 1_000 },
    ),
    /HTTP 503/u,
  );
  assert.equal(failedCancelled, true);
});

test('bounded fetch aborts both a stalled header wait and a stalled body', async () => {
  const headerSignals: AbortSignal[] = [];
  await assert.rejects(
    fetchBoundedResponseBytes(
      signal => {
        headerSignals.push(signal);
        return new Promise<Response>(() => undefined);
      },
      { label: '响应头', maxBytes: 8, timeoutMs: 20 },
    ),
    /响应头读取超时/u,
  );
  assert.equal(headerSignals.length, 1);
  assert.equal(headerSignals[0]!.aborted, true);

  let bodyCancelled = false;
  const stalled = new Response(new ReadableStream<Uint8Array>({
    cancel() {
      bodyCancelled = true;
    },
  }));
  await assert.rejects(
    fetchBoundedResponseBytes(
      async () => stalled,
      { label: '响应体', maxBytes: 8, timeoutMs: 20 },
    ),
    /响应体读取超时/u,
  );
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(bodyCancelled, true);
});
