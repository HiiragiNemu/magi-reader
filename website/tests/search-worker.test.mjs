import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const workerSource = await readFile(
  new URL('../public/search-worker.js', import.meta.url),
  'utf8',
);

const makePayload = (entries) =>
  new TextEncoder().encode(JSON.stringify(entries));

const sha256 = (payload) =>
  createHash('sha256').update(payload).digest('hex');

const makeWorker = (fetchImpl) => {
  let messageHandler;
  const posted = [];
  const waiters = [];
  const self = {
    addEventListener(type, handler) {
      if (type === 'message') messageHandler = handler;
    },
    postMessage(message) {
      posted.push(message);
      for (const waiter of waiters.splice(0)) waiter(message);
    },
  };
  const context = vm.createContext({
    console,
    crypto: webcrypto,
    fetch: fetchImpl,
    self,
    setTimeout,
    TextDecoder,
    Uint8Array,
  });
  vm.runInContext(workerSource, context, { filename: 'search-worker.js' });

  return {
    post(data) {
      assert.ok(messageHandler, 'worker message handler was registered');
      messageHandler({ data });
    },
    posted,
    nextMessage() {
      return new Promise((resolve) => waiters.push(resolve));
    },
  };
};

const responseFor = (payload) => ({
  ok: true,
  status: 200,
  headers: {
    get(name) {
      return name.toLowerCase() === 'content-length'
        ? String(payload.byteLength)
        : null;
    },
  },
  body: {
    getReader() {
      let consumed = false;
      return {
        async read() {
          if (consumed) return { done: true };
          consumed = true;
          return { done: false, value: payload };
        },
        async cancel() {},
        releaseLock() {},
      };
    },
  },
});

const waitForResult = async (worker, sequence) => {
  for (;;) {
    const message = await worker.nextMessage();
    if (message.type === 'results' && message.sequence === sequence) return message;
  }
};

test('queues a search until a verified content-addressed source is initialized', async () => {
  const payload = makePayload([
    { id: 'story-1', c: '鹿目圆: 魔法少女', l: 'cn' },
  ]);
  const fetched = [];
  const worker = makeWorker(async (url, options) => {
    fetched.push([url, options.cache]);
    return responseFor(payload);
  });

  worker.post({
    type: 'search',
    sequence: 1,
    query: '魔法少女',
    includeJapanese: false,
  });
  worker.post({
    type: 'init',
    sources: [{
      url: 'https://example.invalid/search/hash.json',
      sha256: sha256(payload),
      bytes: payload.byteLength,
      entries: 1,
    }],
  });

  const result = await waitForResult(worker, 1);
  assert.deepEqual(fetched, [
    ['https://example.invalid/search/hash.json', 'no-cache'],
  ]);
  assert.equal(JSON.stringify(result.matches), '[["story-1","魔法少女"]]');
});

test('rejects a hash mismatch and safely falls back to another verified source', async () => {
  const payload = makePayload([
    { id: 'story-2', c: '暁美ほむら: 約束', l: 'jp' },
  ]);
  const fetched = [];
  const worker = makeWorker(async (url, options) => {
    fetched.push([url, options.cache]);
    return responseFor(payload);
  });
  worker.post({
    type: 'init',
    sources: [
      {
        url: 'https://example.invalid/search/bad.json',
        sha256: '0'.repeat(64),
        bytes: payload.byteLength,
        entries: 1,
      },
      {
        url: 'https://example.invalid/search_content.json',
        sha256: sha256(payload),
        bytes: payload.byteLength,
        entries: 1,
      },
    ],
  });
  worker.post({
    type: 'search',
    sequence: 2,
    query: '約束',
    includeJapanese: true,
  });

  const result = await waitForResult(worker, 2);
  assert.deepEqual(fetched, [
    ['https://example.invalid/search/bad.json', 'no-cache'],
    ['https://example.invalid/search_content.json', 'no-cache'],
  ]);
  assert.equal(result.matches[0][0], 'story-2');
});

test('cancels a streamed response as soon as it exceeds the manifest size', async () => {
  const payload = makePayload([
    { id: 'story-3', c: '超出清单大小', l: 'cn' },
  ]);
  let cancelled = false;
  let reads = 0;
  const response = {
    ok: true,
    status: 200,
    headers: { get: () => null },
    body: {
      getReader() {
        return {
          async read() {
            reads += 1;
            if (reads === 1) return { done: false, value: payload.subarray(0, 4) };
            if (reads === 2) return { done: false, value: payload.subarray(4, 9) };
            throw new Error('超限后不应继续读取');
          },
          async cancel() {
            cancelled = true;
          },
          releaseLock() {},
        };
      },
    },
  };
  const worker = makeWorker(async () => response);
  worker.post({
    type: 'init',
    sources: [{
      url: 'https://example.invalid/search/too-large.json',
      sha256: '0'.repeat(64),
      bytes: 8,
      entries: 1,
    }],
  });
  worker.post({
    type: 'search',
    sequence: 3,
    query: '清单',
    includeJapanese: false,
  });

  for (;;) {
    const message = await worker.nextMessage();
    if (message.type !== 'error' || message.sequence !== 3) continue;
    assert.equal(message.message, '索引超过大小限制');
    break;
  }
  assert.equal(cancelled, true);
  assert.equal(reads, 2);
});

test('rejects an oversized declared content-length before opening the stream', async () => {
  let opened = false;
  let cancelled = false;
  const worker = makeWorker(async () => ({
    ok: true,
    status: 200,
    headers: {
      get: () => String(256 * 1024 * 1024 + 1),
    },
    body: {
      async cancel() {
        cancelled = true;
      },
      getReader() {
        opened = true;
        throw new Error('不应打开超大响应');
      },
    },
  }));
  worker.post({
    type: 'init',
    sources: [{
      url: 'https://example.invalid/search_content.json',
      sha256: '0'.repeat(64),
      bytes: 256 * 1024 * 1024,
      entries: 1,
    }],
  });
  worker.post({
    type: 'search',
    sequence: 4,
    query: '测试',
    includeJapanese: false,
  });

  for (;;) {
    const message = await worker.nextMessage();
    if (message.type !== 'error' || message.sequence !== 4) continue;
    assert.equal(message.message, '索引超过大小限制');
    break;
  }
  assert.equal(cancelled, true);
  assert.equal(opened, false);
});
