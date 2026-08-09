export type ReaderFontBundleId =
  | 'chinese'
  | 'japanese'
  | 'exedraChinese'
  | 'exedraChineseFallback'
  | 'exedraJapanese';

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
  exedraChineseEnabled: boolean;
  exedraChineseFallbackEnabled: boolean;
  exedraJapaneseEnabled: boolean;
};

export type ReaderFontBundleRuntime = {
  status: ReaderFontBundleStatus;
  cached: boolean;
  loadedBytes: number;
  source: 'cache' | 'network' | 'local' | 'mixed' | null;
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
  delivery?: 'network' | 'local-import';
  acceptedInternalNames?: readonly string[];
};

export type ReaderFontBundleDefinition = {
  id: ReaderFontBundleId;
  label: string;
  description: string;
  totalBytes: number;
  faces: readonly ReaderFontFaceDefinition[];
  activation?: 'download' | 'local-import';
  scope?: 'all-readers' | 'exedra-only';
  licenseUrl?: string;
  sourceUrl?: string;
};

export const READER_FONT_PREFERENCES_STORAGE_KEY =
  'magi-reader-font-preferences-v2';
export const READER_FONT_CACHE_NAME =
  'magi-reader-fonts-v2-exedra-ea4e2e85-3e13805d-e40f4d90';

export const READER_FONT_BUNDLE_IDS = [
  'chinese',
  'japanese',
  'exedraChinese',
  'exedraChineseFallback',
  'exedraJapanese',
] as const satisfies readonly ReaderFontBundleId[];

export const READER_FONT_BUNDLES: Record<
  ReaderFontBundleId,
  ReaderFontBundleDefinition
> = {
  chinese: {
    id: 'chinese',
    label: '游戏中文字体',
    description: '正文使用腾祥嘉丽大圆，标题与角色名使用腾祥智黑。',
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
  exedraChinese: {
    id: 'exedraChinese',
    label: 'Exedra 简体中文字体',
    description:
      '猫啃网糖圆体 v0.12beta（粉圆直系简中衍生，GB2312 6763/6763）；生僻字回退到 Resource Han Rounded CN、Noto Sans SC。',
    totalBytes: 2_881_764,
    activation: 'download',
    scope: 'exedra-only',
    licenseUrl:
      'https://github.com/NightFurySL2001/TangYuan-font/blob/561190610f7c34939396bd9f745a5393f4815ddd/LICENSE.txt',
    sourceUrl:
      'https://github.com/NightFurySL2001/TangYuan-font/releases/tag/v0.12beta',
    faces: [
      {
        family: 'MagiReaderExedraTangYuan',
        url: '/api/fonts/exedra-tangyuan/v0.12beta',
        bytes: 2_881_764,
        sha256:
          'ea4e2e85cc49ed7a0ea9f2347a9c5e6e9c3ea1a1c9130280796cceb77e0dc800',
        weight: '400',
      },
    ],
  },
  exedraJapanese: {
    id: 'exedraJapanese',
    label: 'Exedra 日文原生字体',
    description:
      '本地导入 JP 客户端的 FOT-TsukuOldGothic Std B 与 FOT-NewCinemaA Std D；文件不会上传。',
    totalBytes: 10_408_188,
    activation: 'local-import',
    scope: 'exedra-only',
    licenseUrl: 'https://fontworks.co.jp/products/font-license/',
    sourceUrl: 'https://lets.fontworks.co.jp/fonts',
    faces: [
      {
        family: 'MagiReaderExedraTsukuOldGothic',
        url: '/__magi-reader-local-fonts/exedra-tsukuoldgothic-v2.100.otf',
        bytes: 5_710_884,
        sha256:
          '3e13805dacb081d44d06c16213319b45f044b777989afde7985fa2afaaf9684a',
        weight: '700',
        delivery: 'local-import',
        acceptedInternalNames: [
          'FOT-TsukuOldGothic Std B',
          'FOT-筑紫オールドゴシック Std B',
          'TsukuOldGothicStd-B',
        ],
      },
      {
        family: 'MagiReaderExedraNewCinemaA',
        url: '/__magi-reader-local-fonts/exedra-newcinemaa-v1.300.otf',
        bytes: 4_697_304,
        sha256:
          'e40f4d90a8010404511b6f113e95c54d5a56a39619076bcd8da4d42fafb3aee5',
        weight: '400',
        delivery: 'local-import',
        acceptedInternalNames: [
          'FOT-NewCinemaA Std D',
          'FOT-ニューシネマA Std D',
          'NewCinemaAStd-D',
        ],
      },
    ],
  },
  exedraChineseFallback: {
    id: 'exedraChineseFallback',
    label: 'Exedra 简中 GBK 回退（可选）',
    description:
      '本地导入 Resource Han Rounded CN v0.990；实测覆盖 GBK 汉字 20902/20902，仅在糖圆体缺字时使用。',
    totalBytes: 14_663_464,
    activation: 'local-import',
    scope: 'exedra-only',
    licenseUrl:
      'https://github.com/CyanoHao/Resource-Han-Rounded/blob/master/LICENSE.txt',
    sourceUrl:
      'https://github.com/CyanoHao/Resource-Han-Rounded/releases/tag/v0.990',
    faces: [
      {
        family: 'MagiReaderExedraChineseGbKFallback',
        url: '/__magi-reader-local-fonts/resource-han-rounded-cn-v0.990.ttf',
        bytes: 14_663_464,
        sha256:
          '1c5c623f008eabef10c45135a48b01b46311f9369c28857355872cfe05f48dc0',
        weight: '400',
        delivery: 'local-import',
        acceptedInternalNames: [
          'Resource Han Rounded CN',
          'Resource Han Rounded CN Regular',
          'Resource-Han-Rounded-CN-Regular',
        ],
      },
    ],
  },
};

const DEFAULT_PREFERENCES: ReaderFontPreferences = {
  chineseEnabled: false,
  japaneseEnabled: false,
  exedraChineseEnabled: false,
  exedraChineseFallbackEnabled: false,
  exedraJapaneseEnabled: false,
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
    exedraChinese: defaultBundleRuntime(),
    exedraChineseFallback: defaultBundleRuntime(),
    exedraJapanese: defaultBundleRuntime(),
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
  exedraChinese: [],
  exedraChineseFallback: [],
  exedraJapanese: [],
};
const importedFaceData = new Map<string, ArrayBuffer>();
const pendingLoads: Partial<Record<ReaderFontBundleId, Promise<boolean>>> = {};

const PREFERENCE_KEYS: Record<
  ReaderFontBundleId,
  keyof ReaderFontPreferences
> = {
  chinese: 'chineseEnabled',
  japanese: 'japaneseEnabled',
  exedraChinese: 'exedraChineseEnabled',
  exedraChineseFallback: 'exedraChineseFallbackEnabled',
  exedraJapanese: 'exedraJapaneseEnabled',
};

const preferenceKeyFor = (
  bundleId: ReaderFontBundleId,
): keyof ReaderFontPreferences => PREFERENCE_KEYS[bundleId];

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
      exedraChineseEnabled: record.exedraChineseEnabled === true,
      exedraChineseFallbackEnabled:
        record.exedraChineseFallbackEnabled === true,
      exedraJapaneseEnabled: record.exedraJapaneseEnabled === true,
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
        bundle.source === 'local' ||
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
        exedraChinese: normalizeBundle('exedraChinese'),
        exedraChineseFallback: normalizeBundle('exedraChineseFallback'),
        exedraJapanese: normalizeBundle('exedraJapanese'),
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
  const keys: Record<ReaderFontBundleId, string> = {
    chinese: 'readerFontChinese',
    japanese: 'readerFontJapanese',
    exedraChinese: 'readerFontExedraChinese',
    exedraChineseFallback: 'readerFontExedraChineseFallback',
    exedraJapanese: 'readerFontExedraJapanese',
  };
  const key = keys[bundleId];
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

const decodeUtf16Be = (bytes: Uint8Array): string => {
  let value = '';
  for (let index = 0; index + 1 < bytes.byteLength; index += 2) {
    value += String.fromCharCode((bytes[index] << 8) | bytes[index + 1]);
  }
  return value.replace(/\0/gu, '').trim();
};

/** Read the user-facing family/full/PostScript names without trusting a file name. */
export const readSfntInternalNames = (data: ArrayBuffer): string[] => {
  const bytes = new Uint8Array(data);
  const view = new DataView(data);
  if (bytes.byteLength < 12) return [];
  const signature = String.fromCharCode(...bytes.subarray(0, 4));
  const isTrueType = view.getUint32(0, false) === 0x00010000;
  if (!isTrueType && signature !== 'OTTO' && signature !== 'true') return [];
  const tableCount = view.getUint16(4, false);
  if (12 + tableCount * 16 > bytes.byteLength) return [];

  let nameOffset = -1;
  let nameLength = 0;
  for (let index = 0; index < tableCount; index += 1) {
    const offset = 12 + index * 16;
    const tag = String.fromCharCode(...bytes.subarray(offset, offset + 4));
    if (tag !== 'name') continue;
    nameOffset = view.getUint32(offset + 8, false);
    nameLength = view.getUint32(offset + 12, false);
    break;
  }
  if (
    nameOffset < 0 ||
    nameLength < 6 ||
    nameOffset + nameLength > bytes.byteLength
  ) return [];

  const recordCount = view.getUint16(nameOffset + 2, false);
  const stringOffset = view.getUint16(nameOffset + 4, false);
  const recordsEnd = nameOffset + 6 + recordCount * 12;
  if (recordsEnd > nameOffset + nameLength) return [];
  const names = new Set<string>();
  for (let index = 0; index < recordCount; index += 1) {
    const record = nameOffset + 6 + index * 12;
    const platform = view.getUint16(record, false);
    const nameId = view.getUint16(record + 6, false);
    if (nameId !== 1 && nameId !== 4 && nameId !== 6 && nameId !== 16) {
      continue;
    }
    const length = view.getUint16(record + 8, false);
    const relativeOffset = view.getUint16(record + 10, false);
    const start = nameOffset + stringOffset + relativeOffset;
    const end = start + length;
    if (start < nameOffset || end > nameOffset + nameLength) continue;
    const raw = bytes.subarray(start, end);
    const decoded = platform === 0 || platform === 3
      ? decodeUtf16Be(raw)
      : new TextDecoder('latin1').decode(raw).replace(/\0/gu, '').trim();
    if (decoded) names.add(decoded);
  }
  return [...names];
};

const validateImportedFontIdentity = (
  face: ReaderFontFaceDefinition,
  data: ArrayBuffer,
): void => {
  if (!face.acceptedInternalNames?.length) return;
  const names = readSfntInternalNames(data);
  if (!face.acceptedInternalNames.some(expected => names.includes(expected))) {
    throw new Error(
      `${face.family} 内部字体名不符（读到：${names.slice(0, 4).join(' / ') || '无'}）。`,
    );
  }
};

type LoadedFaceData = {
  data: ArrayBuffer;
  source: 'cache' | 'network' | 'local';
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

  const imported = importedFaceData.get(face.url);
  if (imported) {
    await validateFontBytes(face, imported);
    return { data: imported.slice(0), source: 'local', cached: false };
  }

  if (face.delivery === 'local-import') {
    throw new Error(`${face.family} 尚未从本机导入。`);
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
  const sources = new Set<'cache' | 'network' | 'local'>();
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

export const importReaderFontBundleFiles = async (
  bundleId: ReaderFontBundleId,
  files: readonly File[],
): Promise<boolean> => {
  const bundle = READER_FONT_BUNDLES[bundleId];
  if (bundle.activation !== 'local-import') {
    throw new Error(`${bundle.label} 不接受本地字体导入。`);
  }
  if (files.length !== bundle.faces.length) {
    updateBundleRuntime(bundleId, {
      status: 'error',
      error: `请选择 ${bundle.faces.length} 个字体文件。`,
      loadedBytes: 0,
      source: null,
    });
    return false;
  }

  updateBundleRuntime(bundleId, {
    status: 'checking',
    error: '',
    loadedBytes: 0,
    source: null,
  });
  try {
    const validated = new Map<ReaderFontFaceDefinition, ArrayBuffer>();
    for (const file of files) {
      if (file.size > 16 * 1024 * 1024) {
        throw new Error(`${file.name} 超过 16 MiB 本地导入上限。`);
      }
      const data = await file.arrayBuffer();
      const digest = await digestSha256(data);
      if (!digest) throw new Error('当前浏览器缺少 SHA-256 完整性校验能力。');
      const face = bundle.faces.find(
        candidate => candidate.sha256 === digest && !validated.has(candidate),
      );
      if (!face) {
        throw new Error(`${file.name} 不是 ${bundle.label} 的已核验字体。`);
      }
      await validateFontBytes(face, data);
      validateImportedFontIdentity(face, data);
      validated.set(face, data);
    }
    if (validated.size !== bundle.faces.length) {
      throw new Error(`需要导入 ${bundle.faces.length} 份不同的已核验字体。`);
    }

    const cacheStorage = getCacheStorage();
    const cache = cacheStorage
      ? await cacheStorage.open(READER_FONT_CACHE_NAME).catch(() => null)
      : null;
    for (const face of bundle.faces) {
      const data = validated.get(face);
      if (!data) throw new Error(`${face.family} 未通过本地校验。`);
      importedFaceData.set(face.url, data.slice(0));
      if (cache) {
        await cache.put(
          face.url,
          new Response(data, {
            status: 200,
            headers: { 'content-type': 'font/otf' },
          }),
        ).catch(() => undefined);
      }
    }
    return await enableReaderFontBundle(bundleId);
  } catch (error) {
    updateBundleRuntime(bundleId, {
      status: 'error',
      error:
        `${error instanceof Error ? error.message : '字体导入失败。'}`
        + ' 已继续使用系统字体。',
      loadedBytes: 0,
      source: null,
    });
    return false;
  }
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
  for (const face of READER_FONT_BUNDLES[bundleId].faces) {
    importedFaceData.delete(face.url);
  }
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
  for (const bundleId of READER_FONT_BUNDLE_IDS) {
    disableReaderFontBundleInternal(bundleId, false);
  }
  persistPreferences({ ...DEFAULT_PREFERENCES });
};

export const initializeReaderFonts = (): Promise<void> => {
  hydratePreferences();
  if (initialization) return initialization;
  initialization = (async () => {
    await Promise.all(
      READER_FONT_BUNDLE_IDS.map(async bundleId => {
        const cached = await inspectBundleCache(bundleId);
        updateBundleRuntime(bundleId, { cached });
      }),
    );
    // Persisted opt-in may load from the dedicated cache. New users keep both
    // flags false, so initialization performs no font network request.
    for (const bundleId of READER_FONT_BUNDLE_IDS) {
      if (runtime.preferences[preferenceKeyFor(bundleId)]) {
        await loadAndEnableReaderFontBundle(bundleId, false);
      }
    }
  })();
  return initialization;
};

export const formatReaderFontBytes = (bytes: number): string =>
  `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
