import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const page = readFileSync(path.resolve('app', 'page.tsx'), 'utf8');
const logo = readFileSync(path.resolve('components', 'MadeInMagiusLogo.tsx'), 'utf8');

test('home catalogue exposes none, partial, and complete translation status', () => {
  assert.match(
    page,
    /type TranslationProgressStatus = 'none' \| 'partial' \| 'complete';/u,
  );
  assert.match(
    page,
    /percent === 0 \? 'none' : percent === 100 \? 'complete' : 'partial'/u,
  );
  assert.match(
    page,
    /const groupProgressStatus = translationProgressStatus\(avgPercent\);/u,
  );
  assert.match(page, /data-translation-status=\{groupProgressStatus\}/u);
});

test('expanded story cards expose their own translation status', () => {
  assert.match(
    page,
    /const itemProgressStatus = translationProgressStatus\(progress\);/u,
  );
  assert.match(page, /data-translation-status=\{itemProgressStatus\}/u);
});

test('accepted MadeInMagius branding remains CSS-addressable in every theme', () => {
  assert.match(
    page,
    /<h1 className="magi-reader-brand min-w-0">[\s\S]*?<MadeInMagiusLogo \/>/u,
  );
  assert.match(logo, /magi-madeinmagius-logo/u);
  assert.match(logo, /<span>MadeIn<\/span><strong>Magius<\/strong>/u);
  assert.doesNotMatch(page, />Archive v3\.[01]</u);
});
