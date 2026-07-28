#!/usr/bin/env python3
"""Safely apply one approved proofreading submission to its canonical TXT source.

This tool is intentionally fail-closed. It validates the current story catalogue,
source identity, language paths, catalogue digest, base file digest, structural
section headers and content digest before modifying one source TXT file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import materialize_proofreading_assets as assets  # noqa: E402

EXEDRA_SOURCE_ROOT = "magiraexedra-translate-data-master/Scenarios_full"
MAGIRECO_SOURCE_ROOT = "magireco-translate-data-master/Scenarios_full"
MAGIRECO_VOICE_SOURCE_ROOT = (
    "magireco-voice-translate-data-master/Scenarios_full/general_voice"
)
SHA256_RE = re.compile(r"^[a-f0-9]{64}$", re.I)
SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
HEADER_RE = re.compile(r"^---\s*\[Section\s+\d+(?:\s+-\s+Branch\s+\d+)?\]\s*\(Source:\s*[^()\r\n]+\.json\s*\)\s*---$", re.I)


class ApplyError(RuntimeError):
    def __init__(self, message: str, *, code: str = "invalid", exit_code: int = 2):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def normalize_text(value: str) -> str:
    return value.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").replace("\0", "")


def sha256_text(value: str) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ApplyError(f"无法读取 UTF-8 文件: {path}: {exc}") from exc


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ApplyError(f"无法读取 JSON: {path}: {exc}") from exc


def require_string(record: Mapping[str, Any], key: str, max_length: int = 1_000_000) -> str:
    value = record.get(key)
    if not isinstance(value, str) or len(value) > max_length:
        raise ApplyError(f"投稿字段 {key} 无效")
    return value


def safe_relative(value: str) -> PurePosixPath:
    if not value or "\\" in value or "\0" in value:
        raise ApplyError("来源身份包含不安全路径")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ApplyError("来源身份包含不安全路径")
    return relative


def find_story(stories: Any, story_id: str) -> Mapping[str, Any]:
    if not isinstance(stories, list):
        raise ApplyError("story_index.json 必须是数组")
    matches = []
    key = story_id.casefold()
    for value in stories:
        if not isinstance(value, dict):
            continue
        identifiers = [value.get("id"), *(value.get("legacy_ids") or [])]
        if any(isinstance(item, str) and item.casefold() == key for item in identifiers):
            matches.append(value)
    if len(matches) != 1:
        raise ApplyError(f"剧情编号在当前目录中应唯一，实际匹配 {len(matches)} 项")
    return matches[0]


def resolve_source_path(repo_root: Path, story: Mapping[str, Any]) -> Path:
    identity = str(story.get("source_identity") or "")
    game = str(story.get("game") or "magireco")
    if game == "exedra":
        match = re.fullmatch(r"exedra:([^:]+):([A-Za-z0-9_.-]{1,96})", identity)
        if not match:
            raise ApplyError("Exedra source_identity 格式无效")
        raw_category, group = match.groups()
        if not SAFE_COMPONENT_RE.fullmatch(raw_category):
            raise ApplyError("Exedra 原始分类名无效")
        filename = story.get("filename_cn")
        if not isinstance(filename, str) or not filename:
            filename = f"{group}_cn.txt"
        if PurePosixPath(filename).name != filename or not filename.lower().endswith(".txt"):
            raise ApplyError("Exedra 中文源文件名无效")
        relative = PurePosixPath(raw_category, group, filename)
        root = repo_root / EXEDRA_SOURCE_ROOT
    elif identity.startswith("general_voice/"):
        match = re.fullmatch(r"general_voice/(\d{6})", identity)
        if not match:
            raise ApplyError("魔法纪录语音 source_identity 格式无效")
        model_id = match.group(1)
        filename = story.get("filename_cn")
        if filename != f"{model_id}_cn.txt":
            raise ApplyError("魔法纪录语音中文源文件名无效")
        relative = PurePosixPath(model_id, filename)
        root = repo_root / MAGIRECO_VOICE_SOURCE_ROOT
    else:
        relative_identity = safe_relative(identity)
        relative = relative_identity.with_suffix(".txt")
        root = repo_root / MAGIRECO_SOURCE_ROOT

    root = root.resolve()
    source = root.joinpath(*relative.parts).resolve()
    try:
        source.relative_to(root)
    except ValueError as exc:
        raise ApplyError("计算出的中文源路径越界") from exc
    return source


def header_signature(value: str) -> tuple[str, ...]:
    headers = []
    for raw in normalize_text(value).split("\n"):
        line = raw.strip()
        if not line.startswith("---"):
            continue
        if not HEADER_RE.fullmatch(line):
            raise ApplyError(f"发现无法识别的结构标题: {line[:160]}")
        headers.append(line)
    if not headers:
        raise ApplyError("投稿文本没有 Section 结构标题")
    return tuple(headers)


@dataclass(frozen=True)
class ApplyResult:
    submission_id: str
    story_id: str
    source_path: Path
    source_relative: str
    old_sha256: str
    new_sha256: str
    nickname: str
    note: str
    materialized_paths: tuple[str, ...]


def apply_submission(
    *,
    repo_root: Path,
    submission_path: Path,
    story_index_path: Path,
    write: bool,
) -> ApplyResult:
    record = load_json(submission_path)
    if not isinstance(record, dict):
        raise ApplyError("投稿记录必须是对象")

    submission_id = require_string(record, "id", 256)
    story_id = require_string(record, "story_id", 256)
    content = normalize_text(require_string(record, "content", 500_000))
    base_sha256 = require_string(record, "base_sha256", 64).lower()
    base_content_sha256 = require_string(record, "base_content_sha256", 64).lower()
    content_sha256 = require_string(record, "content_sha256", 64).lower()
    catalog_sha256 = require_string(record, "catalog_sha256", 64).lower()
    target_branch = require_string(record, "target_branch", 256)
    source_identity = require_string(record, "source_identity", 1_024)
    source_path_cn = require_string(record, "source_path_cn", 4_096)
    source_path_jp = require_string(record, "source_path_jp", 4_096)
    nickname = require_string(record, "nickname", 40)
    note = require_string(record, "note", 1_000)

    for label, digest in (
        ("base_sha256", base_sha256),
        ("base_content_sha256", base_content_sha256),
        ("content_sha256", content_sha256),
        ("catalog_sha256", catalog_sha256),
    ):
        if not SHA256_RE.fullmatch(digest):
            raise ApplyError(f"{label} 不是有效 SHA-256")
    if target_branch != "EXEDRA-TEST":
        raise ApplyError(f"投稿目标分支不是 EXEDRA-TEST: {target_branch}")
    if sha256_text(content) != content_sha256:
        raise ApplyError("投稿正文哈希与记录不一致")
    if content_sha256 == base_content_sha256:
        raise ApplyError("投稿正文与编辑前规范化文本相同", code="no_changes", exit_code=4)

    story_index_bytes = story_index_path.read_bytes()
    if sha256_bytes(story_index_bytes) != catalog_sha256:
        raise ApplyError(
            "剧情目录版本已变化，投稿需要重新确认",
            code="stale_catalog",
            exit_code=3,
        )
    story = find_story(json.loads(story_index_bytes.decode("utf-8-sig")), story_id)
    expected = {
        "source_identity": str(story.get("source_identity") or ""),
        "source_path_cn": str(story.get("path_cn") or ""),
        "source_path_jp": str(story.get("path_jp") or ""),
    }
    supplied = {
        "source_identity": source_identity,
        "source_path_cn": source_path_cn,
        "source_path_jp": source_path_jp,
    }
    for key in expected:
        if supplied[key] != expected[key]:
            raise ApplyError(
                f"{key} 与当前剧情目录不一致",
                code="stale_catalog",
                exit_code=3,
            )
    if not expected["source_path_cn"]:
        raise ApplyError("当前剧情没有可校对的中文源文件")

    source = resolve_source_path(repo_root, story)
    if not source.is_file() or source.is_symlink():
        raise ApplyError(f"中文源文件不存在或不是普通文件: {source}")
    current = normalize_text(read_utf8(source))
    current_sha256 = sha256_text(current)
    if current_sha256 != base_sha256:
        raise ApplyError(
            "中文源文本已更新，投稿基准已过期",
            code="stale_source",
            exit_code=3,
        )
    if header_signature(current) != header_signature(content):
        raise ApplyError(
            "Section/Branch 结构发生变化，拒绝自动应用",
            code="structure_changed",
            exit_code=5,
        )

    # Exactly one final LF makes reviews deterministic without changing the
    # reader-visible content. Hash metadata still refers to normalized content.
    output = content.rstrip("\n") + "\n"
    try:
        materialization = assets.materialize(
            source,
            repo_root=repo_root,
            write=write,
            reviewed_text=output,
        )
    except assets.MaterializeError as exc:
        raise ApplyError(
            f"校对内容无法生成可播放 JSON/TXT：{exc}",
            code="materialization_failed",
            exit_code=5,
        ) from exc

    return ApplyResult(
        submission_id=submission_id,
        story_id=str(story.get("id") or story_id),
        source_path=source,
        source_relative=source.relative_to(repo_root.resolve()).as_posix(),
        old_sha256=current_sha256,
        new_sha256=str(materialization["reviewedTxtSha256"]),
        nickname=nickname,
        note=note,
        materialized_paths=tuple(materialization["materializedPaths"]),
    )


def emit_result(result: ApplyResult, output_path: Path | None) -> None:
    payload = {
        "submission_id": result.submission_id,
        "story_id": result.story_id,
        "source_path": result.source_relative,
        "old_sha256": result.old_sha256,
        "new_sha256": result.new_sha256,
        "nickname": result.nickname,
        "note": result.note,
        "materialized_paths": list(result.materialized_paths),
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output_path:
        output_path.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            for key in ("submission_id", "story_id", "source_path", "old_sha256", "new_sha256"):
                handle.write(f"{key}={payload[key]}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--story-index", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    story_index = (
        args.story_index.resolve()
        if args.story_index
        else repo_root / "website/public/story_index.json"
    )
    try:
        result = apply_submission(
            repo_root=repo_root,
            submission_path=args.submission.resolve(),
            story_index_path=story_index,
            write=args.write,
        )
        emit_result(result, args.output.resolve() if args.output else None)
        return 0
    except ApplyError as exc:
        error = {"ok": False, "code": exc.code, "error": str(exc)}
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
