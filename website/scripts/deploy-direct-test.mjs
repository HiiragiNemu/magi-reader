import { spawnSync } from 'node:child_process';
import {
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const DEFAULT_WORKER_NAME = 'magireader-exedra-cn-test';
const DEFAULT_KV_TITLE = 'magi-submissions-exedra-cn-test';
const ID_RE = /^[a-f0-9]{32}$/iu;

const flagValue = (name) => {
  const index = process.argv.indexOf(name);
  if (index < 0) return null;
  const value = process.argv[index + 1];
  if (!value || value.startsWith('--')) {
    throw new Error(`${name} 缺少参数`);
  }
  return value;
};

const hasFlag = (name) => process.argv.includes(name);
const stripAnsi = (value) => value.replace(/\u001b\[[0-9;]*m/gu, '');

const workerName = (
  flagValue('--worker-name') ??
  process.env.MAGIREADER_TEST_WORKER_NAME ??
  DEFAULT_WORKER_NAME
).trim();
const namespaceTitle = (
  flagValue('--kv-title') ??
  process.env.MAGIREADER_TEST_KV_TITLE ??
  DEFAULT_KV_TITLE
).trim();
const explicitNamespaceId = (
  flagValue('--kv-id') ??
  process.env.SUBMISSIONS_KV_NAMESPACE_ID ??
  ''
).trim();
const message = (
  flagValue('--message') ??
  `Direct test deployment ${new Date().toISOString()}`
).trim();
const dryRun = hasFlag('--dry-run');
const skipBuild = hasFlag('--skip-build');
const keepConfig = hasFlag('--keep-config');

if (!/^[a-z0-9][a-z0-9-]{0,62}$/u.test(workerName)) {
  throw new Error(`测试 Worker 名称无效：${workerName}`);
}
if (!namespaceTitle || namespaceTitle.length > 256) {
  throw new Error('KV namespace 名称为空或过长');
}
if (explicitNamespaceId && !ID_RE.test(explicitNamespaceId)) {
  throw new Error('SUBMISSIONS_KV_NAMESPACE_ID 必须是 32 位十六进制字符串');
}

const projectRoot = process.cwd();
const sourceConfig = path.resolve(projectRoot, 'wrangler.jsonc');
const verifyConfig = path.resolve(
  projectRoot,
  'scripts',
  'verify-cloudflare-config.mjs',
);
const wranglerEntry = path.resolve(
  projectRoot,
  'node_modules',
  'wrangler',
  'bin',
  'wrangler.js',
);
const generatedDirectory = path.resolve(
  projectRoot,
  '.wrangler',
  'direct-test',
);
const resolvedConfig = path.join(generatedDirectory, 'wrangler.resolved.jsonc');
const testConfig = path.join(generatedDirectory, 'wrangler.test.jsonc');

for (const required of [sourceConfig, verifyConfig, wranglerEntry]) {
  if (!existsSync(required)) {
    throw new Error(`缺少直接部署所需文件：${required}`);
  }
}

const run = (command, args, options = {}) => {
  const result = spawnSync(command, args, {
    cwd: projectRoot,
    env: { ...process.env, ...(options.env ?? {}) },
    encoding: options.capture ? 'utf8' : undefined,
    stdio: options.capture ? ['ignore', 'pipe', 'pipe'] : 'inherit',
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const details = options.capture
      ? `\n${String(result.stdout ?? '')}\n${String(result.stderr ?? '')}`
      : '';
    throw new Error(
      `${command} ${args.join(' ')} 失败（退出码 ${result.status}）${details}`,
    );
  }
  return options.capture
    ? `${String(result.stdout ?? '')}\n${String(result.stderr ?? '')}`
    : '';
};

const collectNamespaceObjects = (value, result = []) => {
  if (Array.isArray(value)) {
    for (const item of value) collectNamespaceObjects(item, result);
  } else if (value && typeof value === 'object') {
    const record = value;
    const id = typeof record.id === 'string' ? record.id.trim() : '';
    const title = typeof record.title === 'string'
      ? record.title.trim()
      : typeof record.name === 'string'
        ? record.name.trim()
        : '';
    if (ID_RE.test(id) && title) result.push({ id, title });
    for (const nested of Object.values(record)) {
      if (nested && typeof nested === 'object') {
        collectNamespaceObjects(nested, result);
      }
    }
  }
  return result;
};

const parseNamespaceList = (raw, exactTitle) => {
  const output = stripAnsi(raw).trim();
  const matches = [];

  const jsonCandidates = [output];
  const firstArray = output.indexOf('[');
  const lastArray = output.lastIndexOf(']');
  if (firstArray >= 0 && lastArray > firstArray) {
    jsonCandidates.push(output.slice(firstArray, lastArray + 1));
  }
  const firstObject = output.indexOf('{');
  const lastObject = output.lastIndexOf('}');
  if (firstObject >= 0 && lastObject > firstObject) {
    jsonCandidates.push(output.slice(firstObject, lastObject + 1));
  }

  for (const candidate of jsonCandidates) {
    try {
      for (const item of collectNamespaceObjects(JSON.parse(candidate))) {
        if (item.title === exactTitle) matches.push(item.id.toLowerCase());
      }
    } catch {
      // Wrangler versions differ; fall through to table/text parsing.
    }
  }

  for (const line of output.split(/\r?\n/gu)) {
    if (!line.includes(exactTitle)) continue;
    for (const match of line.matchAll(/[a-f0-9]{32}/giu)) {
      matches.push(match[0].toLowerCase());
    }
  }

  const unique = [...new Set(matches)];
  if (unique.length === 0) {
    throw new Error(
      `Wrangler 返回中没有找到名称完全等于 ${JSON.stringify(exactTitle)} 的 KV namespace。`,
    );
  }
  if (unique.length !== 1) {
    throw new Error(
      `KV namespace 名称 ${JSON.stringify(exactTitle)} 对应多个 ID：${unique.join(', ')}`,
    );
  }
  return unique[0];
};

const resolveNamespaceId = () => {
  if (explicitNamespaceId) return explicitNamespaceId.toLowerCase();
  const output = run(
    process.execPath,
    [wranglerEntry, 'kv', 'namespace', 'list', '--config', sourceConfig],
    { capture: true },
  );
  return parseNamespaceList(output, namespaceTitle);
};

const replaceExactlyOnce = (source, expression, replacement, label) => {
  const matches = source.match(new RegExp(expression.source, `${expression.flags.includes('g') ? expression.flags : `${expression.flags}g`}`));
  if (!matches || matches.length !== 1) {
    throw new Error(`${label} 预期匹配 1 次，实际 ${matches?.length ?? 0} 次`);
  }
  return source.replace(expression, replacement);
};

const prepareConfig = (namespaceId) => {
  mkdirSync(generatedDirectory, { recursive: true });
  run(
    process.execPath,
    [
      verifyConfig,
      '--config',
      sourceConfig,
      '--output',
      resolvedConfig,
    ],
    { env: { SUBMISSIONS_KV_NAMESPACE_ID: namespaceId } },
  );

  let source = readFileSync(resolvedConfig, 'utf8');
  source = replaceExactlyOnce(
    source,
    /"name"\s*:\s*"[^"]+"/u,
    `"name": ${JSON.stringify(workerName)}`,
    'Worker name',
  );
  source = replaceExactlyOnce(
    source,
    /"service"\s*:\s*"[^"]+"/u,
    `"service": ${JSON.stringify(workerName)}`,
    'WORKER_SELF_REFERENCE service',
  );
  if (source.includes('00000000000000000000000000000000')) {
    throw new Error('生成配置仍包含全零 KV ID');
  }
  if (!source.includes(namespaceId)) {
    throw new Error('生成配置没有包含解析出的测试 KV ID');
  }
  writeFileSync(testConfig, source, { encoding: 'utf8', mode: 0o600 });
  return testConfig;
};

const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';
let namespaceId = '';
let preparedConfig = '';
try {
  namespaceId = resolveNamespaceId();
  console.log(`测试 Worker：${workerName}`);
  console.log(`测试 KV：${namespaceTitle} (${namespaceId})`);
  preparedConfig = prepareConfig(namespaceId);

  if (!skipBuild) {
    run(npmCommand, ['run', 'build:worker']);
  } else if (!existsSync(path.resolve(projectRoot, '.open-next', 'worker.js'))) {
    throw new Error('--skip-build 需要已有 .open-next/worker.js');
  }

  const deployArgs = [
    wranglerEntry,
    'deploy',
    '--config',
    preparedConfig,
    '--strict',
    '--message',
    message,
  ];
  if (dryRun) deployArgs.push('--dry-run');
  run(process.execPath, deployArgs);
  console.log(
    dryRun
      ? '直接测试部署 dry-run 已通过。'
      : `测试 Worker 已部署：https://${workerName}.workers.dev`,
  );
} finally {
  if (!keepConfig) {
    rmSync(resolvedConfig, { force: true });
    rmSync(testConfig, { force: true });
  } else if (preparedConfig) {
    console.log(`保留临时配置：${preparedConfig}`);
  }
}
