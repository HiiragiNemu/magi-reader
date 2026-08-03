#!/usr/bin/env python3
"""Materialize official TW zh-CN data and all feature-branch outputs."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tw_official_import_core import import_corpus  # noqa: E402


def run(*command: str) -> None:
    print("RUN", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--manifest-root", type=Path, required=True)
    args = parser.parse_args()

    scenario_root = args.scenario_root.resolve(strict=True)
    manifest_root = args.manifest_root.resolve(strict=True)
    report = import_corpus(scenario_root, manifest_root)

    run(sys.executable, "tools/patch_tw_deploy_workflow.py")
    run(sys.executable, "generate_story_index.py")
    run(sys.executable, "tools/apply_tw_official_features.py")
    run(
        sys.executable,
        "generate_machine_translation_manifest.py",
        "--translation-base",
        "65f221f2aaa5a9fe161ed32e03e4dfbb93d4746d",
        "--translation-commit",
        "3d463befe7a10d4cb72034378ce2a6f23c377abb",
    )
    run(sys.executable, "tools/build_split_search_indexes.py")

    ignore = ROOT / ".gitignore"
    value = ignore.read_text(encoding="utf-8")
    for line in (
        "artifacts/search-split/search_content.*.json",
        ".tw-official-source/",
    ):
        if line not in value.splitlines():
            value = value.rstrip() + "\n" + line + "\n"
    ignore.write_text(value, encoding="utf-8")

    stats = report.get("stats") if isinstance(report, dict) else None
    if not isinstance(stats, dict) or not stats.get("official_tw_groups"):
        raise RuntimeError("没有生成任何台服官方中文剧情组")
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
