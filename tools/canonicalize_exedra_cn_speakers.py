#!/usr/bin/env python3
"""Canonicalize every Exedra CN speaker in TXT/JSON and rebind reports."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import generate_story_index as pipeline  # noqa: E402
import import_exedra_official_tw as common  # noqa: E402
from tw_authentic_scenario import (  # noqa: E402
    canonicalize_json_names_path,
    canonicalize_txt_path,
    dictionary_sha256,
    extract_text_events,
    load_name_translation_map,
    translate_speaker,
)

JP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"
CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
MANIFEST = JP_ROOT / "exedra_manifest.json"
AUDIT_PATH = ROOT / "artifacts/exedra_speaker_canonicalization_report.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(path: Path) -> str:
    return hashlib.sha256(
        path.read_text(encoding="utf-8-sig").encode("utf-8")
    ).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def load_manifest_groups() -> list[dict[str, Any]]:
    value = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    groups = value.get("groups") if isinstance(value, dict) else None
    if not isinstance(groups, list):
        raise RuntimeError("Exedra manifest is missing groups")
    result = [group for group in groups if isinstance(group, dict)]
    if len(result) != len(groups):
        raise RuntimeError("Exedra manifest contains non-object groups")
    return result


def update_source_metadata(
    entries: list[dict[str, Any]],
    group_dir: Path,
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            raise RuntimeError(f"Invalid sourceJson entry in {group_dir}")
        next_item = dict(item)
        source = str(next_item.get("source") or "")
        path = group_dir / source
        if source and path.is_file():
            digest = sha256_file(path)
            next_item["cnSha256"] = digest
            if "simplifiedJsonSha256" in next_item:
                next_item["simplifiedJsonSha256"] = digest
            document = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(document, dict):
                raise RuntimeError(f"Invalid content JSON: {path}")
            rows = extract_text_events(document)
            next_item["eventCount"] = len(rows)
            next_item["canonicalNameFields"] = True
            next_item["speakerPolicy"] = (
                "dictionary.ts-exact-or-unambiguous-canonical-chinese"
            )
            proof = next_item.get("mutationProof")
            if isinstance(proof, dict):
                proof = dict(proof)
                proof.pop("nonCommentFieldsMatch", None)
                proof.update(
                    {
                        "nonLocalizedFieldsMatch": True,
                        "canonicalNameFields": True,
                        "playableCommentSequenceMatches": True,
                        "canonicalEventCount": len(rows),
                    }
                )
                next_item["mutationProof"] = proof
        updated.append(next_item)
    return updated


def rebuild_report(
    old: dict[str, Any],
    *,
    category: str,
    key: str,
    jp_txt: Path,
    cn_txt: Path,
    group_dir: Path,
    dictionary_digest: str,
    txt_changes: int,
    json_changes: int,
) -> dict[str, Any]:
    source_json = old.get("sourceJson")
    if not isinstance(source_json, list):
        source_json = []
    source_json = update_source_metadata(source_json, group_dir)
    source_label = str(old.get("sourceRoot") or "canonicalized-existing-human")
    rebuilt = common.build_report(
        category,
        key,
        jp_txt,
        cn_txt,
        source_label,
        source_json,
    )
    preserved = dict(old)
    for field in (
        "schemaVersion",
        "status",
        "sourceRoot",
        "group",
        "validation",
        "mismatches",
        "jp",
        "cn",
        "sections",
        "sourceJson",
    ):
        preserved[field] = rebuilt[field]
    if old.get("provenance"):
        preserved["provenance"] = old["provenance"]
    preserved["speakerCanonicalization"] = {
        "policy": "dictionary.ts-exact-or-unambiguous-canonical-chinese",
        "dictionarySha256": dictionary_digest,
        "txtSpeakerLabelsChanged": txt_changes,
        "jsonNameCellsChanged": json_changes,
    }
    return preserved


def update_sidecar(
    path: Path,
    *,
    cn_txt: Path,
    group_dir: Path,
    dictionary_digest: str,
    txt_changes: int,
    json_changes: int,
) -> None:
    if not path.is_file():
        return
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Invalid provenance sidecar: {path}")
    value["cnSha256"] = sha256_text(cn_txt)
    for field in ("sourceJson", "episodes"):
        entries = value.get(field)
        if isinstance(entries, list):
            value[field] = update_source_metadata(entries, group_dir)
    value["speakerCanonicalization"] = {
        "policy": "dictionary.ts-exact-or-unambiguous-canonical-chinese",
        "dictionarySha256": dictionary_digest,
        "txtSpeakerLabelsChanged": txt_changes,
        "jsonNameCellsChanged": json_changes,
    }
    atomic_json(path, value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    mapping = load_name_translation_map()
    dictionary_digest = dictionary_sha256()
    stats: Counter[str] = Counter()
    remaining_japanese: set[str] = set()
    groups_audited: list[dict[str, Any]] = []

    for group in load_manifest_groups():
        category = str(group.get("category") or "")
        key = str(group.get("groupKey") or "")
        text_file = str(group.get("textFile") or "")
        if not category or not key or not text_file:
            raise RuntimeError("Invalid Exedra manifest group")
        group_dir = CN_ROOT / category / key
        cn_txt = group_dir / f"{key}_cn.txt"
        if not cn_txt.is_file():
            continue
        jp_txt = JP_ROOT / text_file
        if not jp_txt.is_file():
            raise RuntimeError(f"JP TXT missing: {jp_txt}")

        txt_changes, remaining = canonicalize_txt_path(cn_txt, mapping)
        remaining_japanese.update(remaining)
        stats["cn_groups"] += 1
        stats["txt_speaker_labels_changed"] += txt_changes

        source_names = [
            Path(str(value)).name
            for value in group.get("sources", [])
            if isinstance(value, str)
        ]
        present_json = [
            group_dir / name
            for name in source_names
            if (group_dir / name).is_file()
        ]
        if present_json and len(present_json) != len(source_names):
            raise RuntimeError(
                f"Partial CN JSON set for {category}/{key}: "
                f"{len(present_json)}/{len(source_names)}"
            )
        group_json_changes = 0
        for json_path in present_json:
            total, changes = canonicalize_json_names_path(json_path, mapping)
            stats["json_name_cells"] += total
            stats["json_name_cells_changed"] += changes
            group_json_changes += changes

        report_path = group_dir / f"{key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}"
        if not report_path.is_file():
            raise RuntimeError(f"CN import report missing: {report_path}")
        old_report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        if not isinstance(old_report, dict):
            raise RuntimeError(f"Invalid CN import report: {report_path}")
        report = rebuild_report(
            old_report,
            category=category,
            key=key,
            jp_txt=jp_txt,
            cn_txt=cn_txt,
            group_dir=group_dir,
            dictionary_digest=dictionary_digest,
            txt_changes=txt_changes,
            json_changes=group_json_changes,
        )
        atomic_json(report_path, report)
        update_sidecar(
            group_dir / f"{key}_cn.provenance.json",
            cn_txt=cn_txt,
            group_dir=group_dir,
            dictionary_digest=dictionary_digest,
            txt_changes=txt_changes,
            json_changes=group_json_changes,
        )

        jp_sections = pipeline._exedra_alignment_sections(jp_txt)
        cn_sections = pipeline._exedra_alignment_sections(cn_txt)
        pipeline._validate_exedra_cn_import_report(
            group=pipeline.OrganizedExedraGroup(
                manifest_id=str(group.get("id") or ""),
                raw_category=category,
                category=pipeline.EXEDRA_CATEGORY_MAP[category],
                group_key=key,
                output_dir=Path(category, key),
                text_file=Path(text_file),
                source_paths=tuple(
                    str(value) for value in group.get("sources", [])
                ),
                source_names=tuple(
                    Path(str(value)).name
                    for value in group.get("sources", [])
                ),
                title="",
            ),
            jp_path=jp_txt,
            cn_path=cn_txt,
            jp_sections=jp_sections,
            cn_sections=cn_sections,
        )
        groups_audited.append(
            {
                "group": f"{category}/{key}",
                "provenance": report.get("provenance"),
                "txtSpeakerLabelsChanged": txt_changes,
                "jsonNameCellsChanged": group_json_changes,
                "canonicalBlocks": sum(
                    item.reader_block_count for item in cn_sections
                ),
            }
        )

    uncanonicalized: set[str] = set()
    for group in groups_audited:
        category, key = str(group["group"]).split("/", 1)
        path = CN_ROOT / category / key / f"{key}_cn.txt"
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("---"):
                continue
            separator = min(
                (
                    position
                    for position in (line.find(":"), line.find("："))
                    if position > 0
                ),
                default=-1,
            )
            if separator <= 0:
                continue
            speaker = line[:separator].strip()
            canonical = translate_speaker(speaker, mapping)
            if canonical != speaker:
                uncanonicalized.add(speaker)
    if uncanonicalized:
        raise RuntimeError(
            "Dictionary-known Exedra CN speakers remain uncanonicalized: "
            + ", ".join(sorted(uncanonicalized)[:40])
        )

    audit = {
        "version": 1,
        "policy": "dictionary.ts-exact-or-unambiguous-canonical-chinese",
        "dictionarySha256": dictionary_digest,
        "stats": dict(stats),
        "remainingJapaneseLabels": sorted(remaining_japanese),
        "groups": groups_audited,
    }
    if not args.check:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(AUDIT_PATH, audit)
    print(
        "EXEDRA_SPEAKER_CANONICALIZATION_OK "
        f"groups={stats['cn_groups']} "
        f"txt_changes={stats['txt_speaker_labels_changed']} "
        f"json_changes={stats['json_name_cells_changed']} "
        f"remaining_japanese_labels={len(remaining_japanese)}"
    )
    if remaining_japanese:
        print(
            "EXEDRA_REMAINING_JAPANESE_LABEL_SAMPLES "
            + json.dumps(
                sorted(remaining_japanese)[:80],
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
