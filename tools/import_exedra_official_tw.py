#!/usr/bin/env python3
"""Import official Taiwan Magia Exedra scenario JSON without GitHub Actions.

The input is an extracted directory containing official Traditional Chinese
scenario JSON.  The importer mirrors the existing JP aggregate groups, never
overwrites existing local CN groups, converts TW strings to Simplified Chinese,
and emits the schema-v1 proof consumed by generate_story_index.py.

Install the converter once:
    py -m pip install opencc-python-reimplemented

Example:
    py tools/import_exedra_official_tw.py D:\\ExedraTW\\Resources\\Scenarios
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import generate_story_index as pipeline  # noqa: E402

JP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"
CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
SECTION_RE = re.compile(
    r"^---\s*\[Section\s+(\d+)\]\s*"
    r"\(Source:\s*([^()\r\n]+\.json)\s*\)\s*---$",
    re.I,
)
EPISODE_RE = re.compile(r"_(\d+)\.json$", re.I)


@dataclass(frozen=True)
class JpLine:
    speaker: str
    text: str
    kind: str


@dataclass(frozen=True)
class JpSection:
    number: int
    source: str
    lines: tuple[JpLine, ...]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def load_opencc():
    try:
        from opencc import OpenCC  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "缺少 opencc-python-reimplemented；请执行："
            "py -m pip install opencc-python-reimplemented"
        ) from exc
    return OpenCC("t2s")


def convert_tree(value: Any, converter) -> Any:
    if isinstance(value, str):
        return converter.convert(value)
    if isinstance(value, list):
        return [convert_tree(item, converter) for item in value]
    if isinstance(value, dict):
        return {key: convert_tree(item, converter) for key, item in value.items()}
    return value


def split_line(line: str) -> tuple[str, str]:
    positions = [position for position in (line.find(":"), line.find("：")) if position > 0]
    if not positions:
        return "旁白", line.strip()
    position = min(positions)
    return line[:position].strip(), line[position + 1 :].strip()


def parse_jp_txt(path: Path) -> tuple[JpSection, ...]:
    sections: list[JpSection] = []
    number: int | None = None
    source = ""
    lines: list[JpLine] = []

    def flush() -> None:
        nonlocal number, source, lines
        if number is None:
            return
        sections.append(JpSection(number, source, tuple(lines)))
        number = None
        source = ""
        lines = []

    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("---"):
            match = SECTION_RE.fullmatch(line)
            if not match:
                raise RuntimeError(f"非规范 Section 头：{path}:{line_number}: {line}")
            flush()
            number = int(match.group(1))
            if number != len(sections) + 1:
                raise RuntimeError(f"Section 不连续：{path}:{line_number}")
            source = Path(match.group(2).strip()).name
            continue
        if number is None:
            raise RuntimeError(f"首个 Section 前存在正文：{path}:{line_number}")
        speaker, text = split_line(line)
        if not speaker or not text:
            raise RuntimeError(f"空说话人或正文：{path}:{line_number}")
        normalized = pipeline._normalize_exedra_speaker(speaker)
        kind = "narration" if normalized in pipeline.EXEDRA_NARRATION_SPEAKERS else "dialogue"
        lines.append(JpLine(speaker, text, kind))
    flush()
    if not sections:
        raise RuntimeError(f"缺少 Section：{path}")
    return tuple(sections)


def index_tw_json(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        raise SystemExit(f"台服剧情目录不存在：{root}")
    buckets: dict[str, list[Path]] = {}
    for path in sorted(root.rglob("*.json")):
        if path.is_symlink() or not path.is_file():
            continue
        buckets.setdefault(path.name.casefold(), []).append(path)
    duplicate = {name: paths for name, paths in buckets.items() if len(paths) > 1}
    if duplicate:
        examples = "; ".join(
            f"{name}: {', '.join(map(str, paths[:3]))}"
            for name, paths in list(duplicate.items())[:10]
        )
        raise SystemExit(f"台服 JSON 文件名不唯一，拒绝猜测匹配：{examples}")
    return {name: paths[0] for name, paths in buckets.items()}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"JSON 无法读取：{path}: {exc}") from exc


def tw_rows(path: Path) -> list[dict[str, Any]]:
    value = load_json(path)
    if not isinstance(value, dict):
        raise RuntimeError(f"台服 JSON 顶层不是对象：{path}")
    rows, diagnostics = pipeline.extract_exedra_dialogue_rows(value)
    serious = [item for item in diagnostics if "重复" not in item]
    if serious:
        raise RuntimeError(f"台服 JSON 结构诊断失败：{path}: {serious[:5]}")
    return rows


def render_group(
    jp_path: Path,
    sections: tuple[JpSection, ...],
    json_index: dict[str, Path],
    converter,
    output_dir: Path,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    lines: list[str] = []
    section_metadata: list[dict[str, Any]] = []
    source_json_metadata: list[dict[str, Any]] = []
    for section in sections:
        tw_path = json_index.get(section.source.casefold())
        if tw_path is None:
            raise RuntimeError(f"缺少台服 JSON：{section.source}")
        raw_tw = load_json(tw_path)
        converted_tw = convert_tree(raw_tw, converter)
        converted_path = output_dir / section.source
        encoded_json = json_bytes(converted_tw)
        if converted_path.exists():
            if converted_path.read_bytes() != encoded_json:
                raise RuntimeError(f"已有中文 JSON 内容不同，拒绝覆盖：{converted_path}")
        else:
            converted_path.parent.mkdir(parents=True, exist_ok=True)
            converted_path.write_bytes(encoded_json)

        rows = tw_rows(tw_path)
        if len(rows) != len(section.lines):
            raise RuntimeError(
                f"台服/日文事件数不一致：{section.source}: "
                f"JP={len(section.lines)} TW={len(rows)}"
            )
        lines.append(f"--- [Section {section.number}] (Source: {section.source}) ---")
        for index, (jp_line, row) in enumerate(zip(section.lines, rows), start=1):
            action = str(row.get("action") or "").casefold()
            tw_kind = "narration" if action == "narration" else "dialogue"
            if tw_kind != jp_line.kind:
                raise RuntimeError(
                    f"台服/日文事件类型不一致：{section.source} 第 {index} 条："
                    f"JP={jp_line.kind} TW={tw_kind}"
                )
            translated = converter.convert(str(row.get("text") or "").strip())
            if not translated:
                raise RuntimeError(f"台服正文为空：{section.source} 第 {index} 条")
            # Keep the exact JP speaker identity. MagiReader translates display names at render
            # time, while the import validator can prove the recurrence sequence byte-for-byte.
            lines.append(f"{jp_line.speaker}：{translated}")
        lines.append("")
        episode_match = EPISODE_RE.search(section.source)
        section_metadata.append({
            "section": section.number,
            "source": section.source,
            "wikiEpisode": int(episode_match.group(1)) if episode_match else section.number - 1,
        })
        source_json_metadata.append({
            "source": section.source,
            "twPath": str(tw_path),
            "simplifiedJsonSha256": sha256_bytes(encoded_json),
        })
    return "\n".join(lines).strip() + "\n", section_metadata, source_json_metadata


def build_report(
    *,
    raw_category: str,
    group_key: str,
    jp_path: Path,
    cn_path: Path,
    section_metadata: list[dict[str, Any]],
    source_json_metadata: list[dict[str, Any]],
    source_root: Path,
) -> dict[str, Any]:
    jp_sections = pipeline._exedra_alignment_sections(jp_path)
    cn_sections = pipeline._exedra_alignment_sections(cn_path)
    if len(jp_sections) != len(cn_sections) or len(jp_sections) != len(section_metadata):
        raise RuntimeError(f"导入后 Section 数量不一致：{group_key}")
    reports: list[dict[str, Any]] = []
    for metadata, jp, cn in zip(section_metadata, jp_sections, cn_sections):
        if (
            jp.number != cn.number
            or jp.source_name != cn.source_name
            or jp.reader_block_count != cn.reader_block_count
            or jp.speaker_sequence_sha256 != cn.speaker_sequence_sha256
        ):
            raise RuntimeError(f"导入后结构证明失败：{group_key} Section {jp.number}")
        reports.append({
            **metadata,
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
        "group": {"category": raw_category, "groupKey": group_key},
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
        "sections": reports,
        "sourceJson": source_json_metadata,
    }


def iter_jp_groups() -> Iterable[tuple[Path, Path]]:
    for path in sorted(JP_ROOT.rglob("*.txt")):
        relative = path.relative_to(JP_ROOT)
        if path.name.endswith("_jp.txt") or path.name.endswith("_cn.txt"):
            continue
        if len(relative.parts) < 2:
            continue
        yield path, relative


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tw_json_root", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only-category", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    converter = load_opencc()
    tw_root = args.tw_json_root.resolve()
    json_index = index_tw_json(tw_root)
    selected = list(iter_jp_groups())
    if args.only_category:
        allowed = set(args.only_category)
        selected = [item for item in selected if item[1].parts[0] in allowed]
    if args.limit > 0:
        selected = selected[: args.limit]

    stats = {"existing_local": 0, "official_tw": 0, "missing_tw": 0, "failed": 0}
    failures: list[str] = []
    for index, (jp_path, relative) in enumerate(selected, start=1):
        output_dir = CN_ROOT / relative.parent
        cn_path = output_dir / relative.name
        group_key = jp_path.stem
        report_path = output_dir / f"{group_key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}"
        if cn_path.exists() or report_path.exists():
            stats["existing_local"] += 1
            continue
        try:
            sections = parse_jp_txt(jp_path)
            missing = [section.source for section in sections if section.source.casefold() not in json_index]
            if missing:
                stats["missing_tw"] += 1
                continue
            if args.dry_run:
                for section in sections:
                    rows = tw_rows(json_index[section.source.casefold()])
                    if len(rows) != len(section.lines):
                        raise RuntimeError(
                            f"事件数不一致：{section.source}: JP={len(section.lines)} TW={len(rows)}"
                        )
                stats["official_tw"] += 1
                continue
            output_dir.mkdir(parents=True, exist_ok=True)
            rendered, section_metadata, source_json_metadata = render_group(
                jp_path, sections, json_index, converter, output_dir
            )
            cn_path.write_text(rendered, encoding="utf-8")
            report = build_report(
                raw_category=relative.parts[0],
                group_key=group_key,
                jp_path=jp_path,
                cn_path=cn_path,
                section_metadata=section_metadata,
                source_json_metadata=source_json_metadata,
                source_root=tw_root,
            )
            report_path.write_bytes(json_bytes(report))
            stats["official_tw"] += 1
        except Exception as exc:  # fail closed per group, continue audit
            stats["failed"] += 1
            failures.append(f"{relative.as_posix()}: {exc}")
            # Never leave a partially proven group behind.
            if cn_path.exists():
                cn_path.unlink()
            if report_path.exists():
                report_path.unlink()
            for section in parse_jp_txt(jp_path):
                candidate = output_dir / section.source
                if candidate.exists():
                    candidate.unlink()
        if index % 25 == 0:
            print(f"processed {index}/{len(selected)} {stats}")

    audit_path = ROOT / "artifacts/exedra_official_tw_import_report.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps({"stats": stats, "failures": failures}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False))
    if failures:
        print(f"失败 {len(failures)} 组；详见 {audit_path}", file=sys.stderr)
    return 2 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
