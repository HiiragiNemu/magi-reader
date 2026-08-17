#!/usr/bin/env python3
"""Apply exact field-level restorations recovered from trusted human Chinese sources.

The trusted-memory artifact contains full candidate JSON files in which only leaves
supported by an older trusted human translation were replaced. This script derives
the exact delta against the branch starting commit, then applies it only when the
current branch still contains the recorded unverified value. Newer manual work wins.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
from pathlib import Path
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


def walk_allowed(value: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[tuple[Any, ...], str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ALLOWED_FIELDS and isinstance(child, str):
                yield path + (key,), child
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


def load_json_at_ref(repo: Path, ref: str, path: str) -> Any:
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{path}"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return json.loads(result.stdout.decode("utf-8"))


def validate_replacement(relative: str, path: tuple[Any, ...], jp_text: str, translated: str) -> None:
    field = path[-1]
    if field not in ALLOWED_FIELDS:
        raise RuntimeError(f"Non-whitelisted field in delta: {relative} {path!r}")
    if translated.count("@") != jp_text.count("@"):
        raise RuntimeError(f"@ count changed: {relative} {path!r}")
    if control_signature(translated) != control_signature(jp_text):
        raise RuntimeError(f"Control-code signature changed: {relative} {path!r}")
    if PLACEHOLDER_RE.findall(translated) != PLACEHOLDER_RE.findall(jp_text):
        raise RuntimeError(f"Placeholder sequence changed: {relative} {path!r}")
    if KANA_RE.search(visible_text(translated)):
        raise RuntimeError(f"Visible kana remains: {relative} {path!r}: {translated!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--patch-root", type=Path, required=True)
    parser.add_argument("--base-ref", default="365ee868107ffae44bd8263a5123a2853e30abd6")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    patch_root = args.patch_root.resolve()
    jp_root = repo / "magireco-source-master" / "Scenarios_full"
    cn_root = repo / "magireco-translate-data-master" / "Scenarios_full"

    changed_files: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    already_applied = 0
    applied_fields = 0
    trusted_delta_fields = 0

    patch_files = sorted(patch_root.rglob("*.json"))
    if not patch_files:
        raise RuntimeError(f"No trusted-memory patch JSON found below {patch_root}")

    for patch_path in patch_files:
        relative = patch_path.relative_to(patch_root).as_posix()
        repo_path = f"magireco-translate-data-master/Scenarios_full/{relative}"
        jp_path = jp_root / relative
        cn_path = cn_root / relative
        if not jp_path.is_file() or not cn_path.is_file():
            raise RuntimeError(f"Missing paired JSON: {relative}")

        baseline = load_json_at_ref(repo, args.base_ref, repo_path)
        trusted = json.loads(patch_path.read_text(encoding="utf-8"))
        jp = json.loads(jp_path.read_text(encoding="utf-8"))
        old_cn = json.loads(cn_path.read_text(encoding="utf-8"))
        new_cn = copy.deepcopy(old_cn)

        if mask_allowed(baseline) != mask_allowed(trusted):
            raise RuntimeError(f"Trusted patch changes non-translatable data: {relative}")

        baseline_leaves = dict(walk_allowed(baseline))
        trusted_leaves = dict(walk_allowed(trusted))
        jp_leaves = dict(walk_allowed(jp))
        if baseline_leaves.keys() != trusted_leaves.keys() or baseline_leaves.keys() != jp_leaves.keys():
            raise RuntimeError(f"Allowed-field structure differs: {relative}")

        file_applied = 0
        for path, recorded_old in baseline_leaves.items():
            trusted_value = trusted_leaves[path]
            if trusted_value == recorded_old:
                continue
            trusted_delta_fields += 1
            current_value = get_path(new_cn, path)
            jp_value = jp_leaves[path]
            validate_replacement(relative, path, jp_value, trusted_value)

            if current_value == trusted_value:
                already_applied += 1
                continue
            if current_value != recorded_old:
                conflicts.append({
                    "file": relative,
                    "path": list(path),
                    "recorded_unverified": recorded_old,
                    "current_manual": current_value,
                    "trusted_memory": trusted_value,
                })
                continue
            set_path(new_cn, path, trusted_value)
            file_applied += 1
            applied_fields += 1

        if mask_allowed(old_cn) != mask_allowed(new_cn):
            raise RuntimeError(f"Non-translatable data changed: {relative}")
        if json.loads(json.dumps(new_cn, ensure_ascii=False)) != new_cn:
            raise RuntimeError(f"JSON round-trip failed: {relative}")
        if file_applied:
            cn_path.write_text(json.dumps(new_cn, ensure_ascii=False, indent=1), encoding="utf-8")
            changed_files.append({"file": relative, "applied_fields": file_applied})

    report = {
        "status": "ok",
        "source": "trusted human translation memory only",
        "patch_json_files": len(patch_files),
        "trusted_delta_fields": trusted_delta_fields,
        "changed_json_files": len(changed_files),
        "applied_fields": applied_fields,
        "already_applied_fields": already_applied,
        "newer_manual_conflicts_skipped": len(conflicts),
        "changed_files": changed_files,
        "conflicts": conflicts,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
