import assert from 'node:assert/strict';
import test from 'node:test';

import {
  categoryOrder,
  EXEDRA_CATEGORY_ORDER,
  MAGIRECO_CATEGORY_ORDER,
} from '../lib/category-order.ts';

test('Magia Record categories preserve the production site navigation order', () => {
  const shuffled = [
    'main_story',
    'event_story',
    'scene0_sub',
    'character_story',
    'Unclassified',
    'mirror_story',
    'costume_story',
    'scene0_main',
    'login_story',
    'general_voice',
  ];
  assert.deepEqual(
    shuffled.sort((left, right) => categoryOrder(left) - categoryOrder(right)),
    [...MAGIRECO_CATEGORY_ORDER],
  );
});

test('Exedra categories retain their numbered source order', () => {
  const shuffled = [...EXEDRA_CATEGORY_ORDER].reverse();
  assert.deepEqual(
    shuffled.sort((left, right) => categoryOrder(left) - categoryOrder(right)),
    [...EXEDRA_CATEGORY_ORDER],
  );
});
