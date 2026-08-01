import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const flagValue = (name) => {
  const index = process.argv.indexOf(name);
  if (index < 0) return null;
  const value = process.argv[index + 1];
  if (!value || value.startsWith('--')) {
    throw new Error(`${name} 缺少路径参数`);
  }
  return value;
};

const configPath = path.resolve(flagValue('--config') ?? 'wrangler.jsonc');
const outputArgument = flagValue('--output');
const outputPath = outputArgument ? path.resolve(outputArgument) : null;
const configSource = fs.readFileSync(configPath, 'utf8');
const placeholderNamespaceId = '00000000000000000000000000000000';
const namespaceIdOverride =
  process.env.SUBMISSIONS_KV_NAMESPACE_ID?.trim() ?? '';

const escapeRegExp = (value) =>
  value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const namespaceBlockFor = (binding) => {
  const blockPattern = new RegExp(
    String.raw`\{(?:(?!\}).)*"binding"\s*:\s*"${escapeRegExp(binding)}"(?:(?!\}).)*"id"\s*:\s*"([^"]+)"(?:(?!\}).)*\}`,
    'su',
  );
  const match = configSource.match(blockPattern);
  return match ? { block: match[0], id: match[1] } : null;
};

const bindingMatches =
  configSource.match(/"binding"\s*:\s*"SUBMISSIONS_KV"/gu) ?? [];
const namespaceBlock = namespaceBlockFor('SUBMISSIONS_KV');
const configuredNamespaceId = namespaceBlock?.id ?? null;
const resolvedNamespaceId =
  outputPath && namespaceIdOverride
    ? namespaceIdOverride
    : configuredNamespaceId;
const errors = [];

if (bindingMatches.length !== 1) {
  errors.push('wrangler 配置必须且只能声明一个 SUBMISSIONS_KV binding');
} else if (!configuredNamespaceId) {
  errors.push('wrangler.jsonc 缺少 SUBMISSIONS_KV namespace ID');
}

if (namespaceIdOverride && !/^[a-f0-9]{32}$/iu.test(namespaceIdOverride)) {
  errors.push('SUBMISSIONS_KV_NAMESPACE_ID 必须是 32 位十六进制字符串');
}
if (!resolvedNamespaceId) {
  errors.push('无法解析 SUBMISSIONS_KV namespace ID');
} else if (resolvedNamespaceId === placeholderNamespaceId) {
  errors.push('SUBMISSIONS_KV 仍使用全零占位 ID');
} else if (!/^[a-f0-9]{32}$/iu.test(resolvedNamespaceId)) {
  errors.push('SUBMISSIONS_KV namespace ID 必须是 32 位十六进制字符串');
}

if (/"SUBMISSIONS_ADMIN_TOKEN"\s*:/u.test(configSource)) {
  errors.push('SUBMISSIONS_ADMIN_TOKEN 必须使用 Worker secret，不能写入 wrangler.jsonc');
}
if (outputPath?.toLowerCase() === configPath.toLowerCase()) {
  errors.push('解析后的部署配置不能覆盖仓库中的 wrangler.jsonc');
}

if (errors.length > 0) {
  for (const error of errors) console.error(error);
  process.exitCode = 1;
} else {
  if (outputPath) {
    const resolvedSource =
      namespaceIdOverride && namespaceBlock
        ? configSource.replace(
            namespaceBlock.block,
            namespaceBlock.block.replace(
              /"id"\s*:\s*"[^"]+"/u,
              `"id": "${namespaceIdOverride}"`,
            ),
          )
        : configSource;
    fs.writeFileSync(outputPath, resolvedSource, {
      encoding: 'utf8',
      mode: 0o600,
    });
    console.log('Cloudflare 部署配置已安全生成。');
  } else {
    console.log('Cloudflare 配置检查通过：投稿 KV 已配置且管理员密钥未写入配置。');
  }
}
