import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const reader = readFileSync(
  new URL('../app/reader/[id]/page.tsx', import.meta.url),
  'utf8',
);
const pipeline = readFileSync(
  new URL('../../generate_story_index.py', import.meta.url),
  'utf8',
);

test('Exedra bilingual rendering uses exact event lines', () => {
  assert.ok(reader.includes('const nextCnLines = isExedraStory'));
  assert.ok(reader.includes('? nextCnEventLines'));
  assert.ok(reader.includes('const nextJpLines = isExedraStory'));
  assert.ok(reader.includes('? nextJpEventLines'));
  assert.ok(reader.includes('sourceReady,\n    isExedraStory,\n  ]);'));
});

test('pipeline separates event structure from localized speaker proof', () => {
  assert.ok(
    pipeline.includes(
      'Exedra bilingual alignment is exact JSON text-event order',
    ),
  );
  assert.ok(
    pipeline.includes(
      'Exedra 中日 JSON 的 ActionType/工作表/行位置顺序不一致',
    ),
  );
  assert.ok(
    pipeline.includes('Exedra 中文 JSON 的 Name 未规范中文化'),
  );
  assert.doesNotMatch(pipeline, /include_speaker = not authentic_tw/u);
});
