import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const workerSource = await readFile(
  new URL('../public/search-worker.js', import.meta.url),
  'utf8',
);

const CHUNK_BYTES = 1024 * 1024;
const sha256 = payload => createHash('sha256').update(payload).digest('hex');
const split = (payload, bytes) => {
  const result = [];
  for (let offset = 0; offset < payload.byteLength; offset += bytes) {
    result.push(payload.subarray(offset, offset + bytes));
  }
  return result;
};

const responseFor = payload => ({
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

const makeWorker = fetchImpl => {
  let handler;
  const posted = [];
  const waiters = [];
  const self = {
    addEventListener(type, callback) {
      if (type === 'message') handler = callback;
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
    Uint32Array,
  });
  vm.runInContext(workerSource, context, { filename: 'search-worker.js' });
  return {
    post(data) {
      assert.ok(handler);
      handler({ data });
    },
    posted,
    nextMessage() {
      return new Promise(resolve => waiters.push(resolve));
    },
  };
};

const waitForResult = async (worker, sequence) => {
  for (;;) {
    const message = await worker.nextMessage();
    if (message.type === 'results' && message.sequence === sequence) return message;
    if (message.type === 'error' && message.sequence === sequence) {
      throw new Error(message.message);
    }
  }
};

test('same-origin physical v2 chunks reassemble one verified JSON stream', async () => {
  assert.match(workerSource, /SEARCH_CHUNK_DELIVERY_RUNTIME_V1/u);
  // Production v2 is fixed at 1 MiB. Make the first searchable row slightly
  // larger than one chunk so this fixture proves real cross-file reassembly
  // instead of weakening the protocol to tiny synthetic chunk sizes.
  const payload = new TextEncoder().encode(JSON.stringify([
    {
      id: 'chunked-1',
      c: `鹿目圆：简体中文全文搜索${'x'.repeat(CHUNK_BYTES + 256)}`,
      l: 'cn',
    },
    { id: 'chunked-2', c: '暁美ほむら：約束', l: 'jp' },
  ]));
  const parts = split(payload, CHUNK_BYTES);
  assert.equal(parts.length, 2);
  const globalSha = sha256(payload);
  const base = `/search-chunks/exedra/${globalSha}/`;
  const fetched = [];
  const worker = makeWorker(async (url, options) => {
    fetched.push([String(url), options.credentials, options.cache]);
    const match = String(url).match(/(\d{4})\.part$/u);
    assert.ok(match, `unexpected URL: ${url}`);
    return responseFor(parts[Number(match[1])]);
  });
  worker.post({
    type: 'init',
    sources: [{
      chunk_base_url: base,
      version: 2,
      sha256: globalSha,
      bytes: payload.byteLength,
      entries: 2,
      chunk_bytes: CHUNK_BYTES,
      chunks: parts.map(part => ({
        bytes: part.byteLength,
        sha256: sha256(part),
      })),
    }],
  });
  worker.post({
    type: 'search',
    sequence: 41,
    query: '简体中文',
    includeJapanese: false,
  });

  const result = await waitForResult(worker, 41);
  assert.equal(result.matches[0][0], 'chunked-1');
  assert.deepEqual(
    fetched.map(item => item[0]),
    parts.map((_, index) => `${base}${String(index).padStart(4, '0')}.part`),
  );
  assert.ok(fetched.every(item => item[1] === 'same-origin'));
});

test('a broken physical chunk falls through to the existing R2 single-object source', async () => {
  const payload = new TextEncoder().encode(JSON.stringify([
    { id: 'fallback-1', c: '环彩羽：回退搜索', l: 'cn' },
  ]));
  const parts = split(payload, CHUNK_BYTES);
  assert.equal(parts.length, 1);
  const globalSha = sha256(payload);
  const base = `/search-chunks/magireco/${globalSha}/`;
  const r2 = `https://example.invalid/search/${globalSha}.json`;
  const fetched = [];
  const worker = makeWorker(async (url) => {
    fetched.push(String(url));
    if (String(url).startsWith(base)) {
      return { ok: false, status: 404, headers: { get: () => null } };
    }
    assert.equal(String(url), r2);
    return responseFor(payload);
  });
  const common = {
    version: 2,
    sha256: globalSha,
    bytes: payload.byteLength,
    entries: 1,
    chunk_bytes: CHUNK_BYTES,
    chunks: parts.map(part => ({ bytes: part.byteLength, sha256: sha256(part) })),
  };
  worker.post({
    type: 'init',
    sources: [
      { ...common, chunk_base_url: base },
      { ...common, url: r2 },
    ],
  });
  worker.post({
    type: 'search',
    sequence: 42,
    query: '回退',
    includeJapanese: false,
  });

  const result = await waitForResult(worker, 42);
  assert.equal(result.matches[0][0], 'fallback-1');
  assert.equal(fetched[0], `${base}0000.part`);
  assert.equal(fetched.at(-1), r2);
});
