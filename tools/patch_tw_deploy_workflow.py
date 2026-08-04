#!/usr/bin/env python3
"""Patch the existing EXEDRA-TEST deployment for TW data and split search."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / ".github/workflows/deploy-exedra-proofreading-test.yml"
MARKER = "# TW_OFFICIAL_EXEDRA_TEST_DEPLOY_V1"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"部署工作流补丁锚点异常：{label}: {count}")
    return text.replace(old, new, 1)


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if MARKER in text:
        print("TW_DEPLOY_WORKFLOW_ALREADY_PATCHED")
        return 0
    if "branches: [EXEDRA-TEST]" not in text:
        raise RuntimeError("部署工作流不再监听 EXEDRA-TEST，拒绝继续")

    text = replace_once(
        text,
        "          python generate_story_index.py\n"
        "          python generate_machine_translation_manifest.py",
        "          python generate_story_index.py\n"
        "          python tools/apply_tw_official_features.py\n"
        "          python generate_machine_translation_manifest.py",
        "数据生成",
    )

    search_pattern = (
        r"      - name: Generate matching search manifest\n"
        r".*?(?=      - name: Build Cloudflare Worker output)"
    )
    search_replacement = """      - name: Generate split Magia Record and Exedra search objects
        shell: bash
        run: |
          set -euo pipefail
          python tools/build_split_search_indexes.py
          python tools/build_split_search_indexes.py --validate-only

      - name: Discover split-search R2 bucket
        id: search_r2
        timeout-minutes: 3
        working-directory: website
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: >-
          node scripts/discover-cloudflare-r2-bucket.mjs
          --target-domain "pub-23cae552ecf24722bf572b29fa8dd03f.r2.dev"

      - name: Upload split search objects to R2
        working-directory: website
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          SEARCH_BUCKET: ${{ steps.search_r2.outputs.bucket_name }}
        shell: bash
        run: |
          set -euo pipefail
          test -n "$SEARCH_BUCKET"
          for scope in magireco exedra; do
            object_key="$(python3 - "$scope" <<'PY2'
          import json, sys
          from pathlib import Path
          scope = sys.argv[1]
          value = json.loads(
              Path(f'public/search_index_manifest.{scope}.json').read_text(
                  encoding='utf-8'
              )
          )
          print(value['object_key'])
          PY2
            )"
            npx wrangler r2 object put \
              "$SEARCH_BUCKET/$object_key" \
              --file "../artifacts/search-split/search_content.$scope.json" \
              --remote
          done

"""
    text, count = re.subn(
        search_pattern,
        search_replacement,
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("无法替换全文搜索部署步骤")

    smoke_old = "if min(map(len, (home, submissions, machine_review))) < 500:"
    smoke_new = "if len(home) < 500 or len(submissions) < 160 or len(machine_review) < 160:"
    if smoke_old in text:
        text = replace_once(text, smoke_old, smoke_new, "烟雾测试长度")

    text = text.rstrip() + "\n\n" + MARKER + "\n"
    PATH.write_text(text, encoding="utf-8")
    print("TW_DEPLOY_WORKFLOW_PATCHED branch=EXEDRA-TEST")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
