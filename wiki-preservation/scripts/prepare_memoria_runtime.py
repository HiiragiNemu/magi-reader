#!/usr/bin/env python3
"""Convert the merged Memoria crawl corpus into compact browser runtime shards."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump(path: Path, value: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":")) + "\n",
        encoding="utf-8",
    )


def shard_for(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[0]


def is_complete(item: dict[str, Any]) -> bool:
    return item.get("articleStatus") == 200 and all(
        item.get(key) is not None
        for key in ("hpMin", "hpMax", "atkMin", "atkMax", "defMin", "defMax")
    ) and bool(item.get("type")) and bool(item.get("effect"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="Merged Memoria directory or memoria.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive-index", type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    source_root = source if source.is_dir() else source.parent
    records_path = source / "memoria.json" if source.is_dir() else source
    source_manifest_path = source_root / "manifest.json"
    records = load(records_path)
    if not isinstance(records, list):
        raise RuntimeError("Memoria source must be a JSON array")
    if len(records) < 1000:
        raise RuntimeError(f"Memoria source is incomplete: {len(records)} records")

    source_manifest = load(source_manifest_path) if source_manifest_path.exists() else {}
    archive_by_title: dict[str, str] = {}
    if args.archive_index and args.archive_index.exists():
        for item in load(args.archive_index.resolve()):
            title = str(item.get("title") or "")
            identifier = str(item.get("id") or "")
            if title and identifier:
                archive_by_title[title] = identifier

    output = args.output.resolve()
    detail_root = output / "memoria"
    detail_root.mkdir(parents=True, exist_ok=True)
    shards: dict[str, dict[str, Any]] = {}
    index: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for source_item in records:
        item = dict(source_item)
        identifier = str(item.get("articleTitle") or item.get("key") or "").strip()
        if not identifier:
            raise RuntimeError(f"Memoria record has no stable identifier: {item}")
        if identifier in seen_ids:
            raise RuntimeError(f"duplicate Memoria identifier: {identifier}")
        seen_ids.add(identifier)
        shard = shard_for(identifier)
        complete = is_complete(item)
        image_url = item.get("imageUrl") or item.get("indexImageUrl")
        article_title = str(item.get("articleTitle") or "")
        article_id = archive_by_title.get(article_title, "")

        detail = {
            key: value
            for key, value in item.items()
            if key not in {"rawTableHtml", "descriptionHtml", "searchText", "indexImageUrl"}
        }
        detail.update({
            "id": identifier,
            "shard": shard,
            "complete": complete,
            "imageUrl": image_url,
            "articleId": article_id,
            "rawTableSha256": item.get("rawTableSha256") or "",
        })
        shards.setdefault(shard, {})[identifier] = detail

        index.append({
            "id": identifier,
            "shard": shard,
            "number": item.get("number"),
            "nameJa": item.get("nameJa") or item.get("key") or identifier,
            "nameZh": item.get("nameZh") or "",
            "rarity": item.get("rarity"),
            "type": item.get("type") or "",
            "artist": item.get("artist") or "",
            "equipLimit": item.get("equipLimit") or "",
            "obtain": item.get("obtain") or "",
            "imageUrl": image_url,
            "sourceTabs": item.get("sourceTabs") or [],
            "complete": complete,
            "articleStatus": item.get("articleStatus"),
            "articleId": article_id,
            "articleUrl": item.get("articleUrl") or "",
            "searchText": item.get("searchText") or " ".join(str(item.get(key) or "") for key in (
                "number", "nameJa", "nameZh", "artist", "rarity", "type", "equipLimit", "obtain",
                "skillName", "skillNameMax", "effect", "effectMax", "descZh", "descJa",
            )),
        })

    index.sort(key=lambda item: (
        item.get("number") is None,
        item.get("number") if item.get("number") is not None else 10**9,
        str(item.get("nameZh") or item.get("nameJa")).casefold(),
    ))
    for shard, values in sorted(shards.items()):
        dump(detail_root / f"{shard}.json", values)

    numbers = {item["number"] for item in index if item.get("number") is not None}
    types = sorted({str(item.get("type")) for item in index if item.get("type")})
    sources = sorted({str(value) for item in index for value in item.get("sourceTabs", []) if value})
    manifest = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat(),
        "source": source_manifest,
        "records": len(index),
        "uniqueNumbers": len(numbers),
        "complete": sum(bool(item["complete"]) for item in index),
        "partial": sum(not item["complete"] for item in index),
        "withImage": sum(bool(item.get("imageUrl")) for item in index),
        "withChineseName": sum(bool(item.get("nameZh")) for item in index),
        "withLocalArticle": sum(bool(item.get("articleId")) for item in index),
        "types": types,
        "sourceTabs": sources,
        "shards": len(shards),
        "shardKeys": sorted(shards),
    }
    if manifest["records"] != len(records) or manifest["shards"] > 16:
        raise RuntimeError(manifest)

    dump(output / "memoria-index.json", index)
    dump(output / "memoria-manifest.json", manifest, pretty=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
