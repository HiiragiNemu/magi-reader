import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
  MACHINE_REVIEW_PANEL_STORAGE_KEY,
  isMachineReviewPanelCollapsedValue,
  readMachineReviewPanelCollapsed,
  writeMachineReviewPanelCollapsed,
} from './machine-review-panel.ts';

test('machine-review panel stores and restores both display choices', () => {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };

  assert.equal(readMachineReviewPanelCollapsed(() => storage), false);
  assert.equal(writeMachineReviewPanelCollapsed(() => storage, true), true);
  assert.equal(
    values.get(MACHINE_REVIEW_PANEL_STORAGE_KEY),
    'collapsed',
  );
  assert.equal(readMachineReviewPanelCollapsed(() => storage), true);
  assert.equal(writeMachineReviewPanelCollapsed(() => storage, false), true);
  assert.equal(
    values.get(MACHINE_REVIEW_PANEL_STORAGE_KEY),
    'expanded',
  );
  assert.equal(readMachineReviewPanelCollapsed(() => storage), false);
});

test('machine-review panel falls back to expanded when storage is blocked', () => {
  const blocked = () => {
    throw new Error('storage blocked');
  };

  assert.equal(readMachineReviewPanelCollapsed(blocked), false);
  assert.equal(writeMachineReviewPanelCollapsed(blocked, true), false);
  assert.equal(isMachineReviewPanelCollapsedValue(null), false);
  assert.equal(isMachineReviewPanelCollapsedValue('unexpected'), false);
});

test('home keeps a keyboard-accessible compact reopen entry without replacing existing controls', () => {
  const source = readFileSync('app/page.tsx', 'utf8');

  assert.match(source, /hidden=\{machineReviewPanelCollapsed\}/u);
  assert.match(source, /aria-controls=\{machineReviewPanelContentId\}/u);
  assert.match(source, /aria-expanded=\{!machineReviewPanelCollapsed\}/u);
  assert.match(source, /展开来源待核验人工校验清单/u);
  assert.match(source, /收起来源待核验人工校验清单/u);
  assert.match(source, /只看来源待核验剧情/u);
  assert.match(source, /href="\/review\/machine-translations"/u);
  assert.match(source, /href="\/review\/submissions"/u);
});
