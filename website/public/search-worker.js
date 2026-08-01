const SEARCH_RESULT_LIMIT = 500;
const SEARCH_CHUNK_SIZE = 750;
const MAX_INDEX_BYTES = 256 * 1024 * 1024;
const MAX_INDEX_ENTRIES = 1_000_000;
const MAX_MANIFEST_CHUNKS = 4096;
const MAX_MANIFEST_CHUNK_BYTES = 1024 * 1024;
const MAX_INDEX_ENTRY_CHARS = 1024 * 1024;

let sources = [];
let entries = null;
let loadingPromise = null;
let activeLoadController = null;
let latestSequence = 0;
let initialized = false;
let pendingSearch = null;

const normalize = (value) => {
  let result = '';
  for (const character of String(value ?? '').normalize('NFKC').toLocaleLowerCase()) {
    if (/[\p{L}\p{N}]/u.test(character)) result += character;
  }
  return result;
};

const cleanContent = (value) =>
  String(value ?? '')
    .replace(/\\n/g, ' ')
    .replace(/[@\n\r]/g, ' ')
    .replace(/(^|\s)[^:：\s]+[:：]\s*/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const hexDigest = (buffer) =>
  Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, '0')).join('');

const SHA256_CONSTANTS = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
  0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
  0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
  0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
  0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
  0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

const rotateRight = (value, bits) =>
  (value >>> bits) | (value << (32 - bits));

class StreamingSha256 {
  constructor() {
    this.state = new Uint32Array([
      0x6a09e667,
      0xbb67ae85,
      0x3c6ef372,
      0xa54ff53a,
      0x510e527f,
      0x9b05688c,
      0x1f83d9ab,
      0x5be0cd19,
    ]);
    this.words = new Uint32Array(64);
    this.buffer = new Uint8Array(64);
    this.bufferLength = 0;
    this.bytesHashed = 0;
    this.finished = false;
    this.result = '';
  }

  compress(bytes, offset) {
    const words = this.words;
    for (let index = 0; index < 16; index += 1) {
      const cursor = offset + index * 4;
      words[index] = (
        (bytes[cursor] << 24) |
        (bytes[cursor + 1] << 16) |
        (bytes[cursor + 2] << 8) |
        bytes[cursor + 3]
      ) >>> 0;
    }
    for (let index = 16; index < 64; index += 1) {
      const word15 = words[index - 15];
      const word2 = words[index - 2];
      const sigma0 = (
        rotateRight(word15, 7) ^
        rotateRight(word15, 18) ^
        (word15 >>> 3)
      ) >>> 0;
      const sigma1 = (
        rotateRight(word2, 17) ^
        rotateRight(word2, 19) ^
        (word2 >>> 10)
      ) >>> 0;
      words[index] = (
        words[index - 16] +
        sigma0 +
        words[index - 7] +
        sigma1
      ) >>> 0;
    }

    let a = this.state[0];
    let b = this.state[1];
    let c = this.state[2];
    let d = this.state[3];
    let e = this.state[4];
    let f = this.state[5];
    let g = this.state[6];
    let h = this.state[7];
    for (let index = 0; index < 64; index += 1) {
      const bigSigma1 = (
        rotateRight(e, 6) ^
        rotateRight(e, 11) ^
        rotateRight(e, 25)
      ) >>> 0;
      const choose = ((e & f) ^ (~e & g)) >>> 0;
      const temporary1 = (
        h +
        bigSigma1 +
        choose +
        SHA256_CONSTANTS[index] +
        words[index]
      ) >>> 0;
      const bigSigma0 = (
        rotateRight(a, 2) ^
        rotateRight(a, 13) ^
        rotateRight(a, 22)
      ) >>> 0;
      const majority = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
      const temporary2 = (bigSigma0 + majority) >>> 0;

      h = g;
      g = f;
      f = e;
      e = (d + temporary1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temporary1 + temporary2) >>> 0;
    }

    this.state[0] = (this.state[0] + a) >>> 0;
    this.state[1] = (this.state[1] + b) >>> 0;
    this.state[2] = (this.state[2] + c) >>> 0;
    this.state[3] = (this.state[3] + d) >>> 0;
    this.state[4] = (this.state[4] + e) >>> 0;
    this.state[5] = (this.state[5] + f) >>> 0;
    this.state[6] = (this.state[6] + g) >>> 0;
    this.state[7] = (this.state[7] + h) >>> 0;
  }

  update(bytes) {
    if (this.finished) throw new Error('SHA-256 已结束');
    if (!(bytes instanceof Uint8Array)) throw new TypeError('SHA-256 输入无效');
    this.bytesHashed += bytes.byteLength;
    if (!Number.isSafeInteger(this.bytesHashed) || this.bytesHashed > MAX_INDEX_BYTES) {
      throw new Error('索引超过大小限制');
    }

    let offset = 0;
    if (this.bufferLength > 0) {
      const copyLength = Math.min(
        bytes.byteLength,
        this.buffer.byteLength - this.bufferLength,
      );
      this.buffer.set(bytes.subarray(0, copyLength), this.bufferLength);
      this.bufferLength += copyLength;
      offset += copyLength;
      if (this.bufferLength === this.buffer.byteLength) {
        this.compress(this.buffer, 0);
        this.bufferLength = 0;
      }
    }
    while (offset + 64 <= bytes.byteLength) {
      this.compress(bytes, offset);
      offset += 64;
    }
    if (offset < bytes.byteLength) {
      this.buffer.set(bytes.subarray(offset), 0);
      this.bufferLength = bytes.byteLength - offset;
    }
  }

  digestHex() {
    if (this.finished) return this.result;
    const bitLengthHigh = Math.floor(this.bytesHashed / 0x20000000) >>> 0;
    const bitLengthLow = (this.bytesHashed * 8) >>> 0;

    this.buffer[this.bufferLength] = 0x80;
    this.bufferLength += 1;
    if (this.bufferLength > 56) {
      this.buffer.fill(0, this.bufferLength);
      this.compress(this.buffer, 0);
      this.bufferLength = 0;
    }
    this.buffer.fill(0, this.bufferLength, 56);
    this.buffer[56] = bitLengthHigh >>> 24;
    this.buffer[57] = bitLengthHigh >>> 16;
    this.buffer[58] = bitLengthHigh >>> 8;
    this.buffer[59] = bitLengthHigh;
    this.buffer[60] = bitLengthLow >>> 24;
    this.buffer[61] = bitLengthLow >>> 16;
    this.buffer[62] = bitLengthLow >>> 8;
    this.buffer[63] = bitLengthLow;
    this.compress(this.buffer, 0);

    this.finished = true;
    this.result = Array.from(
      this.state,
      (word) => word.toString(16).padStart(8, '0'),
    ).join('');
    return this.result;
  }
}

const sanitizeSource = (source) => {
  if (!source || typeof source !== 'object' || typeof source.url !== 'string') {
    return null;
  }

  const sha256 = String(source.sha256 ?? '').toLowerCase();
  const bytes = Number(source.bytes);
  const expectedEntries = Number(source.entries);
  const version = source.version === 2 ? 2 : 1;
  if (
    (source.version !== undefined && source.version !== 1 && source.version !== 2) ||
    !/^[a-f0-9]{64}$/.test(sha256) ||
    !Number.isSafeInteger(bytes) ||
    bytes <= 0 ||
    bytes > MAX_INDEX_BYTES ||
    !Number.isSafeInteger(expectedEntries) ||
    expectedEntries <= 0 ||
    expectedEntries > MAX_INDEX_ENTRIES
  ) {
    return null;
  }
  const addressedHash = source.url.match(
    /\/search\/([a-f0-9]{64})\.json(?:[?#].*)?$/i,
  )?.[1]?.toLowerCase();
  if (addressedHash && addressedHash !== sha256) return null;

  const sanitized = {
    url: source.url,
    version,
    sha256,
    bytes,
    maxBytes: bytes,
    entries: expectedEntries,
  };

  if (version === 1) return sanitized;

  const chunkBytes = Number(source.chunk_bytes);
  const rawChunks = source.chunks;
  if (
    !Number.isSafeInteger(chunkBytes) ||
    chunkBytes <= 0 ||
    chunkBytes > MAX_MANIFEST_CHUNK_BYTES ||
    !Array.isArray(rawChunks) ||
    rawChunks.length === 0 ||
    rawChunks.length > MAX_MANIFEST_CHUNKS ||
    rawChunks.length !== Math.ceil(bytes / chunkBytes)
  ) {
    return null;
  }

  const chunks = [];
  let chunkTotal = 0;
  for (let index = 0; index < rawChunks.length; index += 1) {
    const rawChunk = rawChunks[index];
    if (!rawChunk || typeof rawChunk !== 'object') return null;
    const chunkLength = Number(rawChunk.bytes);
    const chunkSha256 = String(rawChunk.sha256 ?? '').toLowerCase();
    const finalChunk = index === rawChunks.length - 1;
    if (
      !Number.isSafeInteger(chunkLength) ||
      chunkLength <= 0 ||
      chunkLength > chunkBytes ||
      (!finalChunk && chunkLength !== chunkBytes) ||
      !/^[a-f0-9]{64}$/.test(chunkSha256)
    ) {
      return null;
    }
    chunkTotal += chunkLength;
    if (!Number.isSafeInteger(chunkTotal) || chunkTotal > bytes) return null;
    chunks.push({ bytes: chunkLength, sha256: chunkSha256 });
  }
  if (chunkTotal !== bytes) return null;

  return {
    ...sanitized,
    chunk_bytes: chunkBytes,
    chunks,
  };
};

const readBoundedResponse = async (response, source, signal) => {
  const limit = source.maxBytes ?? MAX_INDEX_BYTES;
  const declaredLengthRaw = response.headers?.get?.('content-length');
  if (declaredLengthRaw !== null && declaredLengthRaw !== undefined) {
    const declaredLength = Number(declaredLengthRaw);
    if (
      Number.isSafeInteger(declaredLength) &&
      declaredLength >= 0 &&
      declaredLength > limit
    ) {
      await response.body?.cancel?.('索引超过大小限制');
      throw new Error('索引超过大小限制');
    }
  }

  const reader = response.body?.getReader?.();
  if (!reader) throw new Error('索引响应无法安全读取');

  const payload = new Uint8Array(limit);
  let total = 0;
  try {
    for (;;) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const { done, value } = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array)) {
        await reader.cancel('索引响应数据无效');
        throw new Error('索引响应数据无效');
      }
      if (value.byteLength > limit - total) {
        await reader.cancel('索引超过大小限制');
        throw new Error('索引超过大小限制');
      }
      payload.set(value, total);
      total += value.byteLength;
    }
  } finally {
    reader.releaseLock?.();
  }

  return total === payload.byteLength ? payload : payload.slice(0, total);
};

const validateCompactEntry = (entry) => {
  if (
    !entry ||
    typeof entry.id !== 'string' ||
    entry.id.length === 0 ||
    typeof entry.c !== 'string' ||
    entry.c.length === 0 ||
    (entry.l !== 'cn' && entry.l !== 'jp')
  ) {
    throw new Error('索引条目格式不正确');
  }
  return { id: entry.id, c: entry.c, l: entry.l };
};

const isJsonWhitespace = (character) =>
  character === ' ' ||
  character === '\t' ||
  character === '\r' ||
  character === '\n';

const createStreamingArrayParser = (expectedEntries) => {
  const compactEntries = [];
  let phase = 'start';
  let inItem = false;
  let itemParts = [];
  let itemLength = 0;
  let stack = [];
  let inString = false;
  let escaped = false;

  const appendItemPart = (part) => {
    if (!part) return;
    if (itemLength + part.length > MAX_INDEX_ENTRY_CHARS) {
      throw new Error('索引单条内容超过大小限制');
    }
    itemParts.push(part);
    itemLength += part.length;
  };

  const finishItem = () => {
    if (compactEntries.length >= expectedEntries) {
      throw new Error('索引条目数与清单不一致');
    }
    let rawEntry;
    try {
      rawEntry = JSON.parse(itemParts.join(''));
    } catch {
      throw new Error('索引格式不正确');
    }
    compactEntries.push(validateCompactEntry(rawEntry));
    itemParts = [];
    itemLength = 0;
    stack = [];
    inString = false;
    escaped = false;
  };

  const beginItem = () => {
    inItem = true;
    itemParts = [];
    itemLength = 0;
    stack = ['{'];
    inString = false;
    escaped = false;
  };

  const push = (text) => {
    if (!text) return;
    let segmentStart = inItem ? 0 : -1;

    for (let index = 0; index < text.length; index += 1) {
      const character = text[index];
      if (inItem) {
        if (index - segmentStart + 1 > MAX_INDEX_ENTRY_CHARS - itemLength) {
          throw new Error('索引单条内容超过大小限制');
        }
        if (inString) {
          if (escaped) {
            escaped = false;
          } else if (character === '\\') {
            escaped = true;
          } else if (character === '"') {
            inString = false;
          }
          continue;
        }
        if (character === '"') {
          inString = true;
          continue;
        }
        if (character === '{' || character === '[') {
          stack.push(character);
          continue;
        }
        if (character === '}' || character === ']') {
          const opening = stack.pop();
          if (
            (character === '}' && opening !== '{') ||
            (character === ']' && opening !== '[')
          ) {
            throw new Error('索引格式不正确');
          }
          if (stack.length === 0) {
            appendItemPart(text.slice(segmentStart, index + 1));
            segmentStart = -1;
            inItem = false;
            finishItem();
            phase = 'separator';
          }
        }
        continue;
      }

      if (isJsonWhitespace(character)) continue;
      if (phase === 'start') {
        if (character !== '[') throw new Error('索引格式不正确');
        phase = 'valueOrEnd';
        continue;
      }
      if (phase === 'valueOrEnd' && character === ']') {
        phase = 'done';
        continue;
      }
      if (phase === 'valueOrEnd' || phase === 'value') {
        if (character !== '{') throw new Error('索引格式不正确');
        beginItem();
        segmentStart = index;
        continue;
      }
      if (phase === 'separator') {
        if (character === ',') {
          phase = 'value';
          continue;
        }
        if (character === ']') {
          phase = 'done';
          continue;
        }
        throw new Error('索引格式不正确');
      }
      if (phase === 'done') throw new Error('索引格式不正确');
    }

    if (inItem && segmentStart >= 0) {
      appendItemPart(text.slice(segmentStart));
    }
  };

  const finish = () => {
    if (inItem || phase !== 'done') throw new Error('索引格式不正确');
    if (compactEntries.length !== expectedEntries) {
      throw new Error('索引条目数与清单不一致');
    }
    return compactEntries;
  };

  return { push, finish };
};

const parseLegacyIndexResponse = async (response, source, signal) => {
  const payload = await readBoundedResponse(response, source, signal);
  if (source.bytes !== undefined && payload.byteLength !== source.bytes) {
    throw new Error('索引大小与清单不一致');
  }
  if (source.sha256) {
    const digest = hexDigest(await crypto.subtle.digest('SHA-256', payload));
    if (digest !== source.sha256) throw new Error('索引校验值与清单不一致');
  }

  const raw = JSON.parse(new TextDecoder().decode(payload));
  if (!Array.isArray(raw)) throw new Error('索引格式不正确');
  if (source.entries !== undefined && raw.length !== source.entries) {
    throw new Error('索引条目数与清单不一致');
  }

  for (const entry of raw) validateCompactEntry(entry);
  // Keep the parsed objects in their compact on-disk shape. Copying every
  // 79 MiB content string into a second normalized object graph caused a large
  // avoidable memory spike on some browsers.
  return raw;
};

const cancelReaderQuietly = async (reader, reason) => {
  try {
    await reader.cancel(reason);
  } catch {
    // The fetch may already have been aborted, which also closes the reader.
  }
};

const parseChunkedIndexResponse = async (response, source, signal) => {
  const declaredLengthRaw = response.headers?.get?.('content-length');
  if (declaredLengthRaw !== null && declaredLengthRaw !== undefined) {
    const declaredLength = Number(declaredLengthRaw);
    if (
      Number.isSafeInteger(declaredLength) &&
      declaredLength >= 0 &&
      declaredLength !== source.bytes
    ) {
      await response.body?.cancel?.('索引大小与清单不一致');
      throw new Error('索引大小与清单不一致');
    }
  }

  const reader = response.body?.getReader?.();
  if (!reader) throw new Error('索引响应无法安全读取');

  const decoder = new TextDecoder('utf-8', { fatal: true });
  const parser = createStreamingArrayParser(source.entries);
  let chunkIndex = 0;
  let chunkOffset = 0;
  let total = 0;
  let currentChunk = new Uint8Array(source.chunks[0].bytes);
  const overallHasher = new StreamingSha256();

  const finishChunk = async () => {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const expected = source.chunks[chunkIndex];
    const digest = hexDigest(
      await crypto.subtle.digest('SHA-256', currentChunk),
    );
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    if (digest !== expected.sha256) {
      throw new Error(`索引第 ${chunkIndex + 1} 块校验值与清单不一致`);
    }
    parser.push(decoder.decode(currentChunk, { stream: true }));
    chunkIndex += 1;
    chunkOffset = 0;
    currentChunk = chunkIndex < source.chunks.length
      ? new Uint8Array(source.chunks[chunkIndex].bytes)
      : null;
  };

  try {
    for (;;) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const { done, value } = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array)) {
        throw new Error('索引响应数据无效');
      }
      let valueOffset = 0;
      while (valueOffset < value.byteLength) {
        if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
        if (!currentChunk || total >= source.bytes) {
          throw new Error('索引超过大小限制');
        }
        const copyLength = Math.min(
          value.byteLength - valueOffset,
          currentChunk.byteLength - chunkOffset,
        );
        currentChunk.set(
          value.subarray(valueOffset, valueOffset + copyLength),
          chunkOffset,
        );
        overallHasher.update(
          value.subarray(valueOffset, valueOffset + copyLength),
        );
        valueOffset += copyLength;
        chunkOffset += copyLength;
        total += copyLength;
        if (chunkOffset === currentChunk.byteLength) await finishChunk();
      }
    }

    if (
      total !== source.bytes ||
      chunkIndex !== source.chunks.length ||
      currentChunk !== null ||
      chunkOffset !== 0
    ) {
      throw new Error('索引大小与清单不一致');
    }
    if (overallHasher.digestHex() !== source.sha256) {
      throw new Error('索引校验值与清单不一致');
    }
    parser.push(decoder.decode());
    return parser.finish();
  } catch (error) {
    await cancelReaderQuietly(reader, '索引读取已停止');
    throw error;
  } finally {
    reader.releaseLock?.();
  }
};

const parseIndexResponse = async (response, source, signal) =>
  source.version === 2
    ? parseChunkedIndexResponse(response, source, signal)
    : parseLegacyIndexResponse(response, source, signal);

const loadIndex = async () => {
  if (entries) return entries;
  if (loadingPromise && !activeLoadController?.signal.aborted) {
    return loadingPromise;
  }
  if (activeLoadController?.signal.aborted) loadingPromise = null;

  const task = (async () => {
    let lastError = null;
    for (const source of sources) {
      const controller = new AbortController();
      activeLoadController = controller;
      try {
        self.postMessage({ type: 'status', status: 'loading' });
        const response = await fetch(source.url, {
          // Revalidate the manifest-selected object so a locally cached 404
          // from pre-publication testing cannot mask a later successful upload.
          cache: source.sha256 ? 'no-cache' : 'force-cache',
          credentials: 'omit',
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        entries = await parseIndexResponse(
          response,
          source,
          controller.signal,
        );
        self.postMessage({ type: 'status', status: 'ready' });
        return entries;
      } catch (error) {
        if (controller.signal.aborted) throw error;
        lastError = error;
      } finally {
        if (activeLoadController === controller) {
          activeLoadController = null;
        }
      }
    }
    throw lastError instanceof Error ? lastError : new Error('正文搜索暂时不可用');
  })();
  loadingPromise = task;

  try {
    return await task;
  } catch (error) {
    if (loadingPromise === task) loadingPromise = null;
    throw error;
  }
};

const search = async ({ sequence, query, includeJapanese }) => {
  latestSequence = Math.max(latestSequence, sequence);
  try {
    const index = await loadIndex();
    if (sequence !== latestSequence) return;

    const normalizedQuery = normalize(query);
    const matches = [];
    const matchedIds = new Set();
    let truncated = false;

    for (let offset = 0; offset < index.length; offset += SEARCH_CHUNK_SIZE) {
      if (sequence !== latestSequence) return;
      const end = Math.min(offset + SEARCH_CHUNK_SIZE, index.length);

      for (let indexPosition = offset; indexPosition < end; indexPosition += 1) {
        const entry = index[indexPosition];
        if ((!includeJapanese && entry.l === 'jp') || matchedIds.has(entry.id)) continue;

        const normalizedContent = normalize(entry.c);
        const matchAt = normalizedContent.indexOf(normalizedQuery);
        if (matchAt < 0) continue;

        // The normalized offset is only a positioning hint. Keeping a little
        // extra context makes snippets useful even with full-width characters.
        const approximateAt = Math.min(matchAt, entry.c.length);
        const start = Math.max(0, approximateAt - 24);
        const endAt = Math.min(entry.c.length, approximateAt + query.length + 48);
        matches.push([
          entry.id,
          cleanContent(entry.c.slice(start, endAt)),
        ]);
        matchedIds.add(entry.id);

        if (matches.length >= SEARCH_RESULT_LIMIT) {
          truncated = true;
          break;
        }
      }

      if (truncated) break;
      await new Promise((resolve) => setTimeout(resolve, 0));
    }

    if (sequence === latestSequence) {
      self.postMessage({ type: 'results', sequence, matches, truncated });
    }
  } catch (error) {
    if (sequence === latestSequence) {
      self.postMessage({
        type: 'error',
        sequence,
        message: error instanceof Error ? error.message : '正文搜索暂时不可用',
      });
    }
  }
};

self.addEventListener('message', (event) => {
  const message = event.data;
  if (!message || typeof message !== 'object') return;

  if (message.type === 'init') {
    sources = Array.isArray(message.sources)
      ? message.sources.map(sanitizeSource).filter(Boolean)
      : [];
    initialized = true;
    const queuedSearch = pendingSearch;
    pendingSearch = null;
    if (queuedSearch) void search(queuedSearch);
    return;
  }

  if (message.type === 'cancel') {
    latestSequence = Math.max(latestSequence, Number(message.sequence) || 0);
    pendingSearch = null;
    activeLoadController?.abort();
    return;
  }

  if (message.type === 'search') {
    const request = {
      sequence: Number(message.sequence) || 0,
      query: String(message.query ?? ''),
      includeJapanese: Boolean(message.includeJapanese),
    };
    latestSequence = Math.max(latestSequence, request.sequence);
    if (!initialized) {
      pendingSearch = request;
    } else {
      void search(request);
    }
  }
});
