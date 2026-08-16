export type ReaderFontBundleId = 'chinese' | 'japanese';

export type ReaderFontBundleStatus =
  | 'idle'
  | 'checking'
  | 'downloading'
  | 'loading'
  | 'ready'
  | 'error'
  | 'unsupported';

export type ReaderFontPreferences = {
  chineseEnabled: boolean;
  japaneseEnabled: boolean;
};

export type ReaderFontBundleRuntime = {
  status: ReaderFontBundleStatus;
  cached: boolean;
  loadedBytes: number;
  source: 'cache' | 'network' | 'mixed' | null;
  error: string;
};

export type ReaderFontRuntimeSnapshot = {
  preferences: ReaderFontPreferences;
  bundles: Record<ReaderFontBundleId, ReaderFontBundleRuntime>;
};

type ReaderFontFaceDefinition = {
  family: string;
  url: string;
  bytes: number;
  sha256: string;
  weight: string;
};

export type ReaderFontBundleDefinition = {
  id: ReaderFontBundleId;
  label: string;
  description: string;
  totalBytes: number;
  faces: readonly ReaderFontFaceDefinition[];
};

export const READER_FONT_PREFERENCES_STORAGE_KEY =
  'magi-reader-font-preferences-v1';
export const READER_FONT_CACHE_NAME =
  'magi-reader-fonts-v1-55b5dffd-9d7f95bc-3f691caf-b9c8b6b8';

export const READER_FONT_BUNDLES: Record<
  ReaderFontBundleId,
  ReaderFontBundleDefinition
> = {
  chinese: {
    id: 'chinese',
    label: '游戏中文字体',
    description: '正文使用腾祥嘉丽大圆；标题、角色名与站点 UI 使用腾祥智黑。',
    totalBytes: 11_713_216,
    faces: [
      {
        family: 'MagiReaderGameChineseBody',
        url: '/fonts/magi-cn-body.55b5dffd7c95.full.woff2',
        bytes: 8_071_072,
        sha256:
          '55b5dffd7c9505c54b83cb3c4f86b70cb67bc45b3a1588a972155e650fa95adf',
        weight: '400',
      },
      {
        family: 'MagiReaderGameChineseTitle',
        url: '/fonts/magi-cn-title.9d7f95bc2c7d.full.woff2',
        bytes: 3_642_144,
        sha256:
          '9d7f95bc2c7d747f5a744f43cfc2e2de988ce03aea4ab58677fa2ab1ee2789f5',
        weight: '400',
      },
    ],
  },
  japanese: {
    id: 'japanese',
    label: '游戏日文字体',
    description: '日文正文使用 TT-Gothic MB101，标题使用 Motoya F4 Aporo。',
    totalBytes: 2_362_452,
    faces: [
      {
        family: 'MagiReaderGameJapaneseBody',
        url: '/fonts/magi-jp-body.3f691cafa21d.full.woff2',
        bytes: 1_252_504,
        sha256:
          '3f691cafa21dd5c5095b72112bad2ced77c47f8acdb2257ea7b69b0b9b59addb',
        // This face has inconsistent legacy bold metadata. A private family and
        // an explicit weight keep browser matching deterministic.
        weight: '500',
      },
      {
        family: 'MagiReaderGameJapaneseTitle',
        url: '/fonts/magi-jp-title.b9c8b6b87882.full.woff2',
        bytes: 1_109_948,
        sha256:
          'b9c8b6b878826f6ec2a97cfa013c7b30590eb6ffe9d32bbefb02b2f95a87f7c5',
        weight: '400',
      },
    ],
  },
};

const DEFAULT_PREFERENCES: ReaderFontPreferences = {
  chineseEnabled: false,
  japaneseEnabled: false,
};

const defaultBundleRuntime = (): ReaderFontBundleRuntime => ({
  status: 'idle',
  cached: false,
  loadedBytes: 0,
  source: null,
  error: '',
});

const defaultRuntimeSnapshot = (): ReaderFontRuntimeSnapshot => ({
  preferences: { ...DEFAULT_PREFERENCES },
  bundles: {
    chinese: defaultBundleRuntime(),
    japanese: defaultBundleRuntime(),
  },
});

const DEFAULT_SERVER_SNAPSHOT = JSON.stringify(defaultRuntimeSnapshot());
const STATUS_VALUES = new Set<ReaderFontBundleStatus>([
  'idle',
  'checking',
  'downloading',
  'loading',
  'ready',
  'error',
  'unsupported',
]);

let runtime = defaultRuntimeSnapshot();
let runtimeSnapshot = DEFAULT_SERVER_SNAPSHOT;
let preferencesHydrated = false;
let initialization: Promise<void> | null = null;
const listeners = new Set<() => void>();
const loadedFaces: Record<ReaderFontBundleId, FontFace[]> = {
  chinese: [],
  japanese: [],
};
const pendingLoads: Partial<Record<ReaderFontBundleId, Promise<boolean>>> = {};

const preferenceKeyFor = (
  bundleId: ReaderFontBundleId,
): keyof ReaderFontPreferences =>
  bundleId === 'chinese' ? 'chineseEnabled' : 'japaneseEnabled';

export const parseReaderFontPreferences = (
  snapshot: string | null,
): ReaderFontPreferences => {
  if (!snapshot) return { ...DEFAULT_PREFERENCES };
  try {
    const parsed: unknown = JSON.parse(snapshot);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ...DEFAULT_PREFERENCES };
    }
    const record = parsed as Record<string, unknown>;
    return {
      chineseEnabled: record.chineseEnabled === true,
      japaneseEnabled: record.japaneseEnabled === true,
    };
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
};

export const parseReaderFontRuntimeSnapshot = (
  snapshot: string,
): ReaderFontRuntimeSnapshot => {
  try {
    const parsed: unknown = JSON.parse(snapshot);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return defaultRuntimeSnapshot();
    }
    const record = parsed as Record<string, unknown>;
    const preferences = parseReaderFontPreferences(
      JSON.stringify(record.preferences ?? null),
    );
    const bundleRecord =
      record.bundles && typeof record.bundles === 'object'
        ? (record.bundles as Record<string, unknown>)
        : {};
    const normalizeBundle = (
      id: ReaderFontBundleId,
    ): ReaderFontBundleRuntime => {
      const value = bundleRecord[id];
      if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return defaultBundleRuntime();
      }
      const bundle = value as Record<string, unknown>;
      const status = STATUS_VALUES.has(bundle.status as ReaderFontBundleStatus)
        ? (bundle.status as ReaderFontBundleStatus)
        : 'idle';
      const loadedBytes =
        typeof bundle.loadedBytes === 'number' &&
        Number.isFinite(bundle.loadedBytes) &&
        bundle.loadedBytes >= 0
          ? Math.floor(bundle.loadedBytes)
          : 0;
      const source =
        bundle.source === 'cache' ||
        bundle.source === 'network' ||
        bundle.source === 'mixed'
          ? bundle.source
          : null;
      return {
        status,
        cached: bundle.cached === true,
        loadedBytes,
        source,
        error: typeof bundle.error === 'string' ? bundle.error : '',
      };
    };
    return {
      preferences,
      bundles: {
        chinese: normalizeBundle('chinese'),
        japanese: normalizeBundle('japanese'),
      },
    };
  } catch {
    return defaultRuntimeSnapshot();
  }
};

const publishRuntime = (): void => {
  runtimeSnapshot = JSON.stringify(runtime);
  for (const listener of listeners) listener();
};

const updateBundleRuntime = (
  bundleId: ReaderFontBundleId,
  update: Partial<ReaderFontBundleRuntime>,
): void => {
  runtime = {
    ...runtime,
    bundles: {
      ...runtime.bundles,
      [bundleId]: { ...runtime.bundles[bundleId], ...update },
    },
  };
  publishRuntime();
};

const persistPreferences = (preferences: ReaderFontPreferences): void => {
  runtime = { ...runtime, preferences };
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(
        READER_FONT_PREFERENCES_STORAGE_KEY,
        JSON.stringify(preferences),
      );
    } catch {
      // Runtime state remains usable when storage is blocked or full.
    }
  }
  publishRuntime();
};

const hydratePreferences = (): void => {
  if (preferencesHydrated) return;
  preferencesHydrated = true;
  if (typeof window === 'undefined') return;
  try {
    runtime = {
      ...runtime,
      preferences: parseReaderFontPreferences(
        window.localStorage.getItem(READER_FONT_PREFERENCES_STORAGE_KEY),
      ),
    };
    runtimeSnapshot = JSON.stringify(runtime);
  } catch {
    // Keep defaults when private browsing blocks localStorage.
  }
};

export const getReaderFontRuntimeSnapshot = (): string => {
  hydratePreferences();
  return runtimeSnapshot;
};

export const getReaderFontRuntimeServerSnapshot = (): string =>
  DEFAULT_SERVER_SNAPSHOT;

export const subscribeReaderFontRuntime = (
  onStoreChange: () => void,
): (() => void) => {
  hydratePreferences();
  listeners.add(onStoreChange);
  return () => listeners.delete(onStoreChange);
};

const getCacheStorage = (): CacheStorage | null =>
  typeof caches === 'undefined' ? null : caches;

const supportsRuntimeFonts = (): boolean =>
  typeof FontFace !== 'undefined' &&
  typeof document !== 'undefined' &&
  Boolean(document.fonts) &&
  Boolean(document.documentElement);

const setRootFontState = (
  bundleId: ReaderFontBundleId,
  active: boolean,
): void => {
  if (typeof document === 'undefined') return;
  const key = bundleId === 'chinese'
    ? 'readerFontChinese'
    : 'readerFontJapanese';
  if (active) document.documentElement.dataset[key] = 'ready';
  else delete document.documentElement.dataset[key];
};

const inspectBundleCache = async (
  bundleId: ReaderFontBundleId,
): Promise<boolean> => {
  const cacheStorage = getCacheStorage();
  if (!cacheStorage) return false;
  try {
    const cache = await cacheStorage.open(READER_FONT_CACHE_NAME);
    const matches = await Promise.all(
      READER_FONT_BUNDLES[bundleId].faces.map(face => cache.match(face.url)),
    );
    return matches.every(Boolean);
  } catch {
    return false;
  }
};

const digestSha256 = async (data: ArrayBuffer): Promise<string | null> => {
  if (!globalThis.crypto?.subtle) return null;
  const digest = await globalThis.crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(digest), value =>
    value.toString(16).padStart(2, '0'),
  ).join('');
};

const validateFontBytes = async (
  face: ReaderFontFaceDefinition,
  data: ArrayBuffer,
): Promise<void> => {
  if (data.byteLength !== face.bytes) {
    throw new Error(
      `${face.family} 文件大小不符（应为 ${face.bytes} 字节，实际 ${data.byteLength} 字节）。`,
    );
  }
  const digest = await digestSha256(data);
  if (digest && digest !== face.sha256) {
    throw new Error(`${face.family} 完整性校验失败。`);
  }
};

type LoadedFaceData = {
  data: ArrayBuffer;
  source: 'cache' | 'network';
  cached: boolean;
};

const readFaceData = async (
  face: ReaderFontFaceDefinition,
): Promise<LoadedFaceData> => {
  const cacheStorage = getCacheStorage();
  const cache = cacheStorage
    ? await cacheStorage.open(READER_FONT_CACHE_NAME).catch(() => null)
    : null;

  if (cache) {
    const cachedResponse = await cache.match(face.url).catch(() => undefined);
    if (cachedResponse) {
      try {
        const data = await cachedResponse.arrayBuffer();
        await validateFontBytes(face, data);
        return { data, source: 'cache', cached: true };
      } catch {
        await cache.delete(face.url).catch(() => false);
      }
    }
  }

  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), 90_000);
  try {
    const response = await fetch(face.url, {
      cache: 'force-cache',
      credentials: 'same-origin',
      signal: controller.signal,
    });
    if (!response.ok) {
      await response.body?.cancel('字体请求失败');
      throw new Error(`${face.family} 下载失败（HTTP ${response.status}）。`);
    }
    const data = await response.arrayBuffer();
    await validateFontBytes(face, data);
    let cached = false;
    if (cache) {
      try {
        await cache.put(
          face.url,
          new Response(data, {
            headers: { 'content-type': 'font/woff2' },
            status: 200,
          }),
        );
        cached = true;
      } catch {
        // Loading still succeeds when storage quota or Cache API writes fail.
      }
    }
    return { data, source: 'network', cached };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`${face.family} 下载超时。`);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
  }
};

const removeLoadedFaces = (bundleId: ReaderFontBundleId): void => {
  if (typeof document !== 'undefined' && document.fonts) {
    for (const face of loadedFaces[bundleId]) document.fonts.delete(face);
  }
  loadedFaces[bundleId] = [];
  setRootFontState(bundleId, false);
};

const loadAndEnableReaderFontBundle = async (
  bundleId: ReaderFontBundleId,
  persist: boolean,
): Promise<boolean> => {
  hydratePreferences();
  if (runtime.bundles[bundleId].status === 'ready') {
    if (persist) {
      persistPreferences({
        ...runtime.preferences,
        [preferenceKeyFor(bundleId)]: true,
      });
    }
    return true;
  }
  if (!supportsRuntimeFonts()) {
    if (persist) {
      persistPreferences({
        ...runtime.preferences,
        [preferenceKeyFor(bundleId)]: false,
      });
    }
    updateBundleRuntime(bundleId, {
      status: 'unsupported',
      loadedBytes: 0,
      source: null,
      error: '当前浏览器缺少 FontFace API，已继续使用系统字体。',
    });
    return false;
  }

  removeLoadedFaces(bundleId);
  updateBundleRuntime(bundleId, {
    status: 'checking',
    loadedBytes: 0,
    source: null,
    error: '',
  });
  const nextFaces: FontFace[] = [];
  const sources = new Set<'cache' | 'network'>();
  let loadedBytes = 0;
  let allCached = true;
  try {
    for (const definition of READER_FONT_BUNDLES[bundleId].faces) {
      const cached = await inspectBundleCache(bundleId);
      updateBundleRuntime(bundleId, {
        status: cached ? 'loading' : 'downloading',
        cached,
        loadedBytes,
      });
      const result = await readFaceData(definition);
      sources.add(result.source);
      allCached &&= result.cached;
      loadedBytes += result.data.byteLength;
      updateBundleRuntime(bundleId, {
        status: 'loading',
        loadedBytes,
      });
      const face = new FontFace(definition.family, result.data, {
        display: 'swap',
        style: 'normal',
        weight: definition.weight,
      });
      const loadedFace = await face.load();
      document.fonts.add(loadedFace);
      nextFaces.push(loadedFace);
    }
    loadedFaces[bundleId] = nextFaces;
    setRootFontState(bundleId, true);
    const source = sources.size > 1
      ? 'mixed'
      : sources.values().next().value ?? null;
    runtime = {
      ...runtime,
      preferences: {
        ...runtime.preferences,
        [preferenceKeyFor(bundleId)]: true,
      },
      bundles: {
        ...runtime.bundles,
        [bundleId]: {
          status: 'ready',
          cached: allCached,
          loadedBytes,
          source,
          error: '',
        },
      },
    };
    if (persist || runtime.preferences[preferenceKeyFor(bundleId)]) {
      persistPreferences(runtime.preferences);
    } else {
      publishRuntime();
    }
    return true;
  } catch (error) {
    for (const face of nextFaces) document.fonts.delete(face);
    loadedFaces[bundleId] = [];
    setRootFontState(bundleId, false);
    const preferences = {
      ...runtime.preferences,
      [preferenceKeyFor(bundleId)]: false,
    };
    runtime = { ...runtime, preferences };
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(
          READER_FONT_PREFERENCES_STORAGE_KEY,
          JSON.stringify(preferences),
        );
      } catch {
        // Runtime fallback does not depend on persistence.
      }
    }
    updateBundleRuntime(bundleId, {
      status: 'error',
      loadedBytes: 0,
      source: null,
      error:
        `${error instanceof Error ? error.message : '字体加载失败。'}`
        + ' 已回退到系统字体。',
    });
    return false;
  }
};

export const enableReaderFontBundle = (
  bundleId: ReaderFontBundleId,
): Promise<boolean> => {
  const pending = pendingLoads[bundleId];
  if (pending) return pending;
  const operation = loadAndEnableReaderFontBundle(bundleId, true).finally(() => {
    delete pendingLoads[bundleId];
  });
  pendingLoads[bundleId] = operation;
  return operation;
};

const disableReaderFontBundleInternal = (
  bundleId: ReaderFontBundleId,
  persist: boolean,
): void => {
  hydratePreferences();
  removeLoadedFaces(bundleId);
  const preferences = {
    ...runtime.preferences,
    [preferenceKeyFor(bundleId)]: false,
  };
  runtime = {
    ...runtime,
    preferences,
    bundles: {
      ...runtime.bundles,
      [bundleId]: {
        ...runtime.bundles[bundleId],
        status: 'idle',
        loadedBytes: 0,
        source: null,
        error: '',
      },
    },
  };
  if (persist) persistPreferences(preferences);
  else publishRuntime();
};

export const disableReaderFontBundle = (
  bundleId: ReaderFontBundleId,
): void => disableReaderFontBundleInternal(bundleId, true);

export const removeReaderFontBundleCache = async (
  bundleId: ReaderFontBundleId,
): Promise<void> => {
  disableReaderFontBundleInternal(bundleId, true);
  const cacheStorage = getCacheStorage();
  if (cacheStorage) {
    try {
      const cache = await cacheStorage.open(READER_FONT_CACHE_NAME);
      await Promise.all(
        READER_FONT_BUNDLES[bundleId].faces.map(face =>
          cache.delete(face.url),
        ),
      );
    } catch {
      // The bundle is already disabled; keep the system-font fallback active.
    }
  }
  updateBundleRuntime(bundleId, { cached: false });
};

export const restoreSystemReaderFonts = (): void => {
  disableReaderFontBundleInternal('chinese', false);
  disableReaderFontBundleInternal('japanese', false);
  persistPreferences({ ...DEFAULT_PREFERENCES });
};

export const initializeReaderFonts = (): Promise<void> => {
  hydratePreferences();
  if (initialization) return initialization;
  initialization = (async () => {
    await Promise.all(
      (['chinese', 'japanese'] as const).map(async bundleId => {
        const cached = await inspectBundleCache(bundleId);
        updateBundleRuntime(bundleId, { cached });
      }),
    );
    // Persisted opt-in may load from the dedicated cache. New users keep both
    // flags false, so initialization performs no font network request.
    for (const bundleId of ['chinese', 'japanese'] as const) {
      if (runtime.preferences[preferenceKeyFor(bundleId)]) {
        await loadAndEnableReaderFontBundle(bundleId, false);
      }
    }
  })();
  return initialization;
};

export const formatReaderFontBytes = (bytes: number): string =>
  `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
