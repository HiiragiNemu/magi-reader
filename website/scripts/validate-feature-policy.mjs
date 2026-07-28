import {
  existsSync,
  readFileSync,
} from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const websiteRoot = process.cwd();
const repositoryRoot = path.resolve(websiteRoot, '..');
const failures = [];
const checks = [];

const read = (relativeToRepository) => {
  const file = path.resolve(repositoryRoot, relativeToRepository);
  if (!existsSync(file)) {
    failures.push(`缺少文件：${relativeToRepository}`);
    return '';
  }
  return readFileSync(file, 'utf8');
};

const parseJson = (relativeToRepository) => {
  const raw = read(relativeToRepository);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (error) {
    failures.push(`${relativeToRepository} 不是有效 JSON：${error}`);
    return null;
  }
};

const requireCondition = (condition, message) => {
  if (condition) checks.push(message);
  else failures.push(message);
};

const requireIncludes = (source, expected, file) =>
  requireCondition(source.includes(expected), `${file} 必须包含 ${JSON.stringify(expected)}`);
const requireExcludes = (source, forbidden, file) =>
  requireCondition(!source.includes(forbidden), `${file} 不得包含 ${JSON.stringify(forbidden)}`);

const exedraManifestPath =
  'magiraexedra-source-master/Scenarios_full/exedra_manifest.json';
const exedraManifest = parseJson(exedraManifestPath);
if (exedraManifest) {
  requireCondition(exedraManifest.schemaVersion === 1, 'Exedra manifest schemaVersion 必须为 1');
  requireCondition(exedraManifest.summary?.groupCount === 443, 'Exedra 逻辑组必须为 443');
  requireCondition(exedraManifest.summary?.sourceCount === 3061, 'Exedra 来源 JSON 必须为 3061');
  requireCondition(exedraManifest.summary?.dialogueCount === 105867, 'Exedra 文本事件必须为 105867');
  requireCondition(
    Array.isArray(exedraManifest.groups) && exedraManifest.groups.length === 443,
    'Exedra groups 数组必须完整包含 443 组',
  );
}

const categoryNormalizerPath = 'website/components/CategoryLabelNormalizer.tsx';
const categoryNormalizer = read(categoryNormalizerPath);
for (const [legacy, expected] of [
  ["'1 主线': '主线'", '主线'],
  ["'2 Sub': '活动'", '活动'],
  ["'3 角色': '角色'", '角色'],
  ["'4 肖像': '肖像'", '肖像'],
  ["'6 语音': '语音'", '语音'],
  ["'7 Namae': 'Namae'", 'Namae'],
  ["'8 Dungeon': '过场动画字幕'", '过场动画字幕'],
  ["'10 战斗': '战斗'", '战斗'],
]) {
  requireIncludes(categoryNormalizer, legacy, categoryNormalizerPath);
  checks.push(`分类显示名：${expected}`);
}

const wranglerPath = 'website/wrangler.jsonc';
const wrangler = parseJson(wranglerPath);
if (wrangler) {
  requireCondition(!Object.hasOwn(wrangler, 'ai'), 'Wrangler 配置不得包含 AI binding');
  requireCondition(
    !Object.hasOwn(wrangler.vars ?? {}, 'EXEDRA_TRANSLATION_MODEL'),
    'Wrangler vars 不得包含 Exedra 翻译模型',
  );
  requireCondition(
    wrangler.vars?.EXEDRA_WIKI_BASE_URL === 'https://exedra.wiki',
    'Exedra Wiki 基础地址必须固定为 https://exedra.wiki',
  );
}

const cloudflareEnvPath = 'website/cloudflare-env.d.ts';
const cloudflareEnv = read(cloudflareEnvPath);
requireExcludes(cloudflareEnv, 'CloudflareAiBinding', cloudflareEnvPath);
requireExcludes(cloudflareEnv, 'EXEDRA_TRANSLATION_MODEL', cloudflareEnvPath);

requireCondition(
  !existsSync(path.resolve(
    repositoryRoot,
    'website/public/data/exedra_machine_translation_manifest.generated.json',
  )),
  '取消后的 Exedra 机翻清单不得存在',
);
requireCondition(
  !existsSync(path.resolve(
    repositoryRoot,
    'generate_exedra_machine_translation_manifest.py',
  )),
  '取消后的 Exedra 机翻清单生成器不得存在',
);

const localizationPath = 'website/lib/exedra-localization.ts';
const localization = read(localizationPath);
requireExcludes(localization, 'loadOrCreateExedraLocalization', localizationPath);
requireExcludes(localization, 'CloudflareAiBinding', localizationPath);
requireIncludes(localization, "'official_tw_human'", localizationPath);
requireIncludes(localization, "'exedra_wiki_human'", localizationPath);

const localizedRoutePath = 'website/app/api/exedra/localized/[id]/route.ts';
const localizedRoute = read(localizedRoutePath);
requireExcludes(localizedRoute, 'loadOrCreateExedraLocalization', localizedRoutePath);
requireExcludes(localizedRoute, 'machineTranslate', localizedRoutePath);
requireIncludes(localizedRoute, 'tryExactWikiLocalization', localizedRoutePath);

const machineReviewPath = 'website/lib/machine-translation-review.ts';
const machineReview = read(machineReviewPath);
requireExcludes(
  machineReview,
  'exedra_machine_translation_manifest',
  machineReviewPath,
);
requireIncludes(machineReview, "export type MachineTranslationSystem = 'magireco'", machineReviewPath);

const voiceSourcePath = 'website/lib/general-voice-source.ts';
const voiceSource = read(voiceSourcePath);
requireIncludes(
  voiceSource,
  "'196f4bfcfa28c446539b4611e4cce7992b0c40d1'",
  voiceSourcePath,
);
requireIncludes(
  voiceSource,
  'https://566b00b8.magiaexedralive2dviewer.pages.dev/story/general',
  voiceSourcePath,
);

const packagePath = 'website/package.json';
const packageJson = parseJson(packagePath);
if (packageJson) {
  requireCondition(
    packageJson.scripts?.test === 'node --experimental-strip-types --test',
    'npm test 必须执行 TypeScript 测试',
  );
  requireCondition(
    packageJson.scripts?.['deploy:test:direct'] ===
      'node scripts/deploy-direct-test.mjs',
    '必须保留隔离测试 Worker 的直接部署命令',
  );
}

for (const directory of [
  'magireco-voice-source-master/Scenarios_full/general_voice',
  'magireco-voice-translate-data-master/Scenarios_full/general_voice',
]) {
  requireCondition(
    existsSync(path.resolve(repositoryRoot, directory)),
    `语音目标目录必须存在：${directory}`,
  );
}
for (const tool of [
  'tools/import_magireco_general_voice.py',
  'tools/import_exedra_official_tw.py',
  'tools/import_exedra_cache_export.py',
  'tools/github_api_checkout.py',
]) {
  requireCondition(
    existsSync(path.resolve(repositoryRoot, tool)),
    `直接处理工具必须存在：${tool}`,
  );
}
requireCondition(
  !existsSync(path.resolve(
    repositoryRoot,
    '.github/workflows/audit-exedra-voice-sources.yml',
  )),
  '不得保留本项目临时 GitHub Actions 审计工作流',
);

const report = {
  version: 1,
  passed: failures.length === 0,
  checkedAt: new Date().toISOString(),
  checks: checks.length,
  failures,
};
console.log(JSON.stringify(report, null, 2));
if (failures.length) process.exitCode = 2;
