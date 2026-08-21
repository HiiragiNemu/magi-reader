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

test('requested hierarchy and source plaques expose distinct hover levels', () => {
  assert.match(home, /magi-home-story-heading-row/u);
  assert.doesNotMatch(home, /hover:scale-\[1\.01\]/u);
  assert.match(css, /magi-home-category-filter\[data-enabled='true'\]:is\(:hover, :focus-within\)/u);
  assert.match(css, /--magi-category-interaction-text:\s*#20282a/u);
  assert.match(css, /--magi-category-interaction-text:\s*#4a2f15/u);
  assert.match(css, /--magi-category-interaction-text:\s*#082f22/u);
  assert.match(css, /data-selected='true'\][\s\S]*?font-weight:\s*900 !important/u);
  assert.match(css, /magi-home-paper-root \.magi-home-category-trigger\s*\{[\s\S]*?font-weight:\s*900 !important/u);
  assert.match(css, /-webkit-text-stroke:\s*0\.18px currentColor/u);
  assert.doesNotMatch(css, /magi-home-category-trigger\[data-selected='false'\][\s\S]{0,160}?color:\s*#5a5347/u);
  assert.match(css, /magi-folder-source-card > \.magi-folder-heading-flow:is\(:hover, :focus-visible\)/u);
  assert.match(css, /magi-home-story-heading-row:is\(:hover, :focus-within\)/u);
  assert.match(css, /magi-home-episode-list > \.magi-home-episode-link:is\(:hover, :focus-visible\)/u);
  assert.match(css, /brightness\(1\.28\) saturate\(0\.32\)/u);
});

test('all home and reader scroll areas reuse theme-native tracks and resize strips', () => {
  assert.match(css, /magi-reader-theme-dark \.magi-settings-window\[data-theme='dark'\]/u);
  assert.match(css, /--magi-settings-hacker:\s*#61f5bf/u);
  assert.match(css, /rgba\(69, 230, 176, 0\.026\) 2px 3px/u);
  assert.match(css, /--magi-reader-scroll-track:\s*#071c2b/u);
  assert.match(css, /--magi-reader-scroll-thumb:\s*#28745f/u);
  assert.match(css, /magi-home-category-nav[\s\S]*?::-webkit-scrollbar-thumb/u);
  assert.match(css, /magi-home-catalog[\s\S]*?::-webkit-scrollbar-thumb/u);
  assert.match(css, /magi-reader-main[\s\S]*?::-webkit-scrollbar-thumb/u);
  assert.match(css, /magi-home-shell \.magi-sidebar-resize-handle/u);
  assert.match(css, /data-sidebar-scroll-container='true'[\s\S]*?::-webkit-scrollbar-thumb/u);
});

test('the extra low-fi border echo is isolated to empty pseudo-elements', () => {
  assert.match(css, /--magi-edge-echo-blur:\s*0\.42px/u);
  assert.match(css, /magi-home-category-trigger::after[\s\S]*?magi-reader-header::after/u);
  assert.match(css, /filter:\s*blur\(var\(--magi-edge-echo-blur/u);
  assert.doesNotMatch(
    css,
    /magi-home-paper-root \.magi-home-category-trigger\s*\{[^}]*filter:\s*blur/u,
  );
});

test('source plaques keep blank remainders while filled segments reuse exact story-card bases', () => {
  assert.match(
    css,
    /--magi-category-card-background:\s*linear-gradient\(\s*105deg,\s*rgba\(93, 100, 101, 0\.98\),\s*rgba\(119, 126, 126, 0\.96\)/u,
  );
  assert.match(
    css,
    /--magi-category-card-background:\s*linear-gradient\(\s*105deg,\s*rgba\(103, 82, 49, 0\.98\),\s*rgba\(126, 103, 65, 0\.96\)/u,
  );
  assert.match(css, /--magi-category-card-background:\s*oklch\(0\.596 0\.145 163\.225\)/u);
  assert.match(css, /--magi-category-card-background:\s*oklab\(0\.378 -0\.0755699 0\.0147714 \/ 0\.4\)/u);
  assert.match(
    css,
    /magi-home-category-filter\s*\{[\s\S]*?background:\s*var\(--magi-category-branch-surface/u,
  );
  assert.match(
    css,
    /magi-home-category-filter::before[\s\S]*?--magi-category-progress-feather:\s*0\.62rem[\s\S]*?--magi-category-progress-feather-half:\s*0\.31rem[\s\S]*?--magi-category-progress-feather-near:\s*0\.14rem[\s\S]*?inline-size:\s*min\([\s\S]*?magi-category-filter-progress[\s\S]*?magi-category-progress-feather-half[\s\S]*?--magi-category-card-background[\s\S]*?background-blend-mode:\s*color, normal[\s\S]*?mask-image:\s*var\(--magi-category-progress-mask\)[\s\S]*?mix-blend-mode:\s*normal/u,
  );
  assert.match(
    css,
    /data-progress-percent='0'\]::before\s*\{[\s\S]*?inline-size:\s*0[\s\S]*?opacity:\s*0/u,
  );
  assert.doesNotMatch(
    css,
    /magi-home-category-filter\[data-progress-percent='100'\]::before/u,
  );
  assert.match(
    css,
    /data-selected='true'\][\s\S]*?background:\s*color-mix\([\s\S]*?--magi-category-branch-surface[\s\S]*?--magi-category-branch-selected-line/u,
  );
  assert.doesNotMatch(css, /--magi-category-progress-base/u);
  assert.match(css, /background-color:\s*rgba\(13, 29, 50, 0\.82\) !important/u);
  assert.match(css, /data-filter='all'\][\s\S]*?--magi-category-progress-fill:\s*transparent/u);
  assert.match(css, /data-filter='human-cn'\][\s\S]*?--magi-category-progress-fill:\s*var\(--magi-source-human-progress-end\)/u);
  assert.match(css, /--magi-folder-progress-feather:\s*1rem/u);
  assert.match(css, /--magi-folder-progress-feather-mid:\s*0\.52rem/u);
  assert.match(css, /--magi-folder-progress-feather-near:\s*0\.2rem/u);
  assert.match(css, /magi-folder-human-progress-end[\s\S]*?- var\(--magi-folder-progress-feather\)/u);
  assert.match(css, /magi-folder-human-fill\) 78%,[\s\S]*?magi-folder-human-fill\) 32%,[\s\S]*?magi-folder-verified-fill/u);
  assert.match(css, /data-verified-progress-percent='0'\][\s\S]*?background:\s*linear-gradient\([\s\S]*?magi-folder-human-fill\) 78%, transparent[\s\S]*?magi-folder-human-fill\) 32%, transparent[\s\S]*?transparent var\(--magi-folder-human-progress-end/u);
  assert.match(css, /data-human-progress-percent='0'\]:not\(\[data-verified-progress-percent='0'\]\)[\s\S]*?background:\s*linear-gradient\([\s\S]*?magi-folder-verified-fill\) 78%, transparent[\s\S]*?magi-folder-verified-fill\) 32%, transparent[\s\S]*?transparent var\(--magi-folder-translated-progress-end/u);
  assert.match(css, /--magi-source-verified-progress-end:\s*oklch\(0\.68 0\.018 195 \/ 0\.26\)/u);
  assert.match(css, /--magi-source-verified-progress-end:\s*oklch\(0\.7 0\.014 195 \/ 0\.22\)/u);
  assert.match(css, /--magi-source-verified-progress-end:\s*oklch\(0\.62 0\.13 175 \/ 0\.58\)/u);
  assert.doesNotMatch(css, /magi-home-category-filter\[data-enabled='true'\][^{]*\{[^}]*--magi-category-branch-surface:\s*color-mix/u);
  assert.match(css, /data-enabled='true'\]:is\(:hover, :focus-within\)[\s\S]*?brightness\(1\.1\)/u);
  assert.match(css, /data-progress-available='false'\]::before,[\s\S]*?data-enabled='false'\]::before[\s\S]*?opacity:\s*0/u);
});
