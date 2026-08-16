import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const reader = readFileSync(
  new URL('../app/reader/[id]/page.tsx', import.meta.url),
  'utf8',
);
const sidebar = readFileSync(
  new URL('../components/Sidebar.tsx', import.meta.url),
  'utf8',
);
const home = readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf8');
const css = readFileSync(
  new URL('../app/ui-refinements.css', import.meta.url),
  'utf8',
);

test('desktop sidebar expands and centers the active story without scrolling the document', () => {
  assert.match(sidebar, /data-sidebar-scroll-container="true"/u);
  assert.match(sidebar, /scrollContainerRef/u);
  assert.match(sidebar, /setCategoryOverrides/u);
  assert.match(sidebar, /setFolderOverrides/u);
  assert.match(sidebar, /container\.scrollTo\(\{/u);
  assert.doesNotMatch(sidebar, /if \(!isOpen \|\| !currentId\) return/u);
  assert.match(reader, /utilityPanelOpen=\{utilityPanelOpen\}/u);
  assert.match(reader, /onOpenUtilityPanel=\{openUtilityPanel\}/u);
});

test('reader utility window leaves document flow and animates into desktop and mobile docks', () => {
  assert.ok(
    reader.indexOf('magi-reader-utility-panel-overlay')
      < reader.indexOf('<main'),
  );
  assert.match(reader, /utilityPanelClosing/u);
  assert.match(reader, /magi-reader-header-stack/u);
  assert.match(reader, /magi-reader-utility-dock-mobile/u);
  assert.match(sidebar, /magi-reader-utility-dock-desktop/u);
  assert.match(css, /magi-reader-utility-open-desktop/u);
  assert.match(css, /magi-reader-utility-close-mobile/u);
  assert.match(css, /\.magi-reader-utility-dock::after/u);
  assert.match(css, /\.magi-reader-source-download/u);
});

test('mobile home toolbar packs controls and supports a draggable review button dock', () => {
  assert.match(home, /MOBILE_REVIEW_PLACEMENT_STORAGE_KEY/u);
  assert.match(home, /mobileReviewPlacement/u);
  assert.match(home, /setPointerCapture/u);
  assert.match(home, /homeToolbarRef/u);
  assert.match(home, /homeHeadingRef/u);
  assert.match(home, /renderMobileReviewButton\('floating'\)/u);
  assert.match(home, /renderMobileReviewButton\('toolbar'\)/u);
  assert.match(home, /magi-home-mobile-category-nav/u);
  assert.match(css, /\.magi-home-mobile-review-button/u);
  assert.match(css, /\.magi-home-mobile-review-button\[data-placement='floating'\]::before/u);
  assert.match(css, /\.magi-home-toolbar-row\s*\{[\s\S]*justify-content: flex-start !important/u);
});
