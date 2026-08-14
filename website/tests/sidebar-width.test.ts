import assert from 'node:assert/strict';
import test from 'node:test';

import {
  HOME_SIDEBAR_WIDTH_DEFAULT,
  HOME_SIDEBAR_WIDTH_MAX,
  HOME_SIDEBAR_WIDTH_MIN,
  SIDEBAR_WIDTH_DEFAULT,
  SIDEBAR_WIDTH_MAX,
  SIDEBAR_WIDTH_MIN,
  clampHomeSidebarWidth,
  clampSidebarWidth,
  parseStoredHomeSidebarWidth,
  parseStoredSidebarWidth,
} from '../lib/sidebar-width.ts';

test('sidebar width is bounded for desktop reading', () => {
  assert.equal(clampSidebarWidth(120), SIDEBAR_WIDTH_MIN);
  assert.equal(clampSidebarWidth(900), SIDEBAR_WIDTH_MAX);
  assert.equal(clampSidebarWidth(347.6), 348);
});

test('stored sidebar width falls back safely', () => {
  assert.equal(parseStoredSidebarWidth(null), SIDEBAR_WIDTH_DEFAULT);
  assert.equal(parseStoredSidebarWidth(''), SIDEBAR_WIDTH_DEFAULT);
  assert.equal(parseStoredSidebarWidth('not-a-number'), SIDEBAR_WIDTH_DEFAULT);
  assert.equal(parseStoredSidebarWidth('420'), 420);
});

test('home catalogue sidebar width is independently bounded and restored', () => {
  assert.equal(clampHomeSidebarWidth(120), HOME_SIDEBAR_WIDTH_MIN);
  assert.equal(clampHomeSidebarWidth(900), HOME_SIDEBAR_WIDTH_MAX);
  assert.equal(clampHomeSidebarWidth(319.7), 320);
  assert.equal(parseStoredHomeSidebarWidth(null), HOME_SIDEBAR_WIDTH_DEFAULT);
  assert.equal(parseStoredHomeSidebarWidth('not-a-number'), HOME_SIDEBAR_WIDTH_DEFAULT);
  assert.equal(parseStoredHomeSidebarWidth('352'), 352);
});
