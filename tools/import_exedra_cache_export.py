#!/usr/bin/env python3
"""Persist exported Exedra Wiki Chinese into the repository.

Download `/api/admin/exedra-localize/export` from the isolated test site, then:
    py tools/import_exedra_cache_export.py exedra-localization-cache-v1.json

Only `exedra_wiki_human` records with exact Exedra identities and exedra.wiki
source URLs are accepted. Existing Chinese groups are never overwritten.
Official Taiwan text uses `import_exedra_official_tw.py` instead.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

import generate_story_index as pipeline  # noqa: E402
import import_exedra_official_tw as common  # noqa: E402

JP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"
CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
MANIFEST = JP_ROOT / "exedra_manifest.json"
STAGING_ROOT = ROOT / "artifacts/.exedra-wiki-staging"
SHA256_RE = re.compile(r"^[a-f0-9]{64}$", re.I)


@dataclass(frozen=True)
class CachedSection:
    number: int
    source: str
    texts: tuple[str, ...]


def normalize(value: str) -> str:
    return (
        value.removeprefix("\ufeff")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\x00", "")
    )


def validate_wiki_url(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2_000:
        raise RuntimeError("Wiki 来源 URL 为空或过长")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != "exedra.wiki":
        raise RuntimeError(f"Wiki 来源域名无效：{value!r}")
    decoded_path = unquote(parsed.path)
    if not decoded_path.startswith("/wiki/") or not decoded_path.rstrip("/").endswith(
        "/Story/Chinese"
    ):
        raise RuntimeError(f"Wiki 来源路径不是角色中文剧情页：{value!r}")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise RuntimeError(f"Wiki 来源 URL 含不允许的认证或端口：{value!r}")
    return value


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
            source = PurePosixPath(match.group(2)).name
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
    if not isinstance(value, dict):
        raise RuntimeError("Exedra 缓存导出顶层不是对象")
    records = value.get("records")
    if (
        value.get("version") != 1
        or value.get("policy") != "trusted_exedra_sources_only"
        or not isinstance(records, list)
    ):
        raise RuntimeError("Exedra 缓存导出版本或政策无效")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            raise RuntimeError(f"records[{index}] 不是对象")
        identity = str(item.get("source_identity") or "")
        if not identity or identity.casefold() in seen:
            raise RuntimeError(f"缓存来源身份为空或重复：{identity}")
        seen.add(identity.casefold())
        if item.get("provenance") != "exedra_wiki_human":
            raise RuntimeError(
                f"缓存含非 Wiki 人工来源，拒绝导入：{identity}: "
                f"{item.get('provenance')!r}"
            )
        item["source_url"] = validate_wiki_url(item.get("source_url"))
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(f"缓存正文为空：{identity}")
        actual_cn = hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()
        declared_cn = str(item.get("cn_sha256") or "")
        declared_jp = str(item.get("jp_sha256") or "")
        if not SHA256_RE.fullmatch(declared_cn) or actual_cn != declared_cn.lower():
            raise RuntimeError(f"缓存中文 SHA-256 不一致：{identity}")
        if not SHA256_RE.fullmatch(declared_jp):
            raise RuntimeError(f"缓存日文 SHA-256 无效：{identity}")
        result.append(item)
    return result


def group_map() -> dict[str, dict[str, Any]]:
    value = common.load_json(MANIFEST)
    if not isinstance(value, dict):
        raise RuntimeError("Exedra manifest 顶层不是对象")
    groups = value.get("groups")
    if value.get("schemaVersion") != 1 or not isinstance(groups, list) or len(groups) != 443:
        raise RuntimeError("Exedra manifest 无效")
    result = {
        str(group["id"]).casefold(): group
        for group in groups
        if isinstance(group, dict)
    }
    if len(result) != 443:
        raise RuntimeError("Exedra manifest 逻辑组不完整或 ID 重复")
    return result


def expected_story_id(group: dict[str, Any]) -> str:
    category = pipeline.EXEDRA_CATEGORY_MAP[str(group["category"])]
    group_key = str(group["groupKey"])
    identity = f"{group['category']}/{group_key}/{group_key}_jp.txt"
    return pipeline.safe_exedra_story_id(category, identity, group_key)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_json", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    export_path = args.export_json.resolve(strict=True)
    records = load_export(export_path)
    if args.limit > 0:
        records = records[: args.limit]
    groups = group_map()
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    stats = {"imported_wiki": 0, "existing_skipped": 0, "failed": 0}
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
        source_paths = group.get("sources")
        if not isinstance(source_paths, list):
            stats["failed"] += 1
            failures.append(f"{identity}: manifest sources 无效")
            continue
        if str(record.get("story_id") or "") != expected_story_id(group):
            stats["failed"] += 1
            failures.append(f"{identity}: story_id 与 manifest 不一致")
            continue

        output_dir = CN_ROOT / category / group_key
        cn_name = f"{group_key}_cn.txt"
        report_name = f"{group_key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}"
        sidecar_name = f"{group_key}_cn.provenance.json"
        expected_names = {
            cn_name,
            report_name,
            sidecar_name,
            *[PurePosixPath(str(value)).name for value in source_paths],
        }
        existing = [output_dir / name for name in expected_names if (output_dir / name).exists()]
        cn_path = output_dir / cn_name
        report_path = output_dir / report_name
        if cn_path.is_file() and report_path.is_file():
            stats["existing_skipped"] += 1
            continue
        if existing:
            stats["failed"] += 1
            failures.append(f"{identity}: 发现不完整既有产物，拒绝覆盖：{existing[:3]}")
            continue

        try:
            jp_path = JP_ROOT / str(group["textFile"])
            expected_jp_sha = pipeline._sha256_utf8_text_file(jp_path)
            if expected_jp_sha != str(record.get("jp_sha256") or "").lower():
                raise RuntimeError("日文源 SHA-256 已变化，缓存过期")

            jp_sections = common.parse_txt(jp_path)
            cached_sections = parse_cached_text(str(record["text"]))
            if len(jp_sections) != len(cached_sections):
                raise RuntimeError("缓存/日文 Section 数量不同")
            if len(source_paths) != len(jp_sections):
                raise RuntimeError("manifest/日文 Section 数量不同")

            translated_sections: list[list[str]] = []
            for jp, cached, raw_source in zip(
                jp_sections,
                cached_sections,
                source_paths,
            ):
                if (
                    jp.number != cached.number
                    or jp.source != cached.source
                    or PurePosixPath(str(raw_source)).name != jp.source
                ):
                    raise RuntimeError(
                        f"Section 来源不同：{raw_source}, {jp.source}, {cached.source}"
                    )
                if len(jp.lines) != len(cached.texts):
                    raise RuntimeError(
                        f"{jp.source} 文本事件数不同："
                        f"JP={len(jp.lines)} CN={len(cached.texts)}"
                    )
                translated_sections.append(list(cached.texts))

            with tempfile.TemporaryDirectory(
                prefix=f"{category}-{group_key}-",
                dir=STAGING_ROOT,
            ) as temporary:
                stage = Path(temporary)
                json_meta: list[dict[str, Any]] = []
                for section, texts, raw_source in zip(
                    jp_sections,
                    translated_sections,
                    source_paths,
                ):
                    jp_json = JP_ROOT / category / group_key / section.source
                    destination = stage / section.source
                    digest = common.apply_translated_texts(
                        jp_json,
                        texts,
                        destination,
                    )
                    json_meta.append({
                        "source": section.source,
                        "manifestSourcePath": str(raw_source),
                        "jpJsonSha256": pipeline._sha256_file(jp_json),
                        "simplifiedJsonSha256": digest,
                    })

                staged_cn = stage / cn_name
                staged_cn.write_text(
                    common.render_cn(jp_sections, translated_sections),
                    encoding="utf-8",
                )
                report = common.build_report(
                    category,
                    group_key,
                    jp_path,
                    staged_cn,
                    Path("exedra-wiki-export"),
                    json_meta,
                )
                report["provenance"] = "exedra_wiki_human"
                report["sourceUrl"] = record["source_url"]
                (stage / report_name).write_bytes(common.json_bytes(report))
                (stage / sidecar_name).write_bytes(common.json_bytes({
                    "version": 1,
                    "storyId": record.get("story_id"),
                    "sourceIdentity": identity,
                    "provenance": "exedra_wiki_human",
                    "sourceUrl": record["source_url"],
                    "generatedAt": record.get("generated_at"),
                    "jpSha256": record.get("jp_sha256"),
                    "cnSha256": pipeline._sha256_utf8_text_file(staged_cn),
                    "sourceJson": json_meta,
                }))

                organized_group = pipeline.OrganizedExedraGroup(
                    manifest_id=identity,
                    raw_category=category,
                    category=pipeline.EXEDRA_CATEGORY_MAP[category],
                    group_key=group_key,
                    output_dir=Path(category, group_key),
                    text_file=Path(str(group["textFile"])),
                    source_paths=tuple(str(value) for value in source_paths),
                    source_names=tuple(section.source for section in jp_sections),
                    title="",
                )
                pipeline._validate_exedra_cn_import_report(
                    group=organized_group,
                    jp_path=jp_path,
                    cn_path=staged_cn,
                    jp_sections=pipeline._exedra_alignment_sections(jp_path),
                    cn_sections=pipeline._exedra_alignment_sections(staged_cn),
                )
                if not args.dry_run:
                    common.commit_staged_group(stage, output_dir)
            stats["imported_wiki"] += 1
        except Exception as exc:
            stats["failed"] += 1
            failures.append(f"{identity}: {exc}")

    audit = ROOT / "artifacts/exedra_wiki_cache_import_report.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(
        json.dumps(
            {"stats": stats, "failures": failures},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    common.shutil.rmtree(STAGING_ROOT, ignore_errors=True)
    print(json.dumps(stats, ensure_ascii=False))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
