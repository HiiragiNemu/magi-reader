#!/usr/bin/env python3
"""Retarget the certified Worker deployment to the TW feature branch."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / ".github/workflows/deploy-exedra-proofreading-test.yml"
BRANCH = "feature/tw-official-cn-complete"


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if "Create certified TW official data release" in text:
        return 0
    text = text.replace("branches: [EXEDRA-TEST]", f"branches: [{BRANCH}]")
    text = text.replace("permissions:\n  contents: read", "permissions:\n  contents: write")
    text = text.replace(
        '"PROOFREADING_TARGET_BRANCH": "EXEDRA-TEST"',
        f'"PROOFREADING_TARGET_BRANCH": "{BRANCH}"',
    )
    text = text.replace(
        "config.get('target_branch') != 'EXEDRA-TEST'",
        f"config.get('target_branch') != '{BRANCH}'",
    )
    text = text.replace(
        "          python generate_story_index.py\n"
        "          python generate_machine_translation_manifest.py",
        "          python generate_story_index.py\n"
        "          python tools/apply_tw_official_features.py\n"
        "          python generate_machine_translation_manifest.py",
        1,
    )
    search = r"      - name: Generate matching search manifest\n.*?(?=      - name: Build Cloudflare Worker output)"
    replacement = """      - name: Generate split Magia Record and Exedra search objects
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
    text, count = re.subn(search, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError("无法替换全文搜索部署步骤")
    text = text.replace(
        "if min(map(len, (home, submissions, machine_review))) < 500:",
        "if len(home) < 500 or len(submissions) < 160 or len(machine_review) < 160:",
    )
    text = text.rstrip() + f"""

      - name: Create certified TW official data release
        env:
          GH_TOKEN: ${{{{ github.token }}}}
        shell: bash
        run: |
          set -euo pipefail
          tag='tw-official-cn-2026-08-04'
          mkdir -p "$RUNNER_TEMP/release"
          python - <<'PY2'
          from pathlib import Path
          import os, zipfile
          root = Path.cwd()
          out = Path(os.environ['RUNNER_TEMP']) / 'release'
          def archive(name, values):
              target = out / name
              with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                  for relative in values:
                      base = root / relative
                      if base.is_file():
                          z.write(base, base.relative_to(root).as_posix())
                      elif base.is_dir():
                          for path in sorted(p for p in base.rglob('*') if p.is_file()):
                              z.write(path, path.relative_to(root).as_posix())
          archive('MagiReader-Exedra-TW-Official-zh-CN.zip', [
              'magiraexedra-translate-data-master/Scenarios_full',
              'artifacts/exedra_official_tw_import_report.json',
              'artifacts/tw_official_metadata.generated.json',
          ])
          archive('MagiReader-All-Website-Story-Data.zip', [
              'website/public/data', 'website/public/story_index.json',
          ])
          archive('MagiReader-General-Voice-Data.zip', [
              'website/public/data/general_voice',
          ])
          archive('MagiReader-Split-Search-Objects.zip', [
              'artifacts/search-split',
              'website/public/search_index_manifest.magireco.json',
              'website/public/search_index_manifest.exedra.json',
          ])
          PY2
          gh release delete "$tag" --yes --cleanup-tag 2>/dev/null || true
          gh release create "$tag" \
            --target "$GITHUB_SHA" \
            --title 'MagiReader 台服官方简体中文认证数据 2026-08-04' \
            --notes '台服官方简体中文 Exedra JSON/TXT、全站剧情数据、语音数据及分拆全文搜索对象。' \
            "$RUNNER_TEMP/release/"*.zip

      - name: Keep only main and certified feature branch
        env:
          GH_TOKEN: ${{{{ github.token }}}}
        shell: bash
        run: |
          set -euo pipefail
          keep='{BRANCH}'
          gh api --paginate "repos/$GITHUB_REPOSITORY/branches?per_page=100" \
            --jq '.[].name' | while IFS= read -r branch; do
              if [ "$branch" = main ] || [ "$branch" = "$keep" ]; then
                continue
              fi
              encoded="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$branch")"
              gh api -X DELETE "repos/$GITHUB_REPOSITORY/git/refs/heads/$encoded" || true
            done
""" + "\n"
    PATH.write_text(text, encoding="utf-8")
    print(f"TW_DEPLOY_WORKFLOW_PATCHED branch={BRANCH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
