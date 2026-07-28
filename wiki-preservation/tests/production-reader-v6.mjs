import { chromium } from 'playwright';
import fs from 'node:fs/promises';

const base = 'https://magireco-cn-reader.pages.dev/';
const revision = '6.0';
const output = 'reader-v6-evidence';
await fs.mkdir(output, { recursive: true });

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForProduction() {
  for (let attempt = 1; attempt <= 100; attempt += 1) {
    const nonce = `${Date.now()}-${attempt}`;
    try {
      const [healthResponse, indexResponse, memoriaManifestResponse, memoriaIndexResponse] = await Promise.all([
        fetch(`${base}health.json?v6=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
        fetch(`${base}?v6=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
        fetch(`${base}data/structured/memoria-manifest.json?v6=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
        fetch(`${base}data/structured/memoria-index.json?v6=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
      ]);
      const [health, index, memoriaManifest, memoriaIndex] = await Promise.all([
        healthResponse.json(), indexResponse.text(), memoriaManifestResponse.json(), memoriaIndexResponse.json(),
      ]);
      if (
        healthResponse.ok && indexResponse.ok && memoriaManifestResponse.ok && memoriaIndexResponse.ok &&
        health.uiVersion === 6 && health.uiRevision === revision && health.counts?.pages === 500 &&
        health.counts?.memoria === 1042 && memoriaManifest.records === 1042 && memoriaIndex.length === 1042 &&
        index.includes(`/dense-reader.css?v=${revision}`) && index.includes(`/memoria-ui.js?v=${revision}`)
      ) return { health, memoriaManifest };
    } catch {}
    await sleep(6000);
  }
  throw new Error('生产站未在等待窗口内提供Reader v6与完整记忆结晶数据');
}

const production = await waitForProduction();
const browser = await chromium.launch({ headless: true });
const failures = [];
const events = [];
const check = (condition, message) => { if (!condition) failures.push(message); };

const desktop = await browser.newContext({ viewport: { width: 2048, height: 1060 }, deviceScaleFactor: 1, locale: 'zh-CN' });
const desktopPage = await desktop.newPage();
desktopPage.on('console', (message) => events.push({ scope: 'desktop', type: message.type(), text: message.text() }));
desktopPage.on('pageerror', (error) => events.push({ scope: 'desktop', type: 'pageerror', text: String(error.stack || error) }));

const mobile = await browser.newContext({
  viewport: { width: 393, height: 852 },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
  locale: 'zh-CN',
  serviceWorkers: 'allow',
});
const page = await mobile.newPage();
page.on('console', (message) => events.push({ scope: 'mobile', type: message.type(), text: message.text() }));
page.on('pageerror', (error) => events.push({ scope: 'mobile', type: 'pageerror', text: String(error.stack || error) }));
page.on('requestfailed', (request) => {
  if (!/\.(?:png|jpe?g|gif|webp|mp3)(?:\?|$)/i.test(request.url())) {
    events.push({ scope: 'mobile', type: 'requestfailed', url: request.url(), text: request.failure()?.errorText || '' });
  }
});

try {
  await desktopPage.goto(`${base}?reader-v6=${Date.now()}#/portal/all`, { waitUntil: 'networkidle', timeout: 90_000 });
  await desktopPage.waitForSelector('.article-row');
  const portalMetrics = await desktopPage.evaluate(() => ({
    mainWidth: document.querySelector('.site-main')?.getBoundingClientRect().width || 0,
    viewport: document.documentElement.clientWidth,
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    cardHeights: [...document.querySelectorAll('.portal-card')].map((node) => node.getBoundingClientRect().height),
    forbiddenCopy: /把原 Wiki|不会删减|这里不是|以保存快照/.test(document.body.innerText),
  }));
  check(portalMetrics.mainWidth >= 1650, `生产门户宽度不足：${JSON.stringify(portalMetrics)}`);
  check(Math.max(...portalMetrics.cardHeights) <= 100, `生产门户入口过高：${JSON.stringify(portalMetrics)}`);
  check(portalMetrics.overflow <= 2, `生产门户横向溢出：${JSON.stringify(portalMetrics)}`);
  check(!portalMetrics.forbiddenCopy, '生产门户仍出现开发指令式文案');
  await desktopPage.screenshot({ path: `${output}/01-portal-desktop.png` });

  const archive = await (await desktop.request.get(`${base}data/archive-index.json?v6=${Date.now()}`)).json();
  const article = archive.find((item) => item.title === '魔女化身' && item.namespace === 0)
    || archive.find((item) => item.title === '千岁由麻' && item.namespace === 0);
  check(Boolean(article), '生产归档缺少长文章验收目标');
  if (article) {
    await desktopPage.goto(`${base}?article-v6=${Date.now()}#/article/${encodeURIComponent(article.id)}`, { waitUntil: 'domcontentloaded', timeout: 90_000 });
    await desktopPage.waitForSelector('.wiki-document');
    await desktopPage.waitForTimeout(2500);
    const articleMetrics = await desktopPage.evaluate(() => {
      const root = document.querySelector('.article-page');
      const body = document.querySelector('.wiki-document');
      const large = [...document.querySelectorAll('.wiki-document img')]
        .map((node) => node.getBoundingClientRect())
        .filter((rect) => rect.width > 250 && rect.height > 150);
      return {
        pageWidth: root?.getBoundingClientRect().width || 0,
        bodyWidth: body?.getBoundingClientRect().width || 0,
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        maxImageHeight: Math.max(0, ...large.map((rect) => rect.height)),
        tableViewports: document.querySelectorAll('.table-viewport').length,
        enhanced: body?.dataset.enhanced || '',
      };
    });
    check(articleMetrics.pageWidth >= 1450, `生产文章未利用宽屏：${JSON.stringify(articleMetrics)}`);
    check(articleMetrics.bodyWidth >= 1150, `生产正文列过窄：${JSON.stringify(articleMetrics)}`);
    check(articleMetrics.maxImageHeight <= 530, `生产文章图片过高：${JSON.stringify(articleMetrics)}`);
    check(articleMetrics.overflow <= 2, `生产文章横向溢出：${JSON.stringify(articleMetrics)}`);
    await desktopPage.screenshot({ path: `${output}/02-article-desktop.png` });
  }

  await page.goto(`${base}?characters-v6=${Date.now()}#/characters`, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  await page.waitForSelector('.character-card');
  await page.waitForFunction(() => document.querySelectorAll('.character-card').length >= 40);
  check((await page.locator('.character-card').count()) >= 40, '人物图鉴首屏条目不足');
  check((await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 2, '人物图鉴横向溢出');

  const characterSearch = page.locator('#character-search');
  await characterSearch.fill('七海八千代');
  await page.waitForFunction(() => [...document.querySelectorAll('.character-card-title strong')].some((node) => node.textContent === '七海八千代'));
  await page.locator('.character-card').filter({ hasText: '七海八千代' }).filter({ hasNotText: 'ver.' }).first().click();
  await page.waitForSelector('.character-detail');
  const characterText = await page.locator('.character-detail').innerText();
  check(characterText.includes('雨宫天'), '七海八千代资料缺少声优');
  check(characterText.includes('播放角色语音'), '人物资料缺少语音入口');
  await page.getByRole('button', { name: /播放角色语音/ }).click();
  await page.waitForSelector('.voice-detail audio');
  const firstAudio = page.locator('.voice-detail audio').first();
  const audio = await firstAudio.evaluate((node) => ({ src: node.getAttribute('src'), controls: node.controls, preload: node.preload }));
  check(audio.controls && audio.preload === 'none', `语音播放器属性错误：${JSON.stringify(audio)}`);
  check(/Vo_char_1002_00_01\.mp3$/.test(audio.src || ''), `七海八千代首条语音地址错误：${audio.src}`);
  const audioResponse = await mobile.request.get(audio.src, { headers: { Range: 'bytes=0-2047' }, timeout: 30_000 });
  check([200, 206].includes(audioResponse.status()), `MP3范围请求失败：HTTP ${audioResponse.status()}`);
  await page.screenshot({ path: `${output}/03-voice-mobile.png` });

  await page.goto(`${base}?memoria-v6=${Date.now()}#/memoria`, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  await page.waitForSelector('.memoria-card');
  await page.waitForFunction(() => document.querySelectorAll('.memoria-card').length >= 40);
  check((await page.locator('.memoria-card').count()) === 48, '记忆结晶首屏不是48条');
  const memoriaStats = await page.locator('.structured-stats').innerText();
  check(memoriaStats.includes('1,042') || memoriaStats.includes('1042'), `记忆结晶总数显示错误：${memoriaStats}`);
  const memoriaSearch = page.locator('#memoria-search');
  await memoriaSearch.fill('1000円未満の魔法');
  await page.waitForFunction(() => [...document.querySelectorAll('.memoria-card')].some((node) => node.textContent.includes('1000円未満の魔法')));
  const memoriaCard = page.locator('.memoria-card').filter({ hasText: '1000円未満の魔法' }).first();
  check(await memoriaCard.count() === 1, '未找到1000円未満の魔法');
  await memoriaCard.click();
  await page.waitForSelector('.memoria-detail');
  const memoriaText = await page.locator('.memoria-detail').innerText();
  check(/HP/.test(memoriaText) && /ATK/.test(memoriaText) && /DEF/.test(memoriaText), '记忆结晶详情缺少数值');
  check(memoriaText.includes('能力效果'), '记忆结晶详情缺少效果对比');
  check(memoriaText.includes('资料完整'), '已验证记忆结晶被错误标为待补');
  check((await page.locator('.memoria-detail .reader-image').count()) === 1, '记忆结晶详情缺少图片');
  check((await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 2, '记忆结晶详情横向溢出');
  await page.screenshot({ path: `${output}/04-memoria-detail-mobile.png` });

  const registration = await page.evaluate(async () => {
    const value = await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) await new Promise((resolve) => setTimeout(resolve, 1500));
    return { active: value.active?.scriptURL || '', controller: Boolean(navigator.serviceWorker.controller) };
  });
  check(registration.active.includes(`/sw-v${revision}.js`), `Service Worker版本错误：${JSON.stringify(registration)}`);
  if (!registration.controller) {
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60_000 });
    await page.waitForSelector('.memoria-detail');
  }
  const cacheState = await page.evaluate(async () => {
    const names = await caches.keys();
    const detailResource = performance.getEntriesByType('resource').map((entry) => entry.name).find((name) => /\/data\/structured\/memoria\/[0-9a-f]\.json/.test(name));
    return {
      names,
      detailResource,
      detailCached: detailResource ? Boolean(await caches.match(detailResource, { ignoreSearch: true })) : false,
    };
  });
  check(cacheState.names.some((name) => name === `magireco-cn-reader-v${revision}-offline-shell`), `缺少v6离线缓存：${JSON.stringify(cacheState)}`);
  check(cacheState.detailCached, `已访问记忆结晶分片没有缓存：${JSON.stringify(cacheState)}`);

  await mobile.setOffline(true);
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForSelector('.memoria-detail', { timeout: 30_000 });
  const offlineText = await page.locator('.memoria-detail').innerText();
  check(offlineText.includes('1000円未満の魔法') || offlineText.includes('1000日元'), '断网后记忆结晶详情未恢复');
  check((await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 2, '离线记忆结晶详情横向溢出');
  await page.screenshot({ path: `${output}/05-memoria-offline-mobile.png` });
  await mobile.setOffline(false);

  const result = {
    production,
    portalMetrics,
    audio,
    audioStatus: audioResponse.status(),
    registration,
    cacheState,
    failures,
    events,
  };
  await fs.writeFile(`${output}/result.json`, JSON.stringify(result, null, 2));
  if (failures.length) throw new Error(failures.join('\n'));
  console.log('PRODUCTION_READER_V6_BROWSER_OK', JSON.stringify(result));
} catch (error) {
  await mobile.setOffline(false).catch(() => {});
  await fs.writeFile(`${output}/failure.txt`, String(error?.stack || error));
  await fs.writeFile(`${output}/events.json`, JSON.stringify(events, null, 2));
  await page.screenshot({ path: `${output}/99-mobile-failure.png` }).catch(() => {});
  await desktopPage.screenshot({ path: `${output}/99-desktop-failure.png` }).catch(() => {});
  throw error;
} finally {
  await browser.close();
}
