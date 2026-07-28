const SEARCH_RESULT_LIMIT = 500;
const SEARCH_CHUNK_SIZE = 750;
const MAX_INDEX_BYTES = 256 * 1024 * 1024;
const MAX_INDEX_ENTRIES = 1_000_000;

let sources = [];
let entries = null;
let loadingPromise = null;
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

const sanitizeSource = (source) => {
  if (!source || typeof source !== 'object' || typeof source.url !== 'string') {
    return null;
  }

  const sha256 = String(source.sha256 ?? '').toLowerCase();
  const bytes = Number(source.bytes);
  const expectedEntries = Number(source.entries);
  if (
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
  return {
    url: source.url,
    sha256,
    bytes,
    maxBytes: bytes,
    entries: expectedEntries,
  };
};

const readBoundedResponse = async (response, source) => {
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

  const chunks = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array)) {
        await reader.cancel('索引响应数据无效');
        throw new Error('索引响应数据无效');
      }
      total += value.byteLength;
      if (total > limit) {
        await reader.cancel('索引超过大小限制');
        throw new Error('索引超过大小限制');
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock?.();
  }

  const payload = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    payload.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return payload;
};

const parseIndexResponse = async (response, source) => {
  const payload = await readBoundedResponse(response, source);
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

  return raw.map((entry) => {
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
    return {
      id: entry.id,
      language: entry.l,
      content: cleanContent(entry.c),
    };
  });
};

const loadIndex = async () => {
  if (entries) return entries;
  if (loadingPromise) return loadingPromise;

  loadingPromise = (async () => {
    let lastError = null;
    for (const source of sources) {
      try {
        self.postMessage({ type: 'status', status: 'loading' });
        const response = await fetch(source.url, {
          // Revalidate the manifest-selected object so a locally cached 404
          // from pre-publication testing cannot mask a later successful upload.
          cache: source.sha256 ? 'no-cache' : 'force-cache',
          credentials: 'omit',
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        entries = await parseIndexResponse(response, source);
        self.postMessage({ type: 'status', status: 'ready' });
        return entries;
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError instanceof Error ? lastError : new Error('正文搜索暂时不可用');
  })();

  try {
    return await loadingPromise;
  } catch (error) {
    loadingPromise = null;
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
        if ((!includeJapanese && entry.language === 'jp') || matchedIds.has(entry.id)) continue;

        const normalizedContent = normalize(entry.content);
        const matchAt = normalizedContent.indexOf(normalizedQuery);
        if (matchAt < 0) continue;

        // The normalized offset is only a positioning hint. Keeping a little
        // extra context makes snippets useful even with full-width characters.
        const approximateAt = Math.min(matchAt, entry.content.length);
        const start = Math.max(0, approximateAt - 24);
        const endAt = Math.min(entry.content.length, approximateAt + query.length + 48);
        matches.push([entry.id, entry.content.slice(start, endAt).trim()]);
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
