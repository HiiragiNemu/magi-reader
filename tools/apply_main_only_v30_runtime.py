#!/usr/bin/env python3
"""Remove remaining EXEDRA-TEST runtime defaults and direct-test tooling."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUBMIT_ROUTE = ROOT / "website/app/api/submit/route.ts"
CONFIG_ROUTE = ROOT / "website/app/api/proofreading/config/route.ts"
GITHUB_PROOFREADING = ROOT / "website/lib/github-proofreading.ts"
VERIFY_OUTPUT = ROOT / "website/scripts/verify-cloudflare-output.mjs"
PACKAGE = ROOT / "website/package.json"
DIRECT_DEPLOY = ROOT / "website/scripts/deploy-direct.mjs"
DIRECT_UTILS = ROOT / "website/scripts/cloudflare-direct-deploy-utils.mjs"
DIRECT_UTILS_TEST = ROOT / "website/scripts/cloudflare-direct-deploy-utils.test.mjs"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, content: str) -> None:
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
        raise RuntimeError(f"direct-test file missing: {path.relative_to(ROOT)}")
    path.unlink()


def main() -> int:
    replace_once(
        SUBMIT_ROUTE,
        "      target_branch: env.PROOFREADING_TARGET_BRANCH?.trim() || 'EXEDRA-TEST',",
        "      target_branch: env.PROOFREADING_TARGET_BRANCH?.trim() || 'main',",
    )
    replace_once(
        CONFIG_ROUTE,
        "      target_branch: env.PROOFREADING_TARGET_BRANCH?.trim() || 'EXEDRA-TEST',",
        "      target_branch: env.PROOFREADING_TARGET_BRANCH?.trim() || 'main',",
    )
    replace_once(
        GITHUB_PROOFREADING,
        "  const targetBranch = record.target_branch || 'EXEDRA-TEST';\n  if (targetBranch !== 'EXEDRA-TEST') {\n    throw new ProofreadingPullRequestError('投稿目标分支不是 EXEDRA-TEST', 'invalid');\n  }",
        "  const targetBranch = record.target_branch || 'main';\n  if (targetBranch !== 'main') {\n    throw new ProofreadingPullRequestError('投稿目标分支不是 main', 'invalid');\n  }",
    )
    replace_once(
        VERIFY_OUTPUT,
        "  // fixtures and non-chunk deployments. The EXEDRA-TEST release pipeline calls\n",
        "  // fixtures and non-chunk deployments. The main production pipeline calls\n",
    )

    package = json.loads(read(PACKAGE))
    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        raise RuntimeError("website/package.json scripts is not an object")
    removed: list[str] = []
    for key in ("predeploy:test:direct", "deploy:test:direct"):
        if key not in scripts:
            raise RuntimeError(f"package script already missing: {key}")
        removed.append(key)
        del scripts[key]
    PACKAGE.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    for path in (DIRECT_DEPLOY, DIRECT_UTILS, DIRECT_UTILS_TEST):
        delete_required(path)

    unexpected: list[str] = []
    for root in (
        ROOT / "website/app",
        ROOT / "website/lib",
        ROOT / "website/scripts",
    ):
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".ts", ".tsx", ".js", ".mjs"}:
                if "EXEDRA-TEST" in read(path):
                    unexpected.append(str(path.relative_to(ROOT)))
    if unexpected:
        raise RuntimeError(
            "runtime files still reference EXEDRA-TEST: " + ", ".join(unexpected)
        )

    print(
        "MAIN_ONLY_V30_RUNTIME_PATCHED "
        f"removedScripts={','.join(removed)} removedDirectFiles=3"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
