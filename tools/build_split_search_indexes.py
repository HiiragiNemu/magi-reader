#!/usr/bin/env python3
"""Build independent Magia Record and Exedra full-text search objects.

The manifests stay in website/public. Large payloads are written under artifacts
for R2 upload and release packaging, so browsers never download the other game's
index.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_search_index_v6 as base  # noqa: E402
PUBLIC = ROOT / "website/public"
ARTIFACTS = ROOT / "artifacts/search-split"
SCOPES = ("magireco", "exedra")


def is_exedra(story: dict[str, Any]) -> bool:
    category = str(story.get("category") or "")
    return category.startswith("exedra_") or story.get("game") == "exedra"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-dir", type=Path, default=PUBLIC)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    public_dir = args.public_dir.resolve()
    output_dir = args.output_dir.resolve()
    story_index_path = public_dir / "story_index.json"
    story_index_bytes = story_index_path.read_bytes()
    stories = json.loads(story_index_bytes.decode("utf-8-sig"))
    if not isinstance(stories, list) or not stories:
        raise base.PipelineError("story_index 顶层必须是非空数组")

    titles = base.load_titles(base.DEFAULT_TITLES_PATH)
    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"version": 1, "scopes": {}}

    for scope in SCOPES:
        selected = [
            story
            for story in stories
            if isinstance(story, dict)
            and (is_exedra(story) if scope == "exedra" else not is_exedra(story))
        ]
        if not selected:
            raise base.PipelineError(f"搜索范围为空：{scope}")
        base.validate_catalog(selected, public_dir)
        stats: Counter[str] = Counter()
        entries = base.build_search_entries(
            stories=selected,
            public_dir=public_dir,
            titles=titles,
            stats=stats,
        )
        base.validate_search_entries(entries, stories=selected)
        payload_path = output_dir / f"search_content.{scope}.json"
        manifest_path = public_dir / f"search_index_manifest.{scope}.json"
        prefix = f"search/{scope}"

        if args.validate_only:
            payload = payload_path.read_bytes()
            existing = json.loads(payload.decode("utf-8-sig"))
            base.validate_search_matches_expected(existing, entries, stories=selected)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            base.validate_search_manifest(
                manifest,
                payload=payload,
                entry_count=len(existing),
                story_index_bytes=story_index_bytes,
                object_key_prefix=prefix,
            )
        else:
            manifest = base.write_search_artifacts_atomic(
                entries,
                output_path=payload_path,
                manifest_path=manifest_path,
                story_index_bytes=story_index_bytes,
                object_key_prefix=prefix,
            )

        report["scopes"][scope] = {
            "stories": len(selected),
            "entries": len(entries),
            "bytes": int(manifest["bytes"]),
            "sha256": str(manifest["sha256"]),
            "object_key": str(manifest["object_key"]),
            "manifest": manifest_path.relative_to(ROOT).as_posix(),
            "payload": payload_path.relative_to(ROOT).as_posix(),
        }
        print(
            f"SEARCH_SCOPE_OK scope={scope} stories={len(selected)} "
            f"entries={len(entries)} bytes={manifest['bytes']} "
            f"object={manifest['object_key']}"
        )

    report_path = output_dir / "split_search_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
