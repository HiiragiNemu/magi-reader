import { chromium } from 'playwright';
import fs from 'node:fs/promises';

const base = process.env.SITE_URL;
if (!base) throw new Error('SITE_URL is required');

await fs.mkdir('public-story-evidence', { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  locale: 'zh-CN',
});
const errors = [];
page.on('pageerror', error => errors.push(String(error.stack || error)));

try {
  await page.goto(`${base}/?probe=${Date.now()}`, {
    waitUntil: 'networkidle',
    timeout: 120_000,
  });
  await page.getByRole('heading', { name: '剧情阅读器' }).waitFor();
  const body = await page.locator('body').innerText();
  for (const forbidden of ['机器翻译人工校验清单', '管理机器校验标记', '投稿审核']) {
    if (body.includes(forbidden)) {
      throw new Error(`review management leaked into public homepage: ${forbidden}`);
    }
  }

  const magirecoLinks = page.locator('a[href^="/reader/"]');
  if (await magirecoLinks.count() < 1) throw new Error('Magia Record stories missing');
  await page.screenshot({ path: 'public-story-evidence/01-magireco-home.png' });

  await page.getByRole('button', { name: '切换到 Magia Exedra 剧情' }).click();
  await page.waitForTimeout(700);
  const exedraLinks = page.locator('a[href^="/reader/"]');
  if (await exedraLinks.count() < 1) throw new Error('Magia Exedra stories missing');
  await page.screenshot({ path: 'public-story-evidence/02-exedra-home.png' });

  await exedraLinks.first().click();
  await page.waitForURL(/\/reader\//, { timeout: 60_000 });
  await page.getByRole('button', { name: '显示中日双语' }).waitFor({ timeout: 60_000 });
  const readerText = await page.locator('main').innerText();
  if (readerText.length < 20 || readerText.includes('无法打开这段剧情')) {
    throw new Error('Exedra reader content failed');
  }
  await page.screenshot({ path: 'public-story-evidence/03-exedra-reader.png' });
} finally {
  await fs.writeFile(
    'public-story-evidence/result.json',
    JSON.stringify({ errors, url: page.url() }, null, 2),
  );
  await browser.close();
}

if (errors.length) throw new Error(errors.join('\n'));
console.log('PUBLIC_MAGIA_STORY_READER_OK');
