#!/usr/bin/env python3
"""Publish raw Magia Record / Magia Exedra scenario JSON with provenance.

The normal reader uses consolidated TXT because it is stable for bilingual
alignment.  This script additionally copies every raw scenario JSON into the
public asset tree, writes a SHA-256 manifest, and attaches exact stem/folder
matches to story_index entries without replacing their normal TXT sources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SOURCE_TREES = (
    ("magireco", "jp", Path("magireco-source-master/Scenarios_full")),
    ("magireco", "cn", Path("magireco-translate-data-master/Scenarios_full")),
    ("exedra", "jp", Path("magiraexedra-source-master/Scenarios_full")),
    ("exedra", "cn", Path("magiraexedra-translate-data-master/Scenarios_full")),
)
EXEDRA_CATEGORY_MAP = {
    "1_Main": "exedra_main",
    "2_Sub": "exedra_sub",
    "3_Character": "exedra_character",
    "4_Portrait": "exedra_portrait",
    "6_Reaction": "exedra_reaction",
    "7_Namae": "exedra_namae",
    "8_Dungeon": "exedra_dungeon",
    "10_Battle": "exedra_battle",
}
SECTION_SUFFIX_RE = re.compile(r"\s+Section\s+\d+$", re.I)
EXCLUDED_SUFFIXES = (".import-report.json",)
EXCLUDED_NAMES = {"exedra_manifest.json", "story_ids.generated.json"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_category(game: str, relative: Path) -> str:
    first = relative.parts[0] if relative.parts else ""
    if game == "exedra":
        return EXEDRA_CATEGORY_MAP.get(re.sub(r"_full$", "", first, flags=re.I), "exedra_unclassified")
    lower = first.casefold()
    for category in (
        "main_story", "event_story", "character_story", "costume_story",
        "login_story", "mirror_story", "scene0_main", "scene0_sub",
    ):
        if category in lower:
            return category
    if "scene0" in lower or lower.startswith("s0"):
        return "scene0_sub" if "sub" in lower else "scene0_main"
    return "Unclassified"


def safe_json_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    files: list[Path] = []
    for path in root.rglob("*.json"):
        if path.is_symlink() or not path.is_file():
            continue
        if path.name in EXCLUDED_NAMES or path.name.endswith(EXCLUDED_SUFFIXES):
            continue
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
        files.append(path)
    return sorted(files, key=lambda value: value.as_posix().casefold())


def story_stems(item: dict[str, Any]) -> set[str]:
    values = {
        str(item.get("raw_id") or ""),
        str(item.get("file_stem") or ""),
        Path(str(item.get("filename_cn") or "")).stem.removesuffix("_cn"),
        Path(str(item.get("filename_jp") or "")).stem.removesuffix("_jp"),
        Path(str(item.get("source_identity") or "")).name,
    }
    for section in item.get("sections") or []:
        value = SECTION_SUFFIX_RE.sub("", str(section)).strip()
        if value.lower().endswith(".json"):
            value = value[:-5]
        values.add(value)
    return {value.casefold() for value in values if value}


def update_story_manifest(public: Path, stories: list[dict[str, Any]]) -> None:
    story_path = public / "story_index.json"
    raw = json.dumps(stories, ensure_ascii=False, indent=2).encode("utf-8")
    story_path.write_bytes(raw)
    manifest_path = public / "story_index.manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    manifest.update({
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "entries": len(stories),
        "raw_json_published": True,
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, default=Path("website/public"))
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args()

    repo = args.repo.resolve()
    public = args.public.resolve()
    output_root = public / "data" / "raw"
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    by_match: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    counts: Counter[str] = Counter()
    total_bytes = 0

    for game, language, relative_root in SOURCE_TREES:
        source_root = (repo / relative_root).resolve()
        for source in safe_json_files(source_root):
            relative = source.relative_to(source_root)
            destination = output_root / game / language / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            category = normalized_category(game, relative)
            folder = relative.parts[1] if len(relative.parts) > 2 else relative.parent.name
            web_path = "/" + destination.relative_to(public).as_posix()
            size = destination.stat().st_size
            entry = {
                "game": game,
                "language": language,
                "category": category,
                "folder": folder,
                "name": source.name,
                "stem": source.stem,
                "path": web_path,
                "bytes": size,
                "sha256": sha256_file(destination),
                "storyIds": [],
            }
            entries.append(entry)
            by_match[(game, language, category.casefold(), source.stem.casefold())].append(entry)
            counts[f"{game}_{language}"] += 1
            total_bytes += size

    if counts["magireco_jp"] <= 0 or counts["magireco_cn"] <= 0 or counts["exedra_jp"] <= 0:
        raise RuntimeError(f"raw JSON source tree incomplete: {dict(counts)}")

    story_path = public / "story_index.json"
    stories: list[dict[str, Any]] = json.loads(story_path.read_text(encoding="utf-8"))
    attached_paths: set[str] = set()
    associated_stories = 0
    for item in stories:
        game = str(item.get("game") or ("exedra" if str(item.get("category", "")).startswith("exedra_") else "magireco"))
        category = str(item.get("category") or "").casefold()
        folder = str(item.get("folder") or "").casefold()
        stems = story_stems(item)
        attached_for_story = 0
        for language in ("cn", "jp"):
            candidates: list[dict[str, Any]] = []
            seen: set[str] = set()
            for stem in stems:
                for entry in by_match.get((game, language, category, stem), []):
                    path = str(entry["path"])
                    if path in seen:
                        continue
                    seen.add(path)
                    candidates.append(entry)
            exact_folder = [entry for entry in candidates if str(entry.get("folder", "")).casefold() == folder]
            selected = exact_folder or candidates
            selected.sort(key=lambda entry: str(entry["path"]).casefold())
            if selected:
                key = f"raw_json_{language}"
                item[key] = [str(entry["path"]) for entry in selected]
                for entry in selected:
                    entry["storyIds"].append(str(item["id"]))
                    attached_paths.add(str(entry["path"]))
                attached_for_story += len(selected)
        if attached_for_story:
            associated_stories += 1

    for entry in entries:
        entry["storyIds"] = sorted(set(entry["storyIds"]), key=str.casefold)

    update_story_manifest(public, stories)
    manifest = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat(),
        "entries": len(entries),
        "bytes": total_bytes,
        "counts": dict(sorted(counts.items())),
        "associatedStories": associated_stories,
        "associatedFiles": len(attached_paths),
        "unassociatedFiles": len(entries) - len(attached_paths),
        "files": entries,
    }
    (public / "raw_story_json_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in manifest.items() if key != "files"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
