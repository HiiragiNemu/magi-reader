import assert from 'node:assert/strict';
import test from 'node:test';

import {
  resolveOfficialChapterTitle,
  resolveOfficialSectionTitle,
} from '../lib/official-tw-titles.ts';

test('one official chapter title replaces the raw folder label', () => {
  assert.equal(
    resolveOfficialChapterTitle(
      [
        { official_tw_chapter_title: ' 第一章 · 针之魔女 ' },
        { official_tw_chapter_title: '第一章 · 针之魔女' },
      ],
      'sub_hari',
    ),
    '第一章 · 针之魔女',
  );
});

test('conflicting or missing chapter titles preserve the fallback', () => {
  assert.equal(
    resolveOfficialChapterTitle(
      [
        { official_tw_chapter_title: '第一章' },
        { official_tw_chapter_title: '第二章' },
      ],
      'raw',
    ),
    'raw',
  );
  assert.equal(resolveOfficialChapterTitle([{}], 'raw'), 'raw');
});

test('official section title follows the one-based Section number', () => {
  const titles = ['首次解放', '第二小节'];
  assert.equal(resolveOfficialSectionTitle(titles, '1', 'Section 1'), '首次解放');
  assert.equal(resolveOfficialSectionTitle(titles, 2, 'Section 2'), '第二小节');
  assert.equal(resolveOfficialSectionTitle(titles, 3, 'Section 3'), 'Section 3');
  assert.equal(resolveOfficialSectionTitle(titles, undefined, 'Branch'), 'Branch');
});
