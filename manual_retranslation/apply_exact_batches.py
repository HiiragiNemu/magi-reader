#!/usr/bin/env python3
"""Apply complete, reviewed Japanese-to-Chinese JSON field bundles fail-closed.

Each bundle is gzip+base64 JSON. It records the exact Japanese source leaf, the
previous unverified Chinese leaf, and its reviewed replacement. The applicator
changes only the ten permitted scenario text/name fields and refuses omissions,
source drift, control-code drift, or overwriting newer manual work.
"""
from __future__ import annotations

import argparse
import base64
import copy
import gzip
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

TEXT_FIELDS = {
    "textLeft", "textRight", "textCenter", "narration",
    "progressNarration", "textSelect",
}
NAME_FIELDS = {"nameLeft", "nameRight", "nameCenter", "nameNarration"}
ALLOWED_FIELDS = TEXT_FIELDS | NAME_FIELDS
TEXT_TAGS = {
    "textBlack", "textRed", "textBlue", "textGreen", "textYellow",
    "textWhite", "textGray", "textPurple", "textOrange",
}
TAG_RE = re.compile(r"\[([^\[\]]+)\]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
PLACEHOLDER_RE = re.compile(
    r"(?:\{[^{}]+\}|%(?:\d+\$)?[-+#0 ]*\d*(?:\.\d+)?[a-zA-Z]|\\[nrt])"
)


def walk_allowed(value: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[tuple[Any, ...], str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ALLOWED_FIELDS and isinstance(child, str):
                yield path + (key,), key, child
            yield from walk_allowed(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_allowed(child, path + (index,))


def get_path(root: Any, path: tuple[Any, ...]) -> Any:
    value = root
    for part in path:
        value = value[part]
    return value


def set_path(root: Any, path: tuple[Any, ...], value: str) -> None:
    target = root
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value


def mask_allowed(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: None if key in ALLOWED_FIELDS and isinstance(child, str)
            else mask_allowed(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [mask_allowed(child) for child in value]
    return value


def control_signature(text: str) -> list[tuple[str, str]]:
    signature: list[tuple[str, str]] = []
    for raw in TAG_RE.findall(text):
        name = raw.split(":", 1)[0]
        signature.append(
            (name, "<translated-visible-text>") if name in TEXT_TAGS else (name, raw)
        )
    return signature


def visible_text(text: str) -> str:
    return TAG_RE.sub("", text)


def safe_relative(value: str) -> Path:
    posix = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or "\x00" in value
        or posix.is_absolute()
        or any(part in {"", ".", ".."} for part in posix.parts)
        or posix.suffix.casefold() != ".json"
    ):
        raise RuntimeError(f"Unsafe scenario path: {value!r}")
    return Path(*posix.parts)


def decode_bundle(path: Path) -> dict[str, Any]:
    encoded = "".join(path.read_text(encoding="ascii").split())
    raw = gzip.decompress(base64.b64decode(encoded, validate=True))
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise RuntimeError(f"Unsupported exact bundle: {path}")
    if value.get("provenance") != "manual_jp_to_zh_cn":
        raise RuntimeError(f"Untrusted bundle provenance: {path}")
    if not isinstance(value.get("files"), list) or not value["files"]:
        raise RuntimeError(f"Bundle contains no files: {path}")
    return value


def normalized_path(parts: Any) -> tuple[Any, ...]:
    if not isinstance(parts, list) or not parts:
        raise RuntimeError(f"Invalid JSON leaf path: {parts!r}")
    result: list[Any] = []
    for part in parts:
        if isinstance(part, bool) or not isinstance(part, (str, int)):
            raise RuntimeError(f"Invalid JSON leaf path component: {part!r}")
        result.append(part)
    return tuple(result)


def validate_translation(relative: str, path: tuple[Any, ...], field: str, jp: str, translated: str) -> None:
    if field not in ALLOWED_FIELDS or path[-1] != field:
        raise RuntimeError(f"Non-whitelisted/mismatched field: {relative} {path!r} {field!r}")
    if KANA_RE.search(visible_text(translated)):
        raise RuntimeError(f"Visible Japanese kana remains: {relative} {path!r}: {translated!r}")
    if field in TEXT_FIELDS:
        if translated.count("@") != jp.count("@"):
            raise RuntimeError(f"@ line-break count changed: {relative} {path!r}")
        if control_signature(translated) != control_signature(jp):
            raise RuntimeError(f"Control-code signature changed: {relative} {path!r}")
        if PLACEHOLDER_RE.findall(translated) != PLACEHOLDER_RE.findall(jp):
            raise RuntimeError(f"Placeholder sequence changed: {relative} {path!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--bundle-root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    bundle_root = (args.bundle_root or repo / "manual_retranslation" / "exact_bundles").resolve()
    jp_root = repo / "magireco-source-master" / "Scenarios_full"
    cn_root = repo / "magireco-translate-data-master" / "Scenarios_full"
    bundle_paths = sorted(bundle_root.rglob("*.json.gz.b64"))
    if not bundle_paths:
        raise RuntimeError(f"No exact translation bundles found below {bundle_root}")

    merged: dict[str, dict[str, Any]] = {}
    batch_ids: list[str] = []
    story_ids: set[str] = set()
    for bundle_path in bundle_paths:
        bundle = decode_bundle(bundle_path)
        batch_id = str(bundle.get("batch_id") or bundle_path.stem)
        batch_ids.append(batch_id)
        stories = bundle.get("stories")
        if isinstance(stories, list):
            for item in stories:
                if isinstance(item, dict) and item.get("story_id") is not None:
                    story_ids.add(str(item["story_id"]))
        for record in bundle["files"]:
            if not isinstance(record, dict):
                raise RuntimeError(f"Invalid file record in {bundle_path}")
            relative = str(record.get("relative") or "")
            safe_relative(relative)
            entries = record.get("entries")
            if not isinstance(entries, list) or not entries:
                raise RuntimeError(f"No field entries for {relative} in {bundle_path}")
            if relative in merged:
                raise RuntimeError(f"Scenario JSON appears in more than one exact bundle: {relative}")
            merged[relative] = {"entries": entries, "batch": batch_id}

    file_reports: list[dict[str, Any]] = []
    changed_fields = 0
    already_applied = 0
    for relative, record in sorted(merged.items()):
        rel_path = safe_relative(relative)
        jp_path = jp_root / rel_path
        cn_path = cn_root / rel_path
        if not jp_path.is_file() or not cn_path.is_file():
            raise RuntimeError(f"Missing paired scenario JSON: {relative}")

        jp = json.loads(jp_path.read_text(encoding="utf-8"))
        old_cn_doc = json.loads(cn_path.read_text(encoding="utf-8"))
        new_cn_doc = copy.deepcopy(old_cn_doc)
        jp_leaves = {path: (field, value) for path, field, value in walk_allowed(jp)}
        cn_leaves = {path: (field, value) for path, field, value in walk_allowed(old_cn_doc)}
        if jp_leaves.keys() != cn_leaves.keys():
            raise RuntimeError(f"Japanese/Chinese allowed-field structure differs: {relative}")

        supplied: dict[tuple[Any, ...], dict[str, Any]] = {}
        for entry in record["entries"]:
            if not isinstance(entry, dict):
                raise RuntimeError(f"Invalid field entry: {relative}")
            path = normalized_path(entry.get("path"))
            if path in supplied:
                raise RuntimeError(f"Duplicate field path: {relative} {path!r}")
            supplied[path] = entry
        if supplied.keys() != jp_leaves.keys():
            missing = sorted((repr(path) for path in jp_leaves.keys() - supplied.keys()))
            extra = sorted((repr(path) for path in supplied.keys() - jp_leaves.keys()))
            raise RuntimeError(
                f"Incomplete exact bundle for {relative}: missing={missing[:10]}, extra={extra[:10]}"
            )

        file_changed = 0
        file_already = 0
        for path, (jp_field, jp_value) in jp_leaves.items():
            entry = supplied[path]
            field = entry.get("field")
            expected_jp = entry.get("jp")
            recorded_old = entry.get("old_cn")
            translated = entry.get("translation")
            if not all(isinstance(value, str) for value in (field, expected_jp, recorded_old, translated)):
                raise RuntimeError(f"Non-string exact bundle field: {relative} {path!r}")
            if field != jp_field or expected_jp != jp_value:
                raise RuntimeError(f"Japanese source drift: {relative} {path!r}")
            validate_translation(relative, path, field, jp_value, translated)
            current = get_path(new_cn_doc, path)
            if current == translated:
                file_already += 1
                already_applied += 1
            elif current == recorded_old:
                set_path(new_cn_doc, path, translated)
                file_changed += 1
                changed_fields += 1
            else:
                raise RuntimeError(
                    f"Refusing to overwrite newer/manual value: {relative} {path!r}; "
                    f"current={current!r}, recorded_old={recorded_old!r}, translation={translated!r}"
                )

        if mask_allowed(old_cn_doc) != mask_allowed(new_cn_doc):
            raise RuntimeError(f"Non-translatable data changed: {relative}")
        if json.loads(json.dumps(new_cn_doc, ensure_ascii=False)) != new_cn_doc:
            raise RuntimeError(f"JSON round-trip failed: {relative}")
        if file_changed:
            cn_path.write_text(json.dumps(new_cn_doc, ensure_ascii=False, indent=1), encoding="utf-8")
        file_reports.append({
            "path": relative,
            "allowed_fields": len(jp_leaves),
            "changed_fields": file_changed,
            "already_applied_fields": file_already,
            "batch": record["batch"],
        })

    report = {
        "status": "ok",
        "provenance": "manual_jp_to_zh_cn",
        "batch_ids": batch_ids,
        "story_ids": sorted(story_ids),
        "story_count": len(story_ids),
        "scenario_json_files": len(file_reports),
        "reviewed_allowed_fields": sum(item["allowed_fields"] for item in file_reports),
        "changed_fields": changed_fields,
        "already_applied_fields": already_applied,
        "files": file_reports,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"exact manual retranslation apply failed: {exc}", file=sys.stderr)
        raise
