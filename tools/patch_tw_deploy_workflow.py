#!/usr/bin/env python3
"""Patch EXEDRA-TEST deployment to require the committed split-search R2 release."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / ".github/workflows/deploy-exedra-proofreading-test.yml"
MARKER = "# TW_SIMPLIFIED_SEARCH_ATOMIC_DEPLOY_V2"


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
    search_replacement = """      - name: Rebuild and certify committed split search release
        shell: bash
        run: |
          set -euo pipefail
          search_public_base='https://pub-23cae552ecf24722bf572b29fa8dd03f.r2.dev'

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

            read -r object_key expected_sha expected_bytes <<< "$(
              python3 - "$scope" <<'PY'
          import json, sys
          from pathlib import Path
          scope = sys.argv[1]
          value = json.loads(
              Path(f'website/public/search_index_manifest.{scope}.json')
              .read_text(encoding='utf-8')
          )
          print(value['object_key'], value['sha256'], value['bytes'])
          PY
            )"

            remote="$RUNNER_TEMP/search-r2-$scope.json"
            curl --fail --location --silent --show-error \
              --retry 4 --retry-all-errors --connect-timeout 15 --max-time 300 \
              -o "$remote" \
              "$search_public_base/$object_key?deploy_verify=${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-$scope"
            actual_bytes="$(wc -c < "$remote" | tr -d ' ')"
            actual_sha="$(sha256sum "$remote" | awk '{print $1}')"
            if [ "$actual_bytes" != "$expected_bytes" ] || [ "$actual_sha" != "$expected_sha" ]; then
              echo "::error::Published R2 search object mismatch for $scope: bytes=$actual_bytes/$expected_bytes sha=$actual_sha/$expected_sha"
              exit 1
            fi
            echo "SEARCH_R2_DEPLOY_INPUT_OK scope=$scope bytes=$actual_bytes sha256=$actual_sha object=$object_key"
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
        raise RuntimeError("无法替换 split-search 部署步骤")

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
    print("TW_SIMPLIFIED_SEARCH_DEPLOY_PATCHED branch=EXEDRA-TEST")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
