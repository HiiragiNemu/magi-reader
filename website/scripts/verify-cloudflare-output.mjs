import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
} from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';

const buildCloudflareOutput = () => {
  const localPayload = path.resolve('public', 'search_content.json');
  const backupDirectory = path.resolve('.magi-reader-generation-backups');
  const heldPayload = path.join(
    backupDirectory,
    'search_content.build-hold.json',
  );

  if (existsSync(heldPayload)) {
    if (existsSync(localPayload)) {
      throw new Error(
        '发现未恢复的搜索文件备份，且 public 中也存在同名文件；为避免覆盖，已停止构建。',
      );
    }
    renameSync(heldPayload, localPayload);
  }

  const shouldHoldPayload = existsSync(localPayload);
  if (shouldHoldPayload) {
    mkdirSync(backupDirectory, { recursive: true });
    renameSync(localPayload, heldPayload);
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
    if (shouldHoldPayload && existsSync(heldPayload)) {
      renameSync(heldPayload, localPayload);
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
const searchPayload = path.join(assetsRoot, 'search_content.json');
const searchManifest = path.join(assetsRoot, 'search_index_manifest.json');
const sourceSearchManifest = path.resolve(
  'public',
  'search_index_manifest.json',
);
const forbiddenAssetEntries = [
  '.build',
  '_worker.js',
  'app-worker.js',
  'cloudflare',
  'middleware',
  'server-functions',
];

const isValidSearchManifest = (manifest) => {
  const sha256 =
    typeof manifest.sha256 === 'string' ? manifest.sha256.toLowerCase() : '';
  const commonValid =
    (manifest.version === 1 || manifest.version === 2) &&
    /^[a-f0-9]{64}$/u.test(sha256) &&
    manifest.object_key === `search/${sha256}.json` &&
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

const errors = [];

if (!existsSync(workerEntry)) {
  errors.push('缺少 OpenNext Worker 入口 .open-next/worker.js');
}
if (!existsSync(assetsRoot)) {
  errors.push('缺少 OpenNext 静态资源目录 .open-next/assets');
}
if (existsSync(searchPayload)) {
  errors.push('搜索大文件不能打包进 Worker 静态资源');
}
if (!existsSync(searchManifest)) {
  errors.push('静态资源缺少 search_index_manifest.json');
} else {
  try {
    const builtManifestSource = readFileSync(searchManifest, 'utf8');
    if (!existsSync(sourceSearchManifest)) {
      errors.push('public 缺少 search_index_manifest.json');
    } else if (
      builtManifestSource !== readFileSync(sourceSearchManifest, 'utf8')
    ) {
      errors.push('构建后的搜索清单与 public 源文件不一致');
    }
    const manifest = JSON.parse(builtManifestSource);
    if (!isValidSearchManifest(manifest)) {
      errors.push('search_index_manifest.json 格式或内容寻址键无效');
    }
  } catch {
    errors.push('search_index_manifest.json 不是有效 JSON');
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
