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
  requireCondition(
    source.includes(expected),
    `${file} 必须包含 ${JSON.stringify(expected)}`,
  );
const requireExcludes = (source, forbidden, file) =>
  requireCondition(
    !source.includes(forbidden),
    `${file} 不得包含 ${JSON.stringify(forbidden)}`,
  );

const exedraManifestPath =
  'magiraexedra-source-master/Scenarios_full/exedra_manifest.json';
const exedraManifest = parseJson(exedraManifestPath);
if (exedraManifest) {
  requireCondition(
    exedraManifest.schemaVersion === 1,
    'Exedra manifest schemaVersion 必须为 1',
  );
  requireCondition(
    exedraManifest.summary?.groupCount === 443,
    'Exedra 逻辑组必须为 443',
  );
  requireCondition(
    exedraManifest.summary?.sourceCount === 3061,
    'Exedra 来源 JSON 必须为 3061',
  );
  requireCondition(
    exedraManifest.summary?.dialogueCount === 105867,
    'Exedra 文本事件必须为 105867',
  );
  requireCondition(
    Array.isArray(exedraManifest.groups) && exedraManifest.groups.length === 443,
    'Exedra groups 数组必须完整包含 443 组',
  );
}

const finalLabels = [
  ['exedra_main', '主线'],
  ['exedra_sub', '活动'],
  ['exedra_character', '角色'],
  ['exedra_portrait', '肖像'],
  ['exedra_reaction', '语音'],
  ['exedra_namae', 'Namae'],
  ['exedra_dungeon', '过场动画字幕'],
  ['exedra_battle', '战斗'],
];
const sidebarPath = 'website/components/Sidebar.tsx';
const sidebar = read(sidebarPath);
const homePath = 'website/app/page.tsx';
const home = read(homePath);
for (const [category, label] of finalLabels) {
  requireIncludes(
    sidebar,
    `${category}: { label: '${label}'`,
    sidebarPath,
  );
  requireIncludes(
    home,
    `${category}: { label: '${label}'`,
    homePath,
  );
}
for (const forbidden of [
  "exedra_main: { label: '1 主线'",
  "exedra_sub: { label: '2 Sub'",
  "exedra_character: { label: '3 角色'",
  "exedra_portrait: { label: '4 肖像'",
  "exedra_reaction: { label: '6 语音'",
  "exedra_namae: { label: '7 Namae'",
  "exedra_dungeon: { label: '8 Dungeon'",
  "exedra_battle: { label: '10 战斗'",
]) {
  requireExcludes(sidebar, forbidden, sidebarPath);
  requireExcludes(home, forbidden, homePath);
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
  requireCondition(
    !Object.hasOwn(wrangler, 'ai'),
    'Wrangler 配置不得包含 AI binding',
  );
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
requireExcludes(localization, "'machine_translation'", localizationPath);
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
requireIncludes(
  machineReview,
  "export type MachineTranslationSystem = 'magireco'",
  machineReviewPath,
);

const voiceSourcePath = 'website/lib/general-voice-source.ts';
const voiceSource = read(voiceSourcePath);
requireIncludes(
  voiceSource,
  "'6d921b630f41341a1c5aba66ec355ef9017e778d'",
  voiceSourcePath,
);
requireIncludes(
  voiceSource,
  'https://566b00b8.magiaexedralive2dviewer.pages.dev/story/general',
  voiceSourcePath,
);
const voiceRuntimePath = 'website/lib/general-voice-runtime.ts';
const voiceRuntime = read(voiceRuntimePath);
requireIncludes(voiceRuntime, 'const EXPECTED_CN_MODELS = 410', voiceRuntimePath);
requireIncludes(voiceRuntime, '继续使用旧缓存', voiceRuntimePath);
const generatorPath = 'generate_story_index.py';
const generator = read(generatorPath);
requireIncludes(
  generator,
  'def scan_general_voice_sources(',
  generatorPath,
);
requireIncludes(
  generator,
  'GENERAL_VOICE_EXPECTED_MODELS = 410',
  generatorPath,
);
requireCondition(
  !existsSync(path.resolve(repositoryRoot, 'website/proxy.ts')),
  '已落盘的语音不得再由 proxy 动态覆盖或依赖上游网络',
);
const voiceManifest = parseJson(
  'magireco-voice-source-master/Scenarios_full/general_voice/general_voice_manifest.json',
);
if (voiceManifest) {
  requireCondition(
    voiceManifest.version === 1 &&
      voiceManifest.modelCount === 410 &&
      Array.isArray(voiceManifest.models) &&
      voiceManifest.models.length === 410,
    '本地语音清单必须完整包含 410 个可播放模型',
  );
}

const packagePath = 'website/package.json';
const packageJson = parseJson(packagePath);
if (packageJson) {
  requireCondition(
    packageJson.engines?.node === '>=22.6.0',
    'Node 版本下限必须支持原生 TypeScript 类型剥离',
  );
  requireCondition(
    packageJson.scripts?.test === 'node --experimental-strip-types --test',
    'npm test 必须执行 TypeScript 测试',
  );
  requireCondition(
    packageJson.scripts?.['test:python'] ===
      'node scripts/run-python-checks.mjs',
    '必须执行 Python 编译和回归测试',
  );
  requireCondition(
    packageJson.scripts?.['deploy:test:direct'] ===
      'node scripts/deploy-direct.mjs',
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
  'tools/import_exedra_human_text.py',
  'tools/import_exedra_wiki_voice.py',
  'tools/github_api_checkout.py',
  'tools/run_python_checks.py',
  'scripts/materialize_proofreading_assets.py',
  'tests/test_exedra_import_tools.py',
  'tests/test_import_exedra_human_text.py',
  'tests/test_import_exedra_wiki_voice.py',
  'tests/test_materialize_proofreading_assets.py',
]) {
  requireCondition(
    existsSync(path.resolve(repositoryRoot, tool)),
    `直接处理/验证工具必须存在：${tool}`,
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
