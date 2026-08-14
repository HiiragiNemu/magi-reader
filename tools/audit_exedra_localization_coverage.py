#!/usr/bin/env python3
"""Audit Exedra Chinese coverage and recorded translation provenance.

The audit is deliberately read-only.  It classifies only explicit metadata in
the generated story index, per-story provenance sidecars, and the existing
machine-translation manifest.  It does not infer translation origin from text
quality, similarity, timestamps, or Git history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "website/public/story_index.json"
DEFAULT_MACHINE_MANIFEST = (
    ROOT / "website/public/data/machine_translation_manifest.generated.json"
)
DEFAULT_TRANSLATION_ROOT = (
    ROOT / "magiraexedra-translate-data-master/Scenarios_full"
)
DEFAULT_OUTPUT = ROOT / "artifacts/exedra_localization_coverage.audit.json"

MACHINE_VALUE_TOKENS = (
    "machine_translation",
    "machine-generated",
    "machine_generated",
    "ai_generated",
    "workers_ai",
    "deepseek",
    "chatgpt",
    "llm",
)
MACHINE_BOOL_KEYS = {
    "machinetranslation",
    "machine_translation",
    "ismachinetranslation",
    "is_machine_translation",
    "aigenerated",
    "ai_generated",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(root: Path, paths: Iterable[Path]) -> str:
    """Hash path + size + content for a deterministic sidecar inventory."""

    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        size = str(path.stat().st_size).encode("ascii")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(size)
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def explicit_machine_signals(value: Any, location: str = "$") -> list[str]:
    """Return explicit machine/AI metadata signals without inspecting prose."""

    signals: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            key_normalized = str(key).replace("-", "_").lower()
            key_compact = key_normalized.replace("_", "")
            if (
                (key_normalized in MACHINE_BOOL_KEYS or key_compact in MACHINE_BOOL_KEYS)
                and child is True
            ):
                signals.append(f"{child_location}=true")
            if key_normalized in {"provenance", "classification", "source_type"}:
                text = str(child).strip().lower()
                if any(token in text for token in MACHINE_VALUE_TOKENS):
                    signals.append(f"{child_location}={child}")
            signals.extend(explicit_machine_signals(child, child_location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            signals.extend(explicit_machine_signals(child, f"{location}[{index}]"))
    return signals


def is_exedra_machine_manifest_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    game = str(entry.get("game") or "").lower()
    category = str(entry.get("category") or "").lower()
    story_id = str(entry.get("story_id") or entry.get("id") or "").lower()
    source_identity = str(entry.get("source_identity") or "").lower()
    return (
        game == "exedra"
        or category.startswith("exedra_")
        or story_id.startswith("exedra_")
        or source_identity.startswith("exedra:")
    )


def story_record(story: dict[str, Any], sidecar: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": story.get("id"),
        "rawId": story.get("raw_id"),
        "category": story.get("category"),
        "title": story.get("title") or story.get("folder") or "",
        "sourceIdentity": story.get("source_identity"),
        "hasCn": story.get("has_cn") is True,
        "officialTw": story.get("official_tw") is True,
        "provenance": sidecar.get("provenance") if sidecar else None,
        "machineTranslation": (
            sidecar.get("machineTranslation") if sidecar else None
        ),
        "pathCn": story.get("path_cn") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--story-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--machine-manifest", type=Path, default=DEFAULT_MACHINE_MANIFEST
    )
    parser.add_argument(
        "--translation-root", type=Path, default=DEFAULT_TRANSLATION_ROOT
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    stories_raw = load_json(args.story_index)
    if not isinstance(stories_raw, list):
        raise ValueError("story index must be a JSON list")
    exedra = [
        story
        for story in stories_raw
        if isinstance(story, dict) and story.get("game") == "exedra"
    ]

    sidecar_paths = list(args.translation_root.rglob("*.provenance.json"))
    sidecars_by_identity: dict[str, tuple[Path, dict[str, Any]]] = {}
    sidecar_machine_signals: list[dict[str, Any]] = []
    provenance_counts: Counter[str] = Counter()
    for path in sidecar_paths:
        value = load_json(path)
        if not isinstance(value, dict):
            raise ValueError(f"provenance sidecar must be an object: {path}")
        identity = str(value.get("sourceIdentity") or "").strip()
        if not identity:
            raise ValueError(f"provenance sidecar lacks sourceIdentity: {path}")
        if identity in sidecars_by_identity:
            raise ValueError(f"duplicate provenance sourceIdentity: {identity}")
        sidecars_by_identity[identity] = (path, value)
        provenance_counts[str(value.get("provenance") or "UNSPECIFIED")] += 1
        signals = explicit_machine_signals(value)
        if signals:
            sidecar_machine_signals.append(
                {
                    "sourceIdentity": identity,
                    "path": path.relative_to(ROOT).as_posix(),
                    "signals": signals,
                }
            )

    missing_sidecars: list[dict[str, Any]] = []
    orphan_sidecars = set(sidecars_by_identity)
    records: list[dict[str, Any]] = []
    index_machine_signals: list[dict[str, Any]] = []
    for story in exedra:
        identity = str(story.get("source_identity") or "")
        pair = sidecars_by_identity.get(identity)
        sidecar = pair[1] if pair else None
        if pair:
            orphan_sidecars.discard(identity)
        if story.get("has_cn") is True and sidecar is None:
            missing_sidecars.append(
                {
                    "id": story.get("id"),
                    "sourceIdentity": identity,
                    "pathCn": story.get("path_cn") or "",
                }
            )
        signals = explicit_machine_signals(story)
        if signals:
            index_machine_signals.append(
                {
                    "id": story.get("id"),
                    "sourceIdentity": identity,
                    "signals": signals,
                }
            )
        records.append(story_record(story, sidecar))

    machine_manifest = load_json(args.machine_manifest)
    machine_entries = (
        machine_manifest.get("entries", [])
        if isinstance(machine_manifest, dict)
        else []
    )
    if not isinstance(machine_entries, list):
        raise ValueError("machine manifest entries must be a list")
    exedra_machine_entries = [
        entry for entry in machine_entries if is_exedra_machine_manifest_entry(entry)
    ]

    portraits = [record for record in records if record["category"] == "exedra_portrait"]
    portrait_non_tw = [record for record in portraits if not record["officialTw"]]
    portrait_missing_cn = [record for record in portraits if not record["hasCn"]]
    portrait_machine = [
        record
        for record in portraits
        if record["machineTranslation"] is True
        or any(
            token in str(record["provenance"] or "").lower()
            for token in MACHINE_VALUE_TOKENS
        )
    ]
    exedra_machine_signal_count = (
        len(sidecar_machine_signals)
        + len(index_machine_signals)
        + len(exedra_machine_entries)
    )

    report = {
        "version": 1,
        "policy": "explicit_metadata_only_no_provenance_inference",
        "inputs": {
            "storyIndex": args.story_index.resolve().as_posix(),
            "storyIndexSha256": file_sha256(args.story_index),
            "machineManifest": args.machine_manifest.resolve().as_posix(),
            "machineManifestSha256": file_sha256(args.machine_manifest),
            "translationRoot": args.translation_root.resolve().as_posix(),
            "provenanceSidecarCount": len(sidecar_paths),
            "provenanceSidecarTreeSha256": tree_sha256(
                args.translation_root, sidecar_paths
            ),
        },
        "counts": {
            "exedraStories": len(records),
            "exedraChineseStories": sum(record["hasCn"] for record in records),
            "exedraMissingChineseStories": sum(
                not record["hasCn"] for record in records
            ),
            "exedraOfficialTwStories": sum(
                record["officialTw"] for record in records
            ),
            "exedraNonTwChineseStories": sum(
                record["hasCn"] and not record["officialTw"] for record in records
            ),
            "exedraChineseStoriesMissingProvenance": len(missing_sidecars),
            "exedraOrphanProvenanceSidecars": len(orphan_sidecars),
            "exedraExplicitMachineSignals": exedra_machine_signal_count,
            "exedraMachineManifestEntries": len(exedra_machine_entries),
            "portraitStories": len(portraits),
            "portraitChineseStories": sum(record["hasCn"] for record in portraits),
            "portraitMissingChineseStories": len(portrait_missing_cn),
            "portraitOfficialTwStories": sum(
                record["officialTw"] for record in portraits
            ),
            "portraitNonTwStories": len(portrait_non_tw),
            "portraitExplicitMachineStories": len(portrait_machine),
        },
        "provenanceCounts": dict(sorted(provenance_counts.items())),
        "portraitNonTwStories": portrait_non_tw,
        "portraitMissingChineseStories": portrait_missing_cn,
        "portraitExplicitMachineStories": portrait_machine,
        "machineSignals": {
            "storyIndex": index_machine_signals,
            "provenanceSidecars": sidecar_machine_signals,
            "machineManifestEntries": exedra_machine_entries,
        },
        "integrity": {
            "chineseStoriesMissingProvenance": missing_sidecars,
            "orphanProvenanceSourceIdentities": sorted(orphan_sidecars),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_hash = file_sha256(args.output)
    counts = report["counts"]
    print(
        "EXEDRA_LOCALIZATION_AUDIT_OK "
        f"exedra={counts['exedraStories']} "
        f"cn={counts['exedraChineseStories']} "
        f"tw={counts['exedraOfficialTwStories']} "
        f"portrait={counts['portraitStories']} "
        f"portrait_cn={counts['portraitChineseStories']} "
        f"portrait_tw={counts['portraitOfficialTwStories']} "
        f"portrait_non_tw={counts['portraitNonTwStories']} "
        f"machine_signals={counts['exedraExplicitMachineSignals']} "
        f"report_sha256={report_hash}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
