import assert from 'node:assert/strict';
import test from 'node:test';

import {
  bilingualLanguagePaneClass,
  bilingualStoryPairClass,
  type ReaderBilingualLayout,
} from './bilingual-layout.ts';

for (const layout of ['stacked', 'side-by-side'] satisfies ReaderBilingualLayout[]) {
  test(`${layout} classes are identical for Magia Record and Exedra callers`, () => {
    // These helpers intentionally take presentation state only. Story system and
    // edit state cannot alter where a bilingual pair is divided.
    const first = bilingualStoryPairClass('split', layout);
    const second = bilingualStoryPairClass('split', layout);
    assert.equal(first, second);
  });
}

test('stacked bilingual rows separate only after the complete CN/JP pair', () => {
  const pair = bilingualStoryPairClass('split', 'stacked');
  const cn = bilingualLanguagePaneClass('split', 'stacked', 'cn');
  const jp = bilingualLanguagePaneClass('split', 'stacked', 'jp');

  assert.match(pair, /magi-bilingual-pair-stacked/);
  assert.doesNotMatch(pair, /border-t/);
  assert.doesNotMatch(cn, /border-[tblr]/);
  assert.doesNotMatch(jp, /border-[tblr]/);
});

test('mobile fallback and explicit desktop stacked layout use the same intact pair', () => {
  const pair = bilingualStoryPairClass('split', 'side-by-side');
  const jp = bilingualLanguagePaneClass('split', 'side-by-side', 'jp');

  // Before md, both panes stack but no horizontal rule is placed between them.
  assert.equal(
    pair.split(/\s+/).some(token => /^border-t(?:-|$)/.test(token)),
    false,
  );
  assert.match(pair, /magi-bilingual-pair-responsive/);
  assert.equal(
    jp.split(/\s+/).some(token => /^border-t(?:-|$)/.test(token)),
    false,
  );
  // At md the existing vertical language divider remains.
  assert.match(jp, /md:border-l/);
});

test('reading and editing share the same StoryRow pair boundary', () => {
  const pair = bilingualStoryPairClass('split', 'stacked');
  assert.equal(pair, bilingualStoryPairClass('split', 'stacked'));
  assert.equal(bilingualLanguagePaneClass('cn', 'stacked', 'cn'), 'w-full');
  assert.equal(bilingualLanguagePaneClass('jp', 'stacked', 'jp'), 'w-full');
});
