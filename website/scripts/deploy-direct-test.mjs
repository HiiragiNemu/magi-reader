import { spawnSync } from 'node:child_process';
import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import {
  parseNamespaceList,
  rewriteTestConfig,
} from './cloudflare-direct-deploy-utils.mjs';

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
const skipChecks = hasFlag('--skip-checks');
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
const openNextRedirect = path.resolve(
  projectRoot,
  '.wrangler',
  'deploy',
  'config.json',
);
const heldOpenNextRedirect = path.join(
  generatedDirectory,
  'opennext-deploy-config.hold.json',
);

for (const required of [sourceConfig, verifyConfig, wranglerEntry]) {
  if (!existsSync(required)) {
    throw new Error(`缺少直接部署所需文件：${required}`);
  }
}

const run = (command, args, options = {}) => {
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? projectRoot,
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

const resolveNamespaceId = () => {
  if (explicitNamespaceId) return explicitNamespaceId.toLowerCase();
  const output = run(
    process.execPath,
    [wranglerEntry, 'kv', 'namespace', 'list', '--config', sourceConfig],
    { capture: true },
  );
  return parseNamespaceList(output, namespaceTitle);
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
  const source = readFileSync(resolvedConfig, 'utf8');
  const rewritten = rewriteTestConfig({
    source,
    workerName,
    namespaceId,
  });
  writeFileSync(testConfig, rewritten, { encoding: 'utf8', mode: 0o600 });
  return testConfig;
};

const holdOpenNextConfigRedirect = () => {
  if (existsSync(heldOpenNextRedirect)) {
    if (existsSync(openNextRedirect)) {
      throw new Error(
        '同时发现 OpenNext 部署配置和旧的暂存配置，拒绝覆盖。',
      );
    }
    mkdirSync(path.dirname(openNextRedirect), { recursive: true });
    renameSync(heldOpenNextRedirect, openNextRedirect);
  }
  if (existsSync(openNextRedirect)) {
    mkdirSync(generatedDirectory, { recursive: true });
    renameSync(openNextRedirect, heldOpenNextRedirect);
    return true;
  }
  return false;
};

const restoreOpenNextConfigRedirect = (held) => {
  if (!held || !existsSync(heldOpenNextRedirect)) return;
  mkdirSync(path.dirname(openNextRedirect), { recursive: true });
  if (existsSync(openNextRedirect)) {
    throw new Error('部署后出现新的 OpenNext 配置，无法安全恢复原配置。');
  }
  renameSync(heldOpenNextRedirect, openNextRedirect);
};

const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';
let preparedConfig = '';
let redirectHeld = false;
try {
  const namespaceId = resolveNamespaceId();
  console.log(`测试 Worker：${workerName}`);
  console.log(`测试 KV：${namespaceTitle} (${namespaceId})`);
  preparedConfig = prepareConfig(namespaceId);

  if (!skipChecks) {
    run(npmCommand, ['run', 'lint']);
    run(npmCommand, ['run', 'type-check']);
    run(npmCommand, ['test']);
  }

  if (!skipBuild) {
    run(npmCommand, ['run', 'build:worker']);
  } else if (!existsSync(path.resolve(projectRoot, '.open-next', 'worker.js'))) {
    throw new Error('--skip-build 需要已有 .open-next/worker.js');
  }

  redirectHeld = holdOpenNextConfigRedirect();
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
  restoreOpenNextConfigRedirect(redirectHeld);
  if (!keepConfig) {
    rmSync(resolvedConfig, { force: true });
    rmSync(testConfig, { force: true });
  } else if (preparedConfig) {
    console.log(`保留临时配置：${preparedConfig}`);
  }
}
