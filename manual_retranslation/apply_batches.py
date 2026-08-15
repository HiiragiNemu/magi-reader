#!/usr/bin/env python3
"""Apply reviewed Japanese-to-Chinese scenario translation maps without altering game data.

Each batch JSON is an object whose keys are ``<scenario-stem>:<1-based text index>``.
The index is counted in JSON insertion order over visible scenario text fields only.
Speaker-name fields are deliberately not modified by this script; they must be reviewed
separately whenever a batch requires name corrections.
"""

from __future__ import annotations

import argparse
import base64
import copy
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

TEXT_FIELDS = {
    "textLeft",
    "textRight",
    "textCenter",
    "narration",
    "progressNarration",
    "textSelect",
}
NAME_FIELDS = {
    "nameLeft",
    "nameRight",
    "nameCenter",
    "nameNarration",
}
ALLOWED_FIELDS = TEXT_FIELDS | NAME_FIELDS
TEXT_TAGS = {
    "textBlack",
    "textRed",
    "textBlue",
    "textGreen",
    "textYellow",
    "textWhite",
    "textGray",
    "textPurple",
    "textOrange",
}
TAG_RE = re.compile(r"\[([^\[\]]+)\]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
PLACEHOLDER_RE = re.compile(
    r"(?:\{[^{}]+\}|%(?:\d+\$)?[-+#0 ]*\d*(?:\.\d+)?[a-zA-Z]|\\[nrt])"
)


def walk_text_fields(value: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[tuple[Any, ...], str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in TEXT_FIELDS and isinstance(child, str):
                yield path + (key,), key, child
            yield from walk_text_fields(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_text_fields(child, path + (index,))


def mask_allowed(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: None if key in ALLOWED_FIELDS and isinstance(child, str) else mask_allowed(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [mask_allowed(child) for child in value]
    return value


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


def control_signature(text: str) -> list[tuple[str, str]]:
    signature: list[tuple[str, str]] = []
    for raw in TAG_RE.findall(text):
        name = raw.split(":", 1)[0]
        if name in TEXT_TAGS:
            signature.append((name, "<translated-visible-text>"))
        else:
            signature.append((name, raw))
    return signature


def visible_text(text: str) -> str:
    return TAG_RE.sub("", text)


def load_maps(batch_root: Path, bundle_root: Path) -> dict[str, dict[int, str]]:
    by_stem: dict[str, dict[int, str]] = defaultdict(dict)
    sources: list[tuple[str, Any]] = []

    for batch_file in sorted(batch_root.glob("*/*.json")):
        sources.append((str(batch_file), json.loads(batch_file.read_text(encoding="utf-8"))))

    for bundle_dir in sorted(path for path in bundle_root.iterdir() if path.is_dir()):
        part_files = sorted(bundle_dir.glob("*.b64"))
        if not part_files:
            continue
        encoded = "".join(part.read_text(encoding="ascii").strip() for part in part_files)
        decoded = gzip.decompress(base64.b64decode(encoded)).decode("utf-8")
        sources.append((str(bundle_dir), json.loads(decoded)))

    if not sources:
        raise RuntimeError(
            f"No reviewed translation maps found below {batch_root} or {bundle_root}"
        )

    for source_name, data in sources:
        if not isinstance(data, dict):
            raise RuntimeError(f"Batch must be a JSON object: {source_name}")
        for identifier, translation in data.items():
            if not isinstance(identifier, str) or ":" not in identifier:
                raise RuntimeError(f"Invalid batch key in {source_name}: {identifier!r}")
            stem, index_text = identifier.rsplit(":", 1)
            try:
                index = int(index_text)
            except ValueError as exc:
                raise RuntimeError(f"Invalid text index in {source_name}: {identifier!r}") from exc
            if index < 1 or not isinstance(translation, str):
                raise RuntimeError(f"Invalid translation entry in {source_name}: {identifier!r}")
            if index in by_stem[stem] and by_stem[stem][index] != translation:
                raise RuntimeError(f"Conflicting translations for {identifier}")
            by_stem[stem][index] = translation
    return dict(by_stem)


def unique_file(root: Path, stem: str) -> Path:
    matches = list(root.glob(f"**/{stem}.json"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {stem}.json below {root}, found {len(matches)}")
    return matches[0]


def apply_one(
    stem: str,
    translations: dict[int, str],
    jp_root: Path,
    cn_root: Path,
) -> dict[str, Any]:
    jp_path = unique_file(jp_root, stem)
    relative_path = jp_path.relative_to(jp_root)
    cn_path = cn_root / relative_path
    if not cn_path.is_file():
        raise RuntimeError(f"Missing paired Chinese JSON: {cn_path}")

    jp = json.loads(jp_path.read_text(encoding="utf-8"))
    old_cn = json.loads(cn_path.read_text(encoding="utf-8"))
    new_cn = copy.deepcopy(old_cn)

    jp_leaves = list(walk_text_fields(jp))
    old_leaves = list(walk_text_fields(old_cn))
    if [(path, key) for path, key, _ in jp_leaves] != [(path, key) for path, key, _ in old_leaves]:
        raise RuntimeError(f"Japanese/Chinese text-field structure differs: {relative_path}")

    expected = set(range(1, len(jp_leaves) + 1))
    supplied = set(translations)
    if supplied != expected:
        missing = sorted(expected - supplied)
        extra = sorted(supplied - expected)
        raise RuntimeError(
            f"Incomplete map for {relative_path}: expected={len(expected)}, supplied={len(supplied)}, "
            f"missing={missing[:20]}, extra={extra[:20]}"
        )

    changed = 0
    for index, (path, _key, jp_text) in enumerate(jp_leaves, start=1):
        translated = translations[index]
        old_text = get_path(old_cn, path)
        if translated.count("@") != jp_text.count("@"):
            raise RuntimeError(f"@ line-break count changed: {relative_path} text #{index}")
        if control_signature(translated) != control_signature(jp_text):
            raise RuntimeError(f"Control-code signature changed: {relative_path} text #{index}")
        if PLACEHOLDER_RE.findall(translated) != PLACEHOLDER_RE.findall(jp_text):
            raise RuntimeError(f"Placeholder sequence changed: {relative_path} text #{index}")
        if KANA_RE.search(visible_text(translated)):
            raise RuntimeError(f"Visible Japanese kana remains: {relative_path} text #{index}: {translated!r}")
        set_path(new_cn, path, translated)
        if translated != old_text:
            changed += 1

    if mask_allowed(old_cn) != mask_allowed(new_cn):
        raise RuntimeError(f"A non-translatable field changed: {relative_path}")

    reparsed = json.loads(json.dumps(new_cn, ensure_ascii=False))
    if reparsed != new_cn:
        raise RuntimeError(f"JSON round-trip failed: {relative_path}")

    cn_path.write_text(json.dumps(new_cn, ensure_ascii=False, indent=1), encoding="utf-8")
    return {
        "path": relative_path.as_posix(),
        "text_fields": len(jp_leaves),
        "changed_vs_previous_cn": changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--batch-root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    batch_root = (args.batch_root or repo_root / "manual_retranslation" / "batches").resolve()
    bundle_root = repo_root / "manual_retranslation" / "bundles"
    jp_root = repo_root / "magireco-source-master" / "Scenarios_full"
    cn_root = repo_root / "magireco-translate-data-master" / "Scenarios_full"
    if not jp_root.is_dir() or not cn_root.is_dir():
        raise RuntimeError(
            "Expected magireco-source-master/Scenarios_full and "
            "magireco-translate-data-master/Scenarios_full below repo root"
        )

    maps = load_maps(batch_root, bundle_root)
    results = [apply_one(stem, maps[stem], jp_root, cn_root) for stem in sorted(maps)]
    report = {
        "status": "ok",
        "scenario_json_files": len(results),
        "translated_text_fields": sum(item["text_fields"] for item in results),
        "changed_vs_previous_cn": sum(item["changed_vs_previous_cn"] for item in results),
        "files": results,
    }
    report_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report_text, encoding="utf-8")
    print(report_text, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # fail closed in CI
        print(f"manual retranslation apply failed: {exc}", file=sys.stderr)
        raise
