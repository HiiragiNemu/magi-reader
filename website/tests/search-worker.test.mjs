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

const splitPayload = (payload, chunkBytes) => {
  const chunks = [];
  for (let offset = 0; offset < payload.byteLength; offset += chunkBytes) {
    chunks.push(payload.subarray(offset, offset + chunkBytes));
  }
  return chunks;
};

const makeV2Source = (payload, entries, chunkBytes = 31) => ({
  url: 'https://example.invalid/search_content.json',
  version: 2,
  sha256: sha256(payload),
  bytes: payload.byteLength,
  entries,
  chunk_bytes: chunkBytes,
  chunks: splitPayload(payload, chunkBytes).map(chunk => ({
    bytes: chunk.byteLength,
    sha256: sha256(chunk),
  })),
});

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
    AbortController,
    console,
    crypto: webcrypto,
    DOMException,
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

const digestWithWorkerSha = (parts) => {
  const self = {
    addEventListener() {},
    postMessage() {},
  };
  const context = vm.createContext({
    AbortController,
    console,
    crypto: webcrypto,
    DOMException,
    fetch() {},
    self,
    TextDecoder,
    Uint8Array,
    Uint32Array,
  });
  vm.runInContext(
    `${workerSource}
    self.__digestParts = (inputParts) => {
      const hasher = new StreamingSha256();
      for (const part of inputParts) hasher.update(part);
      return hasher.digestHex();
    };`,
    context,
    { filename: 'search-worker-sha256.js' },
  );
  return self.__digestParts(parts);
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

test('streaming SHA-256 matches standard vectors across update boundaries', () => {
  const vectors = [
    [],
    [new TextEncoder().encode('abc')],
    [
      new TextEncoder().encode('a'.repeat(31)),
      new TextEncoder().encode('a'.repeat(33)),
    ],
    [
      new TextEncoder().encode('环彩'),
      new TextEncoder().encode('羽'.repeat(100)),
    ],
  ];
  for (const parts of vectors) {
    const expected = createHash('sha256');
    for (const part of parts) expected.update(part);
    assert.equal(digestWithWorkerSha(parts), expected.digest('hex'));
  }
});

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

const responseForChunks = (payload, networkChunkBytes) => {
  const chunks = splitPayload(payload, networkChunkBytes);
  return {
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
        let index = 0;
        return {
          async read() {
            if (index >= chunks.length) return { done: true };
            const value = chunks[index];
            index += 1;
            return { done: false, value };
          },
          async cancel() {},
          releaseLock() {},
        };
      },
    },
  };
};

test('cancel aborts an in-flight full-text index download', async () => {
  let markStarted;
  const started = new Promise(resolve => {
    markStarted = resolve;
  });
  let requestSignal;
  const worker = makeWorker(async (_url, options) => {
    requestSignal = options.signal;
    markStarted();
    return await new Promise((_resolve, reject) => {
      options.signal.addEventListener(
        'abort',
        () => reject(new DOMException('Aborted', 'AbortError')),
        { once: true },
      );
    });
  });
  worker.post({
    type: 'init',
    sources: [{
      url: 'https://example.invalid/search/slow.json',
      sha256: '0'.repeat(64),
      bytes: 1024,
      entries: 1,
    }],
  });
  worker.post({
    type: 'search',
    sequence: 5,
    query: '正文',
    includeJapanese: false,
  });

  await started;
  worker.post({ type: 'cancel', sequence: 6 });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(requestSignal?.aborted, true);
  assert.equal(
    worker.posted.some(message => message.type === 'error'),
    false,
  );
});

test('v2 streams escaped Unicode entries across manifest and network boundaries', async () => {
  const payload = makePayload([
    {
      id: 'story-streamed',
      c: '环彩羽: 跨块✨字符串，包含引号"、反斜线\\与换行\n后的契约',
      l: 'cn',
    },
    {
      id: 'story-nested-looking',
      c: '鹿目圆: 台词里的 {括号} 与 [数组] 不改变 JSON 层级',
      l: 'cn',
    },
  ]);
  const source = makeV2Source(payload, 2, 23);
  const worker = makeWorker(async () => responseForChunks(payload, 7));
  worker.post({ type: 'init', sources: [source] });
  worker.post({
    type: 'search',
    sequence: 7,
    query: '换行后的契约',
    includeJapanese: false,
  });

  const result = await waitForResult(worker, 7);
  assert.equal(result.matches.length, 1);
  assert.equal(result.matches[0][0], 'story-streamed');
});

test('v2 rejects a per-chunk hash mismatch before accepting entries', async () => {
  const payload = makePayload([
    { id: 'story-bad-chunk', c: '块校验失败', l: 'cn' },
  ]);
  const source = makeV2Source(payload, 1, 19);
  source.chunks[1].sha256 = '0'.repeat(64);
  const worker = makeWorker(async () => responseForChunks(payload, 5));
  worker.post({ type: 'init', sources: [source] });
  worker.post({
    type: 'search',
    sequence: 8,
    query: '校验',
    includeJapanese: false,
  });

  for (;;) {
    const message = await worker.nextMessage();
    if (message.type !== 'error' || message.sequence !== 8) continue;
    assert.match(message.message, /第 2 块校验值/u);
    break;
  }
  assert.equal(
    worker.posted.some(message => message.type === 'results'),
    false,
  );
});

test('v2 cancellation aborts a partially consumed streamed response', async () => {
  const payload = makePayload([
    { id: 'story-cancel-v2', c: '取消中的正文', l: 'cn' },
  ]);
  const source = makeV2Source(payload, 1, 17);
  let markWaiting;
  const waiting = new Promise(resolve => {
    markWaiting = resolve;
  });
  let requestSignal;
  let readerCancelled = false;
  const worker = makeWorker(async (_url, options) => {
    requestSignal = options.signal;
    let reads = 0;
    return {
      ok: true,
      status: 200,
      headers: { get: () => String(payload.byteLength) },
      body: {
        getReader() {
          return {
            async read() {
              reads += 1;
              if (reads === 1) {
                return { done: false, value: payload.subarray(0, 5) };
              }
              markWaiting();
              return await new Promise((_resolve, reject) => {
                options.signal.addEventListener(
                  'abort',
                  () => reject(new DOMException('Aborted', 'AbortError')),
                  { once: true },
                );
              });
            },
            async cancel() {
              readerCancelled = true;
            },
            releaseLock() {},
          };
        },
      },
    };
  });
  worker.post({ type: 'init', sources: [source] });
  worker.post({
    type: 'search',
    sequence: 9,
    query: '正文',
    includeJapanese: false,
  });

  await waiting;
  worker.post({ type: 'cancel', sequence: 10 });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(requestSignal?.aborted, true);
  assert.equal(readerCancelled, true);
  assert.equal(
    worker.posted.some(message => message.type === 'error'),
    false,
  );
});

test('v2 enforces the manifest entry limit while parsing the top-level array', async () => {
  const payload = makePayload([
    { id: 'story-one', c: '第一条', l: 'cn' },
    { id: 'story-two', c: '第二条', l: 'cn' },
  ]);
  const source = makeV2Source(payload, 1, 29);
  const worker = makeWorker(async () => responseForChunks(payload, 11));
  worker.post({ type: 'init', sources: [source] });
  worker.post({
    type: 'search',
    sequence: 11,
    query: '第一条',
    includeJapanese: false,
  });

  for (;;) {
    const message = await worker.nextMessage();
    if (message.type !== 'error' || message.sequence !== 11) continue;
    assert.equal(message.message, '索引条目数与清单不一致');
    break;
  }
});

test('rejects a source whose declared global entry count exceeds the hard limit', async () => {
  let fetched = false;
  const worker = makeWorker(async () => {
    fetched = true;
    throw new Error('invalid source must not be fetched');
  });
  worker.post({
    type: 'init',
    sources: [{
      url: 'https://example.invalid/search_content.json',
      version: 2,
      sha256: 'a'.repeat(64),
      bytes: 2,
      entries: 1_000_001,
      chunk_bytes: 2,
      chunks: [{ bytes: 2, sha256: 'b'.repeat(64) }],
    }],
  });
  worker.post({
    type: 'search',
    sequence: 12,
    query: '正文',
    includeJapanese: false,
  });

  for (;;) {
    const message = await worker.nextMessage();
    if (message.type !== 'error' || message.sequence !== 12) continue;
    assert.equal(message.message, '正文搜索暂时不可用');
    break;
  }
  assert.equal(fetched, false);
});

test('rejects a content-addressed URL whose object hash disagrees with the manifest', async () => {
  const payload = makePayload([
    { id: 'story-addressed', c: '内容寻址', l: 'cn' },
  ]);
  const source = {
    ...makeV2Source(payload, 1, 17),
    url: `https://example.invalid/search/${'0'.repeat(64)}.json`,
  };
  let fetched = false;
  const worker = makeWorker(async () => {
    fetched = true;
    return responseFor(payload);
  });
  worker.post({ type: 'init', sources: [source] });
  worker.post({
    type: 'search',
    sequence: 13,
    query: '寻址',
    includeJapanese: false,
  });

  for (;;) {
    const message = await worker.nextMessage();
    if (message.type !== 'error' || message.sequence !== 13) continue;
    assert.equal(message.message, '正文搜索暂时不可用');
    break;
  }
  assert.equal(fetched, false);
});

test('v2 rejects chunk-valid content that disagrees with the global object hash', async () => {
  const payload = makePayload([
    { id: 'story-global-mismatch', c: '整体校验', l: 'cn' },
  ]);
  const source = makeV2Source(payload, 1, 17);
  source.sha256 = 'a'.repeat(64);
  source.url = `https://example.invalid/search/${source.sha256}.json`;
  const worker = makeWorker(async () => responseForChunks(payload, 5));
  worker.post({ type: 'init', sources: [source] });
  worker.post({
    type: 'search',
    sequence: 14,
    query: '整体',
    includeJapanese: false,
  });

  for (;;) {
    const message = await worker.nextMessage();
    if (message.type !== 'error' || message.sequence !== 14) continue;
    assert.equal(message.message, '索引校验值与清单不一致');
    break;
  }
  assert.equal(
    worker.posted.some(message => message.type === 'results'),
    false,
  );
});
