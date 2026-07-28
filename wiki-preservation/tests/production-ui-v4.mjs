import { chromium } from 'playwright';
import fs from 'node:fs/promises';

const base = 'https://magireco-cn-reader.pages.dev/';
const output = 'ui-test-output';
await fs.mkdir(output, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 393, height: 852 },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
  colorScheme: 'dark',
  locale: 'zh-CN',
});
const page = await context.newPage();
const failures = [];
const check = (condition, message) => { if (!condition) failures.push(message); };

async function diagnosticState(stage, error = null) {
  const state = await page.evaluate(() => ({
    url: location.href,
    hash: location.hash,
    portalCards: [...document.querySelectorAll('[data-portal]')].map((node) => ({
      id: node.dataset.portal,
      active: node.classList.contains('active'),
      text: node.textContent?.replace(/\s+/g, ' ').trim().slice(0, 160),
      rect: node.getBoundingClientRect().toJSON(),
    })),
    activeCards: [...document.querySelectorAll('.portal-card.active')].map((node) => node.dataset.portal),
    resultRows: document.querySelectorAll('#portal-results .article-row').length,
    resultHeading: document.querySelector('#portal-results h2')?.textContent || '',
    appText: document.querySelector('#app')?.textContent?.replace(/\s+/g, ' ').trim().slice(0, 500) || '',
  })).catch((evaluationError) => ({ evaluationError: String(evaluationError) }));
  await fs.writeFile(`${output}/diagnostic-${stage}.json`, JSON.stringify({ state, error: error ? String(error.stack || error) : null }, null, 2));
  return state;
}

try {
  await page.goto(`${base}?ui-test=${Date.now()}#/portal/all`, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  await page.waitForSelector('.portal-card', { timeout: 30_000 });
  check(await page.locator('.portal-card').count() >= 8, '主题入口卡片数量不足');
  await page.screenshot({ path: `${output}/01-portal-all-mobile.png` });
  await diagnosticState('portal-all');

  const characterCard = page.locator('[data-portal="characters"]');
  check(await characterCard.count() === 1, '找不到唯一的人物入口卡片');
  await characterCard.scrollIntoViewIfNeeded();
  await characterCard.click({ timeout: 15_000 });
  await page.waitForFunction(() => location.hash === '#/portal/characters', null, { timeout: 15_000 });
  await page.waitForFunction(() => document.querySelectorAll('#portal-results .article-row').length > 0, null, { timeout: 15_000 });
  const characterState = await diagnosticState('characters');
  check(characterState.hash === '#/portal/characters', `人物入口URL错误：${characterState.hash}`);
  check(characterState.resultRows > 0, '人物入口点击后没有结果');
  check(characterState.activeCards?.includes('characters'), '人物入口没有选中反馈');
  await page.locator('#portal-results').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${output}/02-characters-results-mobile.png` });

  await page.locator('#portal-results .article-row').first().click();
  await page.waitForSelector('.article-page .wiki-document', { timeout: 30_000 });
  await page.waitForTimeout(800);

  const metrics = await page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const images = [...document.querySelectorAll('.wiki-document img')];
    const tables = [...document.querySelectorAll('.wiki-document table')];
    const bodyRect = document.querySelector('.wiki-document')?.getBoundingClientRect();
    return {
      viewport,
      documentScrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      articleWidth: bodyRect?.width || 0,
      oversizedImages: images.filter((img) => img.getBoundingClientRect().width > viewport + 1).length,
      unwrappedTables: tables.filter((table) => !table.parentElement?.classList.contains('table-viewport')).length,
      imageCount: images.length,
      tableCount: tables.length,
    };
  });
  check(metrics.documentScrollWidth <= metrics.viewport + 2, `页面横向溢出：${JSON.stringify(metrics)}`);
  check(metrics.bodyScrollWidth <= metrics.viewport + 2, `body横向溢出：${JSON.stringify(metrics)}`);
  check(metrics.articleWidth <= metrics.viewport, `正文宽度超出视口：${JSON.stringify(metrics)}`);
  check(metrics.oversizedImages === 0, `存在超出视口图片：${JSON.stringify(metrics)}`);
  check(metrics.unwrappedTables === 0, `存在未包裹表格：${JSON.stringify(metrics)}`);
  await fs.writeFile(`${output}/metrics.json`, JSON.stringify(metrics, null, 2));

  await page.locator('.display-menu > summary').click();
  for (const [label, id] of [['日间', 'light'], ['夜间', 'dark'], ['护眼', 'eye'], ['纯黑', 'oled']]) {
    const button = page.getByRole('button', { name: label, exact: true });
    await button.click();
    check(await page.locator('html').getAttribute('data-theme') === id, `主题切换失败：${label}`);
    if (label !== '纯黑') await page.locator('.display-menu > summary').click();
  }
  await page.screenshot({ path: `${output}/03-article-oled-mobile.png` });

  const image = page.locator('.wiki-document img:not(.image-failed)').first();
  if (await image.count()) {
    await image.scrollIntoViewIfNeeded();
    await image.click();
    check(await page.locator('#image-viewer').evaluate((node) => node.open), '图片全屏查看器没有打开');
    await page.screenshot({ path: `${output}/04-image-viewer-mobile.png` });
    await page.locator('[data-close-viewer]').click();
  }

  if (failures.length) throw new Error(failures.join('\n'));
  console.log('PRODUCTION_UI_V4_BROWSER_OK', metrics);
} catch (error) {
  await diagnosticState('failure', error);
  await page.screenshot({ path: `${output}/99-failure-mobile.png` }).catch(() => {});
  throw error;
} finally {
  await browser.close();
}
