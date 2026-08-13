import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  READER_FONT_BUNDLES,
  READER_FONT_BUNDLE_IDS,
  READER_FONT_PREFERENCES_STORAGE_KEY,
  disableReaderFontBundle,
  enableReaderFontBundle,
  getReaderFontRuntimeSnapshot,
  initializeReaderFonts,
  parseReaderFontPreferences,
  parseReaderFontRuntimeSnapshot,
  readSfntInternalNames,
  removeReaderFontBundleCache,
} from './reader-fonts.ts';

type ReaderFontManifest = {
  version: number;
  conversion: string;
  converterVersions: {
    fontTools: string;
    brotli: string;
  };
  fonts: Array<{
    id: string;
    woff2File: string;
    woff2Url: string;
    woff2Bytes: number;
    woff2Sha256: string;
    glyphs: number;
    unicodeCodePoints: number;
    fsType: string;
    fullConversion: boolean;
  }>;
};

const manifest = JSON.parse(
  readFileSync('public/fonts/reader-font-manifest.json', 'utf8'),
) as ReaderFontManifest;

test('reader font preferences are opt-in and reject non-boolean values', () => {
  assert.deepEqual(parseReaderFontPreferences(null), {
    chineseEnabled: false,
    japaneseEnabled: false,
    exedraChineseEnabled: false,
    exedraJapaneseEnabled: false,
  });
  assert.deepEqual(
    parseReaderFontPreferences(
      JSON.stringify({ chineseEnabled: 'true', japaneseEnabled: true }),
    ),
    {
      chineseEnabled: false,
      japaneseEnabled: true,
      exedraChineseEnabled: false,
      exedraJapaneseEnabled: false,
    },
  );
  assert.deepEqual(parseReaderFontPreferences('{broken'), {
    chineseEnabled: false,
    japaneseEnabled: false,
    exedraChineseEnabled: false,
    exedraJapaneseEnabled: false,
  });
});

test('full WOFF2 assets match the pinned manifest and runtime definitions', () => {
  assert.equal(manifest.version, 2);
  assert.match(manifest.conversion, /full glyph set, no subsetting/u);
  assert.ok(manifest.converterVersions.fontTools.length > 0);
  assert.ok(manifest.converterVersions.brotli.length > 0);
  assert.equal(manifest.fonts.length, 7);

  for (const record of manifest.fonts) {
    const bytes = readFileSync(`public/fonts/${record.woff2File}`);
    assert.equal(bytes.subarray(0, 4).toString('ascii'), 'wOF2');
    assert.equal(bytes.byteLength, record.woff2Bytes);
    assert.equal(
      createHash('sha256').update(bytes).digest('hex'),
      record.woff2Sha256,
    );
    assert.equal(record.fullConversion, true);
    assert.ok(record.glyphs > 7_000);
    assert.ok(record.unicodeCodePoints > 7_000);
  }

  for (const bundleId of [
    'chinese',
    'japanese',
    'exedraChinese',
    'exedraJapanese',
  ] as const) {
    const bundle = READER_FONT_BUNDLES[bundleId];
    assert.equal(
      bundle.totalBytes,
      bundle.faces.reduce((total, face) => total + face.bytes, 0),
    );
    for (const face of bundle.faces) {
      const record = manifest.fonts.find(item => item.woff2Url === face.url);
      assert.ok(record, `manifest entry missing for ${face.url}`);
      assert.equal(record.woff2Bytes, face.bytes);
      assert.equal(record.woff2Sha256, face.sha256);
    }
  }
});

test('Exedra font definitions use the audited TangYuan and JP client WOFF2 files', () => {
  assert.deepEqual(READER_FONT_BUNDLE_IDS, [
    'chinese',
    'japanese',
    'exedraChinese',
    'exedraJapanese',
  ]);
  const chinese = READER_FONT_BUNDLES.exedraChinese;
  assert.equal(chinese.scope, 'exedra-only');
  assert.equal(chinese.activation, 'download');
  assert.equal(chinese.totalBytes, 1_386_160);
  assert.equal(
    chinese.faces[0].url,
    '/fonts/exedra-zh-tangyuan.0901bb62ccd1.full.woff2',
  );
  assert.equal(
    chinese.faces[0].sha256,
    '0901bb62ccd113f214201a8760146875bec0769664765a66172a5fe79e19b411',
  );
  assert.match(chinese.licenseUrl ?? '', /LICENSE\.txt/u);

  const japanese = READER_FONT_BUNDLES.exedraJapanese;
  assert.equal(japanese.scope, 'exedra-only');
  assert.equal(japanese.activation, 'download');
  assert.equal(japanese.totalBytes, 6_120_892);
  assert.equal(japanese.faces.length, 2);
  assert.deepEqual(
    japanese.faces.map(face => [face.url, face.bytes, face.sha256]),
    [
      [
        '/fonts/exedra-jp-ui-tsuku.431afe7080dc.full.woff2',
        2_750_668,
        '431afe7080dcb5c6337bf2ab6ec1d04449123aa4841a1f85a9bdfd3c5bd8b7b3',
      ],
      [
        '/fonts/exedra-jp-story-newcinema.687768deeccd.full.woff2',
        3_370_224,
        '687768deeccd50f66a4aefc7f30bc7d8095be462628507715f26be7f8eea7762',
      ],
    ],
  );
});

test('local font validation reads internal SFNT full names instead of file names', () => {
  const name = 'FOT-TsukuOldGothic Std B';
  const encoded = new Uint8Array(name.length * 2);
  for (let index = 0; index < name.length; index += 1) {
    encoded[index * 2] = name.charCodeAt(index) >> 8;
    encoded[index * 2 + 1] = name.charCodeAt(index) & 0xff;
  }
  const nameOffset = 28;
  const nameLength = 18 + encoded.byteLength;
  const data = new ArrayBuffer(nameOffset + nameLength);
  const bytes = new Uint8Array(data);
  const view = new DataView(data);
  view.setUint32(0, 0x00010000, false);
  view.setUint16(4, 1, false);
  bytes.set(new TextEncoder().encode('name'), 12);
  view.setUint32(20, nameOffset, false);
  view.setUint32(24, nameLength, false);
  view.setUint16(nameOffset, 0, false);
  view.setUint16(nameOffset + 2, 1, false);
  view.setUint16(nameOffset + 4, 18, false);
  view.setUint16(nameOffset + 6, 3, false);
  view.setUint16(nameOffset + 8, 1, false);
  view.setUint16(nameOffset + 10, 0x0409, false);
  view.setUint16(nameOffset + 12, 4, false);
  view.setUint16(nameOffset + 14, encoded.byteLength, false);
  view.setUint16(nameOffset + 16, 0, false);
  bytes.set(encoded, nameOffset + 18);
  assert.deepEqual(readSfntInternalNames(data), [name]);
});

test('default initialization fetches nothing; manual enable caches and disable restores system fonts', async () => {
  const savedWindow = globalThis.window;
  const savedDocument = globalThis.document;
  const savedFontFace = globalThis.FontFace;
  const savedFetch = globalThis.fetch;
  const savedCaches = globalThis.caches;

  const localValues = new Map<string, string>();
  const cachedBytes = new Map<string, Uint8Array>();
  const activeFaces = new Set<unknown>();
  const dataset: Record<string, string> = {};
  let networkRequests = 0;
  let corruptChineseDownload = false;

  const keyFor = (request: RequestInfo | URL): string =>
    typeof request === 'string'
      ? request
      : request instanceof URL
        ? request.pathname
        : new URL(request.url).pathname;

  const memoryCache = {
    match: async (request: RequestInfo | URL) => {
      const bytes = cachedBytes.get(keyFor(request));
      return bytes
        ? new Response(bytes.slice() as unknown as BodyInit, { status: 200 })
        : undefined;
    },
    put: async (request: RequestInfo | URL, response: Response) => {
      cachedBytes.set(
        keyFor(request),
        new Uint8Array(await response.arrayBuffer()),
      );
    },
    delete: async (request: RequestInfo | URL) =>
      cachedBytes.delete(keyFor(request)),
  };

  class FakeFontFace {
    readonly family: string;
    readonly source: string | ArrayBuffer;
    readonly descriptors?: FontFaceDescriptors;

    constructor(
      family: string,
      source: string | ArrayBuffer,
      descriptors?: FontFaceDescriptors,
    ) {
      this.family = family;
      this.source = source;
      this.descriptors = descriptors;
    }

    async load(): Promise<FakeFontFace> {
      return this;
    }
  }

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      localStorage: {
        getItem: (key: string) => localValues.get(key) ?? null,
        setItem: (key: string, value: string) => localValues.set(key, value),
      },
    },
  });
  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: {
      documentElement: { dataset },
      fonts: {
        add: (face: unknown) => activeFaces.add(face),
        delete: (face: unknown) => activeFaces.delete(face),
      },
    },
  });
  Object.defineProperty(globalThis, 'FontFace', {
    configurable: true,
    value: FakeFontFace,
  });
  Object.defineProperty(globalThis, 'caches', {
    configurable: true,
    value: { open: async () => memoryCache },
  });
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: async (request: RequestInfo | URL) => {
      networkRequests += 1;
      const url = keyFor(request);
      const record = manifest.fonts.find(item => item.woff2Url === url);
      assert.ok(record, `unexpected fetch: ${url}`);
      if (corruptChineseDownload && url.includes('magi-cn-')) {
        return new Response(new Uint8Array([0, 1, 2]) as unknown as BodyInit, {
          status: 200,
        });
      }
      const bytes = readFileSync(`public/fonts/${record.woff2File}`);
      return new Response(bytes as unknown as BodyInit, { status: 200 });
    },
  });

  try {
    await initializeReaderFonts();
    assert.equal(networkRequests, 0, 'default initialization must not fetch fonts');
    assert.equal(activeFaces.size, 0);

    assert.equal(await enableReaderFontBundle('japanese'), true);
    assert.equal(networkRequests, 2);
    assert.equal(activeFaces.size, 2);
    assert.equal(dataset.readerFontJapanese, 'ready');
    let state = parseReaderFontRuntimeSnapshot(
      getReaderFontRuntimeSnapshot(),
    );
    assert.equal(state.bundles.japanese.status, 'ready');
    assert.equal(state.bundles.japanese.cached, true);
    assert.equal(state.bundles.japanese.source, 'network');
    assert.equal(state.preferences.japaneseEnabled, true);

    disableReaderFontBundle('japanese');
    assert.equal(activeFaces.size, 0);
    assert.equal(dataset.readerFontJapanese, undefined);
    state = parseReaderFontRuntimeSnapshot(getReaderFontRuntimeSnapshot());
    assert.equal(state.bundles.japanese.status, 'idle');
    assert.equal(state.bundles.japanese.cached, true);
    assert.equal(state.preferences.japaneseEnabled, false);

    assert.equal(await enableReaderFontBundle('japanese'), true);
    assert.equal(networkRequests, 2, 're-enable must use the dedicated cache');
    state = parseReaderFontRuntimeSnapshot(getReaderFontRuntimeSnapshot());
    assert.equal(state.bundles.japanese.source, 'cache');

    await removeReaderFontBundleCache('japanese');
    assert.equal(activeFaces.size, 0);
    assert.equal(cachedBytes.size, 0);
    state = parseReaderFontRuntimeSnapshot(getReaderFontRuntimeSnapshot());
    assert.equal(state.bundles.japanese.cached, false);
    assert.equal(
      JSON.parse(
        localValues.get(READER_FONT_PREFERENCES_STORAGE_KEY) ?? '{}',
      ).japaneseEnabled,
      false,
    );

    corruptChineseDownload = true;
    assert.equal(await enableReaderFontBundle('chinese'), false);
    assert.equal(dataset.readerFontChinese, undefined);
    state = parseReaderFontRuntimeSnapshot(getReaderFontRuntimeSnapshot());
    assert.equal(state.bundles.chinese.status, 'error');
    assert.match(state.bundles.chinese.error, /已回退到系统字体/u);
    assert.equal(state.preferences.chineseEnabled, false);
    assert.equal(activeFaces.size, 0);
  } finally {
    for (const [key, value] of [
      ['window', savedWindow],
      ['document', savedDocument],
      ['FontFace', savedFontFace],
      ['fetch', savedFetch],
      ['caches', savedCaches],
    ] as const) {
      if (value === undefined) Reflect.deleteProperty(globalThis, key);
      else {
        Object.defineProperty(globalThis, key, {
          configurable: true,
          value,
        });
      }
    }
  }
});

test('reader page assigns distinct body/title roles without static font preloads', () => {
  const page = readFileSync('app/reader/[id]/page.tsx', 'utf8');
  const settings = readFileSync('components/ReaderFontSettings.tsx', 'utf8');
  const css = readFileSync('app/globals.css', 'utf8');
  const layout = readFileSync('app/layout.tsx', 'utf8');

  assert.match(page, /reader-font-cn-body/u);
  assert.match(page, /reader-font-cn-title/u);
  assert.match(page, /reader-font-jp-body/u);
  assert.match(page, /reader-font-jp-title/u);
  assert.match(page, /initializeReaderFonts/u);
  assert.match(page, /data-reader-game=\{isExedraStory/u);
  assert.match(page, /isExedraStory=\{isExedraStory\}/u);
  assert.match(
    page,
    /directSourceResolution\.sources\?\.kind === 'exedra-trusted-runtime'\s*\|\|\s*currentStory\?\.game === 'exedra'/u,
  );
  assert.match(page, /exedra-jp-story-text/u);
  assert.match(page, /lang="zh-Hans"/u);
  assert.match(page, /lang="ja"/u);
  assert.match(settings, /Magia Exedra 原生字体/u);
  assert.match(settings, /猫啃网糖圆体/u);
  assert.match(settings, /FOT-TsukuOldGothic Std B/u);
  assert.match(settings, /FOT-NewCinemaA Std D/u);
  assert.match(settings, /三份均为完整未裁字 WOFF2，无需本地导入/u);
  assert.doesNotMatch(
    settings,
    /\['exedraChinese', 'exedraChineseFallback', 'exedraJapanese'\]/u,
  );
  assert.match(settings, /下载并启用/u);
  assert.match(settings, /全部恢复系统字体/u);
  assert.match(css, /data-reader-font-exedra-chinese/u);
  assert.doesNotMatch(css, /data-reader-font-exedra-chinese-fallback/u);
  assert.match(css, /\.exedra-reader/u);
  assert.match(css, /:lang\(zh-Hans\)/u);
  assert.match(css, /:lang\(ja\)/u);
  assert.match(
    css,
    /data-reader-font-exedra-japanese[^}]+reader-font-jp-title:lang\(ja\)[^}]+MagiReaderExedraTsukuOldGothic/su,
  );
  assert.match(
    css,
    /data-reader-font-exedra-japanese[^}]+exedra-jp-story-text:lang\(ja\)[^}]+MagiReaderExedraNewCinemaA/su,
  );
  assert.match(css, /Resource Han Rounded CN/u);
  assert.match(css, /Noto Sans SC/u);
  assert.doesNotMatch(css, /@font-face\s*\{/u);
  assert.doesNotMatch(layout, /preload[^\n]+fonts/u);
});
