#!/usr/bin/env python3
"""Patch EXEDRA-TEST deployment for deploy-time same-origin search chunks."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / ".github/workflows/deploy-exedra-proofreading-test.yml"
MARKER = "# TW_SIMPLIFIED_SEARCH_ATOMIC_DEPLOY_V4"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"部署工作流补丁锚点异常：{label}: {count}")
    return text.replace(old, new, 1)


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if MARKER in text:
        print("TW_SIMPLIFIED_SEARCH_DEPLOY_ALREADY_PATCHED")
        return 0
    if "branches: [EXEDRA-TEST]" not in text:
        raise RuntimeError("部署工作流不再监听 EXEDRA-TEST，拒绝继续")
    if "python tools/apply_tw_official_metadata.py" not in text:
        raise RuntimeError("部署工作流缺少台服官方 metadata 生成步骤")

    search_pattern = (
        r"      - name: Generate matching split search manifests\n"
        r".*?(?=      - name: Build Cloudflare Worker output)"
    )
    search_replacement = """      - name: Rebuild and materialize certified split-search chunks
        shell: bash
        run: |
          set -euo pipefail
          python tools/patch_search_chunk_runtime.py
          for scope in magireco exedra; do
            git show "$GITHUB_SHA:website/public/search_index_manifest.$scope.json" \
              > "$RUNNER_TEMP/committed-search-index-manifest.$scope.json"
          done

          python tools/build_split_search_indexes.py
          python tools/build_split_search_indexes.py --validate-only
          for scope in magireco exedra; do
            cmp \
              "$RUNNER_TEMP/committed-search-index-manifest.$scope.json" \
              "website/public/search_index_manifest.$scope.json"
          done
          python tools/search_chunk_delivery.py materialize
          python tools/search_chunk_delivery.py verify-tree --root website/public

"""
    text, count = re.subn(
        search_pattern,
        search_replacement,
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("无法替换 split-search 部署步骤")

    smoke_anchor = "      - name: Smoke-test public site and dynamic proofreading state\n"
    chunk_smoke = """      - name: Smoke-test deployed split-search chunks
        env:
          SITE_URL: https://${{ env.TEST_WORKER_HOSTNAME }}
        shell: bash
        run: |
          set -euo pipefail
          python tools/search_chunk_delivery.py verify-http --base-url "$SITE_URL"

"""
    text = replace_once(text, smoke_anchor, chunk_smoke + smoke_anchor, "远端搜索分块烟雾测试")

    smoke_old = "if min(map(len, (home, submissions, machine_review))) < 500:"
    smoke_new = "if len(home) < 500 or len(submissions) < 160 or len(machine_review) < 160:"
    if smoke_old in text:
        text = replace_once(text, smoke_old, smoke_new, "烟雾测试长度")
    elif smoke_new not in text:
        raise RuntimeError("找不到烟雾测试长度门禁")

    provenance_old = "              'exedra_wiki_human',\n"
    provenance_new = (
        "              'exedra_wiki_human',\n"
        "              'exedra_wiki_voice_human',\n"
    )
    if provenance_new not in text:
        text = replace_once(text, provenance_old, provenance_new, "可信 Wiki voice provenance")

    text = text.rstrip() + "\n\n" + MARKER + "\n"
    PATH.write_text(text, encoding="utf-8")
    print("TW_SIMPLIFIED_SEARCH_DEPLOY_PATCHED branch=EXEDRA-TEST delivery=same-origin-chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
