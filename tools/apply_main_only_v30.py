#!/usr/bin/env python3
"""Apply the final main-only V30 font scope and retire the test environment.

The migration is intentionally fail-closed: every expected source fragment must
match exactly, and the validation workflow removes this script only after the
full repository test/build suite succeeds.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ROOT / "website/app/providers.tsx"
HOME = ROOT / "website/app/page.tsx"
READER = ROOT / "website/app/reader/[id]/page.tsx"
REFINEMENTS = ROOT / "website/app/ui-refinements.css"
READER_FONTS = ROOT / "website/lib/reader-fonts.ts"
EXEDRA_FONTS = ROOT / "website/lib/exedra-fonts.ts"
EXEDRA_SETTINGS = ROOT / "website/components/ExedraFontSettings.tsx"
CONFIGURE_PAGES = ROOT / "website/scripts/configure-pages-project.mjs"
CLOUDFLARE_TEST = ROOT / "website/tests/cloudflare-deployment.test.mjs"
PROOFREADING_TEST = ROOT / "website/tests/proofreading-workflow.test.mjs"
FONT_TEST = ROOT / "website/tests/global-font-scope-main-only.test.mjs"
COMMUNITY_WORKFLOW = ROOT / ".github/workflows/community-proofreading-pr.yml"
MATERIALIZE_WORKFLOW = ROOT / ".github/workflows/materialize-tw-official-cn.yml"
TEST_DEPLOY_WORKFLOW = ROOT / ".github/workflows/deploy-exedra-proofreading-test.yml"
REPAIR_WORKFLOW = ROOT / ".github/workflows/repair-authentic-tw.yml"
VOICE_PATCH_WORKFLOW = ROOT / ".github/workflows/patch-voice-fallback-smoke.yml"
RETIRE_WORKFLOW = ROOT / ".github/workflows/retire-exedra-test-environment.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")


def replace_once(path: Path, old: str, new: str) -> None:
    source = read(path)
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} replacement count={count}; expected 1"
        )
    write(path, source.replace(old, new, 1))


def delete_required(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"required deletion target missing: {path.relative_to(ROOT)}")
    path.unlink()


CSS_APPEND = r'''

/* =========================================
   Reader UI V30 — global game-font scope and Exedra whole-UI font skin
   ========================================= */

/* 腾祥智黑 covers all site UI when the Chinese game-font bundle is active. */
html[data-reader-font-chinese='ready'] .magi-site-font-scope,
html[data-reader-font-chinese='ready'] .magi-site-font-scope :where(
  button,
  input,
  textarea,
  select,
  option,
  summary,
  label,
  h1,
  h2,
  h3,
  h4,
  h5,
  h6,
  .font-serif,
  .font-sans,
  .font-mono
) {
  font-family:
    "MagiReaderGameChineseTitle",
    "Microsoft YaHei",
    "Noto Sans SC",
    system-ui,
    sans-serif !important;
}

/* 腾祥嘉丽大圆 remains the Chinese story/proofreading prose face. */
html[data-reader-font-chinese='ready'] .magi-site-font-scope .reader-font-cn-body,
html[data-reader-font-chinese='ready'] .magi-site-font-scope .reader-font-cn-body *,
html[data-reader-font-chinese='ready'] .magi-site-font-scope .magi-translation-textarea,
html[data-reader-font-chinese='ready'] .magi-site-font-scope .magi-translation-linebreak-overlay,
html[data-reader-font-chinese='ready'] .magi-site-font-scope .magi-home-search-snippet {
  font-family:
    "MagiReaderGameChineseBody",
    "Microsoft YaHei",
    "Noto Sans SC",
    system-ui,
    sans-serif !important;
}

html[data-reader-font-chinese='ready'] .magi-site-font-scope .reader-font-cn-title,
html[data-reader-font-chinese='ready'] .magi-site-font-scope .reader-font-cn-title *,
html[data-reader-font-chinese='ready'] .magi-site-font-scope .magi-reader-speaker-label,
html[data-reader-font-chinese='ready'] .magi-site-font-scope .magi-translation-speaker-input {
  font-family:
    "MagiReaderGameChineseTitle",
    "Microsoft YaHei",
    "Noto Sans SC",
    system-ui,
    sans-serif !important;
}

/* Chinese UI fonts must not leak into Japanese story rows. */
html[data-reader-font-chinese='ready'] .magi-site-font-scope .reader-font-jp-body,
html[data-reader-font-chinese='ready'] .magi-site-font-scope .reader-font-jp-body * {
  font-family:
    "Yu Gothic",
    "Hiragino Kaku Gothic ProN",
    "Noto Sans JP",
    sans-serif !important;
}

html[data-reader-font-chinese='ready'] .magi-site-font-scope .reader-font-jp-title,
html[data-reader-font-chinese='ready'] .magi-site-font-scope .reader-font-jp-title * {
  font-family:
    "Yu Gothic",
    "Hiragino Kaku Gothic ProN",
    "Noto Sans JP",
    sans-serif !important;
}

html[data-reader-font-japanese='ready'] .magi-site-font-scope .reader-font-jp-body,
html[data-reader-font-japanese='ready'] .magi-site-font-scope .reader-font-jp-body * {
  font-family:
    "MagiReaderGameJapaneseBody",
    "Yu Gothic",
    "Noto Sans JP",
    sans-serif !important;
}

html[data-reader-font-japanese='ready'] .magi-site-font-scope .reader-font-jp-title,
html[data-reader-font-japanese='ready'] .magi-site-font-scope .reader-font-jp-title * {
  font-family:
    "MagiReaderGameJapaneseTitle",
    "Yu Gothic",
    "Noto Sans JP",
    sans-serif !important;
}

/* 猫啃网糖圆体 is a whole-UI Exedra skin, including Chinese prose. */
html[data-exedra-font-tang-yuan='ready'] .magi-exedra-ui-scope,
html[data-exedra-font-tang-yuan='ready'] .magi-exedra-ui-scope :where(
  button,
  input,
  textarea,
  select,
  option,
  summary,
  label,
  h1,
  h2,
  h3,
  h4,
  h5,
  h6,
  .font-serif,
  .font-sans,
  .font-mono,
  .reader-font-cn-body,
  .reader-font-cn-title,
  .magi-reader-speaker-label,
  .magi-translation-speaker-input,
  .magi-translation-textarea,
  .magi-translation-linebreak-overlay,
  .magi-home-search-snippet
) {
  font-family:
    "MagiReaderExedraTangYuan",
    "Resource Han Rounded CN",
    "Noto Sans SC",
    system-ui,
    sans-serif !important;
}

/* Preserve Japanese language roles after the whole-Exedra UI override. */
html[data-exedra-font-tang-yuan='ready'] .magi-exedra-ui-scope .reader-font-jp-body,
html[data-exedra-font-tang-yuan='ready'] .magi-exedra-ui-scope .reader-font-jp-body *,
html[data-exedra-font-tang-yuan='ready'] .magi-exedra-ui-scope .reader-font-jp-title,
html[data-exedra-font-tang-yuan='ready'] .magi-exedra-ui-scope .reader-font-jp-title * {
  font-family:
    "Yu Gothic",
    "Hiragino Kaku Gothic ProN",
    "Noto Sans JP",
    sans-serif !important;
}

html[data-reader-font-japanese='ready'][data-exedra-font-tang-yuan='ready']
  .magi-exedra-ui-scope .reader-font-jp-body,
html[data-reader-font-japanese='ready'][data-exedra-font-tang-yuan='ready']
  .magi-exedra-ui-scope .reader-font-jp-body * {
  font-family:
    "MagiReaderGameJapaneseBody",
    "Yu Gothic",
    "Noto Sans JP",
    sans-serif !important;
}

html[data-reader-font-japanese='ready'][data-exedra-font-tang-yuan='ready']
  .magi-exedra-ui-scope .reader-font-jp-title,
html[data-reader-font-japanese='ready'][data-exedra-font-tang-yuan='ready']
  .magi-exedra-ui-scope .reader-font-jp-title * {
  font-family:
    "MagiReaderGameJapaneseTitle",
    "Yu Gothic",
    "Noto Sans JP",
    sans-serif !important;
}

html[data-exedra-font-tsuku='ready'] .magi-exedra-ui-scope .reader-font-jp-title,
html[data-exedra-font-tsuku='ready'] .magi-exedra-ui-scope .reader-font-jp-title * {
  font-family:
    "MagiReaderExedraTsukuOldGothic",
    "Yu Gothic",
    "Noto Sans JP",
    sans-serif !important;
}

html[data-exedra-font-new-cinema='ready'] .magi-exedra-ui-scope .reader-font-jp-body,
html[data-exedra-font-new-cinema='ready'] .magi-exedra-ui-scope .reader-font-jp-body * {
  font-family:
    "MagiReaderExedraNewCinemaA",
    "Yu Gothic",
    "Noto Sans JP",
    sans-serif !important;
}
'''

RETIRE_WORKFLOW_CONTENT = r'''name: Retire EXEDRA test environment

on:
  push:
    branches: [main]

permissions:
  contents: write

concurrency:
  group: retire-exedra-test-environment
  cancel-in-progress: false

jobs:
  retire:
    if: contains(github.event.head_commit.message, '[main-only-v30]')
    runs-on: ubuntu-latest
    timeout-minutes: 15
    env:
      TEST_WORKER_NAME: magireader-exedra-cn-test

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Delete dedicated Cloudflare test Worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        shell: bash
        run: |
          set -euo pipefail
          if [ -z "$CLOUDFLARE_API_TOKEN" ] || [ -z "$CLOUDFLARE_ACCOUNT_ID" ]; then
            echo 'Cloudflare cleanup credentials are missing.' >&2
            exit 1
          fi
          api="https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/$TEST_WORKER_NAME"
          status="$(curl --silent --show-error \
            --output "$RUNNER_TEMP/delete-test-worker.json" \
            --write-out '%{http_code}' \
            --request DELETE \
            --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
            --header 'Content-Type: application/json' \
            "$api")"
          if [ "$status" != '200' ] && [ "$status" != '404' ]; then
            cat "$RUNNER_TEMP/delete-test-worker.json" >&2 || true
            echo "Test Worker deletion returned HTTP $status" >&2
            exit 1
          fi
          verify_status="$(curl --silent --show-error \
            --output "$RUNNER_TEMP/verify-test-worker.json" \
            --write-out '%{http_code}' \
            --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
            "$api")"
          if [ "$verify_status" != '404' ]; then
            cat "$RUNNER_TEMP/verify-test-worker.json" >&2 || true
            echo "Test Worker still resolves through the Cloudflare API (HTTP $verify_status)." >&2
            exit 1
          fi
          echo 'EXEDRA_TEST_WORKER_RETIRED'

      - name: Delete retired test and implementation branches
        shell: bash
        run: |
          set -euo pipefail
          for branch in \
            EXEDRA-TEST \
            work/main-only-v30-font-scope \
            tmp-v30-bootstrap-safety \
            tmp-main-only-v30-validation \
            tmp-main-only-v30-cleanup \
            tmp-v30-do-not-use \
            tmp-v30-final-safety \
            tmp-v30-ignore-2; do
            if git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
              git push origin --delete "$branch"
            fi
            if git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
              echo "Branch still exists: $branch" >&2
              exit 1
            fi
          done
          echo 'EXEDRA_TEST_BRANCH_RETIRED'
'''

FONT_TEST_CONTENT = r'''import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const providers = readFileSync(new URL('../app/providers.tsx', import.meta.url), 'utf8');
const home = readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf8');
const reader = readFileSync(new URL('../app/reader/[id]/page.tsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('../app/ui-refinements.css', import.meta.url), 'utf8');
const readerFonts = readFileSync(new URL('../lib/reader-fonts.ts', import.meta.url), 'utf8');
const exedraFonts = readFileSync(new URL('../lib/exedra-fonts.ts', import.meta.url), 'utf8');
const exedraSettings = readFileSync(new URL('../components/ExedraFontSettings.tsx', import.meta.url), 'utf8');
const configurePages = readFileSync(new URL('../scripts/configure-pages-project.mjs', import.meta.url), 'utf8');
const cleanupWorkflow = readFileSync(
  new URL('../../.github/workflows/retire-exedra-test-environment.yml', import.meta.url),
  'utf8',
);
const testDeployWorkflow = new URL(
  '../../.github/workflows/deploy-exedra-proofreading-test.yml',
  import.meta.url,
);

test('persisted optional fonts initialize globally before home or reader routing', () => {
  assert.match(providers, /initializeReaderFonts/u);
  assert.match(providers, /initializeExedraFonts/u);
  assert.match(providers, /void initializeReaderFonts\(\)/u);
  assert.match(providers, /void initializeExedraFonts\(\)/u);
  assert.match(providers, /magi-site-font-scope/u);
});

test('Exedra home and reader screens expose one bounded whole-UI font scope', () => {
  assert.match(home, /storySystem === 'exedra' \? 'magi-exedra-ui-scope'/u);
  assert.match(reader, /isExedraStory \? 'magi-exedra-ui-scope'/u);
  assert.match(home, /magi-home-search-snippet reader-font-cn-body/u);
});

test('Chinese game fonts separate prose from titles and cover the complete UI', () => {
  assert.match(readerFonts, /正文使用腾祥嘉丽大圆/u);
  assert.match(readerFonts, /站点 UI 使用腾祥智黑/u);
  assert.match(css, /data-reader-font-chinese='ready'[\s\S]*magi-site-font-scope[\s\S]*MagiReaderGameChineseTitle/u);
  assert.match(css, /reader-font-cn-body[\s\S]*MagiReaderGameChineseBody/u);
  assert.match(css, /magi-reader-speaker-label[\s\S]*MagiReaderGameChineseTitle/u);
});

test('TangYuan covers all Exedra UI while Japanese story font roles stay isolated', () => {
  assert.match(exedraFonts, /Exedra 全部 UI 与简体中文正文/u);
  assert.match(exedraSettings, /猫啃网糖圆体覆盖 Exedra 全部 UI 与简体中文正文/u);
  assert.match(css, /data-exedra-font-tang-yuan='ready'[\s\S]*magi-exedra-ui-scope[\s\S]*MagiReaderExedraTangYuan/u);
  assert.match(css, /data-exedra-font-tsuku='ready'[\s\S]*reader-font-jp-title/u);
  assert.match(css, /data-exedra-font-new-cinema='ready'[\s\S]*reader-font-jp-body/u);
});

test('repository policy is main-only and retirement removes the old environment', () => {
  assert.equal(existsSync(testDeployWorkflow), false);
  assert.match(cleanupWorkflow, /workers\/scripts\/\$TEST_WORKER_NAME/u);
  assert.match(cleanupWorkflow, /EXEDRA-TEST/u);
  assert.match(cleanupWorkflow, /git push origin --delete/u);
  assert.match(cleanupWorkflow, /EXEDRA_TEST_WORKER_RETIRED/u);
  assert.match(cleanupWorkflow, /EXEDRA_TEST_BRANCH_RETIRED/u);
  assert.match(configurePages, /PROOFREADING_TARGET_BRANCH:\s*plainText\('main'\)/u);
});
'''


def patch_cloudflare_test() -> None:
    source = read(CLOUDFLARE_TEST)
    source = source.replace(
        "import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';",
        "import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';",
        1,
    )
    constant = """const testDeploymentWorkflow = path.resolve(\n  '..',\n  '.github',\n  'workflows',\n  'deploy-exedra-proofreading-test.yml',\n);\n"""
    if source.count(constant) != 1:
        raise RuntimeError("cloudflare deployment test workflow constant drifted")
    source = source.replace(constant, "", 1)
    marker = "test('isolated Exedra V4 deployment verifies search chunks, revision, voice systems and decoder', () => {"
    start = source.find(marker)
    if start < 0:
        raise RuntimeError("isolated Exedra deployment test marker not found")
    replacement = r'''test('main-only deployment retires the dedicated Exedra test environment', () => {
  const retiredWorkflow = path.resolve(
    '..',
    '.github',
    'workflows',
    'deploy-exedra-proofreading-test.yml',
  );
  const cleanupWorkflow = path.resolve(
    '..',
    '.github',
    'workflows',
    'retire-exedra-test-environment.yml',
  );
  assert.equal(existsSync(retiredWorkflow), false);
  const cleanup = readFileSync(cleanupWorkflow, 'utf8');
  assert.match(cleanup, /magireader-exedra-cn-test/u);
  assert.match(cleanup, /workers\/scripts\/\$TEST_WORKER_NAME/u);
  assert.match(cleanup, /git push origin --delete/u);
  assert.match(cleanup, /EXEDRA-TEST/u);
});
'''
    write(CLOUDFLARE_TEST, source[:start] + replacement)


def patch_proofreading_test() -> None:
    source = read(PROOFREADING_TEST)
    import_old = "import { readFileSync } from 'node:fs';\n"
    import_new = "import { existsSync, readFileSync } from 'node:fs';\n"
    if source.count(import_old) != 1:
        raise RuntimeError("proofreading test node:fs import drifted")
    source = source.replace(import_old, import_new, 1)

    community_start = source.find(
        "test('community proofreading PR CI materializes playable JSON before TXT'"
    )
    retired_start = source.find(
        "test('TW simplified test deployment is isolated, deterministic and chunk-verified'"
    )
    next_start = source.find(
        "test('review login presents shared team token as the simple default'",
        retired_start,
    )
    if community_start < 0 or retired_start < 0 or next_start < 0:
        raise RuntimeError("proofreading test section markers drifted")
    community = source[community_start:retired_start]
    old_assert = "  assert.match(workflow, /branches:\\s*\\[EXEDRA-TEST\\]/u);\n"
    if community.count(old_assert) != 1:
        raise RuntimeError("community workflow branch assertion drifted")
    community = community.replace(
        old_assert,
        "  assert.match(workflow, /branches:\\s*\\[main\\]/u);\n",
        1,
    )
    retirement = r'''test('main-only proofreading and TW materialization target production main', () => {
  const retiredWorkflow = path.resolve(
    '../.github/workflows/deploy-exedra-proofreading-test.yml',
  );
  const cleanup = read('../.github/workflows/retire-exedra-test-environment.yml');
  const materialize = read('../.github/workflows/materialize-tw-official-cn.yml');
  const configure = read('scripts/configure-pages-project.mjs');
  assert.equal(existsSync(retiredWorkflow), false);
  assert.match(cleanup, /magireader-exedra-cn-test/u);
  assert.match(cleanup, /EXEDRA-TEST/u);
  assert.match(cleanup, /git push origin --delete/u);
  assert.match(materialize, /ref:\s*main/u);
  assert.match(materialize, /git push origin HEAD:main/u);
  assert.doesNotMatch(materialize, /branches:\s*\[EXEDRA-TEST\]/u);
  assert.match(
    configure,
    /PROOFREADING_TARGET_BRANCH:\s*plainText\('main'\)/u,
  );
});

'''
    write(
        PROOFREADING_TEST,
        source[:community_start]
        + community
        + retirement
        + source[next_start:],
    )


def patch_main_only_workflows() -> None:
    replace_once(
        COMMUNITY_WORKFLOW,
        "    branches: [EXEDRA-TEST]\n",
        "    branches: [main]\n",
    )
    replace_once(
        CONFIGURE_PAGES,
        "  PROOFREADING_TARGET_BRANCH: plainText('EXEDRA-TEST'),\n",
        "  PROOFREADING_TARGET_BRANCH: plainText('main'),\n",
    )
    replace_once(
        MATERIALIZE_WORKFLOW,
        "name: Materialize TW Official Simplified Chinese into EXEDRA-TEST\n",
        "name: Materialize TW Official Simplified Chinese into main\n",
    )
    replace_once(
        MATERIALIZE_WORKFLOW,
        "on:\n  push:\n    branches: [EXEDRA-TEST]\n  workflow_dispatch:\n",
        "on:\n  workflow_dispatch:\n",
    )
    replace_once(
        MATERIALIZE_WORKFLOW,
        "  group: materialize-tw-official-cn-exedra-test\n",
        "  group: materialize-tw-official-cn-main\n",
    )
    replace_once(
        MATERIALIZE_WORKFLOW,
        "          ref: EXEDRA-TEST\n",
        "          ref: main\n",
    )
    replace_once(
        MATERIALIZE_WORKFLOW,
        "          git push origin HEAD:EXEDRA-TEST\n",
        "          git push origin HEAD:main\n",
    )


def assert_main_only_policy() -> None:
    allowed = {
        "retire-exedra-test-environment.yml",
        "apply-main-only-v30.yml",
    }
    unexpected_workflows: list[str] = []
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        if path.name in allowed:
            continue
        if "EXEDRA-TEST" in read(path):
            unexpected_workflows.append(str(path.relative_to(ROOT)))
    if unexpected_workflows:
        raise RuntimeError(
            "non-retirement workflows still reference EXEDRA-TEST: "
            + ", ".join(unexpected_workflows)
        )


def main() -> int:
    replace_once(
        PROVIDERS,
        'import { createContext, useContext, useEffect, useSyncExternalStore } from "react";\n',
        'import { createContext, useContext, useEffect, useSyncExternalStore } from "react";\n\n'
        'import { initializeExedraFonts } from "@/lib/exedra-fonts";\n'
        'import { initializeReaderFonts } from "@/lib/reader-fonts";\n',
    )
    replace_once(
        PROVIDERS,
        "  useEffect(() => {\n    document.documentElement.classList.toggle('dark', theme === 'dark');\n  }, [theme]);\n\n  return (\n",
        "  useEffect(() => {\n    document.documentElement.classList.toggle('dark', theme === 'dark');\n  }, [theme]);\n\n"
        "  useEffect(() => {\n    void initializeReaderFonts();\n    void initializeExedraFonts();\n  }, []);\n\n  return (\n",
    )
    replace_once(
        PROVIDERS,
        '      <div className={`min-h-screen transition-colors duration-300 relative z-0 bg-transparent',
        '      <div className={`magi-site-font-scope min-h-screen transition-colors duration-300 relative z-0 bg-transparent',
    )

    replace_once(
        HOME,
        '    <div className={`magi-home-shell flex h-screen h-[100dvh] overflow-hidden ${',
        "    <div className={`magi-home-shell ${storySystem === 'exedra' ? 'magi-exedra-ui-scope' : ''} flex h-screen h-[100dvh] overflow-hidden ${",
    )
    replace_once(
        HOME,
        'className={`px-2 py-1.5 text-xs font-serif border-t ${',
        'className={`magi-home-search-snippet reader-font-cn-body px-2 py-1.5 text-xs font-serif border-t ${',
    )
    replace_once(
        READER,
        '    <div className={`magi-reader-root magi-reader-theme-${theme} flex h-screen h-[100dvh] overflow-hidden ${THEME_STYLES[theme]}`}>',
        "    <div className={`magi-reader-root ${isExedraStory ? 'magi-exedra-ui-scope' : ''} magi-reader-theme-${theme} flex h-screen h-[100dvh] overflow-hidden ${THEME_STYLES[theme]}`}>",
    )

    replace_once(
        READER_FONTS,
        "    description: '正文使用腾祥嘉丽大圆，标题与角色名使用腾祥智黑。',",
        "    description: '正文使用腾祥嘉丽大圆；标题、角色名与站点 UI 使用腾祥智黑。',",
    )
    replace_once(
        EXEDRA_FONTS,
        "      'Exedra 简体中文正文；生僻字继续使用 Resource Han Rounded CN / Noto Sans SC。',",
        "      'Exedra 全部 UI 与简体中文正文；日文剧情仍使用独立日文字体。',",
    )
    replace_once(
        EXEDRA_SETTINGS,
        "        默认不请求、不启用这些字体。点击后才下载，并且只影响 Exedra\n        对应语言；魔法纪录与另一侧对照语言保持原样。",
        "        默认不请求、不启用这些字体。猫啃网糖圆体覆盖 Exedra 全部 UI 与简体中文正文；\n        日文剧情仍使用独立日文字体，魔法纪录页面保持原样。",
    )

    css = read(REFINEMENTS)
    if "Reader UI V30 — global game-font scope" in css:
        raise RuntimeError("V30 CSS already exists")
    write(REFINEMENTS, css + CSS_APPEND)

    patch_cloudflare_test()
    patch_proofreading_test()
    patch_main_only_workflows()

    delete_required(TEST_DEPLOY_WORKFLOW)
    delete_required(REPAIR_WORKFLOW)
    delete_required(VOICE_PATCH_WORKFLOW)
    write(RETIRE_WORKFLOW, RETIRE_WORKFLOW_CONTENT)
    if FONT_TEST.exists():
        raise RuntimeError(f"test already exists: {FONT_TEST.relative_to(ROOT)}")
    write(FONT_TEST, FONT_TEST_CONTENT)

    assert_main_only_policy()
    print("MAIN_ONLY_V30_FONT_SCOPE_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
