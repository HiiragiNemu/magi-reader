#!/usr/bin/env python3
"""Import extracted official Taiwan Exedra scenario JSON directly.

This tool never uses GitHub Actions.  It mirrors the existing Japanese organizer
manifest, preserves the Japanese JSON schema/speaker identities, replaces only
text-event Comment cells with official Taiwan text converted to Simplified
Chinese, and emits `<groupKey>_cn.txt` plus the schema-v1 import proof required
by `generate_story_index.py`.

Install once:
    py -m pip install opencc-python-reimplemented

Usage:
    py tools/import_exedra_official_tw.py D:\ExedraTW\scenario
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import generate_story_index as pipeline  # noqa: E402

JP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"
CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
MANIFEST = JP_ROOT / "exedra_manifest.json"
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

    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
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
            current_source = Path(match.group(2)).name
            continue
        if current_number is None:
            raise RuntimeError(f"首个 Section 前存在正文：{path}:{line_number}")
        speaker, text = split_line(line)
        normalized = pipeline._normalize_exedra_speaker(speaker)
        kind = "narration" if normalized in pipeline.EXEDRA_NARRATION_SPEAKERS else "dialogue"
        if not speaker or not text:
            raise RuntimeError(f"空说话人或正文：{path}:{line_number}")
        current_lines.append(Line(speaker, text, kind))
    flush()
    if not sections:
        raise RuntimeError(f"缺少 Section：{path}")
    return tuple(sections)


def load_groups() -> list[dict[str, Any]]:
    value = load_json(MANIFEST)
    groups = value.get("groups") if isinstance(value, dict) else None
    if value.get("schemaVersion") != 1 or not isinstance(groups, list) or len(groups) != 443:
        raise RuntimeError("Exedra organizer manifest 版本或组数异常")
    return groups


def index_by_basename(root: Path) -> dict[str, Path]:
    buckets: dict[str, list[Path]] = {}
    for path in sorted(root.rglob("*.json")):
        if path.is_file() and not path.is_symlink():
            buckets.setdefault(path.name.casefold(), []).append(path)
    duplicates = {name: paths for name, paths in buckets.items() if len(paths) != 1}
    if duplicates:
        sample = next(iter(duplicates.items()))
        raise RuntimeError(f"台服 JSON 文件名不唯一：{sample[0]}: {sample[1][:3]}")
    return {name: paths[0] for name, paths in buckets.items()}


def extract_rows(path: Path) -> list[dict[str, Any]]:
    value = load_json(path)
    if not isinstance(value, dict):
        raise RuntimeError(f"台服 JSON 顶层不是对象：{path}")
    rows, diagnostics = pipeline.extract_exedra_dialogue_rows(value)
    serious = [item for item in diagnostics if "重复" not in item]
    if serious:
        raise RuntimeError(f"台服 JSON 结构诊断失败：{path}: {serious[:3]}")
    return rows


def mutable_text_sheets(document: dict[str, Any]):
    groups: list[tuple[list[tuple[list[Any], int]], list[list[tuple[list[Any], int]]]]] = []
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
            action = str(cells[action_index] if action_index < len(cells) else "").strip()
            comment = cells[comment_index] if comment_index < len(cells) else ""
            if action.casefold() not in TEXT_ACTIONS or not isinstance(comment, str) or not comment.strip():
                continue
            speaker = str(cells[name_index] if name_index < len(cells) else "").strip()
            refs.append((cells, comment_index))
            fingerprint_rows.append((action, speaker, comment.strip()))
        if not refs:
            continue
        fingerprint = json.dumps(fingerprint_rows, ensure_ascii=False, separators=(",", ":"))
        existing = fingerprints.get(fingerprint)
        if existing is None:
            fingerprints[fingerprint] = len(groups)
            groups.append((refs, []))
        else:
            groups[existing][1].append(refs)
    return groups


def apply_translated_texts(jp_json: Path, texts: list[str], destination: Path) -> str:
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
    if destination.exists() and destination.read_bytes() != encoded:
        raise RuntimeError(f"已有中文 JSON 不同，拒绝覆盖：{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def render_cn(sections: tuple[Section, ...], translated: list[list[str]]) -> str:
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


def build_report(category: str, group_key: str, jp_path: Path, cn_path: Path, source_root: Path, json_meta):
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
            raise RuntimeError(f"导入后结构证明失败：{group_key} Section {jp.number}")
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
            "readerNormalizedBlockCount": sum(item.reader_block_count for item in jp_sections),
        },
        "cn": {
            "renderedSha256": pipeline._sha256_utf8_text_file(cn_path),
            "sectionCount": len(cn_sections),
            "readerNormalizedBlockCount": sum(item.reader_block_count for item in cn_sections),
        },
        "sections": sections,
        "sourceJson": json_meta,
    }


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
    converter = OpenCC("t2s")
    source_root = args.tw_json_root.resolve()
    tw_index = index_by_basename(source_root)
    groups = load_groups()
    if args.only_category:
        allowed = set(args.only_category)
        groups = [group for group in groups if group.get("category") in allowed]
    if args.limit > 0:
        groups = groups[: args.limit]

    stats = {"existing_local": 0, "official_tw": 0, "missing_tw": 0, "failed": 0}
    failures: list[str] = []
    for index, group in enumerate(groups, 1):
        category = str(group["category"])
        group_key = str(group["groupKey"])
        jp_path = JP_ROOT / str(group["textFile"])
        output_dir = CN_ROOT / category / group_key
        cn_path = output_dir / f"{group_key}_cn.txt"
        report_path = output_dir / f"{group_key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}"
        if cn_path.exists() or report_path.exists():
            stats["existing_local"] += 1
            continue
        try:
            sections = parse_txt(jp_path)
            missing = [section.source for section in sections if section.source.casefold() not in tw_index]
            if missing:
                stats["missing_tw"] += 1
                continue
            translated_sections: list[list[str]] = []
            json_meta = []
            for section in sections:
                tw_path = tw_index[section.source.casefold()]
                rows = extract_rows(tw_path)
                if len(rows) != len(section.lines):
                    raise RuntimeError(
                        f"台服/日文事件数不同：{section.source}: "
                        f"JP={len(section.lines)} TW={len(rows)}"
                    )
                texts: list[str] = []
                for row_number, (row, jp_line) in enumerate(zip(rows, section.lines), 1):
                    kind = "narration" if str(row.get("action") or "").casefold() == "narration" else "dialogue"
                    if kind != jp_line.kind:
                        raise RuntimeError(
                            f"事件类型不同：{section.source} 第 {row_number} 条"
                        )
                    text = converter.convert(str(row.get("text") or "").strip())
                    if not text:
                        raise RuntimeError(f"台服正文为空：{section.source} 第 {row_number} 条")
                    texts.append(text)
                translated_sections.append(texts)
                if not args.dry_run:
                    jp_json = JP_ROOT / category / group_key / section.source
                    destination = output_dir / section.source
                    digest = apply_translated_texts(jp_json, texts, destination)
                    json_meta.append({
                        "source": section.source,
                        "twPath": str(tw_path),
                        "simplifiedJsonSha256": digest,
                    })
            if not args.dry_run:
                output_dir.mkdir(parents=True, exist_ok=True)
                cn_path.write_text(render_cn(sections, translated_sections), encoding="utf-8")
                report = build_report(
                    category, group_key, jp_path, cn_path, source_root, json_meta
                )
                report_path.write_bytes(json_bytes(report))
            stats["official_tw"] += 1
        except Exception as exc:
            stats["failed"] += 1
            failures.append(f"{category}/{group_key}: {exc}")
            if not args.dry_run:
                for path in output_dir.glob("*") if output_dir.exists() else []:
                    if path.is_file() and path.name not in {cn_path.name, report_path.name}:
                        path.unlink()
                cn_path.unlink(missing_ok=True)
                report_path.unlink(missing_ok=True)
        if index % 25 == 0:
            print(f"processed {index}/{len(groups)} {stats}")

    audit = ROOT / "artifacts/exedra_official_tw_import_report.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(
        json.dumps({"stats": stats, "failures": failures}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
