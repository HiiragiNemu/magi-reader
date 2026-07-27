import assert from 'node:assert/strict';
import test from 'node:test';

import {
  generalVoiceCatalogEntries,
  generalVoiceScriptToTxt,
  parseGeneralVoiceManifest,
  parseGeneralVoiceScript,
} from './general-voice-source.ts';

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
    percent: 100,
    has_cn: true,
    has_jp: false,
    filename_cn: '100100_cn.txt',
    path_cn: '/data/general_voice/100100/100100_cn.txt',
    title: '环彩羽 · 2 条语音',
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

test('general voice parser rejects duplicate or unsafe model ids', () => {
  assert.throws(() => parseGeneralVoiceManifest({
    version: 1,
    languages: ['cn'],
    models: [
      { id: '../100100', charId: '1001', langs: { cn: { groups: 1, voices: 1 } } },
    ],
  }));
});
