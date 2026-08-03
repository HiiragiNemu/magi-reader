#!/usr/bin/env python3
"""Inject already-simplified official Taiwan Exedra text into JP schemas."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT)]
import import_exedra_official_tw as tw  # noqa: E402
import generate_story_index as pipeline  # noqa: E402

SCENARIO_SHA256 = "64c86700651b845b484f6100fed61a8c2b860028cda8130456a57979ee907452"
MANIFEST_SHA256 = "9125ae75d02ac69572fafc08fe2c1479ff872f6394d03b77f5bd046471ebda74"


def load_mst(root: Path, name: str) -> list[dict[str, Any]]:
    value = json.loads((root / name).read_text(encoding="utf-8-sig"))
    payload = value.get("payload") if isinstance(value, dict) else None
    rows = payload.get("mstList") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise RuntimeError(f"MST 格式无效：{name}")
    return rows


def resource_key(value: str) -> str:
    path = PurePosixPath(value.strip().replace("\\", "/"))
    if path.suffix.casefold() == ".json":
        path = path.with_suffix("")
    return path.as_posix().strip("/").casefold()


def title_catalog(root: Path) -> dict[str, dict[str, Any]]:
    adv = load_mst(root, "getAdvMstList.json")
    stages = {
        row["fieldStageMstId"]: row
        for row in load_mst(root, "getFieldStageMstList.json")
        if isinstance(row.get("fieldStageMstId"), int)
    }
    links: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in load_mst(root, "getCollectionConditionMstList.json"):
        if row.get("objectType") != 6:
            continue
        adv_id, stage_id = row.get("objectId"), row.get("fieldStageMstId")
        if isinstance(adv_id, int) and stage_id in stages:
            links[adv_id].append(stages[stage_id])

    def rank(stage: dict[str, Any]) -> tuple[int, int]:
        difficulty = int(stage.get("difficulty") or 99)
        return {1: 0, 4: 1, 2: 2, 3: 3}.get(difficulty, 9), int(
            stage.get("fieldStageMstId") or 0
        )

    result: dict[str, dict[str, Any]] = {}
    for row in adv:
        resource = row.get("advResourceName")
        adv_id = row.get("advMstId")
        if not isinstance(resource, str) or not isinstance(adv_id, int):
            continue
        key = resource_key(resource)
        if key in result:
            raise RuntimeError(f"advResourceName 重复：{resource}")
        name = str(row.get("name") or "").strip()
        sub_name = str(row.get("subName") or "").strip()
        section_title = sub_name or name or PurePosixPath(key).name
        if name and sub_name and name != sub_name and not name.startswith(sub_name):
            section_title = f"{name} · {sub_name}"
        choices = sorted(links.get(adv_id, []), key=rank)
        stage = choices[0] if choices else {}
        chapter_title = " · ".join(
            item
            for item in (
                str(stage.get("subTitle") or "").strip(),
                str(stage.get("name") or "").strip(),
            )
            if item
        )
        result[key] = {
            "advMstId": adv_id,
            "advTitleMstId": int(row.get("advTitleMstId") or 0),
            "name": name,
            "subName": sub_name,
            "sectionTitle": section_title,
            "chapterTitle": chapter_title,
            "fieldStageMstId": int(stage.get("fieldStageMstId") or 0),
            "fieldSeriesMstId": int(stage.get("fieldSeriesMstId") or 0),
        }
    return result


def replace_directory(staged: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    incoming = target.with_name(f".{target.name}.tw-incoming")
    backup = target.with_name(f".{target.name}.tw-backup")
    shutil.rmtree(incoming, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    shutil.copytree(staged, incoming)
    installed = False
    try:
        if target.exists():
            os.replace(target, backup)
        os.replace(incoming, target)
        installed = True
    except Exception:
        if installed:
            shutil.rmtree(target, ignore_errors=True)
        if backup.exists():
            os.replace(backup, target)
        raise
    finally:
        shutil.rmtree(incoming, ignore_errors=True)
        if installed:
            shutil.rmtree(backup, ignore_errors=True)


def import_corpus(scenario_root: Path, manifest_root: Path) -> dict[str, Any]:
    index = tw.TwSourceIndex(scenario_root)
    titles = title_catalog(manifest_root)
    metadata: dict[str, dict[str, Any]] = {}
    stats: Counter[str] = Counter()
    failures: list[dict[str, str]] = []

    for number, group in enumerate(tw.load_groups(), 1):
        category = str(group.get("category") or "")
        key = str(group.get("groupKey") or "")
        identity = str(group.get("id") or "")
        sources = group.get("sources")
        try:
            if not category or not key or not identity or not isinstance(sources, list):
                raise RuntimeError("manifest group 无效")
            jp_txt = tw.JP_ROOT / str(group.get("textFile") or "")
            sections = tw.parse_txt(jp_txt)
            if len(sections) != len(sources):
                raise RuntimeError("manifest/Section 数量不同")
            translated: list[list[str]] = []
            resolved: list[tuple[tw.Section, str, Path, Path]] = []
            official_sections: list[dict[str, Any]] = []
            chapters: Counter[str] = Counter()

            for section, source_value in zip(sections, sources):
                source = str(source_value)
                if PurePosixPath(source).name != section.source:
                    raise RuntimeError(f"manifest/Section 来源不同：{source}")
                tw_json = index.resolve(source)
                jp_json = tw.JP_ROOT / category / key / section.source
                jp_rows, tw_rows = tw.extract_rows(jp_json), tw.extract_rows(tw_json)
                tw.validate_row_alignment(section.source, jp_rows, tw_rows, section)
                texts = [str(row.get("text") or "").strip() for row in tw_rows]
                if any(not text for text in texts):
                    raise RuntimeError(f"台服正文为空：{section.source}")
                translated.append(texts)
                resolved.append((section, source, jp_json, tw_json))
                title = titles.get(resource_key(source), {})
                chapter = str(title.get("chapterTitle") or "")
                if chapter:
                    chapters[chapter] += 1
                official_sections.append(
                    {
                        "section": section.number,
                        "source": section.source,
                        "resource": resource_key(source),
                        **title,
                    }
                )

            with tempfile.TemporaryDirectory(prefix=f"tw-{category}-{key}-") as temp:
                stage = Path(temp)
                json_meta: list[dict[str, Any]] = []
                for (section, source, jp_json, tw_json), texts in zip(resolved, translated):
                    digest = tw.apply_translated_texts(jp_json, texts, stage / section.source)
                    json_meta.append(
                        {
                            "source": section.source,
                            "manifestSourcePath": source,
                            "twPath": index.relative_name(tw_json),
                            "twSha256": pipeline._sha256_file(tw_json),
                            "simplifiedJsonSha256": digest,
                            "provenance": "official_tw_human",
                        }
                    )
                cn_txt = stage / f"{key}_cn.txt"
                cn_txt.write_text(tw.render_cn(sections, translated), encoding="utf-8")
                report = tw.build_report(
                    category,
                    key,
                    jp_txt,
                    cn_txt,
                    f"Scenarios_zh-CN.7z#{SCENARIO_SHA256}",
                    json_meta,
                )
                report.update(
                    {
                        "sourceArchiveSha256": SCENARIO_SHA256,
                        "manifestArchiveSha256": MANIFEST_SHA256,
                        "officialTitles": official_sections,
                    }
                )
                (stage / f"{key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}").write_bytes(
                    tw.json_bytes(report)
                )
                chapter_title = chapters.most_common(1)[0][0] if chapters else ""
                sidecar = {
                    "version": 2,
                    "sourceIdentity": identity,
                    "provenance": "official_tw_human",
                    "machineTranslation": False,
                    "officialTw": True,
                    "sourceArchiveSha256": SCENARIO_SHA256,
                    "manifestArchiveSha256": MANIFEST_SHA256,
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "jpSha256": pipeline._sha256_utf8_text_file(jp_txt),
                    "cnSha256": pipeline._sha256_utf8_text_file(cn_txt),
                    "chapterTitle": chapter_title,
                    "sections": official_sections,
                    "sourceJson": json_meta,
                }
                (stage / f"{key}_cn.provenance.json").write_bytes(tw.json_bytes(sidecar))
                pipeline._validate_exedra_cn_import_report(
                    group=pipeline.OrganizedExedraGroup(
                        manifest_id=identity,
                        raw_category=category,
                        category=pipeline.EXEDRA_CATEGORY_MAP[category],
                        group_key=key,
                        output_dir=Path(category, key),
                        text_file=Path(str(group.get("textFile") or "")),
                        source_paths=tuple(str(v) for v in sources),
                        source_names=tuple(section.source for section in sections),
                        title="",
                    ),
                    jp_path=jp_txt,
                    cn_path=cn_txt,
                    jp_sections=pipeline._exedra_alignment_sections(jp_txt),
                    cn_sections=pipeline._exedra_alignment_sections(cn_txt),
                )
                replace_directory(stage, tw.CN_ROOT / category / key)

            metadata[identity] = {
                "sourceIdentity": identity,
                "category": category,
                "groupKey": key,
                "officialTw": True,
                "chapterTitle": chapter_title,
                "sectionTitles": [
                    str(item.get("sectionTitle") or item["source"])
                    for item in official_sections
                ],
                "sections": official_sections,
            }
            stats["official_tw_groups"] += 1
            stats["official_tw_json_files"] += len(sources)
            stats["official_tw_text_events"] += sum(map(len, translated))
        except FileNotFoundError as exc:
            stats["missing_tw_groups"] += 1
            failures.append({"group": f"{category}/{key}", "reason": str(exc)})
        except Exception as exc:  # noqa: BLE001
            stats["failed_groups"] += 1
            failures.append({"group": f"{category}/{key}", "reason": str(exc)})
        if number % 25 == 0:
            print(f"TW_IMPORT_PROGRESS {number}/443 {dict(stats)}")

    value = {
        "version": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "scenarioArchiveSha256": SCENARIO_SHA256,
        "manifestArchiveSha256": MANIFEST_SHA256,
        "stats": dict(stats),
        "failures": failures,
    }
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "exedra_official_tw_import_report.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "tw_official_metadata.generated.json").write_text(
        json.dumps(
            {
                "version": 1,
                "scenarioArchiveSha256": SCENARIO_SHA256,
                "manifestArchiveSha256": MANIFEST_SHA256,
                "stories": metadata,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if stats["failed_groups"]:
        raise RuntimeError(f"台服导入结构失败：{stats['failed_groups']}")
    return value
