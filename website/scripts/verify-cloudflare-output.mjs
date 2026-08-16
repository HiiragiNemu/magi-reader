import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
} from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';

const searchScopes = ['magireco', 'exedra'];
const searchPayloadNames = [
  'search_content.json',
  ...searchScopes.map((scope) => `search_content.${scope}.json`),
];

const buildCloudflareOutput = () => {
  const backupDirectory = path.resolve('.magi-reader-generation-backups');
  const payloads = searchPayloadNames.map((name) => ({
    local: path.resolve('public', name),
    held: path.join(
      backupDirectory,
      name.replace(/\.json$/u, '.build-hold.json'),
    ),
  }));

  for (const payload of payloads) {
    if (!existsSync(payload.held)) continue;
    if (existsSync(payload.local)) {
      throw new Error(
        `发现未恢复的搜索文件备份，且 public 中也存在 ${path.basename(payload.local)}；为避免覆盖，已停止构建。`,
      );
    }
    renameSync(payload.held, payload.local);
  }

  const payloadsToHold = payloads.filter((payload) => existsSync(payload.local));
  if (payloadsToHold.length > 0) {
    mkdirSync(backupDirectory, { recursive: true });
    for (const payload of payloadsToHold) {
      renameSync(payload.local, payload.held);
    }
  }

  try {
    const cliEntry = path.resolve(
      'node_modules',
      '@opennextjs',
      'cloudflare',
      'dist',
      'cli',
      'index.js',
    );
    if (!existsSync(cliEntry)) {
      throw new Error('缺少 @opennextjs/cloudflare 构建工具，请先安装依赖。');
    }
    const result = spawnSync(
      process.execPath,
      [cliEntry, 'build'],
      { cwd: process.cwd(), env: process.env, stdio: 'inherit' },
    );
    if (result.error) throw result.error;
    if (result.status !== 0) {
      throw new Error(`OpenNext Cloudflare 构建失败（退出码 ${result.status}）`);
    }
  } finally {
    for (const payload of payloadsToHold) {
      if (existsSync(payload.held)) {
        renameSync(payload.held, payload.local);
      }
    }
  }
};

if (process.argv.includes('--build')) {
  try {
    buildCloudflareOutput();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  }
}

const outputRoot = path.resolve('.open-next');
const workerEntry = path.join(outputRoot, 'worker.js');
const assetsRoot = path.join(outputRoot, 'assets');
const searchPayloads = searchPayloadNames.map((name) => path.join(assetsRoot, name));
const searchManifests = searchScopes.map((scope) => ({
  scope,
  built: path.join(assetsRoot, `search_index_manifest.${scope}.json`),
  source: path.resolve('public', `search_index_manifest.${scope}.json`),
}));
const sourceStoryIndex = path.resolve('public', 'story_index.json');
const forbiddenAssetEntries = [
  '.build',
  '_worker.js',
  'app-worker.js',
  'cloudflare',
  'middleware',
  'server-functions',
];

const isValidSearchManifest = (manifest, scope) => {
  const sha256 =
    typeof manifest.sha256 === 'string' ? manifest.sha256.toLowerCase() : '';
  const commonValid =
    (manifest.version === 1 || manifest.version === 2) &&
    /^[a-f0-9]{64}$/u.test(sha256) &&
    manifest.object_key === `search/${scope}/${sha256}.json` &&
    Number.isSafeInteger(manifest.bytes) &&
    manifest.bytes > 0 &&
    manifest.bytes <= 256 * 1024 * 1024 &&
    Number.isSafeInteger(manifest.entries) &&
    manifest.entries > 0 &&
    manifest.entries <= 1_000_000 &&
    /^[a-f0-9]{64}$/u.test(manifest.story_index_sha256 ?? '');
  if (!commonValid || manifest.version === 1) return commonValid;

  if (
    manifest.chunk_bytes !== 1024 * 1024 ||
    !Array.isArray(manifest.chunks) ||
    manifest.chunks.length !== Math.ceil(manifest.bytes / manifest.chunk_bytes)
  ) {
    return false;
  }
  let total = 0;
  for (let index = 0; index < manifest.chunks.length; index += 1) {
    const chunk = manifest.chunks[index];
    const finalChunk = index === manifest.chunks.length - 1;
    if (
      !chunk ||
      typeof chunk !== 'object' ||
      !Number.isSafeInteger(chunk.bytes) ||
      chunk.bytes <= 0 ||
      chunk.bytes > manifest.chunk_bytes ||
      (!finalChunk && chunk.bytes !== manifest.chunk_bytes) ||
      !/^[a-f0-9]{64}$/u.test(chunk.sha256 ?? '')
    ) {
      return false;
    }
    total += chunk.bytes;
  }
  return total === manifest.bytes;
};

const verifyBuiltSearchChunks = (manifest, scope, errors) => {
  const directory = path.join(assetsRoot, 'search-chunks', scope, manifest.sha256);
  // Generic output verification remains backward-compatible with manifest-only
  // fixtures and non-chunk deployments. The main production pipeline calls
  // search_chunk_delivery.py verify-tree immediately after the build, which is
  // the fail-closed authority that requires every physical chunk to exist.
  if (!existsSync(directory)) return;
  const overall = createHash('sha256');
  let total = 0;
  for (let index = 0; index < manifest.chunks.length; index += 1) {
    const expected = manifest.chunks[index];
    const part = path.join(directory, `${String(index).padStart(4, '0')}.part`);
    if (!existsSync(part)) {
      errors.push(`${scope} 搜索分块缺少第 ${index + 1} 块`);
      return;
    }
    const data = readFileSync(part);
    const digest = createHash('sha256').update(data).digest('hex');
    if (data.byteLength !== expected.bytes || digest !== expected.sha256) {
      errors.push(`${scope} 搜索分块第 ${index + 1} 块大小或 SHA-256 不一致`);
      return;
    }
    overall.update(data);
    total += data.byteLength;
  }
  if (total !== manifest.bytes || overall.digest('hex') !== manifest.sha256) {
    errors.push(`${scope} 搜索分块重组后的全局大小或 SHA-256 不一致`);
  }
};

const errors = [];
let storyIndexSha256 = '';

if (!existsSync(sourceStoryIndex)) {
  errors.push('public 缺少 story_index.json');
} else {
  storyIndexSha256 = createHash('sha256')
    .update(readFileSync(sourceStoryIndex))
    .digest('hex');
}

if (!existsSync(workerEntry)) {
  errors.push('缺少 OpenNext Worker 入口 .open-next/worker.js');
}
if (!existsSync(assetsRoot)) {
  errors.push('缺少 OpenNext 静态资源目录 .open-next/assets');
}
for (const searchPayload of searchPayloads) {
  if (existsSync(searchPayload)) {
    errors.push(`搜索大文件不能打包进 Worker 静态资源: ${path.basename(searchPayload)}`);
  }
}
for (const searchManifest of searchManifests) {
  if (!existsSync(searchManifest.built)) {
    errors.push(`静态资源缺少 ${path.basename(searchManifest.built)}`);
    continue;
  }
  try {
    const builtManifestSource = readFileSync(searchManifest.built, 'utf8');
    if (!existsSync(searchManifest.source)) {
      errors.push(`public 缺少 ${path.basename(searchManifest.source)}`);
    } else if (
      builtManifestSource !== readFileSync(searchManifest.source, 'utf8')
    ) {
      errors.push(`构建后的 ${searchManifest.scope} 搜索清单与 public 源文件不一致`);
    }
    const manifest = JSON.parse(builtManifestSource);
    if (!isValidSearchManifest(manifest, searchManifest.scope)) {
      errors.push(`${path.basename(searchManifest.built)} 格式或内容寻址键无效`);
    } else if (
      storyIndexSha256 &&
      manifest.story_index_sha256 !== storyIndexSha256
    ) {
      errors.push(`${searchManifest.scope} 搜索清单与当前 story_index.json 不匹配`);
    } else if (manifest.version === 2) {
      verifyBuiltSearchChunks(manifest, searchManifest.scope, errors);
    }
  } catch {
    errors.push(`${path.basename(searchManifest.built)} 不是有效 JSON`);
  }
}

for (const entry of forbiddenAssetEntries) {
  if (existsSync(path.join(assetsRoot, entry))) {
    errors.push(`静态资源目录包含服务端产物: .open-next/assets/${entry}`);
  }
}

if (errors.length > 0) {
  for (const error of errors) console.error(error);
  process.exitCode = 1;
} else {
  console.log('Cloudflare 输出检查通过：服务端代码与静态资源已分离。');
}

// SEARCH_CHUNK_DELIVERY_BUILD_VERIFY_V1
