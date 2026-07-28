#!/usr/bin/env python3
"""Build search_content.json from story_index path mappings.

Unlike the legacy scanner, IDs are never re-derived from filenames.  This is
required for Exedra, where prefixes such as ``main`` and ``cv`` collide across
thousands of files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

from generate_story_index import (
    DEFAULT_PUBLIC_DIR,
    DEFAULT_TITLES_PATH,
    PipelineError,
    SCRIPT_DIR,
    extract_exedra_dialogue_rows,
    load_titles,
    validate_catalog,
)


S0_PREFIX = "@S0\t"
DEFAULT_SEARCH_MANIFEST_NAME = "search_index_manifest.json"
DEFAULT_OBJECT_KEY_PREFIX = "search"
MAX_SEARCH_INDEX_BYTES = 256 * 1024 * 1024
MAX_SEARCH_INDEX_ENTRIES = 1_000_000


def normalize_scene0_extended_lines(content: str) -> str:
    """Convert ``@S0`` JSON lines to searchable speaker/text lines."""

    normalized_lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(S0_PREFIX):
            try:
                payload = json.loads(stripped[len(S0_PREFIX) :])
                speaker = str(payload.get("speaker") or "旁白").strip() or "旁白"
                text = str(payload.get("text") or "").replace("\\n", " ").strip()
                if text:
                    normalized_lines.append(f"{speaker}: {text}")
                continue
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        normalized_lines.append(line)
    return "\n".join(normalized_lines)


def clean_content_for_search(content: str) -> str:
    content = normalize_scene0_extended_lines(content)
    content = content.replace("\\n", " ")

    # Remove Magia Record and Exedra bundle headers line-by-line.
    content = re.sub(r"(?m)^\s*---.*?---\s*$", " ", content)

    # Preserve both ruby base text and reading for search.
    content = re.sub(
        r"<r=([^>]+)>(.*?)</r>",
        lambda match: f"{match.group(2)} {match.group(1)}",
        content,
        flags=re.I | re.S,
    )
    # Exedra arbitrary colours/sizes and legacy symbolic colours.
    content = re.sub(
        r"<color=[^>]+>(.*?)</color>",
        r"\1",
        content,
        flags=re.I | re.S,
    )
    content = re.sub(
        r"<size=[^>]+>(.*?)</size>",
        r"\1",
        content,
        flags=re.I | re.S,
    )
    content = re.sub(
        r"<(red|blue|yellow|black)>(.*?)</\1>",
        r"\2",
        content,
        flags=re.I | re.S,
    )
    content = re.sub(
        r"\[text(?:Red|Blue|Yellow|Black):(.*?)\]",
        r"\1",
        content,
        flags=re.I | re.S,
    )
    content = re.sub(r"</?[A-Za-z][^>]*>", " ", content)
    return re.sub(r"\s+", " ", content).strip()


def extract_exedra_json_search_text(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Exedra JSON 读取失败: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PipelineError(f"Exedra JSON 顶层必须是对象: {path}")

    rows, diagnostics = extract_exedra_dialogue_rows(data)
    if not rows:
        detail = "; ".join(diagnostics[:3])
        raise PipelineError(f"Exedra JSON 没有可索引文本: {path}: {detail}")
    lines = []
    for row in rows:
        speaker = str(row.get("speaker") or "").strip()
        text = str(row.get("text") or "")
        lines.append(f"{speaker}: {text}" if speaker else text)
    return "\n".join(lines)


def _resolve_public_source(public_dir: Path, web_path: str) -> Path:
    if not web_path.startswith("/"):
        raise PipelineError(f"索引路径必须以 / 开头: {web_path}")
    candidate = (public_dir / web_path.lstrip("/")).resolve()
    try:
        candidate.relative_to(public_dir.resolve())
    except ValueError as exc:
        raise PipelineError(f"索引路径越界: {web_path}") from exc
    return candidate


def read_search_source(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        try:
            return path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise PipelineError(f"TXT 读取失败: {path}: {exc}") from exc
    if suffix == ".json":
        return extract_exedra_json_search_text(path)
    raise PipelineError(f"不支持的搜索来源格式: {path}")


def build_search_entries(
    *,
    stories: Sequence[Mapping[str, Any]],
    public_dir: Path,
    titles: Mapping[str, str] | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[dict[str, str]]:
    title_map = titles or {}
    search_index: list[dict[str, str]] = []
    seen_slots: dict[tuple[str, str], str] = {}
    seen_sources: dict[str, tuple[str, str]] = {}
    build_stats: MutableMapping[str, int] = stats if stats is not None else Counter()
    for key in (
        "manifest_source_slots",
        "search_indexed_slots",
        "search_fallback_slots",
    ):
        build_stats[key] = 0

    for story in stories:
        story_id = str(story.get("id") or "")
        if not story_id:
            raise PipelineError("story_index 条目缺少 id")
        title = str(story.get("title") or "")
        if not title:
            file_stem = str(story.get("file_stem") or "")
            raw_id = str(story.get("raw_id") or "")
            title = title_map.get(file_stem) or title_map.get(raw_id) or ""

        for lang in ("cn", "jp"):
            web_path = str(story.get(f"path_{lang}") or "")
            if not web_path:
                continue
            slot_key = (story_id, lang)
            previous_slot_path = seen_slots.get(slot_key)
            if previous_slot_path is not None:
                raise PipelineError(
                    f"搜索语言槽重复: {story_id}/{lang}: "
                    f"{previous_slot_path}, {web_path}"
                )
            seen_slots[slot_key] = web_path

            source_key = web_path.casefold()
            previous_source_owner = seen_sources.get(source_key)
            if previous_source_owner is not None:
                raise PipelineError(
                    f"搜索来源被多个语言槽复用: {web_path}: "
                    f"{previous_source_owner[0]}/{previous_source_owner[1]}, "
                    f"{story_id}/{lang}"
                )
            seen_sources[source_key] = slot_key
            build_stats["manifest_source_slots"] = (
                build_stats.get("manifest_source_slots", 0) + 1
            )

            source_path = _resolve_public_source(public_dir, web_path)
            if not source_path.is_file():
                raise PipelineError(f"{story_id}: 搜索来源不存在: {source_path}")
            content = clean_content_for_search(read_search_source(source_path))
            if title:
                content = f"{title} {content}".strip()
            if not content:
                content = (
                    str(story.get("file_stem") or "").strip()
                    or str(story.get("raw_id") or "").strip()
                    or story_id
                )
                build_stats["search_fallback_slots"] = (
                    build_stats.get("search_fallback_slots", 0) + 1
                )
            search_index.append({"id": story_id, "c": content, "l": lang})
            build_stats["search_indexed_slots"] = (
                build_stats.get("search_indexed_slots", 0) + 1
            )

    indexed = build_stats.get("search_indexed_slots", 0)
    total = build_stats.get("manifest_source_slots", 0)
    if indexed != total:
        raise PipelineError(
            f"搜索映射记账不一致: 来源 {total}, 已索引 {indexed}"
        )
    validate_search_entries(search_index, stories=stories)
    return search_index


def _story_source_slots(
    stories: Sequence[Mapping[str, Any]],
) -> set[tuple[str, str]]:
    slots: set[tuple[str, str]] = set()
    story_ids: set[str] = set()
    for index, story in enumerate(stories):
        story_id = str(story.get("id") or "")
        if not story_id:
            raise PipelineError(f"story_index[{index}] 缺少 id")
        if story_id in story_ids:
            raise PipelineError(f"story_index 重复 id: {story_id}")
        story_ids.add(story_id)
        for lang in ("cn", "jp"):
            if story.get(f"path_{lang}"):
                slots.add((story_id, lang))
    return slots


def validate_search_entries(
    entries: Sequence[Mapping[str, Any]],
    *,
    stories: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    if not isinstance(entries, list):
        raise PipelineError("search_content 必须是数组")
    seen_slots: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries):
        if not all(isinstance(entry.get(key), str) for key in ("id", "c", "l")):
            raise PipelineError(f"search_content[{index}] 字段类型错误")
        if not entry["id"] or not entry["c"] or entry["l"] not in {"cn", "jp"}:
            raise PipelineError(f"search_content[{index}] 字段值错误")
        slot = (entry["id"], entry["l"])
        if slot in seen_slots:
            raise PipelineError(
                f"search_content 重复故事语言槽: {entry['id']}/{entry['l']}"
            )
        seen_slots.add(slot)

    if stories is not None:
        expected_slots = _story_source_slots(stories)
        missing = expected_slots - seen_slots
        unexpected = seen_slots - expected_slots
        if missing or unexpected:
            missing_example = next(iter(sorted(missing)), None)
            unexpected_example = next(iter(sorted(unexpected)), None)
            raise PipelineError(
                "search_content 与当前 story_index 不一致: "
                f"缺失 {len(missing)}"
                f"{f'（例如 {missing_example[0]}/{missing_example[1]}）' if missing_example else ''}, "
                f"多余 {len(unexpected)}"
                f"{f'（例如 {unexpected_example[0]}/{unexpected_example[1]}）' if unexpected_example else ''}"
            )


def validate_search_matches_expected(
    actual: Sequence[Mapping[str, Any]],
    expected: Sequence[Mapping[str, Any]],
    *,
    stories: Sequence[Mapping[str, Any]],
) -> None:
    """Reject missing, extra, or stale content for any story/language slot."""

    validate_search_entries(actual, stories=stories)
    validate_search_entries(expected, stories=stories)
    actual_map = {
        (str(entry["id"]), str(entry["l"])): str(entry["c"])
        for entry in actual
    }
    expected_map = {
        (str(entry["id"]), str(entry["l"])): str(entry["c"])
        for entry in expected
    }
    stale_slots = [
        slot
        for slot in sorted(expected_map)
        if actual_map.get(slot) != expected_map[slot]
    ]
    if stale_slots:
        example = stale_slots[0]
        raise PipelineError(
            "search_content 内容陈旧: "
            f"{len(stale_slots)} 个故事语言槽与当前来源不一致，"
            f"例如 {example[0]}/{example[1]}"
        )


def serialize_search_entries(
    entries: Sequence[Mapping[str, Any]],
) -> bytes:
    validate_search_entries(entries)
    return json.dumps(
        entries,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _normalize_object_key_prefix(value: str) -> str:
    prefix = value.strip().strip("/")
    if (
        not prefix
        or "\\" in prefix
        or any(part in {"", ".", ".."} for part in prefix.split("/"))
    ):
        raise PipelineError(f"非法 R2 object key 前缀: {value!r}")
    return prefix


def build_search_manifest(
    payload: bytes,
    *,
    entry_count: int,
    story_index_bytes: bytes,
    object_key_prefix: str = DEFAULT_OBJECT_KEY_PREFIX,
) -> dict[str, Any]:
    if not payload or len(payload) > MAX_SEARCH_INDEX_BYTES:
        raise PipelineError(
            "search_content 大小必须在 1 字节到 "
            f"{MAX_SEARCH_INDEX_BYTES} 字节之间"
        )
    if entry_count <= 0 or entry_count > MAX_SEARCH_INDEX_ENTRIES:
        raise PipelineError(
            "search_content 条目数必须在 1 到 "
            f"{MAX_SEARCH_INDEX_ENTRIES} 之间"
        )
    digest = hashlib.sha256(payload).hexdigest()
    prefix = _normalize_object_key_prefix(object_key_prefix)
    return {
        "version": 1,
        "sha256": digest,
        "bytes": len(payload),
        "entries": entry_count,
        "object_key": f"{prefix}/{digest}.json",
        "story_index_sha256": hashlib.sha256(story_index_bytes).hexdigest(),
    }


def validate_search_manifest(
    manifest: Mapping[str, Any],
    *,
    payload: bytes,
    entry_count: int,
    story_index_bytes: bytes,
    object_key_prefix: str = DEFAULT_OBJECT_KEY_PREFIX,
) -> None:
    expected = build_search_manifest(
        payload,
        entry_count=entry_count,
        story_index_bytes=story_index_bytes,
        object_key_prefix=object_key_prefix,
    )
    if dict(manifest) != expected:
        differing = sorted(
            key
            for key in set(manifest) | set(expected)
            if manifest.get(key) != expected.get(key)
        )
        raise PipelineError(
            "search_index_manifest.json 与当前产物不一致: "
            + ", ".join(differing)
        )


def _write_bytes_atomic(payload: bytes, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def write_search_index_atomic(
    entries: Sequence[Mapping[str, Any]],
    output_path: Path,
) -> None:
    payload = serialize_search_entries(entries)
    _write_bytes_atomic(payload, output_path)
    try:
        written = json.loads(output_path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"搜索索引写入后校验失败: {output_path}: {exc}") from exc
    validate_search_entries(written)


def write_search_artifacts_atomic(
    entries: Sequence[Mapping[str, Any]],
    *,
    output_path: Path,
    manifest_path: Path,
    story_index_bytes: bytes,
    object_key_prefix: str = DEFAULT_OBJECT_KEY_PREFIX,
) -> dict[str, Any]:
    if output_path.resolve() == manifest_path.resolve():
        raise PipelineError("搜索大文件与 manifest 不能使用同一路径")
    payload = serialize_search_entries(entries)
    manifest = build_search_manifest(
        payload,
        entry_count=len(entries),
        story_index_bytes=story_index_bytes,
        object_key_prefix=object_key_prefix,
    )
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    # The small manifest is the publication pointer, so replace it last.
    _write_bytes_atomic(payload, output_path)
    _write_bytes_atomic(manifest_payload, manifest_path)
    validate_search_manifest(
        json.loads(manifest_path.read_bytes()),
        payload=output_path.read_bytes(),
        entry_count=len(entries),
        story_index_bytes=story_index_bytes,
        object_key_prefix=object_key_prefix,
    )
    return manifest


def _resolve_argument_path(value: str | None, default: Path) -> Path:
    path = Path(value) if value is not None else default
    if not path.is_absolute():
        path = SCRIPT_DIR / path
    return path.resolve()


def run(args: argparse.Namespace) -> int:
    public_dir = _resolve_argument_path(args.public_dir, DEFAULT_PUBLIC_DIR)
    story_index_path = _resolve_argument_path(
        args.story_index,
        public_dir / "story_index.json",
    )
    output_path = _resolve_argument_path(
        args.output,
        public_dir / "search_content.json",
    )
    manifest_path = _resolve_argument_path(
        getattr(args, "manifest", None),
        public_dir / DEFAULT_SEARCH_MANIFEST_NAME,
    )
    titles_path = _resolve_argument_path(args.titles, DEFAULT_TITLES_PATH)
    object_key_prefix = getattr(
        args,
        "object_key_prefix",
        DEFAULT_OBJECT_KEY_PREFIX,
    )

    if not story_index_path.is_file():
        raise PipelineError(f"story_index 不存在: {story_index_path}")
    try:
        story_index_bytes = story_index_path.read_bytes()
        stories = json.loads(story_index_bytes.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"story_index 读取失败: {exc}") from exc
    if not isinstance(stories, list):
        raise PipelineError("story_index 顶层必须是数组")

    validation = validate_catalog(stories, public_dir)
    titles = load_titles(titles_path)
    search_stats: Counter[str] = Counter()
    entries = build_search_entries(
        stories=stories,
        public_dir=public_dir,
        titles=titles,
        stats=search_stats,
    )
    validate_search_entries(entries, stories=stories)
    candidate_payload = serialize_search_entries(entries)
    candidate_manifest = build_search_manifest(
        candidate_payload,
        entry_count=len(entries),
        story_index_bytes=story_index_bytes,
        object_key_prefix=object_key_prefix,
    )

    print(f"story_index 条目: {validation['stories']}")
    print(f"搜索索引条目: {len(entries)}")
    print(f"manifest 来源槽: {search_stats['manifest_source_slots']}")
    print(f"回退标识来源槽: {search_stats['search_fallback_slots']}")
    print(f"R2 object key: {candidate_manifest['object_key']}")
    if args.validate_only:
        if not output_path.is_file():
            raise PipelineError(f"现有 search_content 不存在: {output_path}")
        if not manifest_path.is_file():
            raise PipelineError(f"搜索 manifest 不存在: {manifest_path}")
        try:
            existing_payload = output_path.read_bytes()
            existing_entries = json.loads(existing_payload.decode("utf-8-sig"))
            existing_manifest = json.loads(
                manifest_path.read_text(encoding="utf-8-sig")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PipelineError(f"现有搜索产物无效: {exc}") from exc
        validate_search_matches_expected(
            existing_entries,
            entries,
            stories=stories,
        )
        if not isinstance(existing_manifest, dict):
            raise PipelineError("搜索 manifest 顶层必须是对象")
        validate_search_manifest(
            existing_manifest,
            payload=existing_payload,
            entry_count=len(existing_entries),
            story_index_bytes=story_index_bytes,
            object_key_prefix=object_key_prefix,
        )
        print("验证通过，未写入文件。")
        return 0
    if args.dry_run:
        print("DRY-RUN：搜索内容已完整构建和验证，未写入文件。")
        return 0

    manifest = write_search_artifacts_atomic(
        entries,
        output_path=output_path,
        manifest_path=manifest_path,
        story_index_bytes=story_index_bytes,
        object_key_prefix=object_key_prefix,
    )
    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"搜索索引已原子替换: {output_path} ({size_mb:.2f} MB)")
    print(f"搜索 manifest 已原子替换: {manifest_path}")
    print(f"请上传搜索大文件到 R2: {manifest['object_key']}")
    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-dir", help="website/public 路径")
    parser.add_argument("--story-index", help="story_index.json 路径")
    parser.add_argument("--output", help="search_content.json 输出路径")
    parser.add_argument(
        "--manifest",
        help=f"{DEFAULT_SEARCH_MANIFEST_NAME} 输出路径",
    )
    parser.add_argument(
        "--object-key-prefix",
        default=DEFAULT_OBJECT_KEY_PREFIX,
        help="R2 内容寻址 object key 前缀（默认 search）",
    )
    parser.add_argument("--titles", help="titles.json 路径")
    parser.add_argument("--dry-run", action="store_true", help="构建验证但不写入")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="验证来源映射及现有搜索索引，不写入",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    if args.dry_run and args.validate_only:
        parser.error("--dry-run 与 --validate-only 不能同时使用")
    try:
        return run(args)
    except PipelineError as exc:
        parser.exit(2, f"错误: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
