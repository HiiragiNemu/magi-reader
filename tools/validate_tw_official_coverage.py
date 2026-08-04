#!/usr/bin/env python3
"""Verify every supplied TW Scenario appears in committed official provenance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"


def normalized(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).as_posix().strip("/").casefold()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-root", type=Path, required=True)
    args = parser.parse_args()
    scenario_root = args.scenario_root.resolve(strict=True)
    source = {
        normalized(path.resolve().relative_to(scenario_root).as_posix())
        for path in scenario_root.rglob("*.json")
        if path.is_file() and not path.is_symlink()
    }
    if len(source) != 2780:
        raise RuntimeError(f"台服 Scenario 来源数量异常：{len(source)}")

    used: set[str] = set()
    provenance_files = 0
    for path in CN_ROOT.rglob("*_cn.provenance.json"):
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict) or value.get("provenance") != "official_tw_human":
            continue
        provenance_files += 1
        rows = value.get("sourceJson")
        if not isinstance(rows, list):
            raise RuntimeError(f"台服 provenance 缺少 sourceJson：{path}")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("twPath"), str):
                raise RuntimeError(f"台服 provenance 来源记录无效：{path}")
            key = normalized(row["twPath"])
            if key not in source:
                raise RuntimeError(f"provenance 指向来源目录外文件：{row['twPath']}")
            used.add(key)

    missing = sorted(source - used)
    if missing:
        raise RuntimeError(
            f"仍有 {len(missing)} 个台服 Scenario 未注入；示例：{missing[:10]}"
        )
    print(
        f"TW_OFFICIAL_COVERAGE_OK source_files={len(source)} "
        f"used_files={len(used)} provenance_groups={provenance_files}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
