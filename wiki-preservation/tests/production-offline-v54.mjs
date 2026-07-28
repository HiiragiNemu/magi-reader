import { chromium } from 'playwright';
import fs from 'node:fs/promises';

const revision = process.env.READER_REVISION || '5.5';
const base = 'https://magireco-cn-reader.pages.dev/';
const output = 'offline-v5-evidence';
await fs.mkdir(output, { recursive: true });

async function waitForProduction() {
  for (let attempt = 1; attempt <= 60; attempt += 1) {
    const nonce = `${Date.now()}-${attempt}`;
    try {
      const [healthResponse, indexResponse, swResponse, appResponse] = await Promise.all([
        fetch(`${base}health.json?offline=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
        fetch(`${base}?offline=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
        fetch(`${base}sw-v${revision}.js?offline=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
        fetch(`${base}app.js?offline=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
      ]);
      const [health, index, sw, app] = await Promise.all([
        healthResponse.json(), indexResponse.text(), swResponse.text(), appResponse.text(),
      ]);
      if (
        healthResponse.ok && indexResponse.ok && swResponse.ok && appResponse.ok &&
        health.uiRevision === revision &&
        index.includes(`/structured-ui.js?v=${revision}`) &&
        index.includes(`/doppel-ui.js?v=${revision}`) &&
        sw.includes(`magireco-cn-reader-v${revision}-offline`) &&
        app.includes(`const UI_VERSION = '${revision}'`) &&
        app.includes('`/sw-v${UI_VERSION}.js`')
      ) return { health };
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
  throw new Error(`生产站未在等待窗口内提供v${revision}版本化离线外壳`);
}

const production = await waitForProduction();
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 393, height: 852 },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
  locale: 'zh-CN',
  serviceWorkers: 'allow',
});
const page = await context.newPage();
const events = [];
page.on('console', (message) => events.push({ type: `console:${message.type()}`, text: message.text() }));
page.on('pageerror', (error) => events.push({ type: 'pageerror', text: String(error.stack || error) }));
page.on('requestfailed', (request) => events.push({ type: 'requestfailed', url: request.url(), error: request.failure()?.errorText || '' }));

try {
  await page.goto(`${base}health.json?seed=${Date.now()}`, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.evaluate(async () => {
    const cache = await caches.open('magireco-cn-reader-v4-ui-20260728-shell');
    await cache.put('/legacy-test', new Response('legacy'));
  });

  await page.goto(`${base}?offline-test=${Date.now()}#/characters`, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  await page.waitForSelector('.character-grid .character-card', { timeout: 40_000 });
  await page.waitForFunction(() => document.querySelectorAll('.character-card').length >= 40);
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));

  await page.waitForFunction(async (expectedRevision) => {
    const prefix = `magireco-cn-reader-v${expectedRevision}-offline`;
    const names = await caches.keys();
    if (!names.includes(`${prefix}-shell`)) return false;
    if (names.some((name) => name.startsWith('magireco-cn-reader-') && !name.startsWith(prefix))) return false;
    const required = [
      '/index.html',
      `/app.js?v=${expectedRevision}`,
      `/structured-ui.js?v=${expectedRevision}`,
      `/doppel-ui.js?v=${expectedRevision}`,
      '/data/structured/characters.json',
    ];
    const results = await Promise.all(required.map((url) => caches.match(url)));
    return results.every(Boolean);
  }, revision, { timeout: 40_000 });

  const onlineState = await page.evaluate(async (expectedRevision) => {
    const registration = await navigator.serviceWorker.ready;
    const cacheNames = await caches.keys();
    const prefix = `magireco-cn-reader-v${expectedRevision}-offline`;
    return {
      hash: location.hash,
      cards: document.querySelectorAll('.character-card').length,
      controller: Boolean(navigator.serviceWorker.controller),
      activeScript: registration.active?.scriptURL || '',
      cacheNames,
      oldCaches: cacheNames.filter((name) => name.startsWith('magireco-cn-reader-') && !name.startsWith(prefix)),
    };
  }, revision);
  if (!onlineState.controller) throw new Error(`Service Worker未控制页面：${JSON.stringify(onlineState)}`);
  if (!onlineState.activeScript.endsWith(`/sw-v${revision}.js`)) throw new Error(`Service Worker脚本文件错误：${JSON.stringify(onlineState)}`);
  if (onlineState.oldCaches.length) throw new Error(`仍存在旧Reader缓存：${JSON.stringify(onlineState)}`);
  await page.screenshot({ path: `${output}/01-online-character-catalog.png`, fullPage: false });

  await context.setOffline(true);
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 45_000 });
  await page.waitForSelector('.character-grid .character-card', { timeout: 30_000 });
  await page.waitForFunction(() => document.querySelectorAll('.character-card').length >= 40);
  const offlineState = await page.evaluate(() => ({
    hash: location.hash,
    cards: document.querySelectorAll('.character-card').length,
    title: document.querySelector('h1')?.textContent || '',
    appText: document.querySelector('#app')?.textContent?.replace(/\s+/g, ' ').trim().slice(0, 500) || '',
    width: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  if (offlineState.title !== '魔法少女与人物') throw new Error(`离线页面标题错误：${JSON.stringify(offlineState)}`);
  if (offlineState.cards < 40) throw new Error(`离线人物卡不足：${JSON.stringify(offlineState)}`);
  if (offlineState.width > offlineState.viewport + 2) throw new Error(`离线页面横向溢出：${JSON.stringify(offlineState)}`);
  await page.screenshot({ path: `${output}/02-offline-character-catalog.png`, fullPage: false });

  await context.setOffline(false);
  const result = { revision, production, onlineState, offlineState, events };
  await fs.writeFile(`${output}/result.json`, JSON.stringify(result, null, 2));
  console.log('PRODUCTION_OFFLINE_READER_OK', JSON.stringify({ revision, onlineState, offlineState }));
} catch (error) {
  await context.setOffline(false).catch(() => {});
  await fs.writeFile(`${output}/failure.txt`, String(error?.stack || error));
  await fs.writeFile(`${output}/events.json`, JSON.stringify(events, null, 2));
  await page.screenshot({ path: `${output}/99-failure.png`, fullPage: false }).catch(() => {});
  throw error;
} finally {
  await browser.close();
}
