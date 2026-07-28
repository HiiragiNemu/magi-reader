#!/usr/bin/env python3
"""Import extracted official Taiwan Exedra scenario JSON directly.

This tool never uses GitHub Actions. It mirrors the existing Japanese organizer
manifest, preserves the Japanese JSON schema and speaker identities, replaces
only text-event Comment cells with official Taiwan text converted to Simplified
Chinese, and emits `<groupKey>_cn.txt`, source JSON, provenance metadata, and the
schema-v1 proof required by `generate_story_index.py`.

Install once:
    py -m pip install opencc-python-reimplemented

Usage:
    py tools/import_exedra_official_tw.py D:\\ExedraTW\\scenario
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import generate_story_index as pipeline  # noqa: E402

JP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"
CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
MANIFEST = JP_ROOT / "exedra_manifest.json"
STAGING_ROOT = ROOT / "artifacts/.exedra-official-tw-staging"
TEXT_ACTIONS = {"talk", "narration", "charactertalk", "onlytext"}
SECTION_RE = re.compile(
    r"^---\s*\[Section\s+(\d+)\]\s*"
    r"\(Source:\s*([^()\r\n]+\.json)\s*\)\s*---$",
    re.I,
)
EPISODE_RE = re.compile(r"_(\d+)\.json$", re.I)


@dataclass(frozen=True)
class Line:
    speaker: str
    text: str
    kind: str


@dataclass(frozen=True)
class Section:
    number: int
    source: str
    lines: tuple[Line, ...]


class TwSourceIndex:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        self.relative: dict[str, Path] = {}
        self.by_name: dict[str, list[Path]] = {}
        for path in sorted(self.root.rglob("*.json")):
            if not path.is_file() or path.is_symlink():
                continue
            resolved = path.resolve(strict=True)
            try:
                relative = resolved.relative_to(self.root).as_posix()
            except ValueError as exc:
                raise RuntimeError(f"台服 JSON 路径越界：{path}") from exc
            key = relative.casefold()
            if key in self.relative:
                raise RuntimeError(f"台服 JSON 相对路径大小写冲突：{relative}")
            self.relative[key] = resolved
            self.by_name.setdefault(path.name.casefold(), []).append(resolved)

    @staticmethod
    def _safe_source_path(value: str) -> PurePosixPath:
        if not value or "\\" in value or "\x00" in value:
            raise RuntimeError(f"manifest sourcePath 非法：{value!r}")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError(f"manifest sourcePath 非法：{value!r}")
        return path

    def resolve(self, source_path: str) -> Path:
        safe = self._safe_source_path(source_path)
        key = safe.as_posix().casefold()
        exact = self.relative.get(key)
        if exact is not None:
            return exact

        suffix = f"/{key}"
        suffix_matches = [
            path
            for relative, path in self.relative.items()
            if relative.endswith(suffix)
        ]
        if len(suffix_matches) == 1:
            return suffix_matches[0]
        if len(suffix_matches) > 1:
            raise RuntimeError(
                f"台服来源后缀匹配不唯一：{source_path}: {suffix_matches[:3]}"
            )

        basename_matches = self.by_name.get(safe.name.casefold(), [])
        if len(basename_matches) == 1:
            return basename_matches[0]
        if not basename_matches:
            raise FileNotFoundError(f"缺少台服 JSON：{source_path}")
        raise RuntimeError(
            f"台服 JSON basename 匹配不唯一：{safe.name}: {basename_matches[:3]}"
        )


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"JSON 无法读取：{path}: {exc}") from exc


def split_line(value: str) -> tuple[str, str]:
    positions = [index for index in (value.find(":"), value.find("：")) if index > 0]
    if not positions:
        return "旁白", value.strip()
    index = min(positions)
    return value[:index].strip(), value[index + 1 :].strip()


def parse_txt(path: Path) -> tuple[Section, ...]:
    sections: list[Section] = []
    current_number: int | None = None
    current_source = ""
    current_lines: list[Line] = []

    def flush() -> None:
        nonlocal current_number, current_source, current_lines
        if current_number is not None:
            sections.append(Section(current_number, current_source, tuple(current_lines)))
        current_number = None
        current_source = ""
        current_lines = []

    try:
        raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"聚合 TXT 无法读取：{path}: {exc}") from exc
    for line_number, raw in enumerate(raw_lines, 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("---"):
            match = SECTION_RE.fullmatch(line)
            if not match:
                raise RuntimeError(f"非法 Section 头：{path}:{line_number}")
            flush()
            current_number = int(match.group(1))
            if current_number != len(sections) + 1:
                raise RuntimeError(f"Section 编号不连续：{path}:{line_number}")
            current_source = PurePosixPath(match.group(2)).name
            continue
        if current_number is None:
            raise RuntimeError(f"首个 Section 前存在正文：{path}:{line_number}")
        speaker, text = split_line(line)
        normalized = pipeline._normalize_exedra_speaker(speaker)
        kind = (
            "narration"
            if normalized in pipeline.EXEDRA_NARRATION_SPEAKERS
            else "dialogue"
        )
        if not speaker or not text:
            raise RuntimeError(f"空说话人或正文：{path}:{line_number}")
        current_lines.append(Line(speaker, text, kind))
    flush()
    if not sections:
        raise RuntimeError(f"缺少 Section：{path}")
    return tuple(sections)


def load_groups() -> list[dict[str, Any]]:
    value = load_json(MANIFEST)
    if not isinstance(value, dict):
        raise RuntimeError("Exedra organizer manifest 顶层不是对象")
    groups = value.get("groups")
    if value.get("schemaVersion") != 1 or not isinstance(groups, list) or len(groups) != 443:
        raise RuntimeError("Exedra organizer manifest 版本或组数异常")
    return [group for group in groups if isinstance(group, dict)]


def extract_rows(path: Path) -> list[dict[str, Any]]:
    value = load_json(path)
    if not isinstance(value, dict):
        raise RuntimeError(f"Exedra JSON 顶层不是对象：{path}")
    rows, diagnostics = pipeline.extract_exedra_dialogue_rows(value)
    serious = [item for item in diagnostics if "重复" not in item]
    if serious:
        raise RuntimeError(f"Exedra JSON 结构诊断失败：{path}: {serious[:3]}")
    return rows


def validate_row_alignment(
    source_name: str,
    jp_rows: list[dict[str, Any]],
    tw_rows: list[dict[str, Any]],
    section: Section,
) -> None:
    if len(jp_rows) != len(section.lines):
        raise RuntimeError(
            f"JP JSON/聚合 TXT 事件数不同：{source_name}: "
            f"JSON={len(jp_rows)} TXT={len(section.lines)}"
        )
    if len(tw_rows) != len(jp_rows):
        raise RuntimeError(
            f"台服/日文事件数不同：{source_name}: "
            f"JP={len(jp_rows)} TW={len(tw_rows)}"
        )
    for index, (jp_row, tw_row, jp_line) in enumerate(
        zip(jp_rows, tw_rows, section.lines),
        1,
    ):
        jp_action = str(jp_row.get("action") or "").strip().casefold()
        tw_action = str(tw_row.get("action") or "").strip().casefold()
        if jp_action != tw_action:
            raise RuntimeError(
                f"动作类型不同：{source_name} 第 {index} 条："
                f"JP={jp_action!r} TW={tw_action!r}"
            )
        for field in ("sheet_index", "row_number"):
            if jp_row.get(field) != tw_row.get(field):
                raise RuntimeError(
                    f"行位置不同：{source_name} 第 {index} 条 {field}："
                    f"JP={jp_row.get(field)!r} TW={tw_row.get(field)!r}"
                )
        kind = "narration" if jp_action == "narration" else "dialogue"
        if kind != jp_line.kind:
            raise RuntimeError(
                f"聚合 TXT 事件类型不同：{source_name} 第 {index} 条"
            )


def mutable_text_sheets(document: dict[str, Any]):
    groups: list[
        tuple[list[tuple[list[Any], int]], list[list[tuple[list[Any], int]]]]
    ] = []
    fingerprints: dict[str, int] = {}
    sheets = document.get("sheetList")
    if not isinstance(sheets, list):
        raise RuntimeError("日文 JSON 缺少 sheetList")
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        header = sheet.get("headerRow")
        contents = sheet.get("contentRowList")
        if not isinstance(header, dict) or not isinstance(contents, list):
            continue
        header_cells = header.get("cellList")
        if not isinstance(header_cells, list):
            continue
        names = [str(value).strip().casefold() for value in header_cells]
        try:
            action_index = names.index("actiontype")
            comment_index = names.index("comment")
            name_index = names.index("name")
        except ValueError:
            continue
        refs: list[tuple[list[Any], int]] = []
        fingerprint_rows: list[tuple[str, str, str]] = []
        for row in contents:
            cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(cells, list):
                continue
            action = str(
                cells[action_index] if action_index < len(cells) else ""
            ).strip()
            comment = cells[comment_index] if comment_index < len(cells) else ""
            if (
                action.casefold() not in TEXT_ACTIONS
                or not isinstance(comment, str)
                or not comment.strip()
            ):
                continue
            speaker = str(
                cells[name_index] if name_index < len(cells) else ""
            ).strip()
            refs.append((cells, comment_index))
            fingerprint_rows.append((action, speaker, comment.strip()))
        if not refs:
            continue
        fingerprint = json.dumps(
            fingerprint_rows,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        existing = fingerprints.get(fingerprint)
        if existing is None:
            fingerprints[fingerprint] = len(groups)
            groups.append((refs, []))
        else:
            groups[existing][1].append(refs)
    return groups


def apply_translated_texts(
    jp_json: Path,
    texts: list[str],
    destination: Path,
) -> str:
    document = load_json(jp_json)
    if not isinstance(document, dict):
        raise RuntimeError(f"日文 JSON 顶层不是对象：{jp_json}")
    groups = mutable_text_sheets(document)
    flattened = [ref for refs, _duplicates in groups for ref in refs]
    if len(flattened) != len(texts):
        raise RuntimeError(
            f"日文 JSON/聚合 TXT 文本事件数不同：{jp_json.name}: "
            f"JSON={len(flattened)} TXT={len(texts)}"
        )
    offset = 0
    for refs, duplicates in groups:
        segment = texts[offset : offset + len(refs)]
        for target_refs in [refs, *duplicates]:
            if len(target_refs) != len(segment):
                raise RuntimeError(f"重复工作表结构不同：{jp_json.name}")
            for (cells, comment_index), text in zip(target_refs, segment):
                cells[comment_index] = text
        offset += len(refs)
    encoded = json_bytes(document)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def render_cn(sections: tuple[Section, ...], translated: list[list[str]]) -> str:
    if len(sections) != len(translated):
        raise RuntimeError("Section 数量不一致")
    lines: list[str] = []
    for section, texts in zip(sections, translated):
        if len(section.lines) != len(texts):
            raise RuntimeError(f"Section {section.number} 文本事件数不一致")
        lines.append(f"--- [Section {section.number}] (Source: {section.source}) ---")
        for jp_line, text in zip(section.lines, texts):
            if not text.strip():
                raise RuntimeError(f"Section {section.number} 含空台服正文")
            lines.append(f"{jp_line.speaker}：{text.strip()}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_report(
    category: str,
    group_key: str,
    jp_path: Path,
    cn_path: Path,
    source_root: Path,
    json_meta: list[dict[str, Any]],
) -> dict[str, Any]:
    jp_sections = pipeline._exedra_alignment_sections(jp_path)
    cn_sections = pipeline._exedra_alignment_sections(cn_path)
    if len(jp_sections) != len(cn_sections):
        raise RuntimeError(f"导入后 Section 数量不一致：{group_key}")
    sections = []
    for jp, cn in zip(jp_sections, cn_sections):
        if (
            jp.number != cn.number
            or jp.source_name != cn.source_name
            or jp.reader_block_count != cn.reader_block_count
            or jp.speaker_sequence_sha256 != cn.speaker_sequence_sha256
        ):
            raise RuntimeError(
                f"导入后结构证明失败：{group_key} Section {jp.number}"
            )
        match = EPISODE_RE.search(jp.source_name)
        sections.append({
            "section": jp.number,
            "source": jp.source_name,
            "wikiEpisode": int(match.group(1)) if match else jp.number - 1,
            "readerNormalizedBlocks": {
                "jp": jp.reader_block_count,
                "cn": cn.reader_block_count,
                "matches": True,
            },
            "speakerSequenceSha256": {
                "jp": jp.speaker_sequence_sha256,
                "cn": cn.speaker_sequence_sha256,
            },
        })
    return {
        "schemaVersion": 1,
        "status": "validated",
        "provenance": "official_tw_human",
        "sourceRoot": str(source_root),
        "group": {"category": category, "groupKey": group_key},
        "validation": {
            "passed": True,
            "mismatchCount": 0,
            "usesLcs": False,
            "usesFuzzyMatching": False,
            "allowsReordering": False,
        },
        "mismatches": [],
        "jp": {
            "contentSha256": pipeline._sha256_utf8_text_file(jp_path),
            "sectionCount": len(jp_sections),
            "readerNormalizedBlockCount": sum(
                item.reader_block_count for item in jp_sections
            ),
        },
        "cn": {
            "renderedSha256": pipeline._sha256_utf8_text_file(cn_path),
            "sectionCount": len(cn_sections),
            "readerNormalizedBlockCount": sum(
                item.reader_block_count for item in cn_sections
            ),
        },
        "sections": sections,
        "sourceJson": json_meta,
    }


def commit_staged_group(stage: Path, output_dir: Path) -> None:
    files = sorted(path for path in stage.iterdir() if path.is_file())
    collisions = [output_dir / path.name for path in files if (output_dir / path.name).exists()]
    if collisions:
        raise RuntimeError(f"目标目录已有文件，拒绝覆盖：{collisions[:3]}")
    output_dir.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []
    try:
        for source in files:
            target = output_dir / source.name
            os.replace(source, target)
            moved.append(target)
    except Exception:
        for target in moved:
            target.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tw_json_root", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only-category", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        from opencc import OpenCC  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "缺少 opencc-python-reimplemented；请执行："
            "py -m pip install opencc-python-reimplemented"
        ) from exc
    converter = OpenCC("tw2sp")
    source_root = args.tw_json_root.resolve(strict=True)
    tw_index = TwSourceIndex(source_root)
    groups = load_groups()
    if args.only_category:
        allowed = set(args.only_category)
        groups = [group for group in groups if group.get("category") in allowed]
    if args.limit > 0:
        groups = groups[: args.limit]

    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    stats = {
        "existing_local": 0,
        "official_tw": 0,
        "missing_tw": 0,
        "failed": 0,
    }
    failures: list[str] = []

    for index, group in enumerate(groups, 1):
        category = str(group.get("category") or "")
        group_key = str(group.get("groupKey") or "")
        source_paths = group.get("sources")
        if not category or not group_key or not isinstance(source_paths, list):
            stats["failed"] += 1
            failures.append(f"manifest group 无效：{group!r}")
            continue

        jp_path = JP_ROOT / str(group.get("textFile") or "")
        output_dir = CN_ROOT / category / group_key
        expected_names = {
            f"{group_key}_cn.txt",
            f"{group_key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}",
            f"{group_key}_cn.provenance.json",
            *[PurePosixPath(str(value)).name for value in source_paths],
        }
        existing = [output_dir / name for name in expected_names if (output_dir / name).exists()]
        cn_path = output_dir / f"{group_key}_cn.txt"
        report_path = output_dir / f"{group_key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}"
        if cn_path.is_file() and report_path.is_file():
            stats["existing_local"] += 1
            continue
        if existing:
            stats["failed"] += 1
            failures.append(
                f"{category}/{group_key}: 发现不完整既有产物，拒绝覆盖：{existing[:3]}"
            )
            continue

        try:
            sections = parse_txt(jp_path)
            if len(source_paths) != len(sections):
                raise RuntimeError(
                    f"manifest/Section 数量不同："
                    f"manifest={len(source_paths)} TXT={len(sections)}"
                )
            translated_sections: list[list[str]] = []
            resolved_sources: list[tuple[Section, str, Path, Path]] = []
            for section, raw_source_path in zip(sections, source_paths):
                source_path = str(raw_source_path)
                if PurePosixPath(source_path).name != section.source:
                    raise RuntimeError(
                        f"manifest/Section 来源不同：{source_path}, {section.source}"
                    )
                tw_path = tw_index.resolve(source_path)
                jp_json = JP_ROOT / category / group_key / section.source
                jp_rows = extract_rows(jp_json)
                tw_rows = extract_rows(tw_path)
                validate_row_alignment(section.source, jp_rows, tw_rows, section)
                texts = [
                    converter.convert(str(row.get("text") or "").strip())
                    for row in tw_rows
                ]
                if any(not text for text in texts):
                    raise RuntimeError(f"台服正文为空：{section.source}")
                translated_sections.append(texts)
                resolved_sources.append((section, source_path, jp_json, tw_path))

            with tempfile.TemporaryDirectory(
                prefix=f"{category}-{group_key}-",
                dir=STAGING_ROOT,
            ) as temporary:
                stage = Path(temporary)
                json_meta: list[dict[str, Any]] = []
                for (section, source_path, jp_json, tw_path), texts in zip(
                    resolved_sources,
                    translated_sections,
                ):
                    destination = stage / section.source
                    digest = apply_translated_texts(jp_json, texts, destination)
                    json_meta.append({
                        "source": section.source,
                        "manifestSourcePath": source_path,
                        "twPath": str(tw_path),
                        "twSha256": pipeline._sha256_file(tw_path),
                        "simplifiedJsonSha256": digest,
                    })

                staged_cn = stage / f"{group_key}_cn.txt"
                staged_cn.write_text(
                    render_cn(sections, translated_sections),
                    encoding="utf-8",
                )
                report = build_report(
                    category,
                    group_key,
                    jp_path,
                    staged_cn,
                    source_root,
                    json_meta,
                )
                staged_report = (
                    stage / f"{group_key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}"
                )
                staged_report.write_bytes(json_bytes(report))
                sidecar = {
                    "version": 1,
                    "sourceIdentity": str(group.get("id") or ""),
                    "provenance": "official_tw_human",
                    "sourceRoot": str(source_root),
                    "generatedAt": __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ).isoformat(),
                    "jpSha256": pipeline._sha256_utf8_text_file(jp_path),
                    "cnSha256": pipeline._sha256_utf8_text_file(staged_cn),
                    "sourceJson": json_meta,
                }
                (stage / f"{group_key}_cn.provenance.json").write_bytes(
                    json_bytes(sidecar)
                )
                # Re-run the repository's independent schema-v1 validator before commit.
                pipeline._validate_exedra_cn_import_report(
                    group=pipeline.OrganizedExedraGroup(
                        manifest_id=str(group.get("id") or ""),
                        raw_category=category,
                        category=pipeline.EXEDRA_CATEGORY_MAP[category],
                        group_key=group_key,
                        output_dir=Path(category, group_key),
                        text_file=Path(str(group.get("textFile") or "")),
                        source_paths=tuple(str(value) for value in source_paths),
                        source_names=tuple(section.source for section in sections),
                        title="",
                    ),
                    jp_path=jp_path,
                    cn_path=staged_cn,
                    jp_sections=pipeline._exedra_alignment_sections(jp_path),
                    cn_sections=pipeline._exedra_alignment_sections(staged_cn),
                )
                if not args.dry_run:
                    commit_staged_group(stage, output_dir)
            stats["official_tw"] += 1
        except FileNotFoundError as exc:
            stats["missing_tw"] += 1
            failures.append(f"{category}/{group_key}: {exc}")
        except Exception as exc:
            stats["failed"] += 1
            failures.append(f"{category}/{group_key}: {exc}")

        if index % 25 == 0:
            print(f"processed {index}/{len(groups)} {stats}")

    audit = ROOT / "artifacts/exedra_official_tw_import_report.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(
        json.dumps(
            {"stats": stats, "failures": failures},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    shutil.rmtree(STAGING_ROOT, ignore_errors=True)
    print(json.dumps(stats, ensure_ascii=False))
    return 2 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
