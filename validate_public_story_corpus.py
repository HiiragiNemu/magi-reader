#!/usr/bin/env python3
"""Validate the generated public story catalogue and the retained raw JSON trees."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit


REQUIRED_MAGIRECO = {"main_story", "event_story", "character_story"}
REQUIRED_EXEDRA = {"exedra_main", "exedra_character"}
RAW_JSON_ROOTS = {
    "magireco_jp": Path("magireco-source-master/Scenarios_full"),
    "magireco_cn": Path("magireco-translate-data-master/Scenarios_full"),
    "exedra_jp": Path("magiraexedra-source-master/Scenarios_full"),
    "exedra_cn": Path("magiraexedra-translate-data-master/Scenarios_full"),
}
RAW_TXT_ROOTS = {
    "magireco_jp": Path("magireco-source-master/Scenarios_full"),
    "magireco_cn": Path("magireco-translate-data-master/Scenarios_full"),
    "exedra_jp": Path("magiraexedra-source-master/Scenarios_full"),
    "exedra_cn": Path("magiraexedra-translate-data-master/Scenarios_full"),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, default=Path("website/public"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    public = args.public.resolve()
    stories = json.loads((public / "story_index.json").read_text(encoding="utf-8"))
    if not isinstance(stories, list) or not stories:
        raise RuntimeError("story index is empty or invalid")

    identifiers = [str(item.get("id") or "") for item in stories]
    if not all(identifiers) or len(identifiers) != len(set(value.casefold() for value in identifiers)):
        raise RuntimeError("story index contains empty or duplicate ids")

    categories = Counter(str(item.get("category") or "") for item in stories)
    magireco = [item for item in stories if not str(item.get("category", "")).startswith("exedra_")]
    exedra = [item for item in stories if str(item.get("category", "")).startswith("exedra_")]
    if not magireco or not exedra:
        raise RuntimeError(f"missing story system: magireco={len(magireco)} exedra={len(exedra)}")
    if not REQUIRED_MAGIRECO <= set(categories):
        raise RuntimeError(f"missing Magia Record categories: {REQUIRED_MAGIRECO - set(categories)}")
    if not REQUIRED_EXEDRA <= set(categories):
        raise RuntimeError(f"missing Exedra categories: {REQUIRED_EXEDRA - set(categories)}")

    referenced: set[Path] = set()
    source_formats: Counter[str] = Counter()
    for item in stories:
        paths = [item.get("path_cn"), item.get("path_jp")]
        if not any(paths):
            raise RuntimeError(f"story has no source: {item.get('id')}")
        for key, raw_path in zip(("path_cn", "path_jp"), paths):
            if not raw_path:
                continue
            value = str(raw_path)
            split = urlsplit(value)
            if split.scheme or split.netloc or split.query or split.fragment:
                raise RuntimeError(f"external or decorated story path: {item.get('id')} {key}={value}")
            if not split.path.startswith("/data/"):
                raise RuntimeError(f"story path is outside /data/: {item.get('id')} {key}={value}")
            decoded = unquote(split.path.lstrip("/"))
            if any(part in {"", ".", ".."} for part in Path(decoded).parts):
                raise RuntimeError(f"unsafe story path: {item.get('id')} {key}={value}")
            local = public / decoded
            if not local.is_file() or local.stat().st_size <= 0:
                raise RuntimeError(f"indexed source missing or empty: {item.get('id')} {key}={local}")
            referenced.add(local.resolve())
            source_formats[local.suffix.lower()] += 1

    # The stable public catalogue intentionally points at consolidated TXT.
    # Raw game JSON is audited separately and can be exposed as provenance data.
    if set(source_formats) != {".txt"}:
        raise RuntimeError(f"unexpected reader source formats: {dict(source_formats)}")

    published_txt = [
        path for path in (public / "data").rglob("*.txt")
        if path.is_file()
    ]
    published_empty_txt = [
        path for path in published_txt
        if path.stat().st_size <= 0
    ]
    if published_empty_txt:
        raise RuntimeError(
            "public data tree contains empty TXT files: "
            + ", ".join(str(path) for path in published_empty_txt[:50])
        )

    raw_json_counts: dict[str, int] = {}
    raw_json_bytes: dict[str, int] = {}
    for label, source in RAW_JSON_ROOTS.items():
        root = source.resolve()
        if not root.exists():
            raw_json_counts[label] = 0
            raw_json_bytes[label] = 0
            continue
        files = [
            path for path in root.rglob("*.json")
            if path.is_file()
            and not path.name.endswith(".import-report.json")
            and path.name not in {"exedra_manifest.json", "story_ids.generated.json"}
        ]
        raw_json_counts[label] = len(files)
        raw_json_bytes[label] = sum(path.stat().st_size for path in files)

    for required in ("magireco_jp", "magireco_cn", "exedra_jp"):
        if raw_json_counts.get(required, 0) <= 0:
            raise RuntimeError(f"raw JSON tree is missing: {required}")

    raw_txt_counts: dict[str, int] = {}
    raw_empty_txt_counts: dict[str, int] = {}
    raw_empty_txt_sample: dict[str, list[str]] = {}
    for label, source in RAW_TXT_ROOTS.items():
        root = source.resolve()
        files = [path for path in root.rglob("*.txt") if path.is_file()] if root.exists() else []
        empty = [path for path in files if path.stat().st_size <= 0]
        raw_txt_counts[label] = len(files)
        raw_empty_txt_counts[label] = len(empty)
        raw_empty_txt_sample[label] = [str(path) for path in empty[:20]]

    report = {
        "stories": len(stories),
        "magireco": len(magireco),
        "exedra": len(exedra),
        "categories": dict(sorted(categories.items())),
        "readerSourceFiles": len(referenced),
        "readerSourceFormats": dict(source_formats),
        "publishedTxtFiles": len(published_txt),
        "publishedEmptyTxtFiles": len(published_empty_txt),
        "rawJsonFiles": raw_json_counts,
        "rawJsonBytes": raw_json_bytes,
        "rawTxtFiles": raw_txt_counts,
        "rawEmptyTxtFiles": raw_empty_txt_counts,
        "rawEmptyTxtSample": raw_empty_txt_sample,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
