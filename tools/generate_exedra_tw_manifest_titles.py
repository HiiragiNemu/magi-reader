#!/usr/bin/env python3
"""Build the auditable Exedra TW chapter/section title catalogue.

The catalogue deliberately keeps three authorities separate:

* ``getFieldStageMstList`` is the only chapter-title authority.
* ``getAdvMstList`` is the only section-title authority.
* the resolved TW Scenario catalogue may supply a leaf/story label only when
  an Adv section label is absent; it never acts as a chapter join.

Every join is exact.  Ambiguous or absent relationships retain the normalized
resource/group identifier and are emitted in ``unresolved`` rather than being
filled by a filename heuristic or majority vote.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT)]

import generate_story_index as pipeline  # noqa: E402
from tw_official_import_core import (  # noqa: E402
    load_mst,
    official_scenario_title_card,
    resource_key,
    simplified_converter,
)
from tw_authentic_scenario import extract_text_events  # noqa: E402


DEFAULT_EXEDRA_MANIFEST = (
    ROOT / "magiraexedra-source-master" / "Scenarios_full" / "exedra_manifest.json"
)
DEFAULT_EXEDRA_JP_ROOT = DEFAULT_EXEDRA_MANIFEST.parent
DEFAULT_EXEDRA_CN_ROOT = (
    ROOT / "magiraexedra-translate-data-master" / "Scenarios_full"
)
DEFAULT_OUTPUT = ROOT / "artifacts" / "exedra_tw_manifest_titles.generated.json"
GALLERY_REPORT_NAME = "tw_gallery_export_report.json"
SCENARIO_CATALOG_RELATIVE = PurePosixPath("tw/resolved_catalog_v3.json")
REQUIRED_TITLE_MANIFESTS = (
    "getAdvMstList.json",
    "getFieldStageMstList.json",
    "getFieldPointMstList.json",
    "getCollectionConditionMstList.json",
)
TITLE_POLICY = "exact_fieldpoint_collection_adv_stage_no_guessing"
JAPANESE_SCRIPT_RE = re.compile(r"[\u3040-\u30ff]")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class CatalogError(RuntimeError):
    """The title source contract is invalid or ambiguous."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"JSON 无法读取：{path}: {exc}") from exc


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _canonical_category(value: str) -> str:
    for category in pipeline.EXEDRA_CATEGORY_MAP:
        if category.casefold() == value.casefold():
            return category
    raise CatalogError(f"未知 Exedra 分类：{value!r}")


def _category_from_resource(key: str) -> str:
    category = PurePosixPath(key).parts[0] if PurePosixPath(key).parts else ""
    return _canonical_category(category)


def _parse_adv_ids(value: Any, *, field: str, point_id: int) -> list[int]:
    text = str(value or "").strip()
    if not text:
        return []
    tokens = [token.strip() for token in text.split(",")]
    if any(not token or not token.isdecimal() for token in tokens):
        raise CatalogError(
            f"FieldPoint {point_id} 的 {field} 不是逗号分隔 Adv ID：{text!r}"
        )
    result = [int(token) for token in tokens]
    if len(result) != len(set(result)):
        raise CatalogError(f"FieldPoint {point_id} 的 {field} 含重复 Adv ID")
    return result


def _manifest_binding(manifest_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    report_path = manifest_root / GALLERY_REPORT_NAME
    report = _read_json(report_path)
    if (
        not isinstance(report, dict)
        or report.get("schemaVersion") != 1
        or report.get("complete") is not True
        or not isinstance(report.get("masterRevision"), str)
        or not report["masterRevision"]
        or not isinstance(report.get("files"), list)
    ):
        raise CatalogError("TW gallery export report 格式或完成状态无效")

    report_files: dict[str, dict[str, Any]] = {}
    for item in report["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("file"), str):
            raise CatalogError("TW gallery export report files 项无效")
        name = item["file"]
        if name in report_files:
            raise CatalogError(f"TW gallery export report 文件重复：{name}")
        report_files[name] = item

    binding: dict[str, Any] = {}
    for name in REQUIRED_TITLE_MANIFESTS:
        path = manifest_root / name
        item = report_files.get(name)
        if item is None or not path.is_file():
            raise CatalogError(f"标题 Manifest 未被当前 export report 收录：{name}")
        actual_sha = _sha256(path)
        expected_sha = str(item.get("sha256") or "").casefold()
        rows = load_mst(manifest_root, name)
        if (
            not SHA256_RE.fullmatch(expected_sha)
            or actual_sha != expected_sha
            or item.get("entries") != len(rows)
        ):
            raise CatalogError(f"标题 Manifest 与 export report 不一致：{name}")
        binding[name] = {
            "sha256": actual_sha,
            "entries": len(rows),
            "endpoint": str(item.get("endpoint") or ""),
            "revision": str(item.get("revision") or ""),
        }
    return report, {
        "masterRevision": report["masterRevision"],
        "galleryExportReport": {
            "relativePath": GALLERY_REPORT_NAME,
            "sha256": _sha256(report_path),
        },
        "manifests": binding,
    }


def _load_exedra_manifest(path: Path) -> dict[str, Any]:
    manifest = _read_json(path)
    if (
        not isinstance(manifest, dict)
        or manifest.get("schemaVersion") != 1
        or manifest.get("categoryOrder") != list(pipeline.EXEDRA_CATEGORY_MAP)
        or not isinstance(manifest.get("groups"), list)
        or not isinstance(manifest.get("sources"), list)
    ):
        raise CatalogError("Exedra organizer manifest 格式无效")
    return manifest


def _load_scenario_catalog(manifest_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    path = manifest_root.joinpath(*SCENARIO_CATALOG_RELATIVE.parts)
    value = _read_json(path)
    if (
        not isinstance(value, dict)
        or value.get("schemaVersion") != 1
        or value.get("language") != "zh_TW"
        or not isinstance(value.get("entries"), list)
    ):
        raise CatalogError("TW resolved Scenario catalog 格式无效")

    result: dict[str, dict[str, Any]] = {}
    for entry in value["entries"]:
        if not isinstance(entry, dict):
            raise CatalogError("TW resolved Scenario catalog 含非对象条目")
        full_path = str(entry.get("fullPath") or "")
        if not full_path.startswith("Scenarios/"):
            continue
        relative = full_path.removeprefix("Scenarios/")
        key = resource_key(relative)
        if not key or key in result:
            raise CatalogError(f"TW resolved Scenario catalog 资源重复：{key!r}")
        result[key] = entry
    return value, result


def _scenario_metadata(
    *,
    key: str,
    entry: Mapping[str, Any] | None,
    scenario_root: Path,
    convert: Callable[[str], str],
) -> dict[str, Any]:
    if entry is None:
        return {"status": "missing_from_resolved_catalog"}
    full_path = str(entry.get("fullPath") or "")
    prefix = "Scenarios/"
    if not full_path.startswith(prefix):
        raise CatalogError(f"Scenario fullPath 无效：{full_path!r}")
    relative = PurePosixPath(full_path.removeprefix(prefix))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise CatalogError(f"Scenario 相对路径无效：{full_path!r}")
    path = scenario_root.joinpath(*relative.parts)
    if not path.is_file():
        return {
            "status": "local_file_missing",
            "catalogFullPath": full_path,
            "catalogDecodedSha256": str(entry.get("decodedSha256") or ""),
            "revision": str(entry.get("revision") or ""),
        }
    local_sha = _sha256(path)
    catalog_sha = str(entry.get("decodedSha256") or "").casefold()
    hash_matches = bool(SHA256_RE.fullmatch(catalog_sha) and local_sha == catalog_sha)
    document = _read_json(path)
    if not isinstance(document, dict):
        raise CatalogError(f"TW Scenario 顶层不是对象：{full_path}")
    book_title_tw = str(document.get("bookTitle") or "").strip()
    content_name_tw = str(document.get("contentName") or "").strip()
    title_cards_tw: list[str] = []
    if _category_from_resource(key) == "2_Sub":
        for event in extract_text_events(document):
            if (
                str(event.get("action") or "").casefold() != "narration"
                or str(event.get("speaker") or "").strip()
            ):
                continue
            title_card = official_scenario_title_card(str(event.get("text") or ""))
            if title_card and title_card not in title_cards_tw:
                title_cards_tw.append(title_card)
    candidate_tw = content_name_tw or book_title_tw
    candidate_field = "contentName" if content_name_tw else "bookTitle" if book_title_tw else ""
    return {
        "status": "verified" if hash_matches else "catalog_hash_mismatch",
        "catalogFullPath": full_path,
        "catalogDecodedSha256": catalog_sha,
        "localSha256": local_sha,
        "revision": str(entry.get("revision") or ""),
        "decodedSize": int(entry.get("decodedSize") or 0),
        "bookTitleTw": book_title_tw,
        "bookTitle": convert(book_title_tw) if book_title_tw else "",
        "contentNameTw": content_name_tw,
        "contentName": convert(content_name_tw) if content_name_tw else "",
        "titleCardsTw": title_cards_tw if hash_matches else [],
        "titleCards": [convert(value) for value in title_cards_tw] if hash_matches else [],
        "titleCandidateTw": candidate_tw if hash_matches else "",
        "titleCandidate": convert(candidate_tw) if candidate_tw and hash_matches else "",
        "titleCandidateField": candidate_field if hash_matches else "",
    }


def _metadata_value(document: Mapping[str, Any]) -> tuple[str, str]:
    content_name = str(document.get("contentName") or "").strip()
    if content_name:
        return content_name, "contentName"
    book_title = str(document.get("bookTitle") or "").strip()
    if book_title:
        return book_title, "bookTitle"
    return "", ""


def _human_cn_metadata(
    *,
    manifest: Mapping[str, Any],
    cn_root: Path,
    jp_root: Path,
    convert: Callable[[str], str],
) -> dict[str, dict[str, Any]]:
    """Return only complete, explicit human metadata changes.

    Human provenance for translated dialogue is not evidence that an untouched
    Japanese ``bookTitle`` became Chinese.  A fallback is therefore accepted
    only when the complete group is human, every source JSON exists, and the CN
    metadata differs from the corresponding JP metadata while containing CJK
    and no Japanese kana.
    """

    result: dict[str, dict[str, Any]] = {}
    for group in manifest["groups"]:
        if not isinstance(group, dict):
            raise CatalogError("Exedra organizer group 不是对象")
        category = _canonical_category(str(group.get("category") or ""))
        group_key = str(group.get("groupKey") or "")
        identity = str(group.get("id") or "")
        sources = group.get("sources")
        if not identity or not group_key or not isinstance(sources, list) or not sources:
            raise CatalogError("Exedra organizer group 缺少 id/groupKey/sources")
        group_dir = cn_root / category / group_key
        sidecar_path = group_dir / f"{group_key}_cn.provenance.json"
        if not sidecar_path.is_file():
            continue
        sidecar = _read_json(sidecar_path)
        source_json = sidecar.get("sourceJson") if isinstance(sidecar, dict) else None
        provenance = str(sidecar.get("provenance") or "") if isinstance(sidecar, dict) else ""
        if (
            not isinstance(sidecar, dict)
            or sidecar.get("sourceIdentity") != identity
            or sidecar.get("machineTranslation") is not False
            or "human" not in provenance.casefold()
            or not isinstance(source_json, list)
            or len(source_json) != len(sources)
        ):
            continue
        source_evidence = {
            str(item.get("source") or ""): item
            for item in source_json
            if isinstance(item, dict) and "human" in str(item.get("provenance") or "").casefold()
        }
        if len(source_evidence) != len(sources):
            continue

        candidates: list[tuple[str, str, str, str]] = []
        complete = True
        for source_path in sources:
            source_path = str(source_path)
            source_name = PurePosixPath(source_path).name
            cn_path = group_dir / source_name
            jp_path = jp_root / category / group_key / source_name
            if (
                source_name not in source_evidence
                or not cn_path.is_file()
                or not jp_path.is_file()
            ):
                complete = False
                break
            cn_document = _read_json(cn_path)
            jp_document = _read_json(jp_path)
            if not isinstance(cn_document, dict) or not isinstance(jp_document, dict):
                complete = False
                break
            cn_value, cn_field = _metadata_value(cn_document)
            jp_value, _jp_field = _metadata_value(jp_document)
            if (
                cn_value
                and cn_value != jp_value
                and CJK_RE.search(cn_value)
                and JAPANESE_SCRIPT_RE.search(cn_value) is None
            ):
                candidates.append(
                    (resource_key(source_path), cn_value, cn_field, provenance)
                )
        if not complete:
            continue
        for key, value, field, provenance in candidates:
            result[key] = {
                "titleTw": value,
                "title": convert(value),
                "field": field,
                "provenance": provenance,
                "sourceIdentity": identity,
            }
    return result


def _stage_bridges(
    *,
    manifest_root: Path,
    adv_by_id: Mapping[int, Mapping[str, Any]],
    stages: Mapping[int, Mapping[str, Any]],
) -> tuple[dict[int, dict[int, dict[str, set[int] | set[str]]]], dict[str, int]]:
    points = load_mst(manifest_root, "getFieldPointMstList.json")
    point_by_id: dict[int, dict[str, Any]] = {}
    point_stage: dict[int, int] = {}
    for point in points:
        point_id = point.get("fieldPointMstId")
        stratum_id = point.get("fieldStratumMstId")
        if not isinstance(point_id, int) or not isinstance(stratum_id, int):
            raise CatalogError("FieldPoint 缺少整数 ID/fieldStratumMstId")
        if point_id in point_by_id:
            raise CatalogError(f"FieldPoint ID 重复：{point_id}")
        stage_id = stratum_id // 10
        if stage_id not in stages:
            raise CatalogError(
                f"FieldPoint {point_id} 的 fieldStratumMstId 无法精确关联 FieldStage"
            )
        point_by_id[point_id] = point
        point_stage[point_id] = stage_id

    bridges: dict[int, dict[int, dict[str, set[int] | set[str]]]] = defaultdict(dict)

    def add(adv_id: int, stage_id: int, *, method: str, point_id: int, condition_id: int = 0) -> None:
        if adv_id not in adv_by_id:
            raise CatalogError(f"章节桥引用不存在的 Adv ID：{adv_id}")
        stage_map = bridges[adv_id]
        evidence = stage_map.setdefault(
            stage_id,
            {"methods": set(), "fieldPointMstIds": set(), "conditionMstIds": set()},
        )
        methods = evidence["methods"]
        point_ids = evidence["fieldPointMstIds"]
        condition_ids = evidence["conditionMstIds"]
        assert isinstance(methods, set) and isinstance(point_ids, set) and isinstance(condition_ids, set)
        methods.add(method)
        point_ids.add(point_id)
        if condition_id:
            condition_ids.add(condition_id)

    direct_need_count = 0
    direct_point_value_count = 0
    for point_id, point in point_by_id.items():
        stage_id = point_stage[point_id]
        for adv_id in _parse_adv_ids(
            point.get("needViewAdvMstIds"),
            field="needViewAdvMstIds",
            point_id=point_id,
        ):
            add(
                adv_id,
                stage_id,
                method="field_point_need_view_adv",
                point_id=point_id,
            )
            direct_need_count += 1
        point_type = point.get("pointType")
        point_value_2 = point.get("pointValue2")
        if point_type in {2, 5} and isinstance(point_value_2, int) and point_value_2:
            add(
                point_value_2,
                stage_id,
                method="field_point_value_2",
                point_id=point_id,
            )
            direct_point_value_count += 1

    condition_count = 0
    for condition in load_mst(manifest_root, "getCollectionConditionMstList.json"):
        if condition.get("objectType") != 6:
            continue
        adv_id = condition.get("objectId")
        point_id = condition.get("fieldPointMstId")
        condition_id = condition.get("collectionConditionMstId")
        if (
            not isinstance(adv_id, int)
            or not isinstance(point_id, int)
            or point_id not in point_by_id
            or not isinstance(condition_id, int)
        ):
            raise CatalogError("CollectionCondition Adv 章节桥缺少有效 ID")
        point = point_by_id[point_id]
        stage_id = point_stage[point_id]
        stage = stages[stage_id]
        if (
            condition.get("fieldStratumMstId") != point.get("fieldStratumMstId")
            or condition.get("fieldStageMstId") != stage_id
            or condition.get("fieldSeriesMstId") != stage.get("fieldSeriesMstId")
        ):
            raise CatalogError(
                f"CollectionCondition {condition_id} 与 FieldPoint/FieldStage 不一致"
            )
        add(
            adv_id,
            stage_id,
            method="collection_condition_via_field_point",
            point_id=point_id,
            condition_id=condition_id,
        )
        condition_count += 1

    return bridges, {
        "fieldPointRows": len(points),
        "fieldPointStageLinks": len(point_stage),
        "fieldPointNeedViewAdvLinks": direct_need_count,
        "fieldPointValue2AdvLinks": direct_point_value_count,
        "collectionConditionAdvLinks": condition_count,
        "linkedAdvIds": len(bridges),
    }


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _resource_fallback(key: str) -> str:
    return PurePosixPath(key).name or key


def build_catalog(
    *,
    manifest_root: Path,
    scenario_root: Path,
    exedra_manifest_path: Path = DEFAULT_EXEDRA_MANIFEST,
    exedra_jp_root: Path = DEFAULT_EXEDRA_JP_ROOT,
    exedra_cn_root: Path = DEFAULT_EXEDRA_CN_ROOT,
    convert: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    convert = convert or simplified_converter()
    manifest_root = manifest_root.resolve(strict=True)
    scenario_root = scenario_root.resolve(strict=True)
    report, source_binding = _manifest_binding(manifest_root)
    organizer = _load_exedra_manifest(exedra_manifest_path)
    scenario_catalog, scenario_entries = _load_scenario_catalog(manifest_root)

    adv_rows = load_mst(manifest_root, "getAdvMstList.json")
    adv_by_id: dict[int, dict[str, Any]] = {}
    adv_by_resource: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in adv_rows:
        adv_id = row.get("advMstId")
        resource = row.get("advResourceName")
        if not isinstance(adv_id, int) or not isinstance(resource, str) or not resource.strip():
            raise CatalogError("Adv 行缺少 advMstId/advResourceName")
        if adv_id in adv_by_id:
            raise CatalogError(f"Adv ID 重复：{adv_id}")
        key = resource_key(resource)
        _category_from_resource(key)
        adv_by_id[adv_id] = row
        adv_by_resource[key].append(row)

    stages: dict[int, dict[str, Any]] = {}
    for row in load_mst(manifest_root, "getFieldStageMstList.json"):
        stage_id = row.get("fieldStageMstId")
        if not isinstance(stage_id, int) or stage_id in stages:
            raise CatalogError(f"FieldStage ID 无效或重复：{stage_id!r}")
        stages[stage_id] = row
    bridges, bridge_stats = _stage_bridges(
        manifest_root=manifest_root,
        adv_by_id=adv_by_id,
        stages=stages,
    )

    source_records: dict[str, dict[str, Any]] = {}
    source_groups: dict[str, str] = {}
    for source in organizer["sources"]:
        if not isinstance(source, dict):
            raise CatalogError("Exedra organizer source 不是对象")
        source_path = str(source.get("sourcePath") or "")
        group_id = str(source.get("groupId") or "")
        key = resource_key(source_path)
        if not key or key in source_records:
            raise CatalogError(f"Exedra organizer source 重复或无效：{source_path!r}")
        _category_from_resource(key)
        source_records[key] = source
        source_groups[key] = group_id

    human_metadata = _human_cn_metadata(
        manifest=organizer,
        cn_root=exedra_cn_root,
        jp_root=exedra_jp_root,
        convert=convert,
    )

    all_resource_keys = sorted(
        set(adv_by_resource) | set(source_records) | set(scenario_entries)
    )
    resources: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []
    resource_stats: Counter[str] = Counter()
    for key in all_resource_keys:
        rows = sorted(adv_by_resource.get(key, []), key=lambda row: int(row["advMstId"]))
        scenario = _scenario_metadata(
            key=key,
            entry=scenario_entries.get(key),
            scenario_root=scenario_root,
            convert=convert,
        )
        section_candidates: list[tuple[str, str, str]] = []
        for row in rows:
            sub_name_tw = str(row.get("subName") or "").strip()
            name_tw = str(row.get("name") or "").strip()
            value_tw = sub_name_tw or name_tw
            source_field = "subName" if sub_name_tw else "name" if name_tw else ""
            if value_tw:
                section_candidates.append((value_tw, convert(value_tw), source_field))
        unique_section_tw = _unique(item[0] for item in section_candidates)

        stage_ids = sorted(
            {
                stage_id
                for row in rows
                for stage_id in bridges.get(int(row["advMstId"]), {})
            }
        )
        stage_entries: list[dict[str, Any]] = []
        for stage_id in stage_ids:
            stage = stages[stage_id]
            subtitle_tw = str(stage.get("subTitle") or "").strip()
            name_tw = str(stage.get("name") or "").strip()
            title_tw = " · ".join(value for value in (subtitle_tw, name_tw) if value)
            evidence_by_adv: list[dict[str, Any]] = []
            for row in rows:
                adv_id = int(row["advMstId"])
                evidence = bridges.get(adv_id, {}).get(stage_id)
                if evidence is None:
                    continue
                evidence_by_adv.append(
                    {
                        "advMstId": adv_id,
                        "methods": sorted(evidence["methods"]),
                        "fieldPointMstIds": sorted(evidence["fieldPointMstIds"]),
                        "collectionConditionMstIds": sorted(evidence["conditionMstIds"]),
                    }
                )
            stage_entries.append(
                {
                    "fieldStageMstId": stage_id,
                    "fieldSeriesMstId": int(stage.get("fieldSeriesMstId") or 0),
                    "subTitleTw": subtitle_tw,
                    "subTitle": convert(subtitle_tw) if subtitle_tw else "",
                    "nameTw": name_tw,
                    "name": convert(name_tw) if name_tw else "",
                    "titleTw": title_tw,
                    "title": convert(title_tw) if title_tw else "",
                    "evidence": evidence_by_adv,
                }
            )

        reasons: list[str] = []
        fallback = _resource_fallback(key)
        human = human_metadata.get(key)
        if len(unique_section_tw) == 1:
            section_title_tw = unique_section_tw[0]
            section_title = convert(section_title_tw)
            section_source_fields = sorted({item[2] for item in section_candidates})
            section_source = (
                "getAdvMstList." + section_source_fields[0]
                if len(section_source_fields) == 1
                else "getAdvMstList.subName_or_name"
            )
            section_status = "resolved"
        elif len(unique_section_tw) > 1:
            section_title_tw = fallback
            section_title = fallback
            section_source = "fallback_resource_id"
            section_status = "ambiguous"
            reasons.append("ambiguous_adv_section_title")
        else:
            section_title_tw = fallback
            section_title = fallback
            section_source = "fallback_resource_id"
            section_status = "unresolved"
            reasons.append("no_authoritative_section_title")

        scenario_title_cards = [
            str(value)
            for value in scenario.get("titleCards") or []
            if str(value)
        ]
        scenario_title_cards_tw = [
            str(value)
            for value in scenario.get("titleCardsTw") or []
            if str(value)
        ]
        if len(scenario_title_cards) == 1 and len(scenario_title_cards_tw) == 1:
            supplemental_title = scenario_title_cards[0]
            supplemental_title_tw = scenario_title_cards_tw[0]
            supplemental_source = "tw_scenario_title_card"
        elif scenario.get("titleCandidate"):
            supplemental_title = str(scenario["titleCandidate"])
            supplemental_title_tw = str(scenario.get("titleCandidateTw") or "")
            supplemental_source = "tw_scenario_metadata." + str(
                scenario.get("titleCandidateField") or ""
            )
        elif human:
            supplemental_title = str(human["title"])
            supplemental_title_tw = str(human["titleTw"])
            supplemental_source = "human_cn_scenario_metadata." + str(human["field"])
        else:
            supplemental_title = ""
            supplemental_title_tw = ""
            supplemental_source = ""

        unique_stage_titles_tw = _unique(
            str(stage.get("titleTw") or "") for stage in stage_entries
        )
        if not stage_ids:
            reasons.append("no_field_stage_link")
            chapter_title_tw = ""
            chapter_title = ""
            chapter_status = "unresolved"
        elif len(unique_stage_titles_tw) == 1:
            chapter_title_tw = unique_stage_titles_tw[0]
            chapter_title = convert(chapter_title_tw)
            chapter_status = "resolved"
        else:
            reasons.append("multiple_field_stage_links")
            chapter_title_tw = ""
            chapter_title = ""
            chapter_status = "ambiguous"

        scenario_status = str(scenario.get("status") or "")
        if scenario_status != "verified":
            reasons.append("tw_scenario_" + scenario_status)
        if key not in source_records:
            reasons.append("not_in_organized_manifest")

        record = {
            "normalizedResourceName": key,
            "category": _category_from_resource(key),
            "organizedGroupId": source_groups.get(key, ""),
            "organizedSourcePath": str(source_records.get(key, {}).get("sourcePath") or ""),
            "advResourceNames": _unique(str(row["advResourceName"]) for row in rows),
            "advMstIds": [int(row["advMstId"]) for row in rows],
            "advTitleMstIds": sorted(
                {int(row.get("advTitleMstId") or 0) for row in rows}
            ),
            "advSectionCandidates": [
                {
                    "advMstId": int(row["advMstId"]),
                    "subNameTw": str(row.get("subName") or "").strip(),
                    "nameTw": str(row.get("name") or "").strip(),
                    "titleTw": (
                        str(row.get("subName") or "").strip()
                        or str(row.get("name") or "").strip()
                    ),
                    "title": convert(
                        str(row.get("subName") or "").strip()
                        or str(row.get("name") or "").strip()
                    ),
                }
                for row in rows
            ],
            "sectionTitleTw": section_title_tw,
            "sectionTitle": section_title,
            "sectionTitleSource": section_source,
            "sectionStatus": section_status,
            "supplementalStoryTitleTw": supplemental_title_tw,
            "supplementalStoryTitle": supplemental_title,
            "supplementalStoryTitleSource": supplemental_source,
            "fieldStageMstIds": stage_ids,
            "fieldStages": stage_entries,
            "chapterTitleTw": chapter_title_tw,
            "chapterTitle": chapter_title,
            "chapterStatus": chapter_status,
            "twScenario": scenario,
            "humanCnScenarioMetadata": human or {},
            "unresolved": sorted(set(reasons)),
        }
        resources[key] = record
        resource_stats["resourceRecords"] += 1
        resource_stats[f"resourceSection_{section_status}"] += 1
        resource_stats[f"resourceChapter_{chapter_status}"] += 1
        resource_stats[f"resourceScenario_{scenario_status}"] += 1
        if reasons:
            unresolved.append(
                {"scope": "resource", "id": key, "reasons": sorted(set(reasons))}
            )

    groups: dict[str, dict[str, Any]] = {}
    group_stats: Counter[str] = Counter()
    for group in organizer["groups"]:
        if not isinstance(group, dict):
            raise CatalogError("Exedra organizer group 不是对象")
        identity = str(group.get("id") or "")
        category = _canonical_category(str(group.get("category") or ""))
        group_key = str(group.get("groupKey") or "")
        source_paths = [str(value) for value in group.get("sources") or []]
        resource_keys = [resource_key(value) for value in source_paths]
        if not identity or identity in groups or not group_key or not resource_keys:
            raise CatalogError(f"Exedra organizer group 无效或重复：{identity!r}")
        try:
            resource_values = [resources[key] for key in resource_keys]
        except KeyError as exc:
            raise CatalogError(f"Group 引用未收录资源：{identity}: {exc}") from exc

        stage_ids = sorted(
            {
                int(stage_id)
                for resource in resource_values
                for stage_id in resource["fieldStageMstIds"]
            }
        )
        stage_by_id = {
            int(stage["fieldStageMstId"]): stage
            for resource in resource_values
            for stage in resource["fieldStages"]
        }
        chapter_titles_tw = _unique(
            str(stage_by_id[stage_id]["titleTw"]) for stage_id in stage_ids
        )
        chapter_titles = [convert(value) for value in chapter_titles_tw]
        if len(chapter_titles_tw) == 1:
            chapter_title = chapter_titles[0]
            chapter_title_tw = chapter_titles_tw[0]
            chapter_status = "resolved"
        elif chapter_titles_tw:
            chapter_title = ""
            chapter_title_tw = ""
            chapter_status = "ambiguous"
        else:
            chapter_title = ""
            chapter_title_tw = ""
            chapter_status = "unresolved"

        section_titles = [str(resource["sectionTitle"]) for resource in resource_values]
        section_titles_tw = [str(resource["sectionTitleTw"]) for resource in resource_values]
        section_sources = [str(resource["sectionTitleSource"]) for resource in resource_values]
        resolved_section_titles = _unique(
            str(resource["sectionTitle"])
            for resource in resource_values
            if not str(resource["sectionTitleSource"]).startswith("fallback_")
        )
        supplemental_titles = _unique(
            str(resource.get("supplementalStoryTitle") or "")
            for resource in resource_values
        )
        supplemental_sources = _unique(
            str(resource.get("supplementalStoryTitleSource") or "")
            for resource in resource_values
            if str(resource.get("supplementalStoryTitle") or "")
        )
        if len(resolved_section_titles) == 1:
            display_title = resolved_section_titles[0]
            display_source = "getAdvMstList"
        elif not resolved_section_titles and len(supplemental_titles) == 1:
            display_title = supplemental_titles[0]
            supplemental_source = (
                supplemental_sources[0] if len(supplemental_sources) == 1 else ""
            )
            display_source = (
                "tw_scenario_title_card"
                if supplemental_source == "tw_scenario_title_card"
                else "human_cn_scenario_metadata"
                if supplemental_source.startswith("human_cn_scenario_metadata.")
                else "tw_scenario_metadata"
            )
        else:
            display_title = group_key
            display_source = "fallback_group_id"

        group_reasons: list[str] = []
        if chapter_status == "ambiguous":
            group_reasons.append("multiple_field_stages_no_single_chapter")
        elif chapter_status == "unresolved":
            group_reasons.append("no_field_stage_link")
        if any(
            str(resource["sectionTitleSource"]).startswith("fallback_")
            for resource in resource_values
        ):
            group_reasons.append("one_or_more_sections_unresolved")
        if display_source == "fallback_group_id":
            group_reasons.append("no_single_authoritative_display_title")

        story_titles: list[str] = []
        story_title_source = ""
        if len(supplemental_titles) == 1:
            story_titles = supplemental_titles
            story_title_source = (
                "scenario_title_card"
                if supplemental_sources == ["tw_scenario_title_card"]
                else supplemental_sources[0]
                if len(supplemental_sources) == 1
                else ""
            )

        groups[identity] = {
            "sourceIdentity": identity,
            "category": category,
            "groupKey": group_key,
            "sourceResources": resource_keys,
            "sourceCount": len(resource_keys),
            "fieldStageMstIds": stage_ids,
            "chapterTitleTw": chapter_title_tw,
            "chapterTitle": chapter_title,
            "chapterTitlesTw": chapter_titles_tw,
            "chapterTitles": chapter_titles,
            "chapterStatus": chapter_status,
            "sectionTitlesTw": section_titles_tw,
            "sectionTitles": section_titles,
            "sectionTitleSources": section_sources,
            "resolvedSectionTitles": resolved_section_titles,
            "storyTitles": story_titles,
            "storyTitleSource": story_title_source,
            "supplementalStoryTitles": supplemental_titles,
            "supplementalStoryTitleSources": supplemental_sources,
            "displayTitle": display_title,
            "displayTitleSource": display_source,
            "twScenarioSourceCount": sum(
                resource["twScenario"].get("status") == "verified"
                for resource in resource_values
            ),
            "unresolved": sorted(set(group_reasons)),
        }
        group_stats["groups"] += 1
        group_stats[f"groupChapter_{chapter_status}"] += 1
        group_stats[f"groupDisplay_{display_source}"] += 1
        if group_reasons:
            unresolved.append(
                {
                    "scope": "group",
                    "id": identity,
                    "reasons": sorted(set(group_reasons)),
                }
            )

    source_binding.update(
        {
            "scenarioCatalog": {
                "relativePath": SCENARIO_CATALOG_RELATIVE.as_posix(),
                "sha256": _sha256(
                    manifest_root.joinpath(*SCENARIO_CATALOG_RELATIVE.parts)
                ),
                "resolvedManifestSha256": str(
                    scenario_catalog.get("resolvedManifestSha256") or ""
                ),
                "generatedAt": scenario_catalog.get("generatedAt"),
                "entries": len(scenario_entries),
            },
            "organizerManifest": {
                "relativePath": "magiraexedra-source-master/Scenarios_full/exedra_manifest.json",
                "sha256": _sha256(exedra_manifest_path),
                "groups": len(groups),
                "sources": len(source_records),
            },
        }
    )
    summary = {
        **dict(sorted(bridge_stats.items())),
        **dict(sorted(resource_stats.items())),
        **dict(sorted(group_stats.items())),
        "advRows": len(adv_rows),
        "uniqueAdvResources": len(adv_by_resource),
        "fieldStageRows": len(stages),
        "organizerGroups": len(groups),
        "organizerSources": len(source_records),
        "scenarioCatalogResources": len(scenario_entries),
        "humanCnMetadataFallbacks": len(human_metadata),
        "unresolvedRecords": len(unresolved),
    }
    return {
        "schemaVersion": 1,
        "policy": TITLE_POLICY,
        "source": source_binding,
        "summary": summary,
        "resources": resources,
        "groups": groups,
        "unresolved": unresolved,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-root", type=Path, required=True)
    parser.add_argument(
        "--scenario-root",
        type=Path,
        help="TW Resources/Scenarios；默认取 Manifest 同级 Resources/Scenarios",
    )
    parser.add_argument("--exedra-manifest", type=Path, default=DEFAULT_EXEDRA_MANIFEST)
    parser.add_argument("--exedra-jp-root", type=Path, default=DEFAULT_EXEDRA_JP_ROOT)
    parser.add_argument("--exedra-cn-root", type=Path, default=DEFAULT_EXEDRA_CN_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    scenario_root = args.scenario_root or (
        args.manifest_root.parent / "Resources" / "Scenarios"
    )
    try:
        value = build_catalog(
            manifest_root=args.manifest_root,
            scenario_root=scenario_root,
            exedra_manifest_path=args.exedra_manifest,
            exedra_jp_root=args.exedra_jp_root,
            exedra_cn_root=args.exedra_cn_root,
        )
        _write_json_atomic(args.output, value)
    except CatalogError as exc:
        raise SystemExit(f"错误：{exc}") from exc
    summary = value["summary"]
    print(
        "EXEDRA_TW_MANIFEST_TITLES_OK "
        f"resources={summary['resourceRecords']} groups={summary['groups']} "
        f"linkedAdvIds={summary['linkedAdvIds']} "
        f"unresolved={summary['unresolvedRecords']} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
