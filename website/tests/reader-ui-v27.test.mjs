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
});

test('reader navigation is an independent draggable floating widget, never a sidebar or header dock', () => {
  assert.match(reader, /DraggableReaderWidget/u);
  assert.match(reader, /UTILITY_WIDGET_POSITION_STORAGE_KEY/u);
  assert.match(reader, /magi-reader-utility-widget/u);
  assert.match(reader, /magi-reader-utility-panel-floating/u);
  assert.match(reader, /magi-reader-utility-fab/u);
  assert.doesNotMatch(reader, /magi-reader-utility-panel-overlay/u);
  assert.doesNotMatch(reader, /magi-reader-utility-dock-mobile/u);
  assert.doesNotMatch(sidebar, /utilityPanelOpen/u);
  assert.doesNotMatch(sidebar, /onOpenUtilityPanel/u);
  assert.doesNotMatch(sidebar, /magi-reader-utility-dock-desktop/u);
  assert.match(css, /\.magi-reader-floating-widget/u);
  assert.match(css, /\.magi-reader-utility-panel-floating/u);
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
