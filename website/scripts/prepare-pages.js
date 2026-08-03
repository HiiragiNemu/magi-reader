#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';

const projectRoot = fs.realpathSync(process.cwd());
const openNextRoot = path.join(projectRoot, '.open-next');
const assetRoot = path.join(openNextRoot, 'assets');
const workerEntry = path.join(openNextRoot, 'worker.js');
const outputRoot = path.join(projectRoot, '.pages-deploy');

function assertInsideProject(candidate) {
  const relative = path.relative(projectRoot, candidate);
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) {
    throw new Error(`Refusing unsafe Pages output path: ${candidate}`);
  }
}

assertInsideProject(outputRoot);
if (!fs.statSync(assetRoot, { throwIfNoEntry: false })?.isDirectory()) {
  throw new Error('Missing .open-next/assets; run the OpenNext build first.');
}
if (!fs.statSync(workerEntry, { throwIfNoEntry: false })?.isFile()) {
  throw new Error('Missing .open-next/worker.js; run the OpenNext build first.');
}

const forbiddenAssetEntries = [
  '_worker.js',
  'app-worker.js',
  '.build',
  'cloudflare',
  'middleware',
  'server-functions',
];
for (const entry of forbiddenAssetEntries) {
  if (fs.existsSync(path.join(assetRoot, entry))) {
    throw new Error(
      `Unsafe server implementation found in public assets: ${entry}`,
    );
  }
}

fs.rmSync(outputRoot, { recursive: true, force: true });
fs.mkdirSync(outputRoot, { recursive: true });
fs.cpSync(assetRoot, outputRoot, { recursive: true, force: true });

// OpenNext already owns static asset resolution through the ASSETS binding.
// Delegating every request to the generated worker preserves Next.js RSC/Flight
// headers and dynamic route handling. A Pages-level ASSETS-first shortcut can
// return ordinary HTML for client-navigation requests and make the router flash
// before falling back to the current page.
const wrapper = String.raw`import appWorker from "../.open-next/worker.js";

export default {
  fetch(request, env, ctx) {
    return appWorker.fetch(request, env, ctx);
  },
};
`;
fs.writeFileSync(path.join(outputRoot, '_worker.js'), wrapper, 'utf8');

let fileCount = 0;
let totalBytes = 0;
const pending = [outputRoot];
while (pending.length > 0) {
  const directory = pending.pop();
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      pending.push(absolute);
    } else if (entry.isFile()) {
      fileCount += 1;
      totalBytes += fs.statSync(absolute).size;
    } else {
      throw new Error(`Unsupported Pages output entry: ${absolute}`);
    }
  }
}

console.log(
  JSON.stringify({
    output: outputRoot,
    publicFiles: fileCount - 1,
    publicBytes: totalBytes - Buffer.byteLength(wrapper),
    workerWrapper: '_worker.js',
  }),
);
