#!/usr/bin/env python3
"""Generate a deterministic Exedra localization/manual-work audit.

The report joins the immutable Exedra organizer manifest, the official-TW
import report, generated TW metadata and the public story catalogue.  It does
not download, translate, mutate corpus files, run Git, or deploy anything.
Both JSON and Markdown outputs are written atomically so an interrupted run
cannot leave a plausible partial checklist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "magiraexedra-source-master/Scenarios_full/exedra_manifest.json"
DEFAULT_IMPORT_REPORT = ROOT / "artifacts/exedra_official_tw_import_report.json"
DEFAULT_METADATA = ROOT / "artifacts/tw_official_metadata.generated.json"
DEFAULT_STORY_INDEX = ROOT / "website/public/story_index.json"
DEFAULT_HUMAN_CHECKLIST = ROOT / "artifacts/exedra_human_processing_checklist_20260802.json"
DEFAULT_JSON = ROOT / "artifacts/exedra_localization_audit.generated.json"
DEFAULT_MARKDOWN = ROOT / "artifacts/exedra_localization_audit.generated.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def as_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} 不是对象")
    return value


def as_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} 不是数组")
    return value


def build_audit(
    manifest_path: Path,
    import_report_path: Path,
    metadata_path: Path,
    story_index_path: Path,
    human_checklist_path: Path,
) -> dict[str, Any]:
    manifest = as_dict(load_json(manifest_path), "Exedra manifest")
    groups = as_list(manifest.get("groups"), "Exedra manifest.groups")
    if manifest.get("schemaVersion") != 1 or len(groups) != 443:
        raise RuntimeError("Exedra manifest 不是预期的 443 组 schema-v1")
    by_identity = {
        str(group.get("id")): group
        for group in groups
        if isinstance(group, dict) and isinstance(group.get("id"), str)
    }
    if len(by_identity) != len(groups):
        raise RuntimeError("Exedra manifest identity 为空或重复")

    import_report = as_dict(load_json(import_report_path), "台服导入报告")
    if import_report.get("status") != "materialized":
        raise RuntimeError("台服导入报告尚未 materialized")
    stats = as_dict(import_report.get("stats"), "台服导入报告.stats")
    metadata_root = as_dict(load_json(metadata_path), "台服元数据")
    metadata = as_dict(metadata_root.get("stories"), "台服元数据.stories")
    human_checklist = as_dict(load_json(human_checklist_path), "0728/Wiki 人工来源清单")
    rejected_core = {
        str(item.get("groupKey")): item
        for item in as_list(
            human_checklist.get("rejectedCoreGroups"),
            "0728/Wiki 人工来源清单.rejectedCoreGroups",
        )
        if isinstance(item, dict) and isinstance(item.get("groupKey"), str)
    }
    rejected_voice = {
        str(item.get("groupKey")): item
        for item in as_list(
            human_checklist.get("rejectedWikiVoiceGroups"),
            "0728/Wiki 人工来源清单.rejectedWikiVoiceGroups",
        )
        if isinstance(item, dict) and isinstance(item.get("groupKey"), str)
    }

    stories_raw = as_list(load_json(story_index_path), "story_index")
    stories = [
        story for story in stories_raw
        if isinstance(story, dict) and story.get("game") == "exedra"
    ]
    stories_by_identity = {
        str(story.get("source_identity")): story
        for story in stories
        if isinstance(story.get("source_identity"), str)
    }
    if len(stories) != 443 or set(stories_by_identity) != set(by_identity):
        raise RuntimeError("story_index 与 443 组 Exedra manifest 身份不一致")

    failure_rows = as_list(import_report.get("failures"), "台服导入报告.failures")
    failures_by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in failure_rows:
        if not isinstance(row, dict):
            raise RuntimeError("台服导入 failures 含非对象")
        raw_group = str(row.get("group") or "")
        if "/" not in raw_group:
            raise RuntimeError(f"台服导入失败项 group 无效：{raw_group!r}")
        category, group_key = raw_group.split("/", 1)
        identity = f"exedra:{category}:{group_key}"
        if identity not in by_identity:
            raise RuntimeError(f"台服导入失败项不在 manifest：{identity}")
        failures_by_group[identity].append({
            "kind": str(row.get("kind") or "unknown"),
            "reason": str(row.get("reason") or "").strip(),
        })

    official: list[dict[str, Any]] = []
    retained_human: list[dict[str, Any]] = []
    remaining_translatable: list[dict[str, Any]] = []
    structural_no_text: list[dict[str, Any]] = []
    category_counts: Counter[str] = Counter()
    for identity in sorted(by_identity):
        group = by_identity[identity]
        story = stories_by_identity[identity]
        category = str(group.get("category") or "")
        turns = int(story.get("turns_jp") or group.get("dialogueCount") or 0)
        item = {
            "sourceIdentity": identity,
            "category": category,
            "groupKey": str(group.get("groupKey") or ""),
            "storyId": str(story.get("id") or ""),
            "title": str(story.get("title") or ""),
            "folder": str(story.get("folder") or ""),
            "turnsJp": turns,
            "pathJp": str(story.get("path_jp") or ""),
            "pathCn": str(story.get("path_cn") or ""),
            "officialTw": identity in metadata,
            "failures": failures_by_group.get(identity, []),
        }
        group_key = str(group.get("groupKey") or "")
        human_rejections: list[dict[str, Any]] = []
        if group_key in rejected_core:
            human_rejections.append({
                "source": "rounddora_0728_or_story_wiki",
                "record": rejected_core[group_key],
            })
        if group_key in rejected_voice:
            human_rejections.append({
                "source": "exedra_wiki_voice",
                "record": rejected_voice[group_key],
            })
        if human_rejections:
            item["humanSourceRejections"] = human_rejections
        if identity in metadata:
            info = metadata[identity]
            if not isinstance(info, dict):
                raise RuntimeError(f"台服元数据记录不是对象：{identity}")
            item["chapterTitle"] = str(info.get("chapterTitle") or "")
            item["sectionTitles"] = info.get("sectionTitles") or []
            official.append(item)
            category_counts[f"official:{category}"] += 1
        elif story.get("path_cn"):
            retained_human.append(item)
            category_counts[f"retained:{category}"] += 1
        elif turns <= 0:
            item["manualReason"] = "structural_no_readable_text_events"
            structural_no_text.append(item)
            category_counts[f"structural:{category}"] += 1
        else:
            item["manualReason"] = (
                "official_tw_missing_or_structurally_unusable; "
                "wiki_or_machine_translation_required"
            )
            remaining_translatable.append(item)
            category_counts[f"remaining:{category}"] += 1

    expected_official = int(stats.get("official_tw_groups") or -1)
    expected_missing = int(stats.get("missing_tw_groups") or -1)
    if len(official) != expected_official:
        raise RuntimeError(
            f"官方台服组数不一致：audit={len(official)} report={expected_official}"
        )
    if len(failure_rows) != expected_missing:
        raise RuntimeError(
            f"台服失败组数不一致：rows={len(failure_rows)} report={expected_missing}"
        )
    if len(official) + len(retained_human) + len(remaining_translatable) + len(structural_no_text) != 443:
        raise RuntimeError("Exedra 审计分类未覆盖全部 443 组")

    source_contract = as_dict(import_report.get("sourceContract"), "sourceContract")
    audit = {
        "version": 1,
        "status": "complete",
        "definitions": {
            "officialTw": "台服官方繁中经 tw2sp 简体化并注入可播放 JSON/TXT",
            "retainedHuman": "已有本地、0728、Wiki 或其他人工中文；未被台服导入覆盖",
            "remainingTranslatable": "有可读日文事件但缺少可用台服中文，需 Wiki/人工/机器补齐",
            "structuralNoText": "播放结构存在但没有可读文本事件，不计为未翻译正文",
        },
        "inputs": {
            "manifest": {"path": manifest_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(manifest_path)},
            "officialTwReport": {"path": import_report_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(import_report_path)},
            "officialTwMetadata": {"path": metadata_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(metadata_path)},
            "storyIndex": {"path": story_index_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(story_index_path)},
            "humanSourceChecklist": {"path": human_checklist_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(human_checklist_path)},
        },
        "sourceProvider": import_report.get("sourceProvider"),
        "sourceContract": source_contract,
        "summary": {
            "totalGroups": 443,
            "officialTwGroups": len(official),
            "retainedHumanGroups": len(retained_human),
            "localizedGroups": len(official) + len(retained_human),
            "remainingTranslatableGroups": len(remaining_translatable),
            "structuralNoTextGroups": len(structural_no_text),
            "officialTwFailureGroups": len(failure_rows),
            "deferredPartialTwFiles": len(as_list(import_report.get("deferredPartialTwSourceFiles"), "deferredPartialTwSourceFiles")),
            "twOnlyWithoutJpFiles": len(as_list(import_report.get("twOnlyWithoutJpSourceFiles"), "twOnlyWithoutJpSourceFiles")),
            "noTextTwFiles": len(as_list(import_report.get("noTextTwSourceFiles"), "noTextTwSourceFiles")),
            "unexpectedUnusedTwFiles": len(as_list(import_report.get("unexpectedUnusedTwSourceFiles"), "unexpectedUnusedTwSourceFiles")),
        },
        "categoryCounts": dict(sorted(category_counts.items())),
        "officialTwGroups": official,
        "retainedHumanGroups": retained_human,
        "remainingTranslatableGroups": remaining_translatable,
        "structuralNoTextGroups": structural_no_text,
        "officialTwFailures": failure_rows,
        "deferredPartialTwSourceFiles": import_report.get("deferredPartialTwSourceFiles"),
        "twOnlyWithoutJpSourceFiles": import_report.get("twOnlyWithoutJpSourceFiles"),
        "noTextTwSourceFiles": import_report.get("noTextTwSourceFiles"),
        "unexpectedUnusedTwSourceFiles": import_report.get("unexpectedUnusedTwSourceFiles"),
        "rounddora0728RejectedMainCandidateFamilies": human_checklist.get(
            "rounddora0728RejectedMainCandidateFamilies"
        ) or [],
    }
    if audit["summary"]["unexpectedUnusedTwFiles"] != 0:
        raise RuntimeError("仍有未分类台服来源文件")
    return audit


def markdown(audit: dict[str, Any]) -> str:
    summary = audit["summary"]
    lines = [
        "# Exedra 中文化与人工处理清单",
        "",
        "> 本文件由 `tools/generate_exedra_localization_audit.py` 确定性生成。",
        "",
        "## 总览",
        "",
        "| 项目 | 数量 |",
        "|---|---:|",
        f"| 逻辑剧情总数 | {summary['totalGroups']} |",
        f"| 台服官方简体化 JSON/TXT | {summary['officialTwGroups']} |",
        f"| 保留的既有人工中文 | {summary['retainedHumanGroups']} |",
        f"| 已有中文合计 | {summary['localizedGroups']} |",
        f"| 尚需 Wiki/人工/机器补齐（有可读正文） | {summary['remainingTranslatableGroups']} |",
        f"| 纯结构、无可读正文 | {summary['structuralNoTextGroups']} |",
        f"| 台服导入失败/缺源记录 | {summary['officialTwFailureGroups']} |",
        f"| 延后处理的部分来源文件 | {summary['deferredPartialTwFiles']} |",
        f"| 台服独有且当前无日服 organizer 的文件 | {summary['twOnlyWithoutJpFiles']} |",
        f"| 未分类来源文件 | {summary['unexpectedUnusedTwFiles']} |",
        "",
        "## 尚需中文化（有可读正文）",
        "",
    ]
    remaining = audit["remainingTranslatableGroups"]
    if remaining:
        lines.extend(["| 来源身份 | 日文事件 | 台服拒绝/缺失理由 |", "|---|---:|---|"])
        for item in remaining:
            reasons = "；".join(
                f"{failure['kind']}: {failure['reason']}"
                for failure in item.get("failures", [])
            ) or "台服导入未形成完整组"
            human_reason_codes: list[str] = []
            for rejection in item.get("humanSourceRejections", []):
                record = rejection.get("record") if isinstance(rejection, dict) else None
                if not isinstance(record, dict):
                    continue
                for code in record.get("reasonCodes") or []:
                    human_reason_codes.append(str(code))
                for code, count in (record.get("reasonCounts") or {}).items():
                    human_reason_codes.append(f"{code}({count})")
            if human_reason_codes:
                reasons += "；人工来源拒绝：" + ", ".join(sorted(set(human_reason_codes)))
            lines.append(
                f"| `{item['sourceIdentity']}` | {item['turnsJp']} | {reasons.replace('|', '\\|')} |"
            )
    else:
        lines.append("无。")

    lines.extend(["", "## 纯结构、无可读正文", ""])
    for item in audit["structuralNoTextGroups"]:
        lines.append(f"- `{item['sourceIdentity']}`")

    lines.extend(["", "## 全部台服导入拒绝/缺源记录", ""])
    for row in audit["officialTwFailures"]:
        lines.append(
            f"- `{row.get('group', '')}` — `{row.get('kind', 'unknown')}` — "
            f"{str(row.get('reason') or '').strip()}"
        )

    lines.extend(["", "## 延后处理的部分来源文件", ""])
    lines.extend(f"- `{value}`" for value in audit["deferredPartialTwSourceFiles"])
    lines.extend(["", "## 台服独有、当前无日服 organizer 的文件", ""])
    lines.extend(f"- `{value}`" for value in audit["twOnlyWithoutJpSourceFiles"])
    lines.extend(["", "## 0728 主线候选家族拒绝记录", ""])
    families = audit["rounddora0728RejectedMainCandidateFamilies"]
    if families:
        for family in families:
            if not isinstance(family, dict):
                continue
            lines.append(
                f"- `{family.get('family', '')}` — `{family.get('status', '')}` — "
                f"{family.get('reason', '')}"
            )
    else:
        lines.append("无。")
    lines.extend(["", "## 输入证据", ""])
    for label, value in audit["inputs"].items():
        lines.append(f"- {label}: `{value['path']}` — SHA-256 `{value['sha256']}`")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--import-report", type=Path, default=DEFAULT_IMPORT_REPORT)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--story-index", type=Path, default=DEFAULT_STORY_INDEX)
    parser.add_argument("--human-checklist", type=Path, default=DEFAULT_HUMAN_CHECKLIST)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    audit = build_audit(
        args.manifest.resolve(strict=True),
        args.import_report.resolve(strict=True),
        args.metadata.resolve(strict=True),
        args.story_index.resolve(strict=True),
        args.human_checklist.resolve(strict=True),
    )
    json_bytes = (
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    markdown_bytes = markdown(audit).encode("utf-8")
    write_atomic(args.json_output.resolve(), json_bytes)
    write_atomic(args.markdown_output.resolve(), markdown_bytes)
    summary = audit["summary"]
    print(
        "EXEDRA_LOCALIZATION_AUDIT_OK "
        f"total={summary['totalGroups']} localized={summary['localizedGroups']} "
        f"remaining={summary['remainingTranslatableGroups']} "
        f"structural_no_text={summary['structuralNoTextGroups']} "
        f"tw_failures={summary['officialTwFailureGroups']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
