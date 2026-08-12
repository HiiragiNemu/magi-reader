import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

import {
  EXEDRA_FONT_DEFINITIONS,
  EXEDRA_FONT_PREFERENCES_STORAGE_KEY,
  disableExedraFont,
  enableExedraFont,
  getExedraFontRuntimeSnapshot,
  initializeExedraFonts,
  parseExedraFontPreferences,
  parseExedraFontRuntimeSnapshot,
  removeExedraFontCache,
} from './exedra-fonts.ts';

const hexBytes = (hex: string): ArrayBuffer => {
  const bytes = new Uint8Array(hex.length / 2);
  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = Number.parseInt(hex.slice(index * 2, index * 2 + 2), 16);
  }
  return bytes.buffer;
};

test('Exedra font preferences are opt-in and ignore malformed values', () => {
  assert.deepEqual(parseExedraFontPreferences(null), {
    tangyuan: false,
    'tsuku-old-gothic': false,
    'new-cinema-a': false,
  });
  assert.deepEqual(
    parseExedraFontPreferences(JSON.stringify({
      tangyuan: true,
      'tsuku-old-gothic': 'true',
      'new-cinema-a': true,
    })),
    {
      tangyuan: true,
      'tsuku-old-gothic': false,
      'new-cinema-a': true,
    },
  );
  assert.deepEqual(parseExedraFontPreferences('{broken'), {
    tangyuan: false,
    'tsuku-old-gothic': false,
    'new-cinema-a': false,
  });
});

test('static Exedra fonts fetch only after opt-in, persist, and can be disabled', async () => {
  const savedWindow = globalThis.window;
  const savedDocument = globalThis.document;
  const savedFontFace = globalThis.FontFace;
  const savedFetch = globalThis.fetch;
  const savedCaches = globalThis.caches;
  const savedCrypto = globalThis.crypto;

  const localValues = new Map<string, string>();
  const cachedBytes = new Map<string, Uint8Array>();
  const activeFaces = new Set<unknown>();
  const dataset: Record<string, string> = {};
  const networkCounts = new Map<string, number>();
  const dataByUrl = new Map(
    Object.values(EXEDRA_FONT_DEFINITIONS).map(definition => [
      definition.url,
      new Uint8Array(definition.bytes),
    ]),
  );

  const keyFor = (request: RequestInfo | URL): string =>
    typeof request === 'string'
      ? request
      : request instanceof URL
        ? request.pathname
        : new URL(request.url).pathname;
  const cache = {
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
    value: { open: async () => cache },
  });
  Object.defineProperty(globalThis, 'crypto', {
    configurable: true,
    value: {
      subtle: {
        digest: async (_algorithm: string, bytes: ArrayBuffer) => {
          const definition = Object.values(EXEDRA_FONT_DEFINITIONS).find(
            candidate => candidate.bytes === bytes.byteLength,
          );
          return hexBytes(definition?.sha256 ?? '00'.repeat(32));
        },
      },
    },
  });
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: async (request: RequestInfo | URL) => {
      const url = keyFor(request);
      networkCounts.set(url, (networkCounts.get(url) ?? 0) + 1);
      const bytes = dataByUrl.get(url);
      assert.ok(bytes, `unexpected font URL ${url}`);
      return new Response(bytes.slice() as unknown as BodyInit, {
        status: 200,
        headers: { 'content-length': String(bytes.byteLength) },
      });
    },
  });

  try {
    await initializeExedraFonts();
    assert.equal(networkCounts.size, 0, 'default initialization must fetch nothing');
    assert.equal(activeFaces.size, 0);

    const tangyuan = EXEDRA_FONT_DEFINITIONS.tangyuan;
    assert.equal(await enableExedraFont('tangyuan'), true);
    assert.equal(networkCounts.get(tangyuan.url), 1);
    assert.equal(dataset.exedraFontTangYuan, 'ready');
    let state = parseExedraFontRuntimeSnapshot(getExedraFontRuntimeSnapshot());
    assert.equal(state.fonts.tangyuan.status, 'ready');
    assert.equal(state.preferences.tangyuan, true);
    assert.match(state.fonts.tangyuan.validation, /SHA-256/u);

    disableExedraFont('tangyuan');
    assert.equal(dataset.exedraFontTangYuan, undefined);
    assert.equal(await enableExedraFont('tangyuan'), true);
    assert.equal(networkCounts.get(tangyuan.url), 1, 're-enable must use Cache Storage');

    const tsuku = EXEDRA_FONT_DEFINITIONS['tsuku-old-gothic'];
    assert.equal(await enableExedraFont('tsuku-old-gothic'), true);
    assert.equal(networkCounts.get(tsuku.url), 1);
    const tsukuFace = [...activeFaces].find(face =>
      face instanceof FakeFontFace && face.family === tsuku.family
    ) as FakeFontFace | undefined;
    assert.equal(tsukuFace?.descriptors?.weight, '400');

    await removeExedraFontCache('tsuku-old-gothic');
    assert.equal(dataset.exedraFontTsuku, undefined);
    assert.equal(cachedBytes.has(tsuku.url), false);
    state = parseExedraFontRuntimeSnapshot(getExedraFontRuntimeSnapshot());
    assert.equal(state.fonts['tsuku-old-gothic'].cached, false);
    assert.equal(
      JSON.parse(
        localValues.get(EXEDRA_FONT_PREFERENCES_STORAGE_KEY) ?? '{}',
      )['tsuku-old-gothic'],
      false,
    );
  } finally {
    for (const [key, value] of [
      ['window', savedWindow],
      ['document', savedDocument],
      ['FontFace', savedFontFace],
      ['fetch', savedFetch],
      ['caches', savedCaches],
      ['crypto', savedCrypto],
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

test('static assets, UI, and CSS keep Exedra language scopes isolated', () => {
  const css = readFileSync('app/globals.css', 'utf8');
  const page = readFileSync('app/reader/[id]/page.tsx', 'utf8');
  const settings = readFileSync('components/ExedraFontSettings.tsx', 'utf8');
  const runtime = readFileSync('lib/exedra-fonts.ts', 'utf8');
  const packageJson = readFileSync('package.json', 'utf8');

  assert.match(css, /\.exedra-page:lang\(zh-Hans\)/u);
  assert.match(css, /\.exedra-page:lang\(ja\)/u);
  assert.match(css, /Resource Han Rounded CN/u);
  assert.match(css, /Noto Sans SC/u);
  assert.equal(EXEDRA_FONT_DEFINITIONS['tsuku-old-gothic'].role, 'ja-ui');
  assert.equal(EXEDRA_FONT_DEFINITIONS['new-cinema-a'].role, 'ja-story');
  assert.match(
    EXEDRA_FONT_DEFINITIONS['tsuku-old-gothic'].description,
    /UI、标题与角色名/u,
  );
  assert.match(
    EXEDRA_FONT_DEFINITIONS['new-cinema-a'].description,
    /剧情、语音与旁白正文/u,
  );
  assert.match(css, /data-exedra-font-tsuku[^}]+reader-font-jp-title/su);
  assert.match(css, /data-exedra-font-new-cinema[^}]+exedra-jp-story-text/su);
  assert.doesNotMatch(
    css,
    /data-exedra-font-tsuku[^}]+reader-font-jp-body/su,
  );
  assert.match(page, /exedra-jp-story-text/u);
  assert.doesNotMatch(css, /@font-face\s*\{/u);
  assert.match(page, /lang=\{isExedra \? 'zh-Hans'/u);
  assert.match(page, /lang=\{isExedra \? 'ja'/u);
  assert.match(page, /isExedra=\{isExedraStory\}/u);
  assert.match(
    page,
    /void initializeReaderFonts\(\);\s*if \(isExedraStory\) void initializeExedraFonts\(\);/u,
  );
  assert.doesNotMatch(
    page,
    /Promise\.all\(\[initializeReaderFonts\(\), initializeExedraFonts\(\)\]\)/u,
  );
  assert.match(settings, /默认不请求、不启用/u);
  assert.match(settings, /下载并启用/u);
  assert.doesNotMatch(settings, /type="file"|FileUp|选择本地/u);
  assert.doesNotMatch(runtime, /importExedraLocalFont|file\.arrayBuffer/u);
  assert.equal(existsSync('app/api/fonts/exedra-tangyuan/route.ts'), false);
  assert.doesNotMatch(packageJson, /fflate/u);

  for (const definition of Object.values(EXEDRA_FONT_DEFINITIONS)) {
    const path = `public${definition.url}`;
    const bytes = readFileSync(path);
    assert.equal(bytes.byteLength, definition.bytes, `${path} byte length`);
    assert.equal(
      createHash('sha256').update(bytes).digest('hex'),
      definition.sha256,
      `${path} SHA-256`,
    );
  }
});
