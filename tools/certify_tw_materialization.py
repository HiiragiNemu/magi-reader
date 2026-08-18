#!/usr/bin/env python3
"""Certify a TW materialization without pinning historical corpus counts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXPECTED_PROVENANCE = {
    "provider": "exedra-wiki-sp",
    "locale": "zh-Hant-TW",
    "authority": "official-tw-client",
    "originalTextUnmodified": True,
    "textTransformation": "reader-tw2sp",
}


class CertificationError(RuntimeError):
    pass


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise CertificationError(f"expected JSON object: {path}")
    return value


def certify(report_path: Path, story_index_path: Path) -> dict[str, int]:
    report = load_object(report_path)
    if report.get("status") != "materialized":
        raise CertificationError("TW import report is not materialized")
    if report.get("sourceProvider") != "exedra-wiki-sp":
        raise CertificationError("TW import report has the wrong provider")

    contract = report.get("sourceContract")
    if not isinstance(contract, dict) or contract.get("schemaVersion") != 1:
        raise CertificationError("TW import report lacks a v1 source contract")
    if contract.get("provenance") != EXPECTED_PROVENANCE:
        raise CertificationError("TW source provenance differs from the v1 contract")
    if contract.get("complete") is not True:
        raise CertificationError("TW source contract is not complete")
    if contract.get("diagnostics") != {
        "missing": 0,
        "failure": 0,
        "parseFailure": 0,
    }:
        raise CertificationError("TW source contract diagnostics are not all zero")
    revisions = contract.get("sourceRevisions")
    if (
        not isinstance(revisions, dict)
        or set(revisions) != {"sp", "scenarios", "manifests"}
        or any(not isinstance(value, str) or not value for value in revisions.values())
    ):
        raise CertificationError("TW source contract revisions are incomplete")

    stats = report.get("stats")
    inventory = report.get("sourceInventory")
    if not isinstance(stats, dict) or not isinstance(inventory, dict):
        raise CertificationError("TW report lacks stats or sourceInventory")

    required = (
        "official_tw_groups",
        "official_tw_json_files",
        "official_tw_text_events",
        "tw_source_files",
        "tw_source_files_used",
        "tw_source_files_unused",
        "tw_source_files_deferred_partial",
        "tw_source_files_tw_only_without_jp",
        "tw_source_files_no_text",
        "tw_source_files_unexpected_unused",
    )
    values: dict[str, int] = {}
    for field in required:
        value = stats.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise CertificationError(f"invalid dynamic statistic: {field}={value!r}")
        values[field] = value

    if values["official_tw_groups"] == 0 or values["official_tw_json_files"] == 0:
        raise CertificationError("TW materialization did not produce official content")
    if values["tw_source_files_unexpected_unused"] != 0:
        raise CertificationError("TW source contains unexpected unused files")
    if values["tw_source_files"] != inventory.get("scenarioFiles"):
        raise CertificationError("TW source count differs from sourceInventory")
    if values["tw_source_files_used"] + values["tw_source_files_unused"] != values["tw_source_files"]:
        raise CertificationError("TW used/unused partition is incomplete")
    if (
        values["tw_source_files_deferred_partial"]
        + values["tw_source_files_tw_only_without_jp"]
        + values["tw_source_files_no_text"]
        != values["tw_source_files_unused"]
    ):
        raise CertificationError("TW unused-file reasons do not partition unused files")

    stories = json.loads(story_index_path.read_text(encoding="utf-8-sig"))
    if not isinstance(stories, list):
        raise CertificationError("story index must be a JSON array")
    official = [
        item for item in stories
        if isinstance(item, dict) and item.get("official_tw") is True
    ]
    if len(official) != values["official_tw_groups"]:
        raise CertificationError("official TW story count differs from import report")
    if not any(item.get("official_tw_chapter_title") for item in official):
        raise CertificationError("official TW chapter titles were not applied")
    if not any(item.get("official_tw_section_titles") for item in official):
        raise CertificationError("official TW section titles were not applied")
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--story-index", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        stats = certify(args.report, args.story_index)
    except (OSError, json.JSONDecodeError, CertificationError) as exc:
        print(f"TW_MATERIALIZATION_CERTIFICATION_ERROR {exc}")
        return 1
    print(
        "TW_MATERIALIZATION_CERTIFIED "
        f"groups={stats['official_tw_groups']} "
        f"json={stats['official_tw_json_files']} "
        f"events={stats['official_tw_text_events']} "
        f"source_files={stats['tw_source_files']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
