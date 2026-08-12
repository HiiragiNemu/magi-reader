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

// Pages must serve generated catalogue/public files directly, but Next.js
// dynamic routes and RSC/Flight navigation must reach OpenNext.  A blanket
// ASSETS-first policy can return the current HTML document for a client-side
// /reader/... navigation, which appears in Chromium as a flash and reload back
// to the catalogue.  Conversely, routing every public data file through
// OpenNext can leave initial catalogue loading waiting indefinitely.
const wrapper = String.raw`import appWorker from "../.open-next/worker.js";

const isRscRequest = (request, url) => {
  const accept = request.headers.get("accept") || "";
  return (
    url.searchParams.has("_rsc") ||
    request.headers.get("rsc") === "1" ||
    request.headers.has("next-router-state-tree") ||
    request.headers.has("next-router-prefetch") ||
    accept.includes("text/x-component")
  );
};

const shouldTryStaticAsset = (request, url) => {
  if (request.method !== "GET" && request.method !== "HEAD") return false;
  if (isRscRequest(request, url)) return false;

  const pathname = url.pathname;
  if (
    pathname.startsWith("/api/") ||
    pathname.startsWith("/reader/") ||
    pathname.startsWith("/review/")
  ) {
    return false;
  }

  return (
    pathname === "/" ||
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/data/") ||
    pathname.startsWith("/audio/") ||
    pathname.startsWith("/fonts/") ||
    /\/[^/]+\.[A-Za-z0-9]{1,16}$/.test(pathname)
  );
};

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (shouldTryStaticAsset(request, url)) {
      const assetResponse = await env.ASSETS.fetch(request);
      if (assetResponse.status !== 404) {
        return assetResponse;
      }
      await assetResponse.body?.cancel();
    }
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
