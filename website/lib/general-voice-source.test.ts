import assert from 'node:assert/strict';
import test from 'node:test';

import {
  generalVoiceCatalogEntries,
  generalVoiceScriptToTxt,
  loadGeneralVoiceManifest,
  parseGeneralVoiceManifest,
  parseGeneralVoiceScript,
} from './general-voice-source.ts';

test('general voice upstream fetch is timed, rejects redirects, and cancels failures', async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ redirect?: RequestRedirect; signal?: AbortSignal | null }> = [];
  let failedCancelled = false;
  globalThis.fetch = (async (_input: URL | RequestInfo, init?: RequestInit) => {
    calls.push({ redirect: init?.redirect, signal: init?.signal });
    if (calls.length === 1) {
      return new Response(new ReadableStream<Uint8Array>({
        cancel() {
          failedCancelled = true;
        },
      }), { status: 502 });
    }
    return Response.json({
      version: 1,
      languages: ['cn'],
      models: [{
        id: '100100',
        charId: '1001',
        langs: { cn: { groups: 1, voices: 1 } },
      }],
    });
  }) as typeof fetch;
  try {
    const loaded = await loadGeneralVoiceManifest();
    assert.equal(loaded.models.length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(calls.length, 2);
  assert.ok(calls.every(call => call.redirect === 'error'));
  assert.ok(calls.every(call => call.signal instanceof AbortSignal));
  assert.equal(failedCancelled, true);
});

const manifest = parseGeneralVoiceManifest({
  version: 1,
  languages: ['cn', 'en'],
  models: [
    {
      id: '100100',
      charId: '1001',
      char: { jp: '環 いろは', cn: '环彩羽', en: 'Iroha Tamaki' },
      costume: { jp: '環 いろは', cn: '环彩羽', en: 'Iroha Tamaki' },
      langs: { cn: { groups: 2, voices: 2 }, en: { groups: 2, voices: 2 } },
    },
  ],
});

const script = parseGeneralVoiceScript({
  story: {
    group_2: [
      {
        autoTurnFirst: 1.2,
        chara: [{ id: 100100, voice: 'vo_char_1001_00_03', textHome: '小忧她@总能让大家微笑。' }],
      },
    ],
    group_1: [
      {
        autoTurnFirst: 2.4,
        chara: [{ id: 100100, voice: 'vo_char_1001_00_01', textHome: '我叫环彩羽。' }],
      },
      { autoTurnFirst: 0.6, chara: [{ id: 100100, motion: 1 }] },
    ],
  },
});

test('general voice manifest creates a safe MagiReader category entry', () => {
  const entries = generalVoiceCatalogEntries(manifest);
  assert.equal(entries.length, 1);
  assert.deepEqual(entries[0], {
    id: 'voice_100100',
    category: 'general_voice',
    folder: '1001 - 环彩羽（環 いろは）',
    percent: 0,
    has_cn: true,
    has_jp: false,
    filename_cn: '100100_cn.txt',
    path_cn: '/data/general_voice/100100/100100_cn.txt',
    title: '100100 · 环彩羽 · 2 条语音 · 字幕汉化率待读取',
    game: 'magireco',
    source_identity: 'general_voice/100100',
  });
});

test('general voice TXT is ordered numerically and preserves canonical sections', () => {
  const txt = generalVoiceScriptToTxt(script, manifest.models[0]);
  assert.match(txt, /^--- \[Section 1\] \(Source: 100100\.json\) ---/u);
  assert.ok(txt.indexOf('vo_char_1001_00_01') < txt.indexOf('vo_char_1001_00_03'));
  assert.match(txt, /环彩羽：【vo_char_1001_00_01｜3秒】我叫环彩羽。/u);
  assert.match(txt, /环彩羽：【vo_char_1001_00_03｜1\.2秒】小忧她／总能让大家微笑。/u);
});

test('general voice TXT preserves every textHome as an independent editable line', () => {
  const multi = parseGeneralVoiceScript({
    story: {
      group_1: [
        {
          autoTurnFirst: 2,
          chara: [{ voice: 'voice_1', textHome: '第一句@后半\n末尾' }],
        },
        {
          chara: [{ textHome: '第二句' }],
        },
      ],
    },
  });
  const txt = generalVoiceScriptToTxt(multi, manifest.models[0]);
  assert.match(txt, /【voice_1｜2秒｜文本 1\/2】第一句／后半／末尾/u);
  assert.match(txt, /【voice_1｜2秒｜文本 2\/2】第二句/u);
  assert.doesNotMatch(txt, /第一句／后半 第二句/u);
});

test('general voice TXT leaves a real empty subtitle slot when textHome is absent', () => {
  const missing = parseGeneralVoiceScript({
    story: {
      group_1: [{
        autoTurnFirst: 20.1,
        chara: [{ voice: 'vo_char_4062_00_01', motion: 200 }],
      }],
    },
  });
  const txt = generalVoiceScriptToTxt(missing, manifest.models[0]);
  assert.match(txt, /【vo_char_4062_00_01｜20\.1秒】\s*$/u);
  assert.doesNotMatch(txt, /语音资源：/u);
});

test('general voice parser rejects duplicate or unsafe model ids', () => {
  assert.throws(() => parseGeneralVoiceManifest({
    version: 1,
    languages: ['cn'],
    models: [
      { id: '../100100', charId: '1001', langs: { cn: { groups: 1, voices: 1 } } },
    ],
  }));
});

test('general voice parser repairs the audited gropu key typo without collisions', () => {
  const repaired = parseGeneralVoiceScript({
    story: {
      group_1: [],
      gropu_2: [{ chara: [{ voice: 'vo_char_3900_00_03' }] }],
    },
  });
  assert.deepEqual(Object.keys(repaired.story), ['group_1', 'group_2']);
  assert.throws(() => parseGeneralVoiceScript({
    story: {
      group_2: [],
      gropu_2: [],
    },
  }), /语音分组无效/u);
});
