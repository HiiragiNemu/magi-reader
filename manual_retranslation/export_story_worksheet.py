#!/usr/bin/env python3
"""Export aligned Japanese/current-Chinese text fields for manual translation.

This script is read-only. It never modifies scenario JSON files. The output is
intended to be filled by a human translator and then converted into an exact
bundle after review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

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


@dataclass(frozen=True)
class TextField:
    path: tuple[str | int, ...]
    key: str
    value: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export JP/CN scenario fields for manual retranslation."
    )
    parser.add_argument(
        "selectors",
        nargs="+",
        help=(
            "Relative JSON path(s), filename stem(s), or story ID(s). "
            "A selector such as 310211 exports every matching 310211*.json file."
        ),
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("magireco-source-master/Scenarios_full"),
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=Path("magireco-translate-data-master/Scenarios_full"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("manual_retranslation/worksheets"),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing worksheet with the same generated name.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def collect_fields(node: Any, path: tuple[str | int, ...] = ()) -> list[TextField]:
    result: list[TextField] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = path + (key,)
            if key in ALLOWED_FIELDS:
                if not isinstance(value, str):
                    raise TypeError(f"allowed field is not a string at {child!r}")
                result.append(TextField(child, key, value))
            elif isinstance(value, (dict, list)):
                result.extend(collect_fields(value, child))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            result.extend(collect_fields(value, path + (index,)))
    return result


def pointer(path: Sequence[str | int]) -> str:
    encoded: list[str] = []
    for part in path:
        if isinstance(part, int):
            encoded.append(str(part))
        else:
            encoded.append(part.replace("~", "~0").replace("/", "~1"))
    return "/" + "/".join(encoded)


def normalize(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def all_json_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise FileNotFoundError(f"scenario root does not exist: {root}")
    return sorted(root.rglob("*.json"), key=lambda item: item.as_posix())


def resolve_selector(selector: str, source_root: Path, source_files: list[Path]) -> list[Path]:
    normalized = normalize(selector)
    direct = source_root / normalized
    if direct.is_file():
        return [direct]

    selector_path = Path(normalized)
    name = selector_path.name
    stem = selector_path.stem if selector_path.suffix.lower() == ".json" else name

    matches: list[Path] = []
    for path in source_files:
        relative = path.relative_to(source_root).as_posix()
        if normalized == relative:
            matches.append(path)
            continue
        if path.name == name and selector_path.suffix.lower() == ".json":
            matches.append(path)
            continue
        if path.stem == stem or path.stem.startswith(stem + "-") or path.stem.startswith(stem + "_"):
            matches.append(path)

    unique = sorted(set(matches), key=lambda item: item.as_posix())
    if not unique:
        raise FileNotFoundError(f"selector did not match a Japanese JSON file: {selector}")
    return unique


def safe_slug(selectors: Sequence[str]) -> str:
    text = "__".join(Path(normalize(value)).stem for value in selectors)
    filtered = "".join(char if char.isalnum() or char in "-_" else "-" for char in text)
    filtered = "-".join(part for part in filtered.split("-") if part)
    return filtered[:160] or "worksheet"


def export(args: argparse.Namespace) -> tuple[Path, Path]:
    source_root: Path = args.source_root
    target_root: Path = args.target_root
    source_files = all_json_files(source_root)

    selected: list[Path] = []
    for selector in args.selectors:
        selected.extend(resolve_selector(selector, source_root, source_files))
    selected = sorted(set(selected), key=lambda item: item.as_posix())

    documents: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    ordinal = 0

    for source_path in selected:
        relative = source_path.relative_to(source_root)
        target_path = target_root / relative
        if not target_path.is_file():
            raise FileNotFoundError(f"matching Chinese JSON does not exist: {target_path}")

        source = load_json(source_path)
        target = load_json(target_path)
        source_fields = collect_fields(source)
        target_fields = collect_fields(target)

        source_paths = [field.path for field in source_fields]
        target_paths = [field.path for field in target_fields]
        if source_paths != target_paths:
            raise AssertionError(f"JP/CN allowed-field paths differ: {relative}")

        file_entries: list[dict[str, Any]] = []
        for file_ordinal, (jp_field, cn_field) in enumerate(
            zip(source_fields, target_fields), start=1
        ):
            ordinal += 1
            entry = {
                "ordinal": ordinal,
                "file_ordinal": file_ordinal,
                "pointer": pointer(jp_field.path),
                "field": jp_field.key,
                "jp": jp_field.value,
                "current_zh_cn": cn_field.value,
                "zh_cn": "",
                "review_status": "untranslated",
                "translator_note": "",
            }
            file_entries.append(entry)
            rows.append(
                {
                    "ordinal": ordinal,
                    "relative_path": relative.as_posix(),
                    **entry,
                }
            )

        documents.append(
            {
                "relative_path": relative.as_posix(),
                "source_sha256": sha256(source_path),
                "current_cn_sha256": sha256(target_path),
                "field_count": len(file_entries),
                "entries": file_entries,
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    slug = safe_slug(args.selectors)
    json_path = args.output_dir / f"{slug}.worksheet.json"
    tsv_path = args.output_dir / f"{slug}.worksheet.tsv"
    if not args.force:
        for path in (json_path, tsv_path):
            if path.exists():
                raise FileExistsError(f"output already exists; use --force: {path}")

    payload = {
        "schema_version": 1,
        "provenance": "manual_jp_to_zh_cn_worksheet",
        "selectors": list(args.selectors),
        "source_root": source_root.as_posix(),
        "target_root": target_root.as_posix(),
        "file_count": len(documents),
        "field_count": ordinal,
        "allowed_fields": sorted(ALLOWED_FIELDS),
        "files": documents,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    columns = [
        "ordinal",
        "relative_path",
        "file_ordinal",
        "pointer",
        "field",
        "jp",
        "current_zh_cn",
        "zh_cn",
        "review_status",
        "translator_note",
    ]
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    return json_path, tsv_path


def main() -> int:
    try:
        args = parse_args()
        json_path, tsv_path = export(args)
    except Exception as exc:  # noqa: BLE001 - CLI should present a concise failure
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json_path)
    print(tsv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
