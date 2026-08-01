import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { createKnownStoryIds } from '../lib/story-id-membership.ts';

test('generated submission membership matches the exact story index IDs', () => {
  const storyIndex = JSON.parse(
    readFileSync(
      new URL('../public/story_index.json', import.meta.url),
      'utf8',
    ),
  ) as Array<{ id: string; legacy_ids?: string[] }>;
  const generatedIds = JSON.parse(
    readFileSync(
      new URL(
        '../public/data/story_ids.generated.json',
        import.meta.url,
      ),
      'utf8',
    ),
  ) as unknown;
  const known = createKnownStoryIds(generatedIds);

  assert.deepEqual([...known], storyIndex.map(story => story.id));
  for (const story of storyIndex) {
    for (const legacyId of story.legacy_ids ?? []) {
      assert.equal(known.has(legacyId), false);
    }
  }
  const realExedraId = 'exedra_character_character_rena_939abf8f5b';
  assert.equal(known.has(realExedraId), true);
  assert.equal(known.has(realExedraId.toUpperCase()), false);
  assert.equal(
    known.has('exedra_character_character_rena_0000000000'),
    false,
  );
});

test('submission membership rejects malformed or ambiguous ID manifests', () => {
  assert.throws(() => createKnownStoryIds([]), /格式|条目/);
  assert.throws(
    () => createKnownStoryIds(['valid-id', 'VALID-ID']),
    /重复/,
  );
  assert.throws(
    () => createKnownStoryIds(['../not-safe']),
    /无效/,
  );
});
