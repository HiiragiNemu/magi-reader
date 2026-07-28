#!/usr/bin/env python3
"""Reconcile audited Magia Record CN folders that differ from JP display paths.

The complete-translation import mirrors JP folder names. MagiReader intentionally
uses a small audited allowlist of CN display folders for stories whose translated
folder title differs. This tool moves only active JSON/TXT files from the JP-named
CN duplicate into the audited CN folder. It performs a full conflict preflight
before writing and never overwrites differing content.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from generate_story_index import MAGIRECO_AUDITED_CROSS_FOLDER_GROUPS

ROOT = Path(__file__).resolve().parent
DEFAULT_CN_ROOT = ROOT / "magireco-translate-data-master" / "Scenarios_full"
ACTIVE_SUFFIXES = {".json", ".txt"}


class ReconciliationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MoveOperation:
    source: Path
    target: Path
    identical_target: bool


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def active_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in ACTIVE_SUFFIXES
        ),
        key=lambda path: path.name,
    )


def relative_label(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def build_plan(cn_root: Path) -> tuple[list[MoveOperation], list[str]]:
    operations: list[MoveOperation] = []
    notes: list[str] = []
    errors: list[str] = []

    for cn_parent, jp_parent, stems in MAGIRECO_AUDITED_CROSS_FOLDER_GROUPS:
        canonical_dir = cn_root.joinpath(*cn_parent)
        duplicate_dir = cn_root.joinpath(*jp_parent)
        canonical_label = "/".join(cn_parent)
        duplicate_label = "/".join(jp_parent)

        source_files = active_files(duplicate_dir)
        notes.append(
            f"{duplicate_label} -> {canonical_label}: "
            f"active source files={len(source_files)}"
        )

        for source in source_files:
            target = canonical_dir / source.name
            if not target.exists():
                operations.append(
                    MoveOperation(source=source, target=target, identical_target=False)
                )
                continue
            if not target.is_file():
                errors.append(f"目标不是普通文件: {relative_label(target, cn_root)}")
                continue
            if sha256(source) != sha256(target):
                errors.append(
                    "同名内容冲突，拒绝覆盖: "
                    f"{relative_label(source, cn_root)} -> "
                    f"{relative_label(target, cn_root)}"
                )
                continue
            operations.append(
                MoveOperation(source=source, target=target, identical_target=True)
            )

        # Every audited logical TXT must exist after applying the overlay plan.
        planned_targets = {operation.target for operation in operations}
        for stem in stems:
            expected = canonical_dir / f"{stem}.txt"
            if not expected.is_file() and expected not in planned_targets:
                errors.append(
                    "审计中文 TXT 在源目录和规范目录均不存在: "
                    f"{relative_label(expected, cn_root)}"
                )

    if errors:
        raise ReconciliationError("\n".join(errors))
    return operations, notes


def write_report(
    report_path: Path,
    cn_root: Path,
    operations: Iterable[MoveOperation],
    notes: Iterable[str],
    wrote: bool,
) -> None:
    operations = list(operations)
    moved = sum(not operation.identical_target for operation in operations)
    deduplicated = sum(operation.identical_target for operation in operations)
    lines = [
        "# Magia Record 中文异名目录归并报告",
        "",
        f"- 模式：{'写入' if wrote else '预演'}",
        f"- 计划/处理的活动文件：{len(operations)}",
        f"- 移入规范目录：{moved}",
        f"- 与规范目录内容相同并去重：{deduplicated}",
        "",
        "## 目录摘要",
        "",
    ]
    lines.extend(f"- {note}" for note in notes)
    lines.extend(["", "## 文件操作", ""])
    lines.extend(
        "- "
        + ("去重" if operation.identical_target else "移动")
        + ": `"
        + relative_label(operation.source, cn_root)
        + "` → `"
        + relative_label(operation.target, cn_root)
        + "`"
        for operation in operations
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cn-root",
        type=Path,
        default=DEFAULT_CN_ROOT,
        help="Magia Record 中文 Scenarios_full 根目录",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="执行移动；默认仅预演并检查冲突",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="可选 Markdown 报告输出路径",
    )
    args = parser.parse_args()

    cn_root = args.cn_root.resolve()
    if not cn_root.is_dir():
        raise ReconciliationError(f"中文 Scenarios_full 不存在: {cn_root}")

    operations, notes = build_plan(cn_root)
    print("=== 中文异名目录归并预检 ===")
    for note in notes:
        print(note)
    print(f"operations: {len(operations)}")
    print(
        "move: "
        f"{sum(not operation.identical_target for operation in operations)}"
    )
    print(
        "deduplicate: "
        f"{sum(operation.identical_target for operation in operations)}"
    )

    if args.write:
        for operation in operations:
            if operation.identical_target:
                operation.source.unlink()
                continue
            operation.target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(operation.source), str(operation.target))
        print("归并已执行；没有覆盖任何不同内容。")
    else:
        print("DRY-RUN：未修改文件。")

    if args.report:
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(
            report_path,
            cn_root,
            operations,
            notes,
            wrote=args.write,
        )
        print(f"report: {report_path}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReconciliationError as exc:
        print(f"错误: {exc}")
        raise SystemExit(2) from exc
