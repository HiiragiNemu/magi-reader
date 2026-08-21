import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const home = readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf8');
const reader = readFileSync(
  new URL('../app/reader/[id]/page.tsx', import.meta.url),
  'utf8',
);
const settings = readFileSync(
  new URL('../components/SiteSettingsWindow.tsx', import.meta.url),
  'utf8',
);
const css = readFileSync(
  new URL('../app/ui-refinements.css', import.meta.url),
  'utf8',
);

test('home toolbar exposes the existing font and site settings through a gear button', () => {
  assert.match(home, /<Settings aria-hidden="true" size=\{16\} \/>/u);
  assert.match(home, /aria-label="打开字体与站点设置"/u);
  assert.match(home, /<SiteSettingsWindow[\s\S]*isExedra=\{storySystem === 'exedra'\}/u);
  assert.match(settings, /<ReaderFontSettings theme=\{theme\} isExedra=\{isExedra\} \/>/u);
});

test('home assigns four explicit low-intensity source provenance states', () => {
  for (const status of [
    'exedra-official-tw',
    'exedra-human-cn',
    'magireco-source-unverified',
    'magireco-human-cn',
  ]) {
    assert.match(home, new RegExp(`'${status}'`, 'u'));
    assert.match(css, new RegExp(`data-source-status='${status}'`, 'u'));
  }
  assert.match(home, /data-source-status=\{groupSourceStatus\}/u);
  assert.match(home, /data-source-status=\{sourceVisualStatus\}/u);
  assert.match(home, /story\.official_tw_section_titles\?\.\[sectionIndex\]\?\.trim\(\)/u);
  assert.match(home, /officialTitle[\s\S]{0,240}\|\| `Episode/u);
});

test('Japanese story bodies and speaker labels carry a language boundary', () => {
  assert.match(reader, /lang="ja"[\s\S]{0,160}reader-font-jp-body/u);
  assert.match(reader, /lang=\{language === 'jp' \? 'ja' : 'zh-Hans'\}/u);
  assert.match(reader, /lang=\{header === row\.jp \? 'ja' : 'zh-Hans'\}/u);
  assert.match(css, /magi-site-font-scope \[lang='ja'\]/u);
  assert.doesNotMatch(
    css,
    /reader-font-cn-title \*,\s*\nhtml\[data-reader-font-chinese='ready'\] \.magi-site-font-scope \.magi-reader-speaker-label/u,
  );
});
