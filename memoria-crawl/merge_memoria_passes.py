#!/usr/bin/env python3
"""Merge repeated Memoria article crawl passes without losing catalog members."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":")) + "\n",
        encoding="utf-8",
    )


def score(item: dict[str, Any]) -> tuple[int, int, int, int, int]:
    stats = sum(item.get(key) is not None for key in ("hpMin", "hpMax", "atkMin", "atkMax", "defMin", "defMax"))
    text = sum(bool(item.get(key)) for key in (
        "nameZh", "artist", "type", "skillName", "skillNameMax", "effect", "effectMax",
        "effectDetail", "effectDetailMax", "descZh", "descJa", "descriptionHtml",
    ))
    return (
        1 if item.get("articleStatus") == 200 else 0,
        stats,
        text,
        1 if item.get("number") is not None else 0,
        len(str(item.get("rawTableHtml") or "")),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    best: dict[str, dict[str, Any]] = {}
    manifests: list[dict[str, Any]] = []
    pass_failures: list[dict[str, Any]] = []

    for source in args.input:
        root = source.resolve()
        manifest = load(root / "manifest.json")
        records = load(root / "memoria.json")
        failures = load(root / "failures.json")
        manifests.append(manifest)
        pass_failures.extend({"pass": str(root), **item} for item in failures)
        for item in records:
            key = str(item["articleTitle"])
            previous = best.get(key)
            if previous is None or score(item) > score(previous):
                best[key] = item

    records = list(best.values())
    records.sort(key=lambda item: ((item.get("number") is None), item.get("number") or 10**9, str(item.get("nameJa") or item.get("key")).casefold()))

    final_failures = [
        {
            "stage": "article",
            "title": item.get("articleTitle"),
            "url": item.get("articleUrl"),
            "status": item.get("articleStatus"),
            "error": item.get("articleError") or "all passes lacked a parsed data table",
        }
        for item in records
        if item.get("articleStatus") != 200 or not all(item.get(key) is not None for key in ("hpMin", "hpMax", "atkMin", "atkMax", "defMin", "defMax"))
    ]

    number_groups: dict[str, list[str]] = {}
    for item in records:
        if item.get("number") is not None:
            number_groups.setdefault(str(item["number"]), []).append(str(item["key"]))

    manifest = {
        "schemaVersion": 3,
        "source": "merged-ordinary-article-passes",
        "passes": len(manifests),
        "snapshotArticleMembers": max((item.get("snapshotArticleMembers", 0) for item in manifests), default=0),
        "selectedArticlePages": len(records),
        "records": len(records),
        "uniqueNumbers": len(number_groups),
        "withImage": sum(bool(item.get("imageUrl")) for item in records),
        "withChineseName": sum(bool(item.get("nameZh")) for item in records),
        "withChineseDescription": sum(bool(item.get("descZh")) for item in records),
        "withJapaneseDescription": sum(bool(item.get("descJa")) for item in records),
        "withStats": sum(all(item.get(key) is not None for key in ("hpMin", "hpMax", "atkMin", "atkMax", "defMin", "defMax")) for item in records),
        "remainingFailures": len(final_failures),
        "passFailureEvents": len(pass_failures),
        "passManifests": manifests,
    }

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    dump(output / "memoria.json", records)
    dump(output / "number-groups.json", number_groups)
    dump(output / "manifest.json", manifest, pretty=True)
    dump(output / "failures.json", final_failures, pretty=True)
    dump(output / "pass-failures.json", pass_failures, pretty=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
