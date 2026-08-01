import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { open, readFile, readdir, stat } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const AUDIO_DIR = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "public",
  "audio",
  "exedra-local",
);
const MANIFEST_PATH = join(AUDIO_DIR, "manifest.json");
const SAFE_ID = /^cv_[a-z0-9_]+$/;

async function sha256File(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path, { highWaterMark: 64 * 1024 })) {
    hash.update(chunk);
  }
  return hash.digest("hex");
}

test("audited Exedra fallback audio exactly matches its bounded manifest", async () => {
  const manifest = JSON.parse(await readFile(MANIFEST_PATH, "utf8"));

  assert.equal(manifest.schemaVersion, 1);
  assert.equal(manifest.policy, "audited_special_reaction_ogg_fallback");
  assert.equal(manifest.totalFiles, 19);
  assert.equal(manifest.totalBytes, 286_305);
  assert.equal(manifest.files.length, manifest.totalFiles);

  const sourceIds = new Set();
  const soundNames = new Set();
  let totalBytes = 0;

  for (const entry of manifest.files) {
    assert.match(entry.sourceId, SAFE_ID);
    assert.match(entry.soundName, SAFE_ID);
    assert.equal(sourceIds.has(entry.sourceId), false);
    assert.equal(soundNames.has(entry.soundName), false);
    sourceIds.add(entry.sourceId);
    soundNames.add(entry.soundName);

    const path = join(AUDIO_DIR, `${entry.soundName}.ogg`);
    const fileStat = await stat(path);
    assert.equal(fileStat.isFile(), true);
    assert.equal(fileStat.size, entry.bytes);
    assert.equal(await sha256File(path), entry.sha256);
    totalBytes += fileStat.size;

    const handle = await open(path, "r");
    try {
      const magic = Buffer.alloc(4);
      const { bytesRead } = await handle.read(magic, 0, magic.length, 0);
      assert.equal(bytesRead, magic.length);
      assert.equal(magic.toString("ascii"), "OggS");
    } finally {
      await handle.close();
    }
  }

  assert.equal(totalBytes, manifest.totalBytes);
  const publishedFiles = (await readdir(AUDIO_DIR))
    .filter((name) => name.endsWith(".ogg"))
    .sort();
  const expectedFiles = [...soundNames]
    .map((name) => `${name}.ogg`)
    .sort();
  assert.deepEqual(publishedFiles, expectedFiles);
});
