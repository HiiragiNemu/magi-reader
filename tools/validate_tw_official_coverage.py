#!/usr/bin/env python3
"""Verify TW provenance, generated JSON hashes, and classified source coverage."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT)]
import generate_story_index as pipeline  # noqa: E402
from tw_official_import_core import tree_sha256  # noqa: E402

CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
DEFAULT_REPORT = ROOT / "artifacts/exedra_official_tw_import_report.json"


def normalized(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).as_posix().strip("/").casefold()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON 顶层不是对象：{path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--expected-source-count", type=int)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    scenario_root = args.scenario_root.resolve(strict=True)
    scenario_hash, scenario_count, _scenario_bytes = tree_sha256(scenario_root)
    source_paths: dict[str, Path] = {}
    for path in sorted(scenario_root.rglob("*.json")):
        if not path.is_file() or path.is_symlink():
            continue
        key = normalized(path.resolve().relative_to(scenario_root).as_posix())
        if key in source_paths:
            raise RuntimeError(f"台服 Scenario 路径大小写冲突：{key}")
        source_paths[key] = path.resolve(strict=True)
    if scenario_count != len(source_paths):
        raise RuntimeError("台服 Scenario 哈希清单与实际路径数不一致")
    if args.expected_source_count is not None and scenario_count != args.expected_source_count:
        raise RuntimeError(
            f"台服 Scenario 来源数量异常：{scenario_count} != {args.expected_source_count}"
        )

    report = load_object(args.report.resolve(strict=True))
    if report.get("scenarioTreeSha256") != scenario_hash:
        raise RuntimeError("导入报告 Scenario tree hash 已过期")
    stats = report.get("stats")
    if not isinstance(stats, dict) or stats.get("failed_groups"):
        raise RuntimeError("导入报告含结构失败或缺少 stats")

    used: set[str] = set()
    provenance_files = 0
    generated_json_files = 0
    for path in sorted(CN_ROOT.rglob("*_cn.provenance.json")):
        value = load_object(path)
        if value.get("provenance") != "official_tw_human":
            continue
        provenance_files += 1
        group_dir = path.parent
        group_key = path.name.removesuffix("_cn.provenance.json")
        cn_txt = group_dir / f"{group_key}_cn.txt"
        if not cn_txt.is_file():
            raise RuntimeError(f"台服 provenance 缺少中文 TXT：{path}")
        if value.get("cnSha256") != pipeline._sha256_utf8_text_file(cn_txt):
            raise RuntimeError(f"台服 provenance 中文 TXT 哈希失效：{path}")
        rows = value.get("sourceJson")
        if not isinstance(rows, list):
            raise RuntimeError(f"台服 provenance 缺少 sourceJson：{path}")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("twPath"), str):
                raise RuntimeError(f"台服 provenance 来源记录无效：{path}")
            key = normalized(row["twPath"])
            source = source_paths.get(key)
            if source is None:
                raise RuntimeError(f"provenance 指向来源目录外文件：{row['twPath']}")
            if key in used:
                raise RuntimeError(f"同一台服来源被重复注入：{row['twPath']}")
            used.add(key)
            if row.get("twSha256") != pipeline._sha256_file(source):
                raise RuntimeError(f"台服来源哈希已变化：{row['twPath']}")
            output_json = group_dir / str(row.get("source") or "")
            if not output_json.is_file():
                raise RuntimeError(f"台服 provenance 缺少生成 JSON：{output_json}")
            if row.get("simplifiedJsonSha256") != pipeline._sha256_file(output_json):
                raise RuntimeError(f"台服简体 JSON 哈希失效：{output_json}")
            generated_json_files += 1

    deferred = {
        normalized(value)
        for value in report.get("deferredPartialTwSourceFiles", [])
        if isinstance(value, str)
    }
    tw_only = {
        normalized(value)
        for value in report.get("twOnlyWithoutJpSourceFiles", [])
        if isinstance(value, str)
    }
    no_text = {
        normalized(value)
        for value in report.get("noTextTwSourceFiles", [])
        if isinstance(value, str)
    }
    unexpected = report.get("unexpectedUnusedTwSourceFiles")
    if unexpected != []:
        raise RuntimeError(f"仍有无法归类的台服 Scenario：{unexpected!r}")
    classified_sets = {
        "used": used,
        "deferred": deferred,
        "tw_only": tw_only,
        "no_text": no_text,
    }
    labels = tuple(classified_sets)
    for index, left in enumerate(labels):
        for right in labels[index + 1 :]:
            overlap = classified_sets[left] & classified_sets[right]
            if overlap:
                raise RuntimeError(
                    f"台服来源覆盖分类发生交集：{left}/{right}={sorted(overlap)[:5]}"
                )
    classified = used | deferred | tw_only | no_text
    if classified != set(source_paths):
        missing = sorted(set(source_paths) - classified)
        extra = sorted(classified - set(source_paths))
        raise RuntimeError(f"台服来源分类不完整：missing={missing[:5]} extra={extra[:5]}")
    expected = {
        "tw_source_files": scenario_count,
        "tw_source_files_used": len(used),
        "tw_source_files_deferred_partial": len(deferred),
        "tw_source_files_tw_only_without_jp": len(tw_only),
        "tw_source_files_no_text": len(no_text),
        "official_tw_no_text_files": len(no_text),
        "tw_source_files_unexpected_unused": 0,
        "official_tw_json_files": generated_json_files,
        "official_tw_groups": provenance_files,
    }
    for field, actual in expected.items():
        if stats.get(field) != actual:
            raise RuntimeError(f"导入报告统计失效：{field}={stats.get(field)} != {actual}")
    print(
        "TW_OFFICIAL_COVERAGE_OK "
        f"source_files={scenario_count} used_files={len(used)} "
        f"deferred_partial={len(deferred)} tw_only_without_jp={len(tw_only)} "
        f"no_text={len(no_text)} "
        f"provenance_groups={provenance_files} generated_json={generated_json_files}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
