#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path.cwd()
SOURCE_PREFIX = "magireco-translate-data-master/Scenarios_full/"
SOURCE_ROOT = ROOT / SOURCE_PREFIX
HUMAN_ONLY_PREFIXES = (
    "main_story/",
    "Scene0主线/",
    "scene0_main/",
)


class RebuildError(RuntimeError):
    pass


def run_git(*args: str, capture: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=ROOT,
        check=False,
        capture_output=capture,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode:
        detail = proc.stderr.strip() if capture else "git command failed"
        raise RebuildError(detail or "git command failed")
    return proc.stdout if capture else ""


def git_tree(ref: str) -> dict[str, str]:
    output = run_git(
        "ls-tree",
        "-r",
        "-z",
        "--format=%(objectname)\t%(path)",
        ref,
        "--",
        SOURCE_PREFIX,
    )
    result: dict[str, str] = {}
    for record in output.split("\0"):
        if not record:
            continue
        sha, path = record.split("\t", 1)
        result[path] = sha
    return result


def blob_hash(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def filesystem_tree() -> dict[str, str]:
    if not SOURCE_ROOT.is_dir():
        raise RebuildError(f"source root missing: {SOURCE_ROOT}")
    result: dict[str, str] = {}
    for path in sorted(SOURCE_ROOT.rglob("*")):
        if path.is_file():
            result[path.relative_to(ROOT).as_posix()] = blob_hash(path.read_bytes())
    return result


def classify(
    baseline: dict[str, str], source: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    baseline_paths = set(baseline)
    source_paths = set(source)
    added = sorted(source_paths - baseline_paths)
    overwritten = sorted(
        path
        for path in baseline_paths & source_paths
        if baseline[path] != source[path]
    )
    deleted = sorted(baseline_paths - source_paths)
    return added, overwritten, deleted


def relative(path: str) -> str:
    if not path.startswith(SOURCE_PREFIX):
        raise RebuildError(f"outside source root: {path}")
    return path[len(SOURCE_PREFIX):]


def is_human_only_added(path: str) -> bool:
    rel = relative(path)
    return any(rel.startswith(prefix) for prefix in HUMAN_ONLY_PREFIXES)


def repair_tree(baseline_ref: str, source_ref: str, report_path: Path) -> dict[str, Any]:
    baseline_sha = run_git("rev-parse", baseline_ref).strip()
    source_sha = run_git("rev-parse", source_ref).strip()
    run_git("merge-base", "--is-ancestor", baseline_sha, source_sha)

    baseline = git_tree(baseline_sha)
    source = git_tree(source_sha)
    added, overwritten, deleted = classify(baseline, source)

    run_git("rm", "-r", "-q", "--ignore-unmatch", SOURCE_PREFIX.rstrip("/"))
    run_git(
        "restore",
        f"--source={baseline_sha}",
        "--staged",
        "--worktree",
        "--",
        SOURCE_PREFIX,
    )

    if added:
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            pathspec_path = Path(handle.name)
            handle.write(b"\0".join(path.encode("utf-8") for path in added) + b"\0")
        try:
            run_git(
                "restore",
                f"--source={source_sha}",
                "--staged",
                "--worktree",
                f"--pathspec-from-file={pathspec_path}",
                "--pathspec-file-nul",
            )
        finally:
            pathspec_path.unlink(missing_ok=True)

    repaired = filesystem_tree()
    expected = dict(baseline)
    expected.update({path: source[path] for path in added})
    if repaired != expected:
        missing = sorted(set(expected) - set(repaired))
        extra = sorted(set(repaired) - set(expected))
        changed = sorted(
            path
            for path in set(expected) & set(repaired)
            if expected[path] != repaired[path]
        )
        raise RebuildError(
            "repaired tree mismatch: "
            f"missing={len(missing)} extra={len(extra)} changed={len(changed)}"
        )

    added_txt = [path for path in added if path.lower().endswith(".txt")]
    added_json = [path for path in added if path.lower().endswith(".json")]
    human_only_added_txt = [path for path in added_txt if is_human_only_added(path)]
    machine_added_txt = [path for path in added_txt if not is_human_only_added(path)]
    report: dict[str, Any] = {
        "schema": 1,
        "trusted_baseline_ref": baseline_ref,
        "trusted_baseline_sha": baseline_sha,
        "source_ref": source_ref,
        "source_sha": source_sha,
        "trusted_baseline_file_total": len(baseline),
        "source_file_total_before_repair": len(source),
        "repaired_file_total": len(repaired),
        "added_file_total": len(added),
        "added_json_total": len(added_json),
        "added_txt_total": len(added_txt),
        "human_only_added_txt_total": len(human_only_added_txt),
        "machine_added_txt_total": len(machine_added_txt),
        "restored_overwritten_human_txt_total": sum(
            path.lower().endswith(".txt") for path in overwritten
        ),
        "restored_deleted_human_txt_total": sum(
            path.lower().endswith(".txt") for path in deleted
        ),
        "added_paths": added,
        "added_json_paths": added_json,
        "added_txt_paths": added_txt,
        "human_only_added_txt_paths": human_only_added_txt,
        "machine_added_txt_paths": machine_added_txt,
        "restored_overwritten_paths": overwritten,
        "restored_deleted_paths": deleted,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "REPAIRED_TRANSLATION_TREE "
        f"baseline={len(baseline)} added={len(added)} repaired={len(repaired)} "
        f"restored_overwritten={len(overwritten)} restored_deleted={len(deleted)} "
        f"machine_txt={len(machine_added_txt)} human_main_txt={len(human_only_added_txt)}"
    )
    return report


def deterministic_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.date_time = (2026, 7, 27, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def package_release(report_path: Path, output_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    baseline = git_tree(report["trusted_baseline_sha"])
    source = git_tree(report["source_sha"])
    repaired = filesystem_tree()
    added = report["added_paths"]
    expected = dict(baseline)
    expected.update({path: source[path] for path in added})
    if repaired != expected:
        raise RebuildError("working tree changed after trusted repair")

    readme = (
        "魔法纪录剧情中文补齐：可信 main 差值修正版\n\n"
        "可信规则：\n"
        "1. main 中存在的所有魔法纪录源文件均视为官方或人工译文，必须逐字节保留。\n"
        "2. 当前分支覆盖或删除 main 文件的内容全部被恢复。\n"
        "3. 只有 main 中不存在的新增文件进入差值集合。\n"
        "4. main_story、Scene0主线、scene0_main 的新增聚合 TXT 仍视为人工主线，不列为机器翻译。\n"
        "5. 本压缩包不包含任何 Exedra 文件。\n\n"
        f"main SHA: {report['trusted_baseline_sha']}\n"
        f"来源 SHA: {report['source_sha']}\n"
        f"恢复被覆盖人工文件: {len(report['restored_overwritten_paths'])}\n"
        f"恢复被删除人工文件: {len(report['restored_deleted_paths'])}\n"
        f"新增机器翻译 TXT 候选: {report['machine_added_txt_total']}\n"
        f"新增但属于人工主线的 TXT: {report['human_only_added_txt_total']}\n"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(repaired):
            data = (ROOT / path).read_bytes()
            archive.writestr(deterministic_zip_info(path), data)
        archive.writestr(
            deterministic_zip_info("README_TRUSTED_MAIN_DELTA.txt"),
            readme.encode("utf-8"),
        )
        archive.writestr(
            deterministic_zip_info("TRUSTED_MAIN_DELTA_MANIFEST.json"),
            (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        for name, paths in (
            ("MACHINE_TRANSLATION_ADDITIONS.txt", report["machine_added_txt_paths"]),
            ("HUMAN_MAIN_ADDITIONS.txt", report["human_only_added_txt_paths"]),
            ("RESTORED_OVERWRITTEN_HUMAN_FILES.txt", report["restored_overwritten_paths"]),
            ("RESTORED_DELETED_HUMAN_FILES.txt", report["restored_deleted_paths"]),
        ):
            archive.writestr(
                deterministic_zip_info(name),
                (("\n".join(paths) + "\n") if paths else "").encode("utf-8"),
            )

    with zipfile.ZipFile(output_path) as archive:
        names = set(archive.namelist())
        source_names = {name for name in names if name.startswith(SOURCE_PREFIX)}
        if source_names != set(expected):
            raise RebuildError(
                f"release source path mismatch: expected={len(expected)} actual={len(source_names)}"
            )
        if any("magiraexedra" in name.lower() for name in names):
            raise RebuildError("release unexpectedly contains Exedra files")
        for path, expected_sha in expected.items():
            data = archive.read(path)
            if blob_hash(data) != expected_sha:
                raise RebuildError(f"release hash mismatch: {path}")

    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    checksum_path = output_path.with_suffix(output_path.suffix + ".sha256.txt")
    checksum_path.write_text(f"{digest}  {output_path.name}\n", encoding="utf-8")
    print(
        "REBUILT_RELEASE_OK "
        f"files={len(expected)} bytes={output_path.stat().st_size} sha256={digest}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    repair = subparsers.add_parser("repair")
    repair.add_argument("--baseline", required=True)
    repair.add_argument("--source", required=True)
    repair.add_argument("--report", type=Path, required=True)

    package = subparsers.add_parser("package")
    package.add_argument("--report", type=Path, required=True)
    package.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "repair":
        repair_tree(args.baseline, args.source, args.report)
    else:
        package_release(args.report, args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RebuildError as exc:
        print(f"error: {exc}")
        raise SystemExit(2) from exc
