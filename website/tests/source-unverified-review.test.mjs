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
  assert.equal(
    manifest.manual_human_verified_total,
    manifest.manual_human_verified_ids.length,
  );
  assert.equal(
    manifest.review_remaining,
    manifest.total - manifest.manual_human_verified_total,
  );
  assert.ok(manifest.entries.length > 0);
  for (const entry of manifest.entries) {
    assert.equal(entry.classification, 'SOURCE_UNVERIFIED');
    assert.equal(entry.provenance, 'source_unverified_added_after_trusted_main');
    assert.equal(entry.review_reason, 'cn_txt_absent_from_trusted_main');
    assert.equal(entry.added_source_json_count, entry.machine_source_json_count);
    assert.equal(
      entry.manual_human_verified,
      manifest.manual_human_verified_ids.includes(entry.story_id),
    );
  }
});

test('public summary keeps a canonical source-unverified field and legacy alias', () => {
  const source = readFileSync('lib/machine-translation-review.ts', 'utf8');
  assert.match(source, /source_unverified_ids:\s*sourceUnverifiedIds/u);
  assert.match(source, /machine_translation_ids:\s*sourceUnverifiedIds/u);
  assert.match(source, /MANUAL_HUMAN_VERIFIED_ID_SET\.has\(entry\.story_id\)/u);
});

test('collapsed review checklist lives beside the brand and takes no catalog space', () => {
  const page = readFileSync('app/page.tsx', 'utf8');
  assert.match(page, /<MadeInMagiusLogo \/>[\s\S]*?校验清单/u);
  assert.match(
    page,
    /hidden=\{machineReviewPanelCollapsed\}/u,
  );
  assert.match(
    page,
    /onClick=\{\(\) => setMachineReviewPanelCollapsedPreference\(!machineReviewPanelCollapsed\)\}/u,
  );
  assert.doesNotMatch(page, /展开来源待核验人工校验清单/u);
  assert.match(page, /transition md:hidden focus-visible/u);
});
