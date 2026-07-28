import { chromium } from 'playwright';
import fs from 'node:fs/promises';

const base = 'https://magireco-cn-reader.pages.dev/';
const output = 'structured-v5-evidence';
await fs.mkdir(output, { recursive: true });

async function waitForProduction() {
  for (let attempt = 1; attempt <= 50; attempt += 1) {
    const nonce = `${Date.now()}-${attempt}`;
    try {
      const [healthResponse, manifestResponse, uiResponse] = await Promise.all([
        fetch(`${base}health.json?v5=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
        fetch(`${base}data/structured/manifest.json?v5=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
        fetch(`${base}structured-ui.js?v5=${nonce}`, { headers: { 'Cache-Control': 'no-cache' } }),
      ]);
      const [health, manifest, ui] = await Promise.all([
        healthResponse.json(), manifestResponse.json(), uiResponse.text(),
      ]);
      if (
        healthResponse.ok && manifestResponse.ok && uiResponse.ok &&
        health.uiVersion === 5 && health.counts?.pages === 500 &&
        manifest.characters >= 235 && manifest.voiceWithAudio >= 16000 &&
        ui.includes('CHARACTER VOICE ARCHIVE')
      ) return { health, manifest };
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
  throw new Error('生产站未在等待窗口内提供结构化v5数据');
}

const production = await waitForProduction();
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
const check = (condition, message) => { if (!condition) failures.push(message); };

try {
  await page.goto(`${base}?structured-test=${Date.now()}#/characters`, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  await page.waitForSelector('.character-grid .character-card', { timeout: 30_000 });
  await page.waitForFunction(() => document.querySelectorAll('.character-grid .character-card').length >= 40);

  const firstPageTitles = await page.locator('.character-card-title strong').allTextContents();
  check(firstPageTitles.length >= 40, `人物首页数量过少：${firstPageTitles.length}`);
  check(!firstPageTitles.some((value) => /Winter Recollection|Music Collection|Ablaze/.test(value)), `人物列表含非人物页面：${firstPageTitles.join(' | ')}`);
  check(await page.getByRole('heading', { name: '魔法少女与人物', exact: true }).count() === 1, '人物图鉴标题缺失');
  check((await page.locator('.structured-stats').innerText()).includes('可播放语音'), '人物图鉴未显示语音统计');
  await page.screenshot({ path: `${output}/01-character-catalog-mobile.png` });

  const search = page.locator('#character-search');
  await search.fill('七海八千代');
  await page.waitForFunction(() => {
    const cards = [...document.querySelectorAll('.character-card-title strong')];
    return cards.length > 0 && cards.some((node) => node.textContent === '七海八千代');
  }, null, { timeout: 15_000 });
  const yachiyoCard = page.locator('.character-card').filter({ hasText: '七海八千代' }).filter({ hasNotText: 'ver.' }).first();
  check(await yachiyoCard.count() === 1, '未找到七海八千代基础人物条目');
  await yachiyoCard.click();
  await page.waitForSelector('.character-detail .profile-fields', { timeout: 20_000 });
  check(location !== undefined, '');
  const profileText = await page.locator('.character-detail').innerText();
  check(profileText.includes('雨宫天'), '人物详情缺少声优');
  check(profileText.includes('七海 やちよ'), '人物详情缺少日文名');
  check(profileText.includes('播放角色语音'), '人物详情缺少语音入口');
  check((await page.locator('.profile-fields > div').count()) >= 12, '人物信息字段过少');
  await page.screenshot({ path: `${output}/02-yachiyo-profile-mobile.png` });

  await page.getByRole('button', { name: /播放角色语音/ }).click();
  await page.waitForSelector('.voice-detail .voice-line audio', { timeout: 30_000 });
  await page.waitForFunction(() => document.querySelectorAll('.voice-line').length >= 40);
  const voiceHeader = await page.locator('.voice-detail-head').innerText();
  check(voiceHeader.includes('七海八千代'), '语音详情人物错误');
  check(voiceHeader.includes('72条记录'), `七海八千代语音数量错误：${voiceHeader}`);
  const audioCount = await page.locator('.voice-line audio').count();
  check(audioCount >= 40, `当前语音页音频控件过少：${audioCount}`);
  const firstAudio = page.locator('.voice-line audio').first();
  const audioInfo = await firstAudio.evaluate((node) => ({
    src: node.getAttribute('src'),
    controls: node.controls,
    preload: node.preload,
  }));
  check(audioInfo.controls === true, '音频控件未启用controls');
  check(audioInfo.preload === 'none', `音频preload不是none：${audioInfo.preload}`);
  check(/Vo_char_1002_00_01\.mp3$/.test(audioInfo.src || ''), `首条语音地址错误：${audioInfo.src}`);

  const audioResponse = await context.request.get(audioInfo.src, {
    headers: { Range: 'bytes=0-2047', 'User-Agent': 'Mozilla/5.0 MagirecoReaderBrowserTest/5.0' },
    timeout: 30_000,
  });
  check([200, 206].includes(audioResponse.status()), `MP3范围请求失败：HTTP ${audioResponse.status()}`);
  const contentType = audioResponse.headers()['content-type'] || '';
  check(/audio|mpeg|octet-stream/i.test(contentType), `MP3 Content-Type异常：${contentType}`);
  check((await page.locator('.voice-translation').first().innerText()).length > 5, '首条语音缺少中文译文');
  await page.screenshot({ path: `${output}/03-yachiyo-voice-player-mobile.png` });

  await page.getByRole('button', { name: '人物资料', exact: true }).click();
  await page.waitForSelector('.character-detail');
  await page.getByRole('button', { name: '阅读完整Wiki正文', exact: true }).click();
  await page.waitForSelector('.article-page .wiki-document', { timeout: 20_000 });
  check(location !== undefined, '');
  check((await page.locator('.wiki-document').innerText()).includes('七海八千代'), 'Wiki正文没有保留人物内容');

  const metrics = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  check(metrics.documentWidth <= metrics.viewport + 2, `页面存在横向溢出：${JSON.stringify(metrics)}`);
  check(metrics.bodyWidth <= metrics.viewport + 2, `body存在横向溢出：${JSON.stringify(metrics)}`);

  const result = {
    production,
    firstPageTitles,
    audioInfo,
    audioHttpStatus: audioResponse.status(),
    audioContentType: contentType,
    metrics,
  };
  await fs.writeFile(`${output}/result.json`, JSON.stringify(result, null, 2));
  if (failures.filter(Boolean).length) throw new Error(failures.filter(Boolean).join('\n'));
  console.log('PRODUCTION_STRUCTURED_V5_BROWSER_OK', JSON.stringify(result));
} catch (error) {
  await fs.writeFile(`${output}/failure.txt`, String(error?.stack || error));
  await page.screenshot({ path: `${output}/99-failure-mobile.png` }).catch(() => {});
  throw error;
} finally {
  await browser.close();
}
