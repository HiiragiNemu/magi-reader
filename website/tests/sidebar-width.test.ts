import assert from 'node:assert/strict';
import test from 'node:test';

import {
  SIDEBAR_WIDTH_DEFAULT,
  SIDEBAR_WIDTH_MAX,
  SIDEBAR_WIDTH_MIN,
  clampSidebarWidth,
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
