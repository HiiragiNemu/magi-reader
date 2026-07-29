import { chromium } from 'playwright';
import fs from 'node:fs/promises';

const base = 'https://magireco-cn-reader.pages.dev/';
const output = 'reader-audio-evidence';
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
const events = [];
page.on('console', (message) => events.push({ type: 'console', level: message.type(), text: message.text() }));
page.on('requestfailed', (request) => events.push({ type: 'requestfailed', url: request.url(), error: request.failure()?.errorText }));

try {
  await page.goto(`${base}?audio-test=${Date.now()}#/audio`, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  await page.waitForSelector('.voice-character-grid .voice-character-card', { timeout: 45_000 });
  const cards = await page.locator('.voice-character-card').count();
  if (cards < 20) throw new Error(`语音人物首屏数量过少：${cards}`);
  const indexMetrics = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    documentWidth: document.documentElement.scrollWidth,
    title: document.querySelector('.voice-audio-page h1')?.textContent || '',
    stats: [...document.querySelectorAll('.voice-audio-stats strong')].map((node) => node.textContent),
    firstName: document.querySelector('.voice-character-card strong')?.textContent || '',
  }));
  if (indexMetrics.documentWidth > indexMetrics.viewport + 2) throw new Error(`语音索引横向溢出：${JSON.stringify(indexMetrics)}`);
  if (indexMetrics.title !== '角色语音') throw new Error(`语音标题错误：${indexMetrics.title}`);
  await page.screenshot({ path: `${output}/01-audio-index-mobile.png` });

  await page.locator('.voice-character-card').first().click();
  await page.waitForSelector('.voice-audio-list .voice-audio-card audio', { timeout: 45_000 });
  const players = await page.locator('.voice-audio-card audio').count();
  if (players < 20) throw new Error(`角色语音播放器数量过少：${players}`);

  const select = page.locator('#audio-costume');
  const optionCount = await select.locator('option').count();
  if (optionCount > 2) {
    const value = await select.locator('option').nth(1).getAttribute('value');
    await select.selectOption(value);
    await page.waitForTimeout(500);
  }

  const firstAudio = page.locator('audio[data-voice-player]').first();
  await firstAudio.evaluate((element) => element.load());
  await page.waitForFunction(() => {
    const audio = document.querySelector('audio[data-voice-player]');
    return Boolean(audio?.currentSrc) && audio.readyState >= 1;
  }, null, { timeout: 45_000 });

  const detailMetrics = await page.evaluate(() => {
    const audio = document.querySelector('audio[data-voice-player]');
    const status = audio?.closest('.voice-audio-card')?.querySelector('[data-source-status]')?.textContent || '';
    return {
      viewport: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      cards: document.querySelectorAll('.voice-audio-card').length,
      players: document.querySelectorAll('audio[data-voice-player]').length,
      currentSrc: audio?.currentSrc || '',
      readyState: audio?.readyState ?? -1,
      status,
      title: document.querySelector('.voice-audio-page h1')?.textContent || '',
      selectedCostume: document.querySelector('#audio-costume')?.value || '',
    };
  });
  if (detailMetrics.documentWidth > detailMetrics.viewport + 2) throw new Error(`语音详情横向溢出：${JSON.stringify(detailMetrics)}`);
  if (!/raw\.githubusercontent\.com|cdn\.mfjl\.wiki|wikia|nocookie/i.test(detailMetrics.currentSrc)) {
    throw new Error(`播放器没有使用允许的GitHub/CDN/Fandom来源：${JSON.stringify(detailMetrics)}`);
  }
  if (detailMetrics.readyState < 1) throw new Error(`音频元数据未载入：${JSON.stringify(detailMetrics)}`);
  await page.screenshot({ path: `${output}/02-audio-character-mobile.png` });

  await firstAudio.evaluate(async (element) => {
    try {
      await element.play();
      await new Promise((resolve) => setTimeout(resolve, 600));
      element.pause();
    } catch {
      // loadedmetadata/currentSrc remains the cross-origin playback criterion.
    }
  });

  const manifestResponse = await page.request.get(`${base}data/voice-audio/manifest.json?test=${Date.now()}`);
  if (!manifestResponse.ok()) throw new Error(`语音manifest HTTP ${manifestResponse.status()}`);
  const manifest = await manifestResponse.json();
  if (manifest.voiceFiles < 18000 || manifest.characters < 220 || manifest.fandomUrls < 17000) {
    throw new Error(`语音完整性不足：${JSON.stringify(manifest)}`);
  }

  const result = { cards, players, indexMetrics, detailMetrics, manifest, events };
  await fs.writeFile(`${output}/result.json`, JSON.stringify(result, null, 2));
  console.log('PRODUCTION_AUDIO_V64_OK', JSON.stringify(detailMetrics));
} catch (error) {
  await page.screenshot({ path: `${output}/99-audio-failure.png` }).catch(() => {});
  await fs.writeFile(`${output}/failure.json`, JSON.stringify({ error: String(error?.stack || error), events }, null, 2));
  throw error;
} finally {
  await browser.close();
}
