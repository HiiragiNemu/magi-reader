import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  extractExedraVoiceId,
  extractMagirecoVoiceId,
  getExedraVoiceUrl,
  getExedraWikiVoiceUrl,
  getMagirecoVoiceProxyUrl,
  isExedraVoiceId,
  isMagirecoVoiceId,
  parseVoiceCue,
} from '../lib/audio/voice-cue.ts';

interface VoiceCatalog {
  groups: Array<{
    sources: Array<{
      soundName: string;
      sourceJson: string;
    }>;
  }>;
  summary: {
    sources: number;
  };
}

test('recognizes only strict Magia Record voice IDs', () => {
  assert.equal(isMagirecoVoiceId('vo_char_3031_00_01'), true);
  assert.equal(isMagirecoVoiceId('vo_char_3031_0_01'), false);
  assert.equal(isMagirecoVoiceId('VO_CHAR_3031_00_01'), false);
  assert.equal(isMagirecoVoiceId('../vo_char_3031_00_01'), false);
  assert.equal(isMagirecoVoiceId('vo_char_3031_00_01_hca'), false);
});

test('extracts Magia Record voice IDs from visible Chinese markers', () => {
  assert.equal(
    extractMagirecoVoiceId('【vo_char_3031_00_01｜19秒】我是绫野梨花！'),
    'vo_char_3031_00_01',
  );
  assert.equal(
    extractMagirecoVoiceId('prefix_vo_char_3031_00_01_suffix'),
    null,
  );
});

test('recognizes Exedra cue filenames without accepting paths or URLs', () => {
  const cue = 'cv_100101_other_story_01';
  assert.equal(isExedraVoiceId(cue), true);
  assert.equal(extractExedraVoiceId(`${cue}.json`), cue);
  assert.equal(extractExedraVoiceId(cue), cue);
  assert.equal(extractExedraVoiceId(`../${cue}.json`), null);
  assert.equal(
    extractExedraVoiceId(`https://example.invalid/${cue}.json`),
    null,
  );
  assert.equal(isExedraVoiceId('cv_100101_OTHER_story_01'), false);
});

test('builds only fixed-origin voice URLs', () => {
  assert.equal(
    getMagirecoVoiceProxyUrl('vo_char_3031_00_01'),
    '/api/audio/magireco-voice/vo_char_3031_00_01',
  );
  assert.equal(
    getExedraWikiVoiceUrl('cv_100101_other_story_01'),
    'https://exedra.wiki/wiki/Special:Redirect/file/cv_100101_other_story_01.ogg',
  );
  assert.equal(
    getExedraWikiVoiceUrl('cv_100803_other_story_01'),
    'https://exedra.wiki/wiki/Special:Redirect/file/cv_100805_other_story_01.ogg',
  );
  assert.equal(
    getExedraVoiceUrl('cv_113401_1'),
    '/audio/exedra-local/cv_namae_call_01.ogg',
  );
  assert.equal(
    getExedraVoiceUrl('cv_100101_other_story_01'),
    getExedraWikiVoiceUrl('cv_100101_other_story_01'),
  );
  assert.throws(
    () => getMagirecoVoiceProxyUrl('../../etc/passwd'),
    /Invalid Magia Record/,
  );
  assert.throws(
    () => getExedraWikiVoiceUrl('https://evil.invalid/a.ogg'),
    /Invalid Magia Exedra/,
  );
});

test('classifies both supported cue systems', () => {
  assert.deepEqual(parseVoiceCue('vo_char_3031_00_01'), {
    id: 'vo_char_3031_00_01',
    system: 'magireco',
  });
  assert.deepEqual(parseVoiceCue('cv_100101_other_story_01'), {
    id: 'cv_100101_other_story_01',
    system: 'exedra',
  });
  assert.equal(parseVoiceCue('se_ui_bad'), null);
});

test('every audited Exedra source resolves to its exact playable audio name', async () => {
  const catalogPath = join(
    dirname(fileURLToPath(import.meta.url)),
    '..',
    '..',
    'artifacts',
    'exedra_voice_catalog.json',
  );
  const catalog = JSON.parse(await readFile(catalogPath, 'utf8')) as VoiceCatalog;
  let sourceCount = 0;

  for (const group of catalog.groups) {
    for (const source of group.sources) {
      sourceCount += 1;
      const sourceId = source.sourceJson
        .split('/')
        .at(-1)
        ?.replace(/\.json$/u, '');
      assert.ok(sourceId);

      const url = getExedraVoiceUrl(sourceId);
      if (sourceId !== source.soundName) {
        assert.equal(
          url,
          `/audio/exedra-local/${source.soundName}.ogg`,
          sourceId,
        );
      } else if (sourceId.startsWith('cv_100803_')) {
        assert.equal(
          url,
          `https://exedra.wiki/wiki/Special:Redirect/file/${sourceId.replace(/^cv_100803_/u, 'cv_100805_')}.ogg`,
          sourceId,
        );
      } else {
        assert.equal(
          url,
          `https://exedra.wiki/wiki/Special:Redirect/file/${source.soundName}.ogg`,
          sourceId,
        );
      }
    }
  }

  assert.equal(sourceCount, catalog.summary.sources);
  assert.equal(sourceCount, 1_167);
});
