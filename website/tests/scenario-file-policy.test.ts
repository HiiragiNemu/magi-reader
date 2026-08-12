import assert from "node:assert/strict";
import test from "node:test";

import {
  isScenarioDataFile,
  isScenarioMetadataFile,
} from "../lib/scenario-file-policy.ts";

test("scenario validation excludes reports and provenance sidecars", () => {
  assert.equal(isScenarioDataFile("character_iroha_1.json"), true);
  assert.equal(isScenarioDataFile("character_iroha_cn.txt"), true);
  assert.equal(isScenarioDataFile("character_iroha_cn.import-report.json"), false);
  assert.equal(isScenarioDataFile("character_iroha_cn.provenance.json"), false);
  assert.equal(isScenarioDataFile("exedra_manifest.json"), false);
  assert.equal(isScenarioMetadataFile("character_iroha_cn.provenance.json"), true);
  assert.equal(isScenarioMetadataFile("character_iroha_1.json"), false);
});
