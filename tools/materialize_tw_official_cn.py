#!/usr/bin/env python3
"""Materialize official TW data into playable Simplified-Chinese JSON/TXT.

The command is deterministic data plumbing: it accepts either explicit local
directories or an extracted source bundle, validates all supplied files,
atomically updates the Exedra Chinese corpus, and rebuilds derived catalogues.
It never downloads, commits, pushes, or deploys anything.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tw_official_import_core import (  # noqa: E402
    SourceBundle,
    import_corpus,
    resolve_source_bundle,
)


def run(*command: str) -> None:
    print("RUN", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-root", type=Path)
    parser.add_argument("--manifest-root", type=Path)
    parser.add_argument(
        "--source-bundle-root",
        type=Path,
        help="Extracted package root containing Resources/Scenarios and Manifests",
    )
    parser.add_argument(
        "--source-provider",
        choices=("local-tree", "wiki-sp-extracted", "exedra-wiki-sp"),
        default="local-tree",
        help="local-tree is for diagnostics; exedra-wiki-sp requires the v1 contract",
    )
    parser.add_argument(
        "--handoff-manifest",
        type=Path,
        help="Optional explicit exedra-tw-sp-handoff.v1.json path",
    )
    parser.add_argument("--expected-source-count", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-derived",
        action="store_true",
        help="Only validate/materialize corpus; do not rebuild public catalogues/search",
    )
    args = parser.parse_args()

    if args.source_bundle_root:
        if args.scenario_root or args.manifest_root:
            parser.error("--source-bundle-root 不能与显式 Scenario/Manifest 同时使用")
        bundle = resolve_source_bundle(
            args.source_bundle_root,
            args.source_provider,
            args.handoff_manifest,
        )
    else:
        if not args.scenario_root or not args.manifest_root:
            parser.error("必须提供 --source-bundle-root 或同时提供 Scenario/Manifest")
        if args.handoff_manifest:
            parser.error("--handoff-manifest 只能与 --source-bundle-root 一起使用")
        if args.source_provider != "local-tree":
            parser.error("SP provider 必须通过 --source-bundle-root 读取完整合同")
        scenario_root = args.scenario_root.resolve(strict=True)
        manifest_root = args.manifest_root.resolve(strict=True)
        common = Path(os.path.commonpath((scenario_root, manifest_root)))
        if common.parent == common:
            parser.error("显式 Scenario/Manifest 的公共父目录不能是磁盘根目录")
        bundle = SourceBundle(
            provider=args.source_provider,
            root=common,
            scenario_root=scenario_root,
            manifest_root=manifest_root,
        )

    print(
        json.dumps(
            {
                "provider": bundle.provider,
                "scenarioRoot": str(bundle.scenario_root),
                "manifestRoot": str(bundle.manifest_root),
                "dryRun": args.dry_run,
            },
            ensure_ascii=False,
        )
    )
    report = import_corpus(
        bundle.scenario_root,
        bundle.manifest_root,
        provider=bundle.provider,
        expected_source_files=args.expected_source_count,
        dry_run=args.dry_run,
        source_contract=bundle.contract,
    )
    if args.dry_run or args.skip_derived:
        print(json.dumps(report.get("stats", {}), ensure_ascii=False))
        return 0

    run(
        sys.executable,
        "tools/validate_tw_official_coverage.py",
        "--scenario-root",
        str(bundle.scenario_root),
        *(
            ("--expected-source-count", str(args.expected_source_count))
            if args.expected_source_count is not None
            else ()
        ),
    )

    run(sys.executable, "generate_story_index.py")
    run(sys.executable, "tools/apply_tw_official_metadata.py")
    run(
        sys.executable,
        "generate_machine_translation_manifest.py",
        "--translation-base",
        "65f221f2aaa5a9fe161ed32e03e4dfbb93d4746d",
        "--translation-commit",
        "3d463befe7a10d4cb72034378ce2a6f23c377abb",
    )
    run(sys.executable, "tools/build_split_search_indexes.py")

    stats = report.get("stats") if isinstance(report, dict) else None
    if not isinstance(stats, dict) or not stats.get("official_tw_groups"):
        raise RuntimeError("没有生成任何台服官方中文剧情组")
    if stats.get("failed_groups"):
        raise RuntimeError(f"台服导入仍有结构失败：{stats}")
    if stats.get("tw_source_files_unexpected_unused"):
        raise RuntimeError(f"台服来源存在无法归类文件：{stats}")
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
