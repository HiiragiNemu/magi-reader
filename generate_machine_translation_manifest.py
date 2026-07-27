#!/usr/bin/env python3
"""Generate the machine-translation review baseline and proofreading source map.

The baseline is defined as Magia Record Chinese TXT source files added or modified by
one translation commit. A reviewed-state overlay is stored at runtime in Cloudflare KV;
therefore this generated file remains an immutable provenance list.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_STORY_INDEX = ROOT / "website" / "public" / "story_index.json"
DEFAULT_MANIFEST = (
    ROOT / "website" / "public" / "data" / "machine_translation_manifest.generated.json"
)
DEFAULT_STORY_MAP = (
    ROOT / "website" / "public" / "data" / "proofreading_story_map.generated.json"
)
SOURCE_PREFIX = "magireco-translate-data-master/Scenarios_full/"
CANONICAL_RENAMES = {
    "event_story/5101 - 常夜之国的叛乱者 ~魔法少女贞德~":
        "event_story/5101 - 常夜之国的叛乱者～魔法少女贞德～",
    "event_story/5175 - Dream Halloween Festa～阿莉娜前辈！做要好孩子的说！～":
        "event_story/5175 - Dream Halloween Festa～阿莉娜前辈！做个好孩子！～",
    "event_story/5216 - 海边的缎带":
        "event_story/5216 - 海岸边的缎带",
}


class ManifestError(RuntimeError):
    pass


def run_git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise ManifestError(completed.stderr.strip() or "git command failed")
    return completed.stdout


def canonicalize_identity(identity: str) -> str:
    result = identity
    for old, new in CANONICAL_RENAMES.items():
        if result == old or result.startswith(f"{old}/"):
            result = f"{new}{result[len(old):]}"
    return result


def changed_txt_identities(translation_commit: str) -> set[str]:
    output = run_git(
        "diff",
        "--name-status",
        "--find-renames",
        f"{translation_commit}^",
        translation_commit,
        "--",
        f"{SOURCE_PREFIX}*.txt",
        f"{SOURCE_PREFIX}**/*.txt",
    )
    identities: set[str] = set()
    for raw_line in output.splitlines():
        fields = raw_line.split("\t")
        if not fields:
            continue
        status = fields[0]
        candidate = fields[-1]
        if status.startswith("D") or not candidate.startswith(SOURCE_PREFIX):
            continue
        if not candidate.lower().endswith(".txt"):
            continue
        relative = candidate[len(SOURCE_PREFIX): -4]
        identities.add(canonicalize_identity(relative))
    if not identities:
        raise ManifestError("translation commit produced no Magia Record TXT changes")
    return identities


def load_story_index(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ManifestError("story_index.json must be an array")
    stories = [item for item in value if isinstance(item, dict)]
    if len(stories) != len(value):
        raise ManifestError("story_index.json contains non-object entries")
    return stories


def repository_path_for(identity: str) -> str:
    return f"{SOURCE_PREFIX}{identity}.txt"


def public_entry(story: dict[str, Any]) -> dict[str, Any]:
    identity = str(story.get("source_identity") or "")
    return {
        "story_id": str(story.get("id") or ""),
        "category": str(story.get("category") or ""),
        "folder": str(story.get("folder") or ""),
        "title": str(story.get("title") or ""),
        "source_identity": identity,
        "repository_path_cn": repository_path_for(identity),
        "path_cn": str(story.get("path_cn") or ""),
        "path_jp": str(story.get("path_jp") or ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--translation-commit", required=True)
    parser.add_argument("--story-index", type=Path, default=DEFAULT_STORY_INDEX)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--story-map-output", type=Path, default=DEFAULT_STORY_MAP)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    commit = run_git("rev-parse", args.translation_commit).strip()
    identities = changed_txt_identities(commit)
    stories = load_story_index(args.story_index.resolve())

    source_map: dict[str, dict[str, Any]] = {}
    machine_entries: list[dict[str, Any]] = []
    matched_identities: set[str] = set()
    for story in stories:
        if story.get("game") == "exedra" or not story.get("path_cn"):
            continue
        entry = public_entry(story)
        story_id = entry["story_id"]
        identity = entry["source_identity"]
        if not story_id or not identity:
            continue
        source_map[story_id] = entry
        if canonicalize_identity(identity) in identities:
            machine_entries.append(entry)
            matched_identities.add(canonicalize_identity(identity))

    unmatched = sorted(identities - matched_identities)
    machine_entries.sort(key=lambda item: (item["category"], item["folder"], item["story_id"]))
    manifest = {
        "version": 1,
        "definition": "magireco_cn_txt_changed_by_translation_commit",
        "translation_commit": commit,
        "total": len(machine_entries),
        "entries": machine_entries,
        "unmatched_source_identities": unmatched,
    }
    story_map = {
        "version": 1,
        "total": len(source_map),
        "stories": source_map,
    }

    encoded_manifest = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    encoded_map = json.dumps(story_map, ensure_ascii=False, separators=(",", ":")) + "\n"
    if args.check:
        if args.manifest_output.read_text(encoding="utf-8") != encoded_manifest:
            raise ManifestError("machine translation manifest is stale")
        if args.story_map_output.read_text(encoding="utf-8") != encoded_map:
            raise ManifestError("proofreading story map is stale")
        print(f"manifest check passed: {len(machine_entries)} machine stories")
        return 0

    for path, content in [
        (args.manifest_output, encoded_manifest),
        (args.story_map_output, encoded_map),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(
        f"generated machine manifest: stories={len(machine_entries)}, "
        f"source_map={len(source_map)}, unmatched={len(unmatched)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManifestError as exc:
        print(f"error: {exc}")
        raise SystemExit(2) from exc
