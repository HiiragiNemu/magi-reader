#!/usr/bin/env python3
"""Organize an immutable Wiki JP Scenario checkout for Reader production."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import organize_exedra_scenarios as organizer  # noqa: E402
from tw_official_import_core import tree_sha256  # noqa: E402


TRUSTED_SOURCE_REPOSITORY = "madoka-exedra-wiki/ma-ex-data"
LOCALIZED_SUFFIX = re.compile(
    # Exedra locale copies use a BCP-47 language + script suffix such as
    # ``_en-Latn`` or ``_zh-Hant-TW``.  Requiring the script subtag avoids
    # dropping legitimate scenario names that merely end in ``_sub``/``_adv``.
    r"_[a-z]{2,3}-[A-Za-z]{4}(?:-[A-Za-z]{2}|-[0-9]{3})?\.json$",
    re.IGNORECASE,
)


class JpSourceError(RuntimeError):
    pass


def _load_manifest(root: Path) -> dict[str, Any]:
    value = json.loads((root / organizer.MANIFEST_NAME).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("summary"), dict):
        raise JpSourceError(f"invalid organizer manifest: {root}")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def materialize(
    source_root: Path,
    output_root: Path,
    receipt_path: Path,
    *,
    source_repository: str,
    source_commit: str,
    current_root: Path | None,
) -> dict[str, Any]:
    if source_repository != TRUSTED_SOURCE_REPOSITORY:
        raise JpSourceError("JP source repository is not canonical")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise JpSourceError("source commit must be a full lowercase Git commit")
    source = source_root.resolve(strict=True)
    if output_root.exists():
        raise JpSourceError(f"refusing to reuse output root: {output_root}")

    # The commit is the immutable whole-repository pin. This additional JSON
    # tree fingerprint binds the exact Scenario inputs selected by this tool.
    organizer._plain_tree_entries(source)
    source_tree, source_count, source_bytes = tree_sha256(source)

    with tempfile.TemporaryDirectory(prefix="exedra-jp-selected-") as temporary_name:
        selected = Path(temporary_name)
        selected_count = 0
        for category in organizer.CATEGORY_ORDER:
            category_source = source / category
            if not category_source.is_dir():
                raise JpSourceError(f"missing required category: {category_source}")
            (selected / category).mkdir(parents=True)
            for path, relative, is_directory in organizer._plain_tree_entries(category_source):
                if is_directory or path.suffix.casefold() != ".json":
                    continue
                if LOCALIZED_SUFFIX.search(path.name):
                    continue
                destination = selected / category / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
                selected_count += 1
        if selected_count == 0:
            raise JpSourceError("JP selection produced no unsuffixed Scenario JSON")

        selected_tree, selected_tree_count, selected_bytes = tree_sha256(selected)
        if selected_tree_count != selected_count:
            raise JpSourceError("JP selected-tree count changed during staging")
        plan = organizer.build_plan(selected)
        proposed = organizer.manifest_for(plan)

        if current_root is not None and current_root.exists():
            current = _load_manifest(current_root)
            for field in ("sourceCount", "groupCount"):
                old = current["summary"].get(field)
                new = proposed["summary"].get(field)
                if not isinstance(old, int) or not isinstance(new, int) or new < old:
                    raise JpSourceError(
                        f"JP non-regression gate failed: {field} {new!r} < {old!r}"
                    )

        organizer.write_stage(plan, output_root)
        organizer.validate_output(plan, output_root)

    manifest_path = output_root / organizer.MANIFEST_NAME
    receipt = {
        "schemaVersion": 1,
        "sourceProvider": "exedra-wiki-jp",
        "provenance": {
            "provider": "exedra-wiki-jp",
            "locale": "ja-JP",
            "authority": "official-jp-client",
            "originalTextUnmodified": True,
        },
        "sourceRepository": source_repository,
        "sourceCommit": source_commit,
        "sourceTreeSha256": source_tree,
        "sourceFileCount": source_count,
        "sourceBytes": source_bytes,
        "selectedTreeSha256": selected_tree,
        "selectedFileCount": selected_tree_count,
        "selectedBytes": selected_bytes,
        "organizer": proposed["summary"],
        "manifestSha256": organizer.sha256_file(manifest_path),
    }
    _write_json_atomic(receipt_path, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-scenarios-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--current-root", type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = materialize(
            args.source_scenarios_root,
            args.output_root,
            args.receipt,
            source_repository=args.source_repository,
            source_commit=args.source_commit,
            current_root=args.current_root,
        )
    except (OSError, json.JSONDecodeError, RuntimeError, JpSourceError) as exc:
        print(f"JP_SOURCE_MATERIALIZATION_ERROR {exc}")
        return 1
    summary = receipt["organizer"]
    print(
        "JP_SOURCE_MATERIALIZED "
        f"commit={receipt['sourceCommit']} "
        f"sources={summary['sourceCount']} groups={summary['groupCount']} "
        f"dialogues={summary['dialogueCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
