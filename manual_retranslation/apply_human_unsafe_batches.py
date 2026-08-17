#!/usr/bin/env python3
"""Apply human translations to the still-unverified leaves of selected candidate stories.

The script reconstructs the conservative coverage calculation used by the manual
retranslation project. A batch maps exact (field, Japanese source) pairs to human
Chinese translations. Only leaves still classified as unsafe are changed.
"""

from __future__ import annotations

import argparse
import base64
import copy
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ALLOWED_FIELDS = {
    "textLeft",
    "textRight",
    "textCenter",
    "narration",
    "progressNarration",
    "textSelect",
    "nameLeft",
    "nameRight",
    "nameCenter",
    "nameNarration",
}
TEXT_FIELDS = {
    "textLeft",
    "textRight",
    "textCenter",
    "narration",
    "progressNarration",
    "textSelect",
}
TOKEN_RE = re.compile(r"\[[^\[\]]+\]")
KANA_RE = re.compile(r"[ぁ-んァ-ヿ]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--trusted", type=Path, required=True)
    parser.add_argument(
        "--spec-glob",
        default="manual_retranslation/human_unsafe_batches/*.json",
    )
    parser.add_argument(
        "--report-dir",
        default="manual_retranslation/reports/human_unsafe_batches",
    )
    return parser.parse_args()


def find_one(root: Path, name: str) -> Path:
    matches = sorted(root.rglob(name))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {name!r} below {root}, got {matches}")
    return matches[0]


def find_scenario_root(root: Path, marker: str) -> Path:
    candidates = sorted(
        path
        for path in root.rglob("Scenarios_full")
        if path.is_dir() and marker in path.as_posix()
    )
    if len(candidates) != 1:
        raise RuntimeError(
            f"expected exactly one Scenarios_full containing {marker!r}, got {candidates}"
        )
    return candidates[0]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def walk_allowed(value: Any, path: tuple[Any, ...] = ()) -> Iterable[tuple[tuple[Any, ...], str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ALLOWED_FIELDS and isinstance(child, str):
                yield path + (key,), key, child
            yield from walk_allowed(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_allowed(child, path + (index,))


def walk_text(value: Any, path: tuple[Any, ...] = ()) -> Iterable[tuple[tuple[Any, ...], str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in TEXT_FIELDS and isinstance(child, str):
                yield path + (key,), key, child
            yield from walk_text(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_text(child, path + (index,))


def get_at(value: Any, path: tuple[Any, ...]) -> Any:
    for component in path:
        value = value[component]
    return value


def set_at(value: Any, path: tuple[Any, ...], replacement: str) -> None:
    parent = value
    for component in path[:-1]:
        parent = parent[component]
    parent[path[-1]] = replacement


def protected_projection(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("__TRANSLATABLE_TEXT__" if key in ALLOWED_FIELDS and isinstance(child, str) else protected_projection(child))
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [protected_projection(child) for child in value]
    return value


def rel_after_scenarios(path: str) -> str:
    marker = "Scenarios_full/"
    if marker not in path:
        raise RuntimeError(f"not a Scenarios_full path: {path}")
    return path.split(marker, 1)[1]


def decode_bundle_parts(directory: Path, suffix: str) -> Any | None:
    parts = sorted(directory.glob(f"*{suffix}"))
    if not parts:
        return None
    encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    return json.loads(gzip.decompress(base64.b64decode(encoded)))


def build_candidate_index(inventory: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stories: dict[str, dict[str, Any]] = {}
    for item in inventory:
        paired: list[str] = []
        unresolved: list[dict[str, Any]] = []
        for json_file in item["json_files"]:
            if json_file["status"] == "paired":
                paired.append(rel_after_scenarios(json_file["source_json"]))
            else:
                unresolved.append(json_file)
        stories[item["story_id"]] = {
            "story_id": item["story_id"],
            "ordinal": item["ordinal"],
            "category": item["category"],
            "folder": item["folder"],
            "title": item["title"],
            "paths": paired,
            "unresolved": unresolved,
        }
    return stories


def build_unique_memory(trusted_data: dict[str, Any]) -> dict[tuple[str, str], str]:
    targets: dict[tuple[str, str], set[str]] = defaultdict(set)
    for mapping in trusted_data["mappings"]:
        targets[(mapping["key"], mapping["source"])].add(mapping["target"])
    return {key: next(iter(values)) for key, values in targets.items() if len(values) == 1}


def collect_manual_provenance(
    repo: Path,
    jp_root: Path,
    candidate_paths: set[str],
) -> tuple[dict[str, dict[tuple[Any, ...], str]], dict[tuple[str, str], str]]:
    manual_root = repo / "manual_retranslation"
    explicit_by_rel: dict[str, dict[tuple[Any, ...], str]] = defaultdict(dict)
    manual_pair_targets: dict[tuple[str, str], set[str]] = defaultdict(set)

    maps_by_stem: dict[str, dict[int, str]] = defaultdict(dict)
    for path in sorted((manual_root / "batches").glob("*/*.json")):
        data = load_json(path)
        for identity, translation in data.items():
            stem, ordinal = identity.rsplit(":", 1)
            maps_by_stem[stem][int(ordinal)] = translation

    for directory in sorted((manual_root / "bundles").glob("*")):
        if not directory.is_dir():
            continue
        data = decode_bundle_parts(directory, ".b64")
        if data is None:
            continue
        for identity, translation in data.items():
            stem, ordinal = identity.rsplit(":", 1)
            maps_by_stem[stem][int(ordinal)] = translation

    for relative in candidate_paths:
        stem = Path(relative).stem
        if stem not in maps_by_stem:
            continue
        jp_path = jp_root / relative
        if not jp_path.is_file():
            continue
        leaves = list(walk_text(load_json(jp_path)))
        for ordinal, (leaf_path, field, jp_text) in enumerate(leaves, 1):
            if ordinal not in maps_by_stem[stem]:
                continue
            translation = maps_by_stem[stem][ordinal]
            explicit_by_rel[relative][leaf_path] = "manual_text_map"
            manual_pair_targets[(field, jp_text)].add(translation)

    for directory in sorted((manual_root / "exact_parts").glob("*")):
        if not directory.is_dir() or not (directory / "READY").exists():
            continue
        data = decode_bundle_parts(directory, ".part")
        if data is None:
            continue
        for file_record in data.get("files", []):
            relative = file_record["relative"]
            for entry in file_record["entries"]:
                leaf_path = tuple(entry["path"])
                explicit_by_rel[relative][leaf_path] = "manual_exact_bundle"
                manual_pair_targets[(entry["field"], entry["jp"])].add(entry["translation"])

    for path in sorted((manual_root / "exact_bundles").glob("*.b64")):
        data = json.loads(gzip.decompress(base64.b64decode(path.read_text(encoding="ascii").strip())))
        for file_record in data.get("files", []):
            relative = file_record["relative"]
            for entry in file_record["entries"]:
                leaf_path = tuple(entry["path"])
                explicit_by_rel[relative][leaf_path] = "manual_exact_bundle"
                manual_pair_targets[(entry["field"], entry["jp"])].add(entry["translation"])

    for pattern in ("manual_batches/*.json", "manual_batches_subset/*.json"):
        for path in sorted(manual_root.glob(pattern)):
            data = load_json(path)
            for story in data.get("stories", []):
                relative = story["relative_path"]
                jp_path = jp_root / relative
                if not jp_path.is_file():
                    continue
                leaves = list(walk_allowed(load_json(jp_path)))
                for entry in story["entries"]:
                    ordinal = entry["ordinal"]
                    leaf_path, field, jp_text = leaves[ordinal - 1]
                    if jp_text != entry["jp"]:
                        raise RuntimeError(
                            f"manual batch Japanese mismatch: {path} {relative} #{ordinal}"
                        )
                    explicit_by_rel[relative][leaf_path] = "manual_allowed_map"
                    manual_pair_targets[(field, jp_text)].add(entry["zh_cn"])

    manual_unique = {
        key: next(iter(values))
        for key, values in manual_pair_targets.items()
        if len(values) == 1
    }
    return explicit_by_rel, manual_unique


def classify_candidate_leaves(
    candidate_paths: set[str],
    current_root: Path,
    old_root: Path,
    jp_root: Path,
    trusted: dict[tuple[str, str], str],
    explicit_by_rel: dict[str, dict[tuple[Any, ...], str]],
    manual_unique: dict[tuple[str, str], str],
) -> dict[str, list[dict[str, Any]]]:
    branch_delta_by_rel: dict[str, dict[tuple[Any, ...], str]] = defaultdict(dict)
    observed_pair_targets: dict[tuple[str, str], set[str]] = defaultdict(set)

    loaded: dict[str, tuple[Any, Any, Any]] = {}
    for relative in sorted(candidate_paths):
        current_path = current_root / relative
        old_path = old_root / relative
        jp_path = jp_root / relative
        if not (current_path.is_file() and old_path.is_file() and jp_path.is_file()):
            raise RuntimeError(f"paired file missing: {relative}")
        current = load_json(current_path)
        old = load_json(old_path)
        jp = load_json(jp_path)
        current_leaves = {path: (field, text) for path, field, text in walk_allowed(current)}
        old_leaves = {path: (field, text) for path, field, text in walk_allowed(old)}
        jp_leaves = {path: (field, text) for path, field, text in walk_allowed(jp)}
        if set(current_leaves) != set(old_leaves) or set(current_leaves) != set(jp_leaves):
            raise RuntimeError(f"allowed-field path mismatch: {relative}")
        loaded[relative] = current, old, jp
        for leaf_path, (field, current_text) in current_leaves.items():
            old_text = old_leaves[leaf_path][1]
            jp_text = jp_leaves[leaf_path][1]
            if current_text != old_text:
                branch_delta_by_rel[relative][leaf_path] = "branch_reviewed_delta"
                observed_pair_targets[(field, jp_text)].add(current_text)
            elif leaf_path in explicit_by_rel.get(relative, {}):
                observed_pair_targets[(field, jp_text)].add(current_text)

    combined_targets: dict[tuple[str, str], set[str]] = defaultdict(set)
    for key, value in trusted.items():
        combined_targets[key].add(value)
    for key, value in manual_unique.items():
        combined_targets[key].add(value)
    for key, values in observed_pair_targets.items():
        combined_targets[key].update(values)
    reusable = {
        key: next(iter(values))
        for key, values in combined_targets.items()
        if len(values) == 1
    }

    unsafe_by_rel: dict[str, list[dict[str, Any]]] = {}
    for relative in sorted(candidate_paths):
        current, old, jp = loaded[relative]
        current_leaves = list(walk_allowed(current))
        old_leaves = list(walk_allowed(old))
        jp_leaves = list(walk_allowed(jp))
        if [(path, field) for path, field, _ in current_leaves] != [
            (path, field) for path, field, _ in old_leaves
        ] or [(path, field) for path, field, _ in current_leaves] != [
            (path, field) for path, field, _ in jp_leaves
        ]:
            raise RuntimeError(f"allowed-field order mismatch: {relative}")

        unsafe: list[dict[str, Any]] = []
        for ordinal, (
            (leaf_path, field, current_text),
            (_, _, old_text),
            (_, _, jp_text),
        ) in enumerate(zip(current_leaves, old_leaves, jp_leaves), 1):
            explicit = explicit_by_rel.get(relative, {}).get(leaf_path)
            reviewed = branch_delta_by_rel.get(relative, {}).get(leaf_path)
            safe = bool(explicit or reviewed)
            if not safe and trusted.get((field, jp_text)) == current_text:
                safe = True
            if not safe and manual_unique.get((field, jp_text)) == current_text:
                safe = True
            if not safe and reusable.get((field, jp_text)) == current_text:
                safe = True
            if not safe and current_text == jp_text and not KANA_RE.search(jp_text):
                safe = True
            if not safe:
                unsafe.append(
                    {
                        "ordinal": ordinal,
                        "path": leaf_path,
                        "field": field,
                        "jp": jp_text,
                        "current": current_text,
                        "old": old_text,
                    }
                )
        unsafe_by_rel[relative] = unsafe
    return unsafe_by_rel


def validate_translation(jp_text: str, translation: str, context: str) -> None:
    if not isinstance(translation, str) or not translation:
        raise RuntimeError(f"empty/non-string translation: {context}")
    if jp_text.count("@") != translation.count("@"):
        raise RuntimeError(
            f"@ count mismatch: {context}: {jp_text.count('@')} != {translation.count('@')}"
        )
    if TOKEN_RE.findall(jp_text) != TOKEN_RE.findall(translation):
        raise RuntimeError(f"control-token mismatch: {context}")
    if KANA_RE.search(translation):
        raise RuntimeError(f"Japanese kana remains in translation: {context}: {translation!r}")


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()
    corpus = args.corpus.resolve()
    trusted_root = args.trusted.resolve()

    current_root = repo / "magireco-translate-data-master" / "Scenarios_full"
    if not current_root.is_dir():
        raise RuntimeError(f"current scenario root not found: {current_root}")

    inventory_path = find_one(corpus, "candidate_inventory.json")
    trusted_path = find_one(trusted_root, "trusted_translation_memory.json.gz")
    old_root = find_scenario_root(corpus, "magireco-translate-data-master")
    jp_root = find_scenario_root(corpus, "magireco-source-master")

    inventory = load_json(inventory_path)
    with gzip.open(trusted_path, "rt", encoding="utf-8") as handle:
        trusted_data = json.load(handle)

    story_index = build_candidate_index(inventory)
    candidate_paths = {
        relative for story in story_index.values() for relative in story["paths"]
    }
    trusted = build_unique_memory(trusted_data)
    explicit_by_rel, manual_unique = collect_manual_provenance(
        repo, jp_root, candidate_paths
    )
    unsafe_by_rel = classify_candidate_leaves(
        candidate_paths,
        current_root,
        old_root,
        jp_root,
        trusted,
        explicit_by_rel,
        manual_unique,
    )

    spec_paths = sorted(repo.glob(args.spec_glob))
    if not spec_paths:
        print("No human unsafe batch specs found; nothing to apply.")
        return 0

    report_dir = repo / args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    grand_total = 0

    for spec_path in spec_paths:
        spec = load_json(spec_path)
        if spec.get("schema_version") != 1:
            raise RuntimeError(f"unsupported schema in {spec_path}")
        batch_id = spec["batch_id"]
        translation_maps: dict[str, dict[tuple[str, str], str]] = {}
        expected_counts: dict[str, int] = {}
        for story_spec in spec["stories"]:
            story_id = story_spec["story_id"]
            if story_id not in story_index:
                raise RuntimeError(f"unknown story_id {story_id} in {spec_path}")
            mapping: dict[tuple[str, str], str] = {}
            for entry in story_spec["translations"]:
                key = (entry["field"], entry["jp"])
                if key in mapping and mapping[key] != entry["zh_cn"]:
                    raise RuntimeError(f"conflicting translation {story_id} {key}")
                validate_translation(entry["jp"], entry["zh_cn"], f"{story_id} {key}")
                mapping[key] = entry["zh_cn"]
            translation_maps[story_id] = mapping
            expected_counts[story_id] = story_spec["expected_unsafe"]

        changed_files: dict[str, dict[str, Any]] = {}
        story_reports: list[dict[str, Any]] = []
        for story_spec in spec["stories"]:
            story_id = story_spec["story_id"]
            story = story_index[story_id]
            mapping = translation_maps[story_id]
            unsafe_entries: list[tuple[str, dict[str, Any]]] = []
            for relative in story["paths"]:
                for entry in unsafe_by_rel[relative]:
                    unsafe_entries.append((relative, entry))
            if len(unsafe_entries) != expected_counts[story_id]:
                raise RuntimeError(
                    f"unsafe count changed for {story_id}: expected {expected_counts[story_id]}, got {len(unsafe_entries)}"
                )

            used_keys: Counter[tuple[str, str]] = Counter()
            per_story_changes: list[dict[str, Any]] = []
            for relative, entry in unsafe_entries:
                key = (entry["field"], entry["jp"])
                if key not in mapping:
                    raise RuntimeError(
                        f"missing human translation for {story_id} {relative} #{entry['ordinal']} {key}"
                    )
                translation = mapping[key]
                validate_translation(
                    entry["jp"],
                    translation,
                    f"{story_id} {relative} #{entry['ordinal']}",
                )
                used_keys[key] += 1

                if relative not in changed_files:
                    path = current_root / relative
                    before = load_json(path)
                    changed_files[relative] = {
                        "path": path,
                        "before": before,
                        "after": copy.deepcopy(before),
                        "changes": [],
                    }
                record = changed_files[relative]
                current_value = get_at(record["after"], entry["path"])
                if current_value != entry["current"]:
                    raise RuntimeError(
                        f"current value drifted: {story_id} {relative} #{entry['ordinal']}"
                    )
                set_at(record["after"], entry["path"], translation)
                change = {
                    "story_id": story_id,
                    "relative": relative,
                    "ordinal": entry["ordinal"],
                    "path": list(entry["path"]),
                    "field": entry["field"],
                    "jp": entry["jp"],
                    "before": entry["current"],
                    "after": translation,
                }
                record["changes"].append(change)
                per_story_changes.append(change)

            unused = sorted(
                {key for key in mapping if used_keys[key] == 0},
                key=lambda item: (item[0], item[1]),
            )
            if unused:
                raise RuntimeError(f"unused translations in {story_id}: {unused}")
            story_reports.append(
                {
                    "story_id": story_id,
                    "title": story["title"],
                    "changed_leaf_count": len(per_story_changes),
                    "changed_file_count": len({item["relative"] for item in per_story_changes}),
                    "changes": per_story_changes,
                }
            )

        for relative, record in changed_files.items():
            before = record["before"]
            after = record["after"]
            if protected_projection(before) != protected_projection(after):
                raise RuntimeError(f"protected JSON content changed: {relative}")
            serialized = json.dumps(after, ensure_ascii=False, indent=2) + "\n"
            json.loads(serialized)
            record["path"].write_text(serialized, encoding="utf-8")

        report = {
            "schema_version": 1,
            "batch_id": batch_id,
            "spec": spec_path.relative_to(repo).as_posix(),
            "story_count": len(story_reports),
            "changed_file_count": len(changed_files),
            "changed_leaf_count": sum(
                story["changed_leaf_count"] for story in story_reports
            ),
            "validation": {
                "json_parse": "passed",
                "protected_fields_deep_equal": "passed",
                "at_line_break_counts": "passed",
                "control_token_sequences": "passed",
                "exact_japanese_source_pairs": "passed",
                "unsafe_count_guards": "passed",
            },
            "stories": story_reports,
        }
        report_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        report["report_sha256"] = hashlib.sha256(report_text.encode("utf-8")).hexdigest()
        output_path = report_dir / f"{batch_id}.json"
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        grand_total += report["changed_leaf_count"]
        print(
            f"Applied {batch_id}: {report['story_count']} stories, "
            f"{report['changed_file_count']} files, {report['changed_leaf_count']} leaves"
        )

    print(f"Grand total applied leaves: {grand_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
