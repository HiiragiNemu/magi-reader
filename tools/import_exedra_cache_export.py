#!/usr/bin/env python3
"""Persist an exported Exedra localization cache into the repository.

Download `/api/admin/exedra-localize/export` from the test site, then run:
    py tools/import_exedra_cache_export.py exedra-localization-cache-v1.json

The importer preserves JP speaker identities, writes translated Comment cells into
copies of the organized JP JSON, creates `<groupKey>_cn.txt`, and emits the same
schema-v1 proof used by local/official imports. Existing CN groups are never
replaced unless `--replace-machine` is explicitly used and the existing
provenance sidecar is also `machine_translation`.
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
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))
import generate_story_index as pipeline  # noqa: E402
import import_exedra_official_tw as common  # noqa: E402

JP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"
CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
MANIFEST = JP_ROOT / "exedra_manifest.json"
IDENTITY_RE = re.compile(r"^exedra:([^:]+):([^:]+)$", re.I)
VALID_PROVENANCE = {"exedra_wiki_human", "machine_translation", "official_tw_human"}


@dataclass(frozen=True)
class CachedSection:
    number: int
    source: str
    texts: tuple[str, ...]


def normalize(value: str) -> str:
    return value.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")


def parse_cached_text(raw: str) -> tuple[CachedSection, ...]:
    sections: list[CachedSection] = []
    number: int | None = None
    source = ""
    texts: list[str] = []

    def flush() -> None:
        nonlocal number, source, texts
        if number is not None:
            sections.append(CachedSection(number, source, tuple(texts)))
        number = None
        source = ""
        texts = []

    for line_number, raw_line in enumerate(normalize(raw).splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("---"):
            match = common.SECTION_RE.fullmatch(line)
            if not match:
                raise RuntimeError(f"缓存含非法 Section 头：第 {line_number} 行")
            flush()
            number = int(match.group(1))
            if number != len(sections) + 1:
                raise RuntimeError("缓存 Section 编号不连续")
            source = Path(match.group(2)).name
            continue
        if number is None:
            raise RuntimeError("缓存正文位于首个 Section 之前")
        _speaker, text = common.split_line(line)
        if not text:
            raise RuntimeError(f"缓存含空正文：第 {line_number} 行")
        texts.append(text)
    flush()
    if not sections:
        raise RuntimeError("缓存不含 Section")
    return tuple(sections)


def load_export(path: Path) -> list[dict[str, Any]]:
    value = common.load_json(path)
    records = value.get("records") if isinstance(value, dict) else None
    if value.get("version") != 1 or not isinstance(records, list):
        raise RuntimeError("Exedra 缓存导出版本无效")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            raise RuntimeError(f"records[{index}] 不是对象")
        identity = str(item.get("source_identity") or "")
        if identity.casefold() in seen:
            raise RuntimeError(f"缓存来源身份重复：{identity}")
        seen.add(identity.casefold())
        provenance = str(item.get("provenance") or "")
        if provenance not in VALID_PROVENANCE:
            raise RuntimeError(f"缓存来源类型不受支持：{identity}: {provenance}")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(f"缓存正文为空：{identity}")
        actual_cn = hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()
        if actual_cn != str(item.get("cn_sha256") or ""):
            raise RuntimeError(f"缓存中文 SHA-256 不一致：{identity}")
        result.append(item)
    return result


def group_map() -> dict[str, dict[str, Any]]:
    value = common.load_json(MANIFEST)
    groups = value.get("groups") if isinstance(value, dict) else None
    if value.get("schemaVersion") != 1 or not isinstance(groups, list) or len(groups) != 443:
        raise RuntimeError("Exedra manifest 无效")
    return {str(group["id"]).casefold(): group for group in groups if isinstance(group, dict)}


def can_replace(output_dir: Path, group_key: str, replace_machine: bool) -> bool:
    cn_path = output_dir / f"{group_key}_cn.txt"
    report = output_dir / f"{group_key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}"
    sidecar = output_dir / f"{group_key}_cn.provenance.json"
    if not cn_path.exists() and not report.exists() and not sidecar.exists():
        return True
    if not replace_machine or not sidecar.is_file():
        return False
    value = common.load_json(sidecar)
    return isinstance(value, dict) and value.get("provenance") == "machine_translation"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_json", type=Path)
    parser.add_argument("--replace-machine", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    records = load_export(args.export_json.resolve())
    if args.limit > 0:
        records = records[: args.limit]
    groups = group_map()
    stats = {
        "imported_wiki": 0,
        "imported_machine": 0,
        "imported_official_tw": 0,
        "existing_skipped": 0,
        "failed": 0,
    }
    failures: list[str] = []

    for record in records:
        identity = str(record["source_identity"])
        group = groups.get(identity.casefold())
        if group is None:
            stats["failed"] += 1
            failures.append(f"{identity}: manifest 中不存在")
            continue
        category = str(group["category"])
        group_key = str(group["groupKey"])
        output_dir = CN_ROOT / category / group_key
        cn_path = output_dir / f"{group_key}_cn.txt"
        report_path = output_dir / f"{group_key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}"
        sidecar_path = output_dir / f"{group_key}_cn.provenance.json"
        if not can_replace(output_dir, group_key, args.replace_machine):
            stats["existing_skipped"] += 1
            continue
        try:
            jp_path = JP_ROOT / str(group["textFile"])
            expected_jp_sha = pipeline._sha256_utf8_text_file(jp_path)
            if expected_jp_sha != str(record.get("jp_sha256") or ""):
                raise RuntimeError("日文源 SHA-256 已变化，缓存过期")
            jp_sections = common.parse_txt(jp_path)
            cached_sections = parse_cached_text(str(record["text"]))
            if len(jp_sections) != len(cached_sections):
                raise RuntimeError("缓存/日文 Section 数量不同")
            translated_sections: list[list[str]] = []
            for jp, cached in zip(jp_sections, cached_sections):
                if jp.number != cached.number or jp.source != cached.source:
                    raise RuntimeError(f"Section 来源不同：{jp.source}, {cached.source}")
                if len(jp.lines) != len(cached.texts):
                    raise RuntimeError(
                        f"{jp.source} 文本事件数不同：JP={len(jp.lines)} CN={len(cached.texts)}"
                    )
                translated_sections.append(list(cached.texts))
            if args.dry_run:
                stats[f"imported_{record['provenance'].replace('exedra_', '').replace('_human', '')}"] = (
                    stats.get(f"imported_{record['provenance'].replace('exedra_', '').replace('_human', '')}", 0) + 1
                )
                continue

            output_dir.mkdir(parents=True, exist_ok=True)
            json_meta = []
            for section, texts in zip(jp_sections, translated_sections):
                jp_json = JP_ROOT / category / group_key / section.source
                destination = output_dir / section.source
                digest = common.apply_translated_texts(jp_json, texts, destination)
                json_meta.append({"source": section.source, "simplifiedJsonSha256": digest})
            cn_path.write_text(common.render_cn(jp_sections, translated_sections), encoding="utf-8")
            report = common.build_report(
                category,
                group_key,
                jp_path,
                cn_path,
                args.export_json.resolve(),
                json_meta,
            )
            report["provenance"] = record["provenance"]
            report["sourceUrl"] = str(record.get("source_url") or "")
            report_path.write_bytes(common.json_bytes(report))
            sidecar_path.write_bytes(common.json_bytes({
                "version": 1,
                "storyId": record.get("story_id"),
                "sourceIdentity": identity,
                "provenance": record["provenance"],
                "sourceUrl": record.get("source_url") or "",
                "generatedAt": record.get("generated_at"),
                "jpSha256": record.get("jp_sha256"),
                "cnSha256": pipeline._sha256_utf8_text_file(cn_path),
            }))
            key = {
                "exedra_wiki_human": "imported_wiki",
                "machine_translation": "imported_machine",
                "official_tw_human": "imported_official_tw",
            }[str(record["provenance"])]
            stats[key] += 1
        except Exception as exc:
            stats["failed"] += 1
            failures.append(f"{identity}: {exc}")
            if not args.dry_run:
                cn_path.unlink(missing_ok=True)
                report_path.unlink(missing_ok=True)
                sidecar_path.unlink(missing_ok=True)
                for source in group.get("sources") or []:
                    (output_dir / Path(str(source)).name).unlink(missing_ok=True)

    audit = ROOT / "artifacts/exedra_cache_import_report.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(
        json.dumps({"stats": stats, "failures": failures}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
