export type ExedraFontId =
  | 'tangyuan'
  | 'tsuku-old-gothic'
  | 'new-cinema-a';

export type ExedraFontStatus =
  | 'idle'
  | 'checking'
  | 'downloading'
  | 'loading'
  | 'ready'
  | 'error'
  | 'unsupported';

export type ExedraFontRuntime = {
  status: ExedraFontStatus;
  cached: boolean;
  loadedBytes: number;
  source: 'cache' | 'network' | null;
  validation: string;
  error: string;
};

export type ExedraFontPreferences = Record<ExedraFontId, boolean>;

export type ExedraFontRuntimeSnapshot = {
  preferences: ExedraFontPreferences;
  fonts: Record<ExedraFontId, ExedraFontRuntime>;
};

export type ExedraFontDefinition = {
  id: ExedraFontId;
  family: string;
  label: string;
  description: string;
  role: 'zh-Hans' | 'ja-ui' | 'ja-story';
  url: string;
  bytes: number;
  sha256: string;
  weight: string;
};

export const EXEDRA_FONT_DEFINITIONS: Record<
  ExedraFontId,
  ExedraFontDefinition
> = {
  tangyuan: {
    id: 'tangyuan',
    family: 'MagiReaderExedraTangYuan',
    label: '猫啃网糖圆体',
    description:
      'Exedra 简体中文正文；生僻字继续使用 Resource Han Rounded CN / Noto Sans SC。',
    role: 'zh-Hans',
    url: '/fonts/exedra-zh-tangyuan.0901bb62ccd1.full.woff2',
    bytes: 1_386_160,
    sha256:
      '0901bb62ccd113f214201a8760146875bec0769664765a66172a5fe79e19b411',
    weight: '400',
  },
  'tsuku-old-gothic': {
    id: 'tsuku-old-gothic',
    family: 'MagiReaderExedraTsukuOldGothic',
    label: 'FOT-TsukuOldGothic Std B',
    description: 'Exedra 日文页面 UI、标题与角色名。',
    role: 'ja-ui',
    url: '/fonts/exedra-jp-ui-tsuku.431afe7080dc.full.woff2',
    bytes: 2_750_668,
    sha256:
      '431afe7080dcb5c6337bf2ab6ec1d04449123aa4841a1f85a9bdfd3c5bd8b7b3',
    // The binary already contains the physical B weight. Registering it as
    // the normal face makes ordinary story text resolve to it reliably.
    weight: '400',
  },
  'new-cinema-a': {
    id: 'new-cinema-a',
    family: 'MagiReaderExedraNewCinemaA',
    label: 'FOT-NewCinemaA Std D',
    description: 'Exedra 日文剧情、语音与旁白正文。',
    role: 'ja-story',
    url: '/fonts/exedra-jp-story-newcinema.687768deeccd.full.woff2',
    bytes: 3_370_224,
    sha256:
      '687768deeccd50f66a4aefc7f30bc7d8095be462628507715f26be7f8eea7762',
    weight: '400',
  },
};

export const EXEDRA_FONT_PREFERENCES_STORAGE_KEY =
  'magi-reader-exedra-font-preferences-v2';
export const EXEDRA_FONT_CACHE_NAME =
  'magi-reader-exedra-fonts-v2-0901bb62-431afe70-687768de';

const FONT_IDS = Object.keys(EXEDRA_FONT_DEFINITIONS) as ExedraFontId[];
const STATUS_VALUES = new Set<ExedraFontStatus>([
  'idle',
  'checking',
  'downloading',
  'loading',
  'ready',
  'error',
  'unsupported',
]);
const DEFAULT_PREFERENCES: ExedraFontPreferences = {
  tangyuan: false,
  'tsuku-old-gothic': false,
  'new-cinema-a': false,
};

const defaultFontRuntime = (): ExedraFontRuntime => ({
  status: 'idle',
  cached: false,
  loadedBytes: 0,
  source: null,
  validation: '',
  error: '',
});

const defaultSnapshot = (): ExedraFontRuntimeSnapshot => ({
  preferences: { ...DEFAULT_PREFERENCES },
  fonts: {
    tangyuan: defaultFontRuntime(),
    'tsuku-old-gothic': defaultFontRuntime(),
    'new-cinema-a': defaultFontRuntime(),
  },
});

const DEFAULT_SERVER_SNAPSHOT = JSON.stringify(defaultSnapshot());
let runtime = defaultSnapshot();
let runtimeSnapshot = DEFAULT_SERVER_SNAPSHOT;
let preferencesHydrated = false;
let initialization: Promise<void> | null = null;
const listeners = new Set<() => void>();
const loadedFaces: Record<ExedraFontId, FontFace[]> = {
  tangyuan: [],
  'tsuku-old-gothic': [],
  'new-cinema-a': [],
};
const pendingLoads: Partial<Record<ExedraFontId, Promise<boolean>>> = {};

export const parseExedraFontPreferences = (
  raw: string | null,
): ExedraFontPreferences => {
  if (!raw) return { ...DEFAULT_PREFERENCES };
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ...DEFAULT_PREFERENCES };
    }
    const value = parsed as Record<string, unknown>;
    return {
      tangyuan: value.tangyuan === true,
      'tsuku-old-gothic': value['tsuku-old-gothic'] === true,
      'new-cinema-a': value['new-cinema-a'] === true,
    };
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
};

export const parseExedraFontRuntimeSnapshot = (
  raw: string,
): ExedraFontRuntimeSnapshot => {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return defaultSnapshot();
    }
    const record = parsed as Record<string, unknown>;
    const preferences = parseExedraFontPreferences(
      JSON.stringify(record.preferences ?? null),
    );
    const fontRecord =
      record.fonts && typeof record.fonts === 'object'
        ? (record.fonts as Record<string, unknown>)
        : {};
    const normalize = (id: ExedraFontId): ExedraFontRuntime => {
      const candidate = fontRecord[id];
      if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
        return defaultFontRuntime();
      }
      const value = candidate as Record<string, unknown>;
      return {
        status: STATUS_VALUES.has(value.status as ExedraFontStatus)
          ? (value.status as ExedraFontStatus)
          : 'idle',
        cached: value.cached === true,
        loadedBytes:
          typeof value.loadedBytes === 'number' &&
          Number.isFinite(value.loadedBytes) &&
          value.loadedBytes >= 0
            ? Math.floor(value.loadedBytes)
            : 0,
        source:
          value.source === 'cache' || value.source === 'network'
            ? value.source
            : null,
        validation: typeof value.validation === 'string' ? value.validation : '',
        error: typeof value.error === 'string' ? value.error : '',
      };
    };
    return {
      preferences,
      fonts: {
        tangyuan: normalize('tangyuan'),
        'tsuku-old-gothic': normalize('tsuku-old-gothic'),
        'new-cinema-a': normalize('new-cinema-a'),
      },
    };
  } catch {
    return defaultSnapshot();
  }
};

const publish = (): void => {
  runtimeSnapshot = JSON.stringify(runtime);
  for (const listener of listeners) listener();
};

const updateFont = (
  id: ExedraFontId,
  next: Partial<ExedraFontRuntime>,
): void => {
  runtime = {
    ...runtime,
    fonts: {
      ...runtime.fonts,
      [id]: { ...runtime.fonts[id], ...next },
    },
  };
  publish();
};

const persistPreferences = (preferences: ExedraFontPreferences): void => {
  runtime = { ...runtime, preferences };
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(
        EXEDRA_FONT_PREFERENCES_STORAGE_KEY,
        JSON.stringify(preferences),
      );
    } catch {
      // The active face remains usable for this tab when storage is blocked.
    }
  }
  publish();
};

const hydratePreferences = (): void => {
  if (preferencesHydrated) return;
  preferencesHydrated = true;
  if (typeof window === 'undefined') return;
  try {
    runtime = {
      ...runtime,
      preferences: parseExedraFontPreferences(
        window.localStorage.getItem(EXEDRA_FONT_PREFERENCES_STORAGE_KEY),
      ),
    };
    runtimeSnapshot = JSON.stringify(runtime);
  } catch {
    // Keep explicit opt-in defaults when private browsing blocks storage.
  }
};

export const getExedraFontRuntimeSnapshot = (): string => {
  hydratePreferences();
  return runtimeSnapshot;
};

export const getExedraFontRuntimeServerSnapshot = (): string =>
  DEFAULT_SERVER_SNAPSHOT;

export const subscribeExedraFontRuntime = (
  listener: () => void,
): (() => void) => {
  hydratePreferences();
  listeners.add(listener);
  return () => listeners.delete(listener);
};

const supportsRuntimeFonts = (): boolean =>
  typeof FontFace !== 'undefined' &&
  typeof document !== 'undefined' &&
  Boolean(document.fonts) &&
  Boolean(document.documentElement) &&
  Boolean(globalThis.crypto?.subtle);

const datasetKey = (id: ExedraFontId): string => {
  if (id === 'tangyuan') return 'exedraFontTangYuan';
  if (id === 'tsuku-old-gothic') return 'exedraFontTsuku';
  return 'exedraFontNewCinema';
};

const setRootState = (id: ExedraFontId, active: boolean): void => {
  if (typeof document === 'undefined') return;
  const key = datasetKey(id);
  if (active) document.documentElement.dataset[key] = 'ready';
  else delete document.documentElement.dataset[key];
};

const digestSha256 = async (bytes: ArrayBuffer): Promise<string> => {
  if (!globalThis.crypto?.subtle) {
    throw new Error('当前浏览器缺少 Web Crypto，不能完成字体 SHA-256 校验。');
  }
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), value =>
    value.toString(16).padStart(2, '0'),
  ).join('');
};

const validateFont = async (
  definition: ExedraFontDefinition,
  data: ArrayBuffer,
): Promise<void> => {
  if (data.byteLength !== definition.bytes) {
    throw new Error(
      `${definition.label} 文件大小不符（应为 ${definition.bytes} 字节，实际 ${data.byteLength} 字节）。`,
    );
  }
  const sha256 = await digestSha256(data);
  if (sha256 !== definition.sha256) {
    throw new Error(`${definition.label} 的 SHA-256 完整性校验失败。`);
  }
};

const getCache = async (): Promise<Cache | null> => {
  if (typeof caches === 'undefined') return null;
  return caches.open(EXEDRA_FONT_CACHE_NAME).catch(() => null);
};

const readCachedFont = async (
  definition: ExedraFontDefinition,
): Promise<ArrayBuffer | null> => {
  const cache = await getCache();
  if (!cache) return null;
  const response = await cache.match(definition.url).catch(() => undefined);
  if (!response) return null;
  try {
    const data = await response.arrayBuffer();
    await validateFont(definition, data);
    return data;
  } catch {
    await cache.delete(definition.url).catch(() => false);
    return null;
  }
};

const cacheFont = async (
  definition: ExedraFontDefinition,
  data: ArrayBuffer,
): Promise<boolean> => {
  const cache = await getCache();
  if (!cache) return false;
  try {
    await cache.put(
      definition.url,
      new Response(data.slice(0), {
        status: 200,
        headers: {
          'content-type': 'font/woff2',
          'cache-control': 'private, max-age=31536000, immutable',
        },
      }),
    );
    return true;
  } catch {
    return false;
  }
};

const readResponseBufferBounded = async (
  response: Response,
  maxBytes: number,
): Promise<ArrayBuffer> => {
  if (!response.body) {
    const data = await response.arrayBuffer();
    if (data.byteLength > maxBytes) throw new Error('字体响应超过大小限制。');
    return data;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel('字体超过大小限制').catch(() => undefined);
        throw new Error('字体响应超过大小限制。');
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const merged = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return merged.buffer;
};

const fetchStaticFont = async (
  definition: ExedraFontDefinition,
): Promise<{ data: ArrayBuffer; cached: boolean }> => {
  const controller = new AbortController();
  const timer = globalThis.setTimeout(() => controller.abort(), 90_000);
  try {
    const response = await fetch(definition.url, {
      cache: 'force-cache',
      credentials: 'same-origin',
      signal: controller.signal,
    });
    if (!response.ok) {
      await response.body?.cancel('字体请求失败');
      throw new Error(`${definition.label} 下载失败（HTTP ${response.status}）。`);
    }
    const lengthHeader = response.headers.get('content-length');
    if (lengthHeader !== null) {
      const declared = Number(lengthHeader);
      if (!Number.isSafeInteger(declared) || declared !== definition.bytes) {
        await response.body?.cancel('字体大小不符');
        throw new Error(`${definition.label} 响应大小与固定版本不符。`);
      }
    }
    const data = await readResponseBufferBounded(response, definition.bytes);
    await validateFont(definition, data);
    return { data, cached: await cacheFont(definition, data) };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`${definition.label} 下载超时。`);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timer);
  }
};

const removeLoadedFaces = (id: ExedraFontId): void => {
  if (typeof document !== 'undefined' && document.fonts) {
    for (const face of loadedFaces[id]) document.fonts.delete(face);
  }
  loadedFaces[id] = [];
  setRootState(id, false);
};

const activateBytes = async (
  definition: ExedraFontDefinition,
  data: ArrayBuffer,
): Promise<void> => {
  const face = new FontFace(definition.family, data, {
    display: 'swap',
    style: 'normal',
    weight: definition.weight,
  });
  const loaded = await face.load();
  document.fonts.add(loaded);
  loadedFaces[definition.id] = [loaded];
  setRootState(definition.id, true);
};

const failFont = (
  id: ExedraFontId,
  error: unknown,
  persist: boolean,
): false => {
  removeLoadedFaces(id);
  const preferences = { ...runtime.preferences, [id]: false };
  if (persist || runtime.preferences[id]) persistPreferences(preferences);
  updateFont(id, {
    status: 'error',
    cached: false,
    loadedBytes: 0,
    source: null,
    validation: '',
    error:
      `${error instanceof Error ? error.message : '字体加载失败。'}`
      + ' 已回退到默认字体。',
  });
  return false;
};

const loadAndEnable = async (
  id: ExedraFontId,
  persist: boolean,
): Promise<boolean> => {
  hydratePreferences();
  if (!supportsRuntimeFonts()) {
    if (persist) persistPreferences({ ...runtime.preferences, [id]: false });
    updateFont(id, {
      status: 'unsupported',
      error: '当前浏览器缺少 FontFace 或 Web Crypto，已使用默认字体。',
    });
    return false;
  }
  if (runtime.fonts[id].status === 'ready') {
    if (persist) persistPreferences({ ...runtime.preferences, [id]: true });
    return true;
  }
  const definition = EXEDRA_FONT_DEFINITIONS[id];
  removeLoadedFaces(id);
  updateFont(id, { status: 'checking', error: '', validation: '' });
  try {
    const cachedData = await readCachedFont(definition);
    let data: ArrayBuffer;
    let source: ExedraFontRuntime['source'];
    let cached: boolean;
    if (cachedData) {
      data = cachedData;
      source = 'cache';
      cached = true;
    } else {
      updateFont(id, { status: 'downloading', cached: false });
      const downloaded = await fetchStaticFont(definition);
      data = downloaded.data;
      source = 'network';
      cached = downloaded.cached;
    }
    updateFont(id, { status: 'loading', loadedBytes: data.byteLength, cached });
    await activateBytes(definition, data);
    runtime = {
      ...runtime,
      preferences: { ...runtime.preferences, [id]: true },
      fonts: {
        ...runtime.fonts,
        [id]: {
          status: 'ready',
          cached,
          loadedBytes: data.byteLength,
          source,
          validation: '固定大小与 SHA-256 校验通过。',
          error: '',
        },
      },
    };
    if (persist || runtime.preferences[id]) persistPreferences(runtime.preferences);
    else publish();
    return true;
  } catch (error) {
    return failFont(id, error, persist);
  }
};

export const enableExedraFont = (id: ExedraFontId): Promise<boolean> => {
  const pending = pendingLoads[id];
  if (pending) return pending;
  const operation = loadAndEnable(id, true).finally(() => {
    delete pendingLoads[id];
  });
  pendingLoads[id] = operation;
  return operation;
};

const disableInternal = (id: ExedraFontId, persist: boolean): void => {
  hydratePreferences();
  removeLoadedFaces(id);
  const preferences = { ...runtime.preferences, [id]: false };
  runtime = {
    ...runtime,
    preferences,
    fonts: {
      ...runtime.fonts,
      [id]: {
        ...runtime.fonts[id],
        status: 'idle',
        loadedBytes: 0,
        source: null,
        validation: '',
        error: '',
      },
    },
  };
  if (persist) persistPreferences(preferences);
  else publish();
};

export const disableExedraFont = (id: ExedraFontId): void =>
  disableInternal(id, true);

export const removeExedraFontCache = async (
  id: ExedraFontId,
): Promise<void> => {
  disableInternal(id, true);
  const cache = await getCache();
  if (cache) {
    await cache.delete(EXEDRA_FONT_DEFINITIONS[id].url).catch(() => false);
  }
  updateFont(id, { cached: false });
};

export const restoreSystemExedraFonts = (): void => {
  for (const id of FONT_IDS) disableInternal(id, false);
  persistPreferences({ ...DEFAULT_PREFERENCES });
};

export const initializeExedraFonts = (): Promise<void> => {
  hydratePreferences();
  if (initialization) return initialization;
  initialization = (async () => {
    const cache = await getCache();
    for (const id of FONT_IDS) {
      const cached = cache
        ? Boolean(
          await cache.match(EXEDRA_FONT_DEFINITIONS[id].url)
            .catch(() => undefined),
        )
        : false;
      updateFont(id, { cached });
    }
    // Default preferences are all false: first-time visitors fetch no font.
    for (const id of FONT_IDS) {
      if (runtime.preferences[id]) await loadAndEnable(id, false);
    }
  })();
  return initialization;
};

export const formatExedraFontBytes = (bytes: number): string =>
  `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
