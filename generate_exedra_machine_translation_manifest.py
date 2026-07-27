#!/usr/bin/env python3
"""Generate Exedra's persisted machine-translation proofreading baseline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import generate_story_index as pipeline

ROOT = Path(__file__).resolve().parent
JP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"
CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
MANIFEST = JP_ROOT / "exedra_manifest.json"
DEFAULT_OUTPUT = ROOT / "website/public/data/exedra_machine_translation_manifest.generated.json"
PROVENANCE = {
    "local_human",
    "official_tw_human",
    "exedra_wiki_human",
    "machine_translation",
}


class ManifestError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"无法读取 JSON：{path}: {exc}") from exc


def load_groups() -> list[dict[str, Any]]:
    value = load_json(MANIFEST)
    groups = value.get("groups") if isinstance(value, dict) else None
    if value.get("schemaVersion") != 1 or not isinstance(groups, list) or len(groups) != 443:
        raise ManifestError("Exedra manifest 版本或组数异常")
    return groups


def title_for(group: dict[str, Any], source_records: list[dict[str, Any]]) -> str:
    titles = [
        str(record.get("bookTitle") or "").strip()
        for record in source_records
        if str(record.get("groupId") or "").casefold()
        == str(group.get("id") or "").casefold()
        and str(record.get("bookTitle") or "").strip()
    ]
    unique = list(dict.fromkeys(titles))
    return unique[0] if len(unique) == 1 else str(group["groupKey"]).replace("_", " ")


def build() -> dict[str, Any]:
    raw = load_json(MANIFEST)
    groups = load_groups()
    source_records = [value for value in raw.get("sources", []) if isinstance(value, dict)]
    entries: list[dict[str, Any]] = []
    counts = {key: 0 for key in sorted(PROVENANCE)}
    untranslated = 0
    sidecar_missing = 0

    for group in groups:
        raw_category = str(group["category"])
        group_key = str(group["groupKey"])
        group_id = str(group["id"])
        output_dir = CN_ROOT / raw_category / group_key
        cn_path = output_dir / f"{group_key}_cn.txt"
        legacy_cn_path = output_dir / f"{group_key}.txt"
        actual_cn = cn_path if cn_path.is_file() else legacy_cn_path if legacy_cn_path.is_file() else None
        if actual_cn is None:
            untranslated += 1
            continue
        sidecar = output_dir / f"{group_key}_cn.provenance.json"
        if sidecar.is_file():
            metadata = load_json(sidecar)
            provenance = str(metadata.get("provenance") or "") if isinstance(metadata, dict) else ""
            if provenance not in PROVENANCE:
                raise ManifestError(f"不支持的 Exedra 中文来源：{sidecar}: {provenance}")
            if str(metadata.get("sourceIdentity") or "").casefold() != group_id.casefold():
                raise ManifestError(f"Exedra 来源侧车身份不一致：{sidecar}")
        else:
            # The five pre-existing validated groups predate sidecars and are trusted local human CN.
            provenance = "local_human"
            sidecar_missing += 1
        counts[provenance] += 1
        if provenance != "machine_translation":
            continue

        category = pipeline.EXEDRA_CATEGORY_MAP[raw_category]
        relative_identity = f"{raw_category}/{group_key}/{group_key}_jp.txt"
        story_id = pipeline.safe_exedra_story_id(category, relative_identity, group_key)
        folder = (
            pipeline.EXEDRA_CHARACTER_DISPLAY_NAMES[group_key]
            if category == "exedra_character"
            else group_key
        )
        destination_rel = Path(category, group_key).as_posix()
        entries.append({
            "story_id": story_id,
            "category": category,
            "folder": folder,
            "title": title_for(group, source_records),
            "source_identity": group_id,
            "repository_path_cn": actual_cn.relative_to(ROOT).as_posix(),
            "path_cn": f"/data/{destination_rel}/{group_key}_cn.txt",
            "path_jp": f"/data/{destination_rel}/{group_key}_jp.txt",
            "provenance": provenance,
            "machine_source_json_count": int(group.get("sourceCount") or 0),
            "direct_txt_changed": True,
        })

    entries.sort(key=lambda item: (item["category"], item["folder"], item["story_id"]))
    return {
        "version": 2,
        "definition": "exedra_cn_provenance_machine_translation_only",
        "system": "exedra",
        "source_manifest_sha256": pipeline._sha256_file(MANIFEST),
        "group_total": len(groups),
        "localized_total": len(groups) - untranslated,
        "untranslated_total": untranslated,
        "provenance_counts": counts,
        "legacy_local_human_without_sidecar": sidecar_missing,
        "total": len(entries),
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    value = build()
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        try:
            current = args.output.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ManifestError(f"Exedra 机翻清单不存在：{args.output}") from exc
        if current != encoded:
            raise ManifestError("Exedra 机翻清单已过期")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(
        f"Exedra manifest: localized={value['localized_total']}/443 "
        f"machine={value['total']} untranslated={value['untranslated_total']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManifestError as exc:
        print(f"error: {exc}")
        raise SystemExit(2) from exc
