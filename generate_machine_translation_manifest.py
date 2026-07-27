#!/usr/bin/env python3
"""Generate the machine-translation review baseline from a trusted main diff.

Trust rule:
- Every Magia Record source file that exists in the trusted baseline must remain byte-for-byte
  identical in the current working tree.
- Every trusted-baseline file must still exist.
- Only Chinese TXT files that are present now but absent from the trusted baseline are machine
  translation candidates.

This deliberately rejects branch-history and release-archive provenance as a classifier. Runtime
human-review state remains stored separately in Cloudflare KV.
"""

from __future__ import annotations

import argparse
import hashlib
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
SOURCE_ROOT = ROOT / SOURCE_PREFIX
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
        ["git", "-c", "core.quotePath=false", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise ManifestError(completed.stderr.strip() or "git command failed")
    return completed.stdout


def git_blob_hash(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def git_tree(ref: str, prefix: str = SOURCE_PREFIX) -> dict[str, str]:
    output = run_git(
        "ls-tree",
        "-r",
        "-z",
        "--format=%(objectname)\t%(path)",
        ref,
        "--",
        prefix,
    )
    result: dict[str, str] = {}
    for record in output.split("\0"):
        if not record:
            continue
        try:
            object_name, path = record.split("\t", 1)
        except ValueError as exc:
            raise ManifestError(f"invalid git ls-tree record: {record!r}") from exc
        result[path] = object_name
    return result


def working_tree(prefix_root: Path = SOURCE_ROOT) -> dict[str, str]:
    if not prefix_root.is_dir():
        raise ManifestError(f"Magia Record source directory is missing: {prefix_root}")
    result: dict[str, str] = {}
    for path in sorted(prefix_root.rglob("*")):
        if not path.is_file():
            continue
        repository_path = path.relative_to(ROOT).as_posix()
        result[repository_path] = git_blob_hash(path.read_bytes())
    return result


def classify_trust_boundary(
    baseline: dict[str, str],
    current: dict[str, str],
) -> tuple[set[str], set[str], set[str]]:
    baseline_paths = set(baseline)
    current_paths = set(current)
    added = current_paths - baseline_paths
    overwritten = {
        path
        for path in baseline_paths & current_paths
        if baseline[path] != current[path]
    }
    deleted = baseline_paths - current_paths
    return added, overwritten, deleted


def canonicalize_identity(identity: str) -> str:
    result = identity.replace("\\", "/").lstrip("/")
    for old, new in CANONICAL_RENAMES.items():
        if result == old or result.startswith(f"{old}/"):
            result = f"{new}{result[len(old):]}"
    return result


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


def relative_source_path(repository_path: str) -> str:
    if not repository_path.startswith(SOURCE_PREFIX):
        raise ManifestError(f"path is outside Magia Record source root: {repository_path}")
    return canonicalize_identity(repository_path[len(SOURCE_PREFIX):])


def build_outputs(
    *,
    trusted_baseline: str,
    source_commit: str,
    stories: list[dict[str, Any]],
    legacy_translation_commit: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline_tree = git_tree(trusted_baseline)
    current_tree = working_tree()
    added, overwritten, deleted = classify_trust_boundary(baseline_tree, current_tree)

    if overwritten:
        sample = "\n".join(sorted(overwritten)[:20])
        raise ManifestError(
            f"trusted main files were overwritten ({len(overwritten)}); restore them first:\n{sample}"
        )
    if deleted:
        sample = "\n".join(sorted(deleted)[:20])
        raise ManifestError(
            f"trusted main files were deleted ({len(deleted)}); restore them first:\n{sample}"
        )

    added_json = {
        relative_source_path(path)
        for path in added
        if path.lower().endswith(".json")
    }
    added_txt_paths = {
        path
        for path in added
        if path.lower().endswith(".txt")
    }

    source_map: dict[str, dict[str, Any]] = {}
    machine_entries: list[dict[str, Any]] = []
    matched_added_json: set[str] = set()
    matched_added_txt_paths: set[str] = set()
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
        if not absolute_txt.is_file():
            missing_repository_txt_paths.append(repository_path)
        if repository_path not in added_txt_paths:
            continue

        references = referenced_json_sources(identity, absolute_txt)
        machine_json = sorted(references & added_json)
        machine_entries.append(
            {
                **entry,
                "provenance": "added_after_trusted_main",
                "machine_source_json_count": len(machine_json),
                "direct_txt_changed": True,
            }
        )
        matched_added_json.update(machine_json)
        matched_added_txt_paths.add(repository_path)

    machine_entries.sort(
        key=lambda item: (item["category"], item["folder"], item["story_id"])
    )
    unreferenced_json = sorted(added_json - matched_added_json)
    unmatched_txt = sorted(added_txt_paths - matched_added_txt_paths)

    manifest: dict[str, Any] = {
        "version": 3,
        "definition": "magireco_cn_txt_absent_from_trusted_main",
        "trusted_baseline": trusted_baseline,
        "source_commit": source_commit,
        "translation_base": trusted_baseline,
        "translation_commit": source_commit,
        "trusted_baseline_file_total": len(baseline_tree),
        "current_file_total": len(current_tree),
        "added_file_total": len(added),
        "changed_json_total": len(added_json),
        "changed_txt_total": len(added_txt_paths),
        "referenced_changed_json_total": len(matched_added_json),
        "protected_human_overwrite_count": 0,
        "protected_human_deletion_count": 0,
        "total": len(machine_entries),
        "entries": machine_entries,
        "unreferenced_changed_json_count": len(unreferenced_json),
        "unreferenced_changed_json_paths": unreferenced_json,
        "unmatched_changed_txt_identities": [
            relative_source_path(path)[:-4] for path in unmatched_txt
        ],
        "missing_repository_txt_paths": sorted(set(missing_repository_txt_paths)),
    }
    if legacy_translation_commit:
        manifest["legacy_translation_commit_not_used_for_classification"] = (
            legacy_translation_commit
        )

    story_map = {
        "version": 1,
        "total": len(source_map),
        "stories": source_map,
    }
    return manifest, story_map


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trusted-baseline")
    parser.add_argument("--source-ref", default="HEAD")
    # Backward-compatible CLI aliases used by existing workflows. The old translation commit
    # is recorded for audit only and is never used to classify a story.
    parser.add_argument("--translation-base")
    parser.add_argument("--translation-commit")
    parser.add_argument("--story-index", type=Path, default=DEFAULT_STORY_INDEX)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--story-map-output", type=Path, default=DEFAULT_STORY_MAP)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    baseline_arg = args.trusted_baseline or args.translation_base or "main"
    baseline = run_git("rev-parse", baseline_arg).strip()
    source_commit = run_git("rev-parse", args.source_ref).strip()
    run_git("merge-base", "--is-ancestor", baseline, source_commit)

    manifest, story_map = build_outputs(
        trusted_baseline=baseline,
        source_commit=source_commit,
        stories=load_story_index(args.story_index.resolve()),
        legacy_translation_commit=args.translation_commit,
    )
    encoded_manifest = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    encoded_map = json.dumps(story_map, ensure_ascii=False, separators=(",", ":")) + "\n"

    if args.check:
        try:
            current_manifest = args.manifest_output.read_text(encoding="utf-8")
            current_map = args.story_map_output.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ManifestError(f"generated manifest is missing: {exc.filename}") from exc
        if current_manifest != encoded_manifest:
            raise ManifestError("machine translation manifest is stale")
        if current_map != encoded_map:
            raise ManifestError("proofreading story map is stale")
        print(
            "manifest check passed: "
            f"stories={manifest['total']}, "
            f"added_txt={manifest['changed_txt_total']}, "
            f"protected_overwrites={manifest['protected_human_overwrite_count']}"
        )
        return 0

    for path, content in [
        (args.manifest_output, encoded_manifest),
        (args.story_map_output, encoded_map),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(
        "generated trusted-main machine manifest: "
        f"stories={manifest['total']}, "
        f"added_files={manifest['added_file_total']}, "
        f"added_json={manifest['changed_json_total']}, "
        f"added_txt={manifest['changed_txt_total']}, "
        f"source_map={story_map['total']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManifestError as exc:
        print(f"error: {exc}")
        raise SystemExit(2) from exc
