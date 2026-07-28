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
  resolveNpmInvocation,
  rewriteTestConfig,
} from './cloudflare-direct-deploy-utils.mjs';

const DEFAULT_WORKER_NAME = 'magireader-exedra-cn-test';
const DEFAULT_KV_TITLE = 'magi-submissions-exedra-cn-test';
const DEFAULT_HOSTNAME =
  'magireader-exedra-cn-test.crynetsystemscell.workers.dev';
const DEFAULT_REPOSITORY = 'HiiragiNemu/magi-reader';
const TURNSTILE_TEST_SITE_KEY = '1x00000000000000000000AA';
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
const hostname = (
  flagValue('--hostname') ??
  process.env.MAGIREADER_TEST_HOSTNAME ??
  DEFAULT_HOSTNAME
).trim();
const targetBranch = (
  flagValue('--target-branch') ??
  process.env.PROOFREADING_TARGET_BRANCH ??
  'EXEDRA-TEST'
).trim();
const githubRepo = (
  flagValue('--github-repo') ??
  process.env.PROOFREADING_GITHUB_REPO ??
  DEFAULT_REPOSITORY
).trim();
const turnstileSiteKey = (
  process.env.TURNSTILE_SITE_KEY ??
  TURNSTILE_TEST_SITE_KEY
).trim();

if (workerName !== DEFAULT_WORKER_NAME) {
  throw new Error(
    `直接部署只允许隔离测试 Worker：${DEFAULT_WORKER_NAME}`,
  );
}
if (namespaceTitle !== DEFAULT_KV_TITLE) {
  throw new Error(
    `直接部署只允许隔离测试 KV：${DEFAULT_KV_TITLE}`,
  );
}
if (hostname !== DEFAULT_HOSTNAME) {
  throw new Error(
    `直接部署只允许隔离测试 hostname：${DEFAULT_HOSTNAME}`,
  );
}
if (targetBranch !== 'EXEDRA-TEST') {
  throw new Error('直接部署的校对目标分支只能是 EXEDRA-TEST');
}
if (githubRepo !== DEFAULT_REPOSITORY) {
  throw new Error(
    `直接部署的 GitHub 仓库只能是 ${DEFAULT_REPOSITORY}`,
  );
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
// Wrangler resolves `main` and `assets.directory` relative to the config
// file, not the current working directory. Keep the temporary deploy config
// beside the committed config so the validated relative OpenNext paths remain
// correct.
const testConfig = path.resolve(
  projectRoot,
  '.wrangler.direct-test.jsonc',
);
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

const gitValue = (args) =>
  run('git', args, { capture: true }).trim().split(/\r?\n/u)[0]?.trim() ?? '';

if (
  run('git', ['status', '--porcelain=v1', '--untracked-files=normal'], {
    capture: true,
  }).trim()
) {
  throw new Error('直接部署要求干净工作区，拒绝部署未提交或未跟踪内容');
}

const resolveNamespaceId = () => {
  const output = run(
    process.execPath,
    [wranglerEntry, 'kv', 'namespace', 'list', '--config', sourceConfig],
    { capture: true },
  );
  const discovered = parseNamespaceList(output, namespaceTitle);
  if (
    explicitNamespaceId &&
    explicitNamespaceId.toLowerCase() !== discovered
  ) {
    throw new Error(
      '显式 KV ID 与隔离测试 namespace 名称解析结果不一致',
    );
  }
  return discovered;
};

const prepareConfig = (namespaceId, sourceCommit) => {
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
    hostname,
    targetBranch,
    sourceCommit,
    githubRepo,
    turnstileSiteKey,
    turnstileTestMode: turnstileSiteKey === TURNSTILE_TEST_SITE_KEY,
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

const npmInvocation = resolveNpmInvocation({
  platform: process.platform,
  nodeExecutable: process.execPath,
  npmExecPath: process.env.npm_execpath,
});
if (
  npmInvocation.prefixArgs.length > 0 &&
  !existsSync(npmInvocation.prefixArgs[0])
) {
  throw new Error(
    `npm CLI 文件不存在：${npmInvocation.prefixArgs[0]}`,
  );
}
const runNpm = (args) => run(
  npmInvocation.command,
  [...npmInvocation.prefixArgs, ...args],
);
let preparedConfig = '';
let redirectHeld = false;
try {
  const namespaceId = resolveNamespaceId();
  const sourceCommit = gitValue(['rev-parse', 'HEAD']);
  console.log(`测试 Worker：${workerName}`);
  console.log(`测试 hostname：${hostname}`);
  console.log(`校对目标分支：${targetBranch}`);
  console.log(`部署来源提交：${sourceCommit}`);
  console.log(`测试 KV：${namespaceTitle} (${namespaceId})`);
  preparedConfig = prepareConfig(namespaceId, sourceCommit);

  if (!skipChecks) {
    runNpm(['run', 'test:python']);
    runNpm(['run', 'lint']);
    runNpm(['run', 'type-check']);
    runNpm(['test']);
  }

  if (!skipBuild) {
    runNpm(['run', 'build:worker']);
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
  if (!keepConfig) {
    rmSync(resolvedConfig, { force: true });
    rmSync(testConfig, { force: true });
  } else if (preparedConfig) {
    console.log(`保留临时配置：${preparedConfig}`);
  }
  restoreOpenNextConfigRedirect(redirectHeld);
}
