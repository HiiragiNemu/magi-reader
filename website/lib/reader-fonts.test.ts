import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  READER_FONT_BUNDLES,
  READER_FONT_PREFERENCES_STORAGE_KEY,
  disableReaderFontBundle,
  enableReaderFontBundle,
  getReaderFontRuntimeSnapshot,
  initializeReaderFonts,
  parseReaderFontPreferences,
  parseReaderFontRuntimeSnapshot,
  removeReaderFontBundleCache,
} from './reader-fonts.ts';

type ReaderFontManifest = {
  version: number;
  conversion: string;
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

test('reader font preferences default to Chinese and reject non-boolean values', () => {
  assert.deepEqual(parseReaderFontPreferences(null), {
    chineseEnabled: true,
    japaneseEnabled: false,
  });
  assert.deepEqual(
    parseReaderFontPreferences(
      JSON.stringify({ chineseEnabled: 'true', japaneseEnabled: true }),
    ),
    { chineseEnabled: false, japaneseEnabled: true },
  );
  assert.deepEqual(parseReaderFontPreferences('{broken'), {
    chineseEnabled: true,
    japaneseEnabled: false,
  });
});

test('full WOFF2 assets match the pinned manifest and runtime definitions', () => {
  assert.equal(manifest.version, 2);
  assert.match(manifest.conversion, /full glyph set, no subsetting/u);
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

  for (const bundle of Object.values(READER_FONT_BUNDLES)) {
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

test('default initialization loads Chinese; manual Japanese enable and disable remain isolated', async () => {
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
    assert.equal(networkRequests, 2, 'default initialization loads Chinese faces');
    assert.equal(activeFaces.size, 2);
    assert.equal(dataset.readerFontChinese, 'ready');

    assert.equal(await enableReaderFontBundle('japanese'), true);
    assert.equal(networkRequests, 4);
    assert.equal(activeFaces.size, 4);
    assert.equal(dataset.readerFontJapanese, 'ready');
    let state = parseReaderFontRuntimeSnapshot(
      getReaderFontRuntimeSnapshot(),
    );
    assert.equal(state.bundles.japanese.status, 'ready');
    assert.equal(state.bundles.japanese.cached, true);
    assert.equal(state.bundles.japanese.source, 'network');
    assert.equal(state.preferences.japaneseEnabled, true);

    disableReaderFontBundle('japanese');
    assert.equal(activeFaces.size, 2);
    assert.equal(dataset.readerFontJapanese, undefined);
    state = parseReaderFontRuntimeSnapshot(getReaderFontRuntimeSnapshot());
    assert.equal(state.bundles.japanese.status, 'idle');
    assert.equal(state.bundles.japanese.cached, true);
    assert.equal(state.preferences.japaneseEnabled, false);

    assert.equal(await enableReaderFontBundle('japanese'), true);
    assert.equal(networkRequests, 4, 're-enable must use the dedicated cache');
    state = parseReaderFontRuntimeSnapshot(getReaderFontRuntimeSnapshot());
    assert.equal(state.bundles.japanese.source, 'cache');

    await removeReaderFontBundleCache('japanese');
    assert.equal(activeFaces.size, 2);
    assert.equal(cachedBytes.size, 2);
    state = parseReaderFontRuntimeSnapshot(getReaderFontRuntimeSnapshot());
    assert.equal(state.bundles.japanese.cached, false);
    assert.equal(
      JSON.parse(
        localValues.get(READER_FONT_PREFERENCES_STORAGE_KEY) ?? '{}',
      ).japaneseEnabled,
      false,
    );

    await removeReaderFontBundleCache('chinese');
    assert.equal(activeFaces.size, 0);
    assert.equal(cachedBytes.size, 0);
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
  assert.match(settings, /游戏字体（按需下载）/u);
  assert.match(settings, /下载并启用/u);
  assert.match(settings, /全部恢复系统字体/u);
  assert.doesNotMatch(css, /@font-face\s*\{/u);
  assert.doesNotMatch(layout, /preload[^\n]+fonts/u);
});
