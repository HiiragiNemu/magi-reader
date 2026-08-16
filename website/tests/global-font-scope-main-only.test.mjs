import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const providers = readFileSync(new URL('../app/providers.tsx', import.meta.url), 'utf8');
const home = readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf8');
const reader = readFileSync(new URL('../app/reader/[id]/page.tsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('../app/ui-refinements.css', import.meta.url), 'utf8');
const readerFonts = readFileSync(new URL('../lib/reader-fonts.ts', import.meta.url), 'utf8');
const exedraFonts = readFileSync(new URL('../lib/exedra-fonts.ts', import.meta.url), 'utf8');
const exedraSettings = readFileSync(new URL('../components/ExedraFontSettings.tsx', import.meta.url), 'utf8');
const configurePages = readFileSync(new URL('../scripts/configure-pages-project.mjs', import.meta.url), 'utf8');
const cleanupWorkflow = readFileSync(
  new URL('../../.github/workflows/retire-exedra-test-environment.yml', import.meta.url),
  'utf8',
);
const testDeployWorkflow = new URL(
  '../../.github/workflows/deploy-exedra-proofreading-test.yml',
  import.meta.url,
);

test('persisted optional fonts initialize globally before home or reader routing', () => {
  assert.match(providers, /initializeReaderFonts/u);
  assert.match(providers, /initializeExedraFonts/u);
  assert.match(providers, /void initializeReaderFonts\(\)/u);
  assert.match(providers, /void initializeExedraFonts\(\)/u);
  assert.match(providers, /magi-site-font-scope/u);
});

test('Exedra home and reader screens expose one bounded whole-UI font scope', () => {
  assert.match(home, /storySystem === 'exedra' \? 'magi-exedra-ui-scope'/u);
  assert.match(reader, /isExedraStory \? 'magi-exedra-ui-scope'/u);
  assert.match(home, /magi-home-search-snippet reader-font-cn-body/u);
});

test('Chinese game fonts separate prose from titles and cover the complete UI', () => {
  assert.match(readerFonts, /正文使用腾祥嘉丽大圆/u);
  assert.match(readerFonts, /站点 UI 使用腾祥智黑/u);
  assert.match(css, /data-reader-font-chinese='ready'[\s\S]*magi-site-font-scope[\s\S]*MagiReaderGameChineseTitle/u);
  assert.match(css, /reader-font-cn-body[\s\S]*MagiReaderGameChineseBody/u);
  assert.match(css, /magi-reader-speaker-label[\s\S]*MagiReaderGameChineseTitle/u);
});

test('TangYuan covers all Exedra UI while Japanese story font roles stay isolated', () => {
  assert.match(exedraFonts, /Exedra 全部 UI 与简体中文正文/u);
  assert.match(exedraSettings, /猫啃网糖圆体覆盖 Exedra 全部 UI 与简体中文正文/u);
  assert.match(css, /data-exedra-font-tang-yuan='ready'[\s\S]*magi-exedra-ui-scope[\s\S]*MagiReaderExedraTangYuan/u);
  assert.match(css, /data-exedra-font-tsuku='ready'[\s\S]*reader-font-jp-title/u);
  assert.match(css, /data-exedra-font-new-cinema='ready'[\s\S]*reader-font-jp-body/u);
});

test('repository policy is main-only and retirement removes the old environment', () => {
  assert.equal(existsSync(testDeployWorkflow), false);
  assert.match(cleanupWorkflow, /workers\/scripts\/\$TEST_WORKER_NAME/u);
  assert.match(cleanupWorkflow, /EXEDRA-TEST/u);
  assert.match(cleanupWorkflow, /git push origin --delete/u);
  assert.match(cleanupWorkflow, /EXEDRA_TEST_WORKER_RETIRED/u);
  assert.match(cleanupWorkflow, /EXEDRA_TEST_BRANCH_RETIRED/u);
  assert.match(configurePages, /PROOFREADING_TARGET_BRANCH:\s*plainText\('main'\)/u);
});
