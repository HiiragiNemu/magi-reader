import { chromium } from 'playwright';
import fs from 'node:fs/promises';

const base = 'https://magireco-cn-reader.pages.dev/';
const output = 'doppel-v53-evidence';
await fs.mkdir(output, { recursive: true });

async function waitForProduction() {
  for (let attempt = 1; attempt <= 50; attempt += 1) {
    const nonce = `${Date.now()}-${attempt}`;
    try {
      const [healthResponse, manifestResponse, doppelResponse, indexResponse, uiResponse] = await Promise.all([
        fetch(`${base}health.json?verify=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
        fetch(`${base}data/structured/manifest.json?verify=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
        fetch(`${base}data/structured/doppel.json?verify=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
        fetch(`${base}?verify=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
        fetch(`${base}doppel-ui.js?verify=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
      ]);
      const [health, manifest, doppel, index, ui] = await Promise.all([
        healthResponse.json(), manifestResponse.json(), doppelResponse.json(), indexResponse.text(), uiResponse.text(),
      ]);
      if (
        healthResponse.ok && manifestResponse.ok && doppelResponse.ok && indexResponse.ok && uiResponse.ok &&
        health.uiVersion === 5 && health.uiRevision === '5.3' &&
        manifest.doppel === 174 && doppel.length === 174 &&
        index.includes('doppel-ui.js?v=5.3') && ui.includes('STRUCTURED DOPPEL ARCHIVE')
      ) return { health, manifest, doppel };
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
  throw new Error('生产站未在等待窗口内提供Doppel v5.3');
}

const production = await waitForProduction();
const yuma = production.doppel.find((item) => item.character === '千岁由麻');
if (!yuma) throw new Error('生产Doppel数据缺少千岁由麻');

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 393, height: 852 },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
  colorScheme: 'light',
  locale: 'zh-CN',
});
const page = await context.newPage();
const failures = [];
const events = [];
const check = (condition, message) => { if (!condition) failures.push(message); };
page.on('console', (message) => events.push({ type: `console:${message.type()}`, text: message.text() }));
page.on('pageerror', (error) => events.push({ type: 'pageerror', text: String(error.stack || error) }));
page.on('requestfailed', (request) => events.push({ type: 'requestfailed', url: request.url(), text: request.failure()?.errorText || '' }));

try {
  await page.goto(`${base}?doppel-test=${Date.now()}#/doppel`, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  await page.waitForSelector('.doppel-grid .doppel-card', { timeout: 30_000 });
  await page.waitForFunction(() => document.querySelectorAll('.doppel-grid .doppel-card').length >= 40);
  check(await page.getByRole('heading', { name: 'Doppel图鉴', exact: true }).count() === 1, 'Doppel图鉴标题缺失');
  check((await page.locator('.structured-stats').innerText()).includes('174'), 'Doppel图鉴未显示174条统计');
  check(await page.locator('.portal-card[data-portal="doppel"]').count() === 0, '旧关键词Doppel卡片仍可见');
  const firstTitles = await page.locator('.doppel-card-copy small').allTextContents();
  check(firstTitles.length >= 40, `Doppel首页条目过少：${firstTitles.length}`);
  await page.screenshot({ path: `${output}/01-doppel-catalog-mobile.png` });

  const search = page.locator('#doppel-search');
  await search.fill('千岁由麻');
  await page.waitForFunction(() => {
    const cards = [...document.querySelectorAll('.doppel-card')];
    return cards.length === 1 && cards[0].textContent?.includes('千岁由麻');
  }, null, { timeout: 15_000 });
  const card = page.locator('.doppel-card').first();
  check((await card.innerText()).includes(yuma.name), `千岁由麻卡片缺少Doppel名：${yuma.name}`);
  await card.click();
  await page.waitForSelector('.doppel-detail .doppel-description', { timeout: 20_000 });
  const detailText = await page.locator('.doppel-detail').innerText();
  for (const [label, value] of [
    ['人物名', yuma.character],
    ['Doppel名', yuma.name],
    ['魔女文字', yuma.runes],
    ['中文感情称号', yuma.epithetZh],
    ['中文姿态', yuma.formZh],
  ]) {
    if (value) check(detailText.includes(value), `Doppel详情缺少${label}：${value}`);
  }
  check(detailText.includes(yuma.descriptionZh.slice(0, 24)), 'Doppel详情缺少中文说明');
  check(detailText.includes(yuma.descriptionJa.slice(0, 18)), 'Doppel详情缺少日文说明');
  check((await page.locator('.doppel-detail-image img').count()) === 1, 'Doppel详情缺少图像');

  const metrics = await page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const image = document.querySelector('.doppel-detail-image img');
    return {
      viewport,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      imageWidth: image?.getBoundingClientRect().width || 0,
    };
  });
  check(metrics.documentWidth <= metrics.viewport + 2, `Doppel详情横向溢出：${JSON.stringify(metrics)}`);
  check(metrics.bodyWidth <= metrics.viewport + 2, `Doppel详情body横向溢出：${JSON.stringify(metrics)}`);
  check(metrics.imageWidth <= metrics.viewport, `Doppel图像超出视口：${JSON.stringify(metrics)}`);
  await page.screenshot({ path: `${output}/02-yuma-doppel-detail-mobile.png` });

  await page.locator('.doppel-detail-image img').click();
  await page.waitForFunction(() => document.querySelector('#image-viewer')?.open === true, null, { timeout: 5000 });
  await page.screenshot({ path: `${output}/03-yuma-doppel-image-viewer.png` });
  await page.locator('[data-close-viewer]').click();

  await page.getByRole('button', { name: '查看人物图鉴', exact: true }).click();
  await page.waitForSelector('.character-detail .profile-fields', { timeout: 20_000 });
  check((await page.locator('.character-detail').innerText()).includes('千岁由麻'), 'Doppel到人物图鉴关联失败');
  await page.getByRole('button', { name: '阅读完整Wiki正文', exact: true }).click();
  await page.waitForSelector('.article-page .wiki-document', { timeout: 20_000 });
  check((await page.locator('.wiki-document').innerText()).includes('魔女化身'), 'Doppel关联的Wiki正文缺少魔女化身章节');

  const result = { yuma, metrics, firstTitles, events };
  await fs.writeFile(`${output}/result.json`, JSON.stringify(result, null, 2));
  if (failures.length) throw new Error(failures.join('\n'));
  console.log('PRODUCTION_DOPPEL_V53_BROWSER_OK', JSON.stringify({ yuma, metrics }));
} catch (error) {
  await fs.writeFile(`${output}/failure.txt`, String(error?.stack || error));
  await fs.writeFile(`${output}/events.json`, JSON.stringify(events, null, 2));
  await page.screenshot({ path: `${output}/99-failure-mobile.png` }).catch(() => {});
  throw error;
} finally {
  await browser.close();
}
