import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const reader = readFileSync(
  new URL('../app/reader/[id]/page.tsx', import.meta.url),
  'utf8',
);
const layout = readFileSync(new URL('../app/layout.tsx', import.meta.url), 'utf8');
const dictionary = readFileSync(
  new URL('../app/config/dictionary.ts', import.meta.url),
  'utf8',
);
const floating = readFileSync(
  new URL('../components/FloatingWindow.tsx', import.meta.url),
  'utf8',
);
const refinements = readFileSync(
  new URL('../app/ui-refinements.css', import.meta.url),
  'utf8',
);

test('Chinese display and editing always pass speaker names through the dictionary', () => {
  assert.match(
    reader,
    /speaker:\s*translatedSpeaker\(\s*cn\?\.speaker \|\| \(jp \?\? basis\)\.speaker \|\| '旁白',\s*\)/u,
  );
  assert.match(
    reader,
    /translatedSpeaker\(\s*row\.cn\?\.speaker \|\| row\.jp\?\.speaker \|\| '旁白',\s*\)/u,
  );
  assert.match(reader, /const displayedSpeaker =\s*language === 'cn'/u);
  assert.match(reader, /translateSpeakerName\(line\.speaker\)/u);
  assert.doesNotMatch(layout, /ExedraSpeakerNameLocalizer/u);
  assert.match(dictionary, /replace\(\/\[・･‧•．\]\/gu, '·'\)/u);
});

test('tool windows use compact scrollable geometry and readable paper surfaces', () => {
  assert.match(floating, /data-window-state=\{isCompact \? 'compact' : 'open'\}/u);
  assert.doesNotMatch(floating, /hidden=\{isCompact\}/u);
  assert.match(refinements, /magi-retro-window-controls[\s\S]*flex-flow: row nowrap/u);
  assert.match(refinements, /data-window-state='compact'[\s\S]*height:/u);
  assert.match(refinements, /magi-floating-window-paper[\s\S]*border-radius/u);
  assert.match(refinements, /background-color: rgba\(242, 233, 209, 0\.985\)/u);
  assert.match(refinements, /magi-home-light-status-unverified::after[\s\S]*display: none/u);
});
