import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const manifest = JSON.parse(
  readFileSync('public/data/machine_translation_manifest.generated.json', 'utf8'),
);

test('source-review manifest uses fail-closed classification', () => {
  assert.equal(manifest.version, 4);
  assert.equal(manifest.classification, 'SOURCE_UNVERIFIED');
  assert.match(manifest.definition, /source_unverified/u);
  assert.equal(manifest.total, manifest.entries.length);
  assert.ok(manifest.entries.length > 0);
  for (const entry of manifest.entries) {
    assert.equal(entry.classification, 'SOURCE_UNVERIFIED');
    assert.equal(entry.provenance, 'source_unverified_added_after_trusted_main');
    assert.equal(entry.review_reason, 'cn_txt_absent_from_trusted_main');
    assert.equal(entry.added_source_json_count, entry.machine_source_json_count);
  }
});

test('public summary keeps a canonical source-unverified field and legacy alias', () => {
  const source = readFileSync('lib/machine-translation-review.ts', 'utf8');
  assert.match(source, /source_unverified_ids:\s*sourceUnverifiedIds/u);
  assert.match(source, /machine_translation_ids:\s*sourceUnverifiedIds/u);
});
