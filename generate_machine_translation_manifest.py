#!/usr/bin/env python3
"""Generate the immutable machine-translation proofreading baseline.

A story is classified as machine translated when its deployed Magia Record Chinese TXT
was directly changed in the translation branch range, or when one of the JSON source
files referenced by that TXT was added/modified in that range. Runtime human-review
state is stored separately in Cloudflare KV, so this generated manifest remains a
reproducible provenance baseline.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
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
SOURCE_HEADER_RE = re.compile(
    r"\(Source:\s*([^()\r\n]+?\.json)\s*\)",
    re.IGNORECASE,
)
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
    result = identity.replace("\\", "/").lstrip("/")
    for old, new in CANONICAL_RENAMES.items():
        if result == old or result.startswith(f"{old}/"):
            result = f"{new}{result[len(old):]}"
    return result


def changed_translation_sources(
    translation_base: str,
    translation_commit: str,
) -> tuple[set[str], set[str]]:
    output = run_git(
        "-c",
        "core.quotePath=false",
        "diff",
        "--name-status",
        "--find-renames",
        translation_base,
        translation_commit,
        "--",
        SOURCE_PREFIX,
    )
    changed_json: set[str] = set()
    changed_txt: set[str] = set()
    for raw_line in output.splitlines():
        fields = raw_line.split("\t")
        if len(fields) < 2:
            continue
        status = fields[0]
        candidate = fields[-1]
        if status.startswith("D") or not candidate.startswith(SOURCE_PREFIX):
            continue
        relative = canonicalize_identity(candidate[len(SOURCE_PREFIX):])
        lowered = relative.lower()
        if lowered.endswith(".json"):
            changed_json.add(relative)
        elif lowered.endswith(".txt"):
            changed_txt.add(relative[:-4])
    if not changed_json and not changed_txt:
        raise ManifestError("translation range produced no Magia Record source changes")
    return changed_json, changed_txt


def load_story_index(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ManifestError("story_index.json must be an array")
    stories = [item for item in value if isinstance(item, dict)]
    if len(stories) != len(value):
        raise ManifestError("story_index.json contains non-object entries")
    return stories


def identity_from_public_cn_path(path_cn: str) -> str:
    if not path_cn.startswith("/data/") or not path_cn.endswith("_cn.txt"):
        raise ManifestError(f"invalid Magia Record CN public path: {path_cn}")
    identity = path_cn[len("/data/") : -len("_cn.txt")]
    if not identity or any(part in {"", ".", ".."} for part in identity.split("/")):
        raise ManifestError(f"unsafe Magia Record CN public path: {path_cn}")
    return canonicalize_identity(identity)


def repository_path_for(identity: str) -> str:
    return f"{SOURCE_PREFIX}{canonicalize_identity(identity)}.txt"


def resolve_source_reference(identity: str, source_reference: str) -> str:
    normalized = source_reference.strip().replace("\\", "/").lstrip("/")
    if not normalized.lower().endswith(".json"):
        raise ManifestError(f"invalid JSON source reference: {source_reference}")
    if "/" in normalized:
        first = normalized.split("/", 1)[0]
        if first in {
            "main_story",
            "event_story",
            "character_story",
            "costume_story",
            "login_story",
            "mirror_story",
            "scene0_main",
            "scene0_sub",
        }:
            return canonicalize_identity(normalized)
        parent = str(PurePosixPath(identity).parent)
        return canonicalize_identity(f"{parent}/{normalized}")
    parent = str(PurePosixPath(identity).parent)
    return canonicalize_identity(f"{parent}/{normalized}")


def referenced_json_sources(identity: str, repository_path: Path) -> set[str]:
    try:
        text = repository_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return set()
    return {
        resolve_source_reference(identity, match.group(1))
        for match in SOURCE_HEADER_RE.finditer(text)
    }


def public_entry(
    story: dict[str, Any],
    *,
    identity: str,
    repository_path: str,
) -> dict[str, Any]:
    return {
        "story_id": str(story.get("id") or ""),
        "category": str(story.get("category") or ""),
        "folder": str(story.get("folder") or ""),
        "title": str(story.get("title") or ""),
        "source_identity": str(story.get("source_identity") or identity),
        "repository_path_cn": repository_path,
        "path_cn": str(story.get("path_cn") or ""),
        "path_jp": str(story.get("path_jp") or ""),
    }


def build_outputs(
    *,
    translation_base: str,
    translation_commit: str,
    stories: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    changed_json, changed_txt = changed_translation_sources(
        translation_base,
        translation_commit,
    )
    source_map: dict[str, dict[str, Any]] = {}
    machine_entries: list[dict[str, Any]] = []
    matched_changed_json: set[str] = set()
    matched_changed_txt: set[str] = set()
    missing_repository_txt_paths: list[str] = []

    for story in stories:
        if story.get("game") == "exedra" or not story.get("path_cn"):
            continue
        path_cn = str(story.get("path_cn") or "")
        identity = identity_from_public_cn_path(path_cn)
        repository_path = repository_path_for(identity)
        entry = public_entry(
            story,
            identity=identity,
            repository_path=repository_path,
        )
        story_id = entry["story_id"]
        if not story_id:
            continue
        existing = source_map.get(story_id)
        if existing is not None and existing != entry:
            raise ManifestError(f"duplicate story id maps to different sources: {story_id}")
        source_map[story_id] = entry

        absolute_txt = ROOT / repository_path
        references = referenced_json_sources(identity, absolute_txt)
        if not absolute_txt.is_file():
            missing_repository_txt_paths.append(repository_path)
        machine_json = sorted(references & changed_json)
        direct_txt_changed = identity in changed_txt
        if not machine_json and not direct_txt_changed:
            continue

        machine_entries.append(
            {
                **entry,
                "machine_source_json_count": len(machine_json),
                "direct_txt_changed": direct_txt_changed,
            }
        )
        matched_changed_json.update(machine_json)
        if direct_txt_changed:
            matched_changed_txt.add(identity)

    machine_entries.sort(
        key=lambda item: (item["category"], item["folder"], item["story_id"])
    )
    unreferenced_json = sorted(changed_json - matched_changed_json)
    unmatched_txt = sorted(changed_txt - matched_changed_txt)
    manifest = {
        "version": 2,
        "definition": "magireco_cn_story_references_translation_branch_json",
        "translation_base": translation_base,
        "translation_commit": translation_commit,
        "changed_json_total": len(changed_json),
        "changed_txt_total": len(changed_txt),
        "referenced_changed_json_total": len(matched_changed_json),
        "total": len(machine_entries),
        "entries": machine_entries,
        "unreferenced_changed_json_count": len(unreferenced_json),
        "unreferenced_changed_json_paths": unreferenced_json,
        "unmatched_changed_txt_identities": unmatched_txt,
        "missing_repository_txt_paths": sorted(set(missing_repository_txt_paths)),
    }
    story_map = {
        "version": 1,
        "total": len(source_map),
        "stories": source_map,
    }
    return manifest, story_map


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--translation-base", required=True)
    parser.add_argument("--translation-commit", required=True)
    parser.add_argument("--story-index", type=Path, default=DEFAULT_STORY_INDEX)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--story-map-output", type=Path, default=DEFAULT_STORY_MAP)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    base = run_git("rev-parse", args.translation_base).strip()
    commit = run_git("rev-parse", args.translation_commit).strip()
    manifest, story_map = build_outputs(
        translation_base=base,
        translation_commit=commit,
        stories=load_story_index(args.story_index.resolve()),
    )
    encoded_manifest = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    encoded_map = json.dumps(story_map, ensure_ascii=False, separators=(",", ":")) + "\n"

    if args.check:
        if args.manifest_output.read_text(encoding="utf-8") != encoded_manifest:
            raise ManifestError("machine translation manifest is stale")
        if args.story_map_output.read_text(encoding="utf-8") != encoded_map:
            raise ManifestError("proofreading story map is stale")
        print(
            "manifest check passed: "
            f"stories={manifest['total']}, "
            f"changed_json={manifest['changed_json_total']}, "
            f"unreferenced_json={manifest['unreferenced_changed_json_count']}"
        )
        return 0

    for path, content in [
        (args.manifest_output, encoded_manifest),
        (args.story_map_output, encoded_map),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(
        "generated machine manifest: "
        f"stories={manifest['total']}, "
        f"changed_json={manifest['changed_json_total']}, "
        f"referenced_json={manifest['referenced_changed_json_total']}, "
        f"unreferenced_json={manifest['unreferenced_changed_json_count']}, "
        f"source_map={story_map['total']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManifestError as exc:
        print(f"error: {exc}")
        raise SystemExit(2) from exc
