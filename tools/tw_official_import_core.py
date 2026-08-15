#!/usr/bin/env python3
"""Inject already-simplified official Taiwan Exedra text into JP schemas."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT)]
import import_exedra_official_tw as tw  # noqa: E402
import generate_story_index as pipeline  # noqa: E402

REQUIRED_MANIFEST_FILES = (
    "getFieldStageMstList.json",
    "getAdvMstList.json",
    "getCollectionConditionMstList.json",
)

OFFICIAL_TITLE_CARD_RE = re.compile(
    r"^\s*<size\s*=\s*150%>\s*(.*?)\s*</size>\s*$",
    re.IGNORECASE | re.DOTALL,
)
OFFICIAL_TITLE_COLOR_WRAPPER_RE = re.compile(
    r"^\s*<color\s*=\s*(?:black|#000000)>\s*(.*?)\s*</color>\s*$",
    re.IGNORECASE | re.DOTALL,
)
OFFICIAL_TITLE_TERMINATORS = frozenset({"\u5f85\u7e8c", "\u5f85\u7eed", "\u5b8c\u7d50", "\u5b8c\u7ed3", "\u5b8c"})


@dataclass(frozen=True)
class SourceBundle:
    """Resolved local files supplied by a source provider.

    ``wiki-sp-extracted`` deliberately has the same on-disk contract as a local
    tree.  A future downloader only has to extract an SP package and hand its
    root to this resolver; downloading, Git operations, and deployment remain
    outside the deterministic data pipeline.
    """

    provider: str
    root: Path
    scenario_root: Path
    manifest_root: Path
    contract: dict[str, Any] | None = None


def _contained_directory(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_dir() or resolved.is_symlink():
        raise RuntimeError(f"来源目录无效：{path}")
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise RuntimeError(f"来源目录越界：{resolved}") from exc
    return resolved


def resolve_source_bundle(
    root: Path,
    provider: str = "local-tree",
    contract_path: Path | None = None,
) -> SourceBundle:
    """Find one Scenario tree and one Manifest tree, failing on ambiguity."""

    if provider not in {"local-tree", "wiki-sp-extracted", "exedra-wiki-sp"}:
        raise RuntimeError(f"未知台服来源 provider：{provider}")
    bundle_root = root.resolve(strict=True)
    if not bundle_root.is_dir() or bundle_root.is_symlink():
        raise RuntimeError(f"台服来源包根目录无效：{root}")

    contract: dict[str, Any] | None = None
    if provider in {"wiki-sp-extracted", "exedra-wiki-sp"}:
        from tw_sp_handoff_contract import verify_contract

        contract = verify_contract(bundle_root, contract_path)
        provider = "exedra-wiki-sp"

    conventional_scenarios = (
        bundle_root / "bundle" / "Resources" / "Scenarios",
        bundle_root / "Resources" / "Scenarios",
        bundle_root / "Scenarios",
    )
    scenario_candidates = [path for path in conventional_scenarios if path.is_dir()]
    if len(scenario_candidates) != 1:
        raise RuntimeError(
            f"Scenario 目录必须唯一，实际 {len(scenario_candidates)} 个："
            f"{scenario_candidates[:5]}"
        )

    conventional_manifests = (
        bundle_root / "bundle" / "Manifests",
        bundle_root / "Manifests",
        bundle_root / "Resources" / "Manifests",
    )
    manifest_candidates = [
        path
        for path in conventional_manifests
        if path.is_dir()
        and all((path / name).is_file() for name in REQUIRED_MANIFEST_FILES)
    ]
    if len(manifest_candidates) != 1:
        raise RuntimeError(
            f"Manifest 目录必须唯一，实际 {len(manifest_candidates)} 个："
            f"{manifest_candidates[:5]}"
        )

    return SourceBundle(
        provider=provider,
        root=bundle_root,
        scenario_root=_contained_directory(scenario_candidates[0], bundle_root),
        manifest_root=_contained_directory(manifest_candidates[0], bundle_root),
        contract=contract,
    )


def tree_sha256(root: Path, pattern: str = "*.json") -> tuple[str, int, int]:
    """Hash path, size, and bytes in a bounded streaming traversal."""

    digest = hashlib.sha256()
    count = 0
    total = 0
    for path in sorted(root.rglob(pattern)):
        if not path.is_file() or path.is_symlink():
            continue
        resolved = path.resolve(strict=True)
        try:
            relative = resolved.relative_to(root.resolve(strict=True)).as_posix()
        except ValueError as exc:
            raise RuntimeError(f"来源文件越界：{path}") from exc
        size = resolved.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        with resolved.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        count += 1
        total += size
    if not count:
        raise RuntimeError(f"来源目录没有匹配文件：{root} ({pattern})")
    return digest.hexdigest(), count, total


def simplified_converter() -> Callable[[str], str]:
    try:
        from opencc import OpenCC  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "缺少 opencc-python-reimplemented；请安装 requirements-data-tools.txt"
        ) from exc
    converter = OpenCC("tw2sp")
    return lambda value: converter.convert(value)


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
        # The Scenario inventory stores files as
        # ``category/resource/resource.json`` while getAdvMstList stores the
        # same identity as ``category/resource``.  Keeping the duplicated
        # filename component made every official chapter/section lookup miss
        # and silently fall back to raw JSON filenames.  Collapse only the
        # exact repeated final component; unrelated nested paths remain
        # untouched and therefore cannot be paired by a fuzzy basename.
        if len(path.parts) >= 2 and path.name.casefold() == path.parent.name.casefold():
            path = path.parent
    return path.as_posix().strip("/").casefold()


def title_catalog(
    root: Path,
    convert: Callable[[str], str] | None = None,
) -> dict[str, dict[str, Any]]:
    convert = convert or (lambda value: value)
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

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in adv:
        resource = row.get("advResourceName")
        adv_id = row.get("advMstId")
        if not isinstance(resource, str) or not isinstance(adv_id, int):
            continue
        key = resource_key(resource)
        grouped[key].append(row)

    result: dict[str, dict[str, Any]] = {}
    for key, candidates in sorted(grouped.items()):
        names = {
            convert(str(row.get("name") or "").strip())
            for row in candidates
            if str(row.get("name") or "").strip()
        }
        sub_names = {
            convert(str(row.get("subName") or "").strip())
            for row in candidates
            if str(row.get("subName") or "").strip()
        }
        stage_options: list[tuple[dict[str, Any], dict[str, Any], str]] = []
        for row in candidates:
            adv_id = int(row["advMstId"])
            for stage in sorted(links.get(adv_id, []), key=rank):
                chapter_name = convert(str(stage.get("name") or "").strip())
                chapter_subtitle = convert(str(stage.get("subTitle") or "").strip())
                chapter_title = " · ".join(
                    item for item in (chapter_subtitle, chapter_name) if item
                )
                if chapter_title:
                    stage_options.append((row, stage, chapter_title))
        chapter_titles = {item[2] for item in stage_options}
        if len(chapter_titles) > 1:
            raise RuntimeError(
                f"advResourceName 重复项章节冲突：{key}: "
                f"{sorted(chapter_titles)!r}"
            )
        if stage_options:
            selected_row, stage, chapter_title = sorted(
                stage_options,
                key=lambda item: (rank(item[1]), int(item[0]["advMstId"])),
            )[0]
        else:
            # Some tutorial/cut-scene resources are deliberately reused by a
            # later Adv row without any collection-stage link.  The highest
            # Adv ID is the newest official label; keep every alias in the
            # provenance so this deterministic preference remains auditable.
            selected_row = max(candidates, key=lambda item: int(item["advMstId"]))
            stage = {}
            chapter_title = ""
        adv_id = int(selected_row["advMstId"])
        name = convert(str(selected_row.get("name") or "").strip())
        sub_name = convert(str(selected_row.get("subName") or "").strip())
        section_title = name or sub_name or PurePosixPath(key).name
        result[key] = {
            "advMstId": adv_id,
            "advTitleMstId": int(selected_row.get("advTitleMstId") or 0),
            "duplicateAdvMstIds": sorted(
                int(row["advMstId"]) for row in candidates
            ),
            "nameAliases": sorted(names),
            "subNameAliases": sorted(sub_names),
            "name": name,
            "subName": sub_name,
            "sectionTitle": section_title,
            "chapterTitle": chapter_title,
            "fieldStageMstId": int(stage.get("fieldStageMstId") or 0),
            "fieldSeriesMstId": int(stage.get("fieldSeriesMstId") or 0),
        }
    return result


def optional_adv_title_catalog(
    root: Path,
    convert: Callable[[str], str] | None = None,
) -> dict[int, str]:
    """Return official gallery titles when the provider supplies that table.

    The v1 TW handoff deliberately requires only the three structural manifests,
    so this table is optional and its absence never permits a guessed title.
    A future SP bundle can add getAdvTitleMstList.json without changing the
    importer; values then flow through the same auditable Traditional-to-
    Simplified conversion as chapter and subsection names.
    """
    convert = convert or (lambda value: value)
    path = root / "getAdvTitleMstList.json"
    if not path.is_file():
        return {}
    result: dict[int, str] = {}
    for row in load_mst(root, path.name):
        key = row.get("advTitleMstId")
        title = convert(str(row.get("title") or "").strip())
        if not isinstance(key, int) or not title:
            continue
        previous = result.get(key)
        if previous and previous != title:
            raise RuntimeError(f"advTitleMstId 标题冲突：{key}: {previous!r} != {title!r}")
        result[key] = title
    return result


def official_scenario_title_card(value: str) -> str:
    """Return a conservative official story title embedded in one TW script.

    Some TW releases do not expose ``getAdvTitleMstList`` but put the event
    title in a dedicated 150% narration card.  Only that exact title-card
    contract is accepted.  Ordinary enlarged dialogue, unknown markup and
    ambiguous multi-line content remain unclassified rather than becoming a
    guessed catalogue title.
    """

    match = OFFICIAL_TITLE_CARD_RE.fullmatch(value)
    if not match:
        return ""
    body = match.group(1)
    color_match = OFFICIAL_TITLE_COLOR_WRAPPER_RE.fullmatch(body)
    if color_match:
        body = color_match.group(1)
    if "<" in body or ">" in body:
        return ""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines or lines[-1] in OFFICIAL_TITLE_TERMINATORS:
        return ""
    return " ".join(lines)


def replace_directory(staged: Path, target: Path) -> None:
    """Install a complete tree with recoverable same-volume rename semantics.

    A previous interrupted run is recovered only when the target is absent and
    the backup is therefore the sole complete copy.  If target and backup both
    exist, the function stops rather than guessing which tree is authoritative.
    """

    target.parent.mkdir(parents=True, exist_ok=True)
    incoming = target.with_name(f".{target.name}.tw-incoming")
    backup = target.with_name(f".{target.name}.tw-backup")
    journal = target.with_name(f".{target.name}.tw-transaction.json")

    def write_journal(state: str) -> None:
        temporary = journal.with_suffix(journal.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "version": 1,
                    "state": state,
                    "target": target.name,
                    "incoming": incoming.name,
                    "backup": backup.name,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, journal)

    if backup.exists() and not target.exists():
        os.replace(backup, target)
    elif backup.exists() and target.exists():
        raise RuntimeError(
            f"发现未决台服事务，目标与备份同时存在；拒绝自动删除：{target}"
        )
    shutil.rmtree(incoming, ignore_errors=True)
    shutil.copytree(staged, incoming)
    expected_hash, expected_count, expected_bytes = tree_sha256(incoming, "*")
    write_journal("prepared")
    moved_original = False
    installed = False
    try:
        if target.exists():
            os.replace(target, backup)
            moved_original = True
            write_journal("backup_created")
        os.replace(incoming, target)
        installed = True
        write_journal("installed")
        actual = tree_sha256(target, "*")
        if actual != (expected_hash, expected_count, expected_bytes):
            raise RuntimeError(
                f"台服目录安装后哈希不一致：{actual!r} != "
                f"{(expected_hash, expected_count, expected_bytes)!r}"
            )
    except Exception:
        if installed:
            shutil.rmtree(target, ignore_errors=True)
        if moved_original and backup.exists():
            os.replace(backup, target)
        journal.unlink(missing_ok=True)
        raise
    shutil.rmtree(incoming, ignore_errors=True)
    if moved_original and backup.exists():
        shutil.rmtree(backup)
    journal.unlink(missing_ok=True)


def import_corpus(
    scenario_root: Path,
    manifest_root: Path,
    *,
    provider: str = "local-tree",
    expected_source_files: int | None = None,
    dry_run: bool = False,
    source_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and atomically overlay every usable official TW group.

    The current Chinese tree is copied to a sibling staging directory first.
    No translated group becomes visible until every structural check passes and
    every supplied TW Scenario has been consumed exactly once by the organizer.
    Groups absent from the TW client are retained and reported for the lower
    priority Wiki/0728/machine-localization stages.
    """

    scenario_root = scenario_root.resolve(strict=True)
    manifest_root = manifest_root.resolve(strict=True)
    for name in REQUIRED_MANIFEST_FILES:
        if not (manifest_root / name).is_file():
            raise RuntimeError(f"Manifest 缺少必需文件：{name}")

    scenario_sha256, scenario_count, scenario_bytes = tree_sha256(scenario_root)
    manifest_sha256, manifest_count, manifest_bytes = tree_sha256(manifest_root)
    if expected_source_files is not None and scenario_count != expected_source_files:
        raise RuntimeError(
            f"台服 Scenario 来源数量异常：{scenario_count} != {expected_source_files}"
        )

    contract_evidence: dict[str, Any] | None = None
    if source_contract is not None:
        catalogs = source_contract.get("catalogs")
        revisions = source_contract.get("sourceRevisions")
        if not isinstance(catalogs, dict) or not isinstance(revisions, dict):
            raise RuntimeError("SP handoff contract 缺少 catalogs/sourceRevisions")
        scenario_catalog = catalogs.get("scenarios")
        manifest_catalog = catalogs.get("manifests")
        if not isinstance(scenario_catalog, dict) or not isinstance(
            manifest_catalog, dict
        ):
            raise RuntimeError("SP handoff contract 缺少 Scenario/Manifest 目录")
        if scenario_catalog.get("fileCount") != scenario_count:
            raise RuntimeError("SP contract Scenario 数量与来源目录不一致")
        if manifest_catalog.get("fileCount") != manifest_count:
            raise RuntimeError("SP contract Manifest 数量与来源目录不一致")
        contract_evidence = {
            "schemaVersion": source_contract.get("schemaVersion"),
            "contractName": source_contract.get("contractName"),
            "provenance": source_contract.get("provenance"),
            "sourceRevisions": revisions,
            "scenarioCatalogSha256": scenario_catalog.get("catalogSha256"),
            "scenarioTreeSha256": scenario_catalog.get("treeSha256"),
            "manifestCatalogSha256": manifest_catalog.get("catalogSha256"),
            "manifestTreeSha256": manifest_catalog.get("treeSha256"),
        }

    convert = simplified_converter()
    index = tw.TwSourceIndex(scenario_root)
    titles = title_catalog(manifest_root, convert)
    adv_titles = optional_adv_title_catalog(manifest_root, convert)
    metadata: dict[str, dict[str, Any]] = {}
    stats: Counter[str] = Counter()
    failures: list[dict[str, str]] = []
    used_tw_paths: set[str] = set()
    deferred_tw_paths: set[str] = set()
    no_text_tw_paths: set[str] = set()
    referenced_tw_paths: set[str] = set()
    for manifest_group in tw.load_groups():
        for raw_source in manifest_group.get("sources", []):
            try:
                matched = index.resolve(str(raw_source))
            except FileNotFoundError:
                continue
            referenced_tw_paths.add(index.relative_name(matched).casefold())
    all_tw_paths = set(index.relative)
    tw_only_paths = all_tw_paths - referenced_tw_paths

    artifacts = ROOT / "artifacts"
    existing_report_path = artifacts / "exedra_official_tw_import_report.json"
    generated_at = ""
    if existing_report_path.is_file():
        try:
            previous_report = json.loads(
                existing_report_path.read_text(encoding="utf-8-sig")
            )
            if (
                previous_report.get("scenarioTreeSha256") == scenario_sha256
                and previous_report.get("manifestTreeSha256") == manifest_sha256
            ):
                generated_at = str(previous_report.get("generatedAt") or "")
        except (OSError, ValueError, TypeError):
            generated_at = ""
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()

    tw.CN_ROOT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".tw-official-corpus-",
        dir=tw.CN_ROOT.parent,
    ) as temporary:
        temporary_root = Path(temporary)
        staged_root = temporary_root / "Scenarios_full"
        if tw.CN_ROOT.exists():
            shutil.copytree(tw.CN_ROOT, staged_root)
        else:
            staged_root.mkdir(parents=True)

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
                group_used_paths: set[str] = set()
                chapters: Counter[str] = Counter()
                scenario_story_titles: list[str] = []
                scenario_story_title_seen: set[str] = set()

                for section, source_value in zip(sections, sources):
                    source = str(source_value)
                    if PurePosixPath(source).name != section.source:
                        raise RuntimeError(f"manifest/Section 来源不同：{source}")
                    tw_json = index.resolve(source)
                    group_used_paths.add(index.relative_name(tw_json).casefold())
                    jp_json = tw.JP_ROOT / category / key / section.source
                    jp_rows, tw_rows = tw.extract_rows(jp_json), tw.extract_rows(tw_json)
                    tw.validate_row_alignment(section.source, jp_rows, tw_rows, section)
                    texts = [
                        convert(str(row.get("text") or "").strip())
                        for row in tw_rows
                    ]
                    if any(not text for text in texts):
                        raise RuntimeError(f"台服正文为空：{section.source}")
                    translated.append(texts)
                    resolved.append((section, source, jp_json, tw_json))
                    for row, text in zip(tw_rows, texts):
                        if (
                            category == "2_Sub"
                            and str(row.get("action") or "").casefold() == "narration"
                            and not str(row.get("speaker") or "").strip()
                        ):
                            scenario_title = official_scenario_title_card(text)
                            if (
                                scenario_title
                                and scenario_title not in scenario_story_title_seen
                            ):
                                scenario_story_title_seen.add(scenario_title)
                                scenario_story_titles.append(scenario_title)
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

                if sum(map(len, translated)) == 0:
                    no_text_tw_paths.update(group_used_paths)
                    no_text_target = staged_root / category / key
                    if no_text_target.exists():
                        shutil.rmtree(no_text_target)
                    stats["official_tw_no_text_groups"] += 1
                    stats["official_tw_no_text_files"] += len(sources)
                    continue

                group_stage = temporary_root / "groups" / category / key
                group_stage.mkdir(parents=True, exist_ok=False)
                json_meta: list[dict[str, Any]] = []
                for (section, source, jp_json, tw_json), texts in zip(
                    resolved,
                    translated,
                ):
                    digest = tw.apply_translated_texts(
                        jp_json,
                        texts,
                        group_stage / section.source,
                    )
                    json_meta.append(
                        {
                            "source": section.source,
                            "manifestSourcePath": source,
                            "twPath": index.relative_name(tw_json),
                            "twSha256": pipeline._sha256_file(tw_json),
                            "jpSha256": pipeline._sha256_file(jp_json),
                            "cnSha256": digest,
                            "simplifiedJsonSha256": digest,
                            "eventCount": len(texts),
                            "provenance": "official_tw_human",
                        }
                    )
                cn_txt = group_stage / f"{key}_cn.txt"
                cn_txt.write_text(tw.render_cn(sections, translated), encoding="utf-8")
                source_label = f"official-tw-{provider}#{scenario_sha256}"
                report = tw.build_report(
                    category,
                    key,
                    jp_txt,
                    cn_txt,
                    source_label,
                    json_meta,
                )
                report.update(
                    {
                        "sourceTreeSha256": scenario_sha256,
                        "manifestTreeSha256": manifest_sha256,
                        "officialTitles": official_sections,
                        "sourceContract": contract_evidence,
                    }
                )
                (group_stage / f"{key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}").write_bytes(
                    tw.json_bytes(report)
                )
                chapter_title = chapters.most_common(1)[0][0] if chapters else ""
                jp_sha256 = pipeline._sha256_utf8_text_file(jp_txt)
                previous_sidecar = tw.CN_ROOT / category / key / f"{key}_cn.provenance.json"
                previous_generated_at = ""
                if previous_sidecar.is_file():
                    try:
                        previous = json.loads(previous_sidecar.read_text(encoding="utf-8-sig"))
                        if (
                            previous.get("provenance") == "official_tw_human"
                            and previous.get("sourceTreeSha256") == scenario_sha256
                            and previous.get("manifestTreeSha256") == manifest_sha256
                            and previous.get("jpSha256") == jp_sha256
                        ):
                            previous_generated_at = str(previous.get("generatedAt") or "")
                    except (OSError, ValueError, TypeError):
                        previous_generated_at = ""
                sidecar = {
                    "version": 3,
                    "sourceIdentity": identity,
                    "provenance": "official_tw_human",
                    "machineTranslation": False,
                    "officialTw": True,
                    "sourceProvider": provider,
                    "sourceContract": contract_evidence,
                    "sourceTreeSha256": scenario_sha256,
                    "manifestTreeSha256": manifest_sha256,
                    "generatedAt": previous_generated_at or generated_at,
                    "jpSha256": jp_sha256,
                    "cnSha256": pipeline._sha256_utf8_text_file(cn_txt),
                    "chapterTitle": chapter_title,
                    "sections": official_sections,
                    "sourceJson": json_meta,
                }
                (group_stage / f"{key}_cn.provenance.json").write_bytes(
                    tw.json_bytes(sidecar)
                )
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

                staged_target = staged_root / category / key
                if staged_target.exists():
                    shutil.rmtree(staged_target)
                staged_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(group_stage, staged_target)
                used_tw_paths.update(group_used_paths)
                manifest_story_titles = list(
                    dict.fromkeys(
                        adv_titles[int(item.get("advTitleMstId") or 0)]
                        for item in official_sections
                        if int(item.get("advTitleMstId") or 0) in adv_titles
                    )
                )
                official_story_titles = manifest_story_titles or scenario_story_titles
                metadata[identity] = {
                    "sourceIdentity": identity,
                    "category": category,
                    "groupKey": key,
                    "officialTw": True,
                    "officialStoryTitles": official_story_titles,
                    "officialStoryTitleSource": (
                        "manifest"
                        if manifest_story_titles
                        else "scenario_title_card"
                        if scenario_story_titles
                        else ""
                    ),
                    "officialScenarioStoryTitles": scenario_story_titles,
                    "chapterTitle": chapter_title,
                    "chapterTitles": sorted(chapters),
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
                deferred_tw_paths.update(group_used_paths)
                stats["missing_tw_groups"] += 1
                failures.append(
                    {
                        "group": f"{category}/{key}",
                        "kind": "missing_source",
                        "reason": str(exc),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                stats["failed_groups"] += 1
                failures.append(
                    {
                        "group": f"{category}/{key}",
                        "kind": "structural_failure",
                        "reason": str(exc),
                    }
                )
            if number % 25 == 0:
                print(f"TW_IMPORT_PROGRESS {number}/443 {dict(stats)}")

        # A group with one missing source is deferred as a whole so that a
        # partially generated TXT/JSON set is never published.  Include every
        # TW file referenced by such groups, even when the missing section was
        # encountered before that file in manifest order.
        deferred_tw_paths = referenced_tw_paths - used_tw_paths - no_text_tw_paths
        unused_tw_paths = sorted(all_tw_paths - used_tw_paths)
        unexpected_unused = sorted(
            all_tw_paths
            - used_tw_paths
            - deferred_tw_paths
            - tw_only_paths
            - no_text_tw_paths
        )
        stats["tw_source_files"] = len(all_tw_paths)
        stats["tw_source_files_used"] = len(used_tw_paths)
        stats["tw_source_files_unused"] = len(unused_tw_paths)
        stats["tw_source_files_deferred_partial"] = len(deferred_tw_paths)
        stats["tw_source_files_tw_only_without_jp"] = len(tw_only_paths)
        stats["tw_source_files_no_text"] = len(no_text_tw_paths)
        stats["tw_source_files_unexpected_unused"] = len(unexpected_unused)
        stats["retained_non_tw_groups"] = 443 - stats["official_tw_groups"]
        value = {
            "version": 3,
            "status": "dry_run" if dry_run else "materialized",
            "generatedAt": generated_at,
            "sourceProvider": provider,
            "sourceContract": contract_evidence,
            "scenarioTreeSha256": scenario_sha256,
            "manifestTreeSha256": manifest_sha256,
            "sourceInventory": {
                "scenarioFiles": scenario_count,
                "scenarioBytes": scenario_bytes,
                "manifestFiles": manifest_count,
                "manifestBytes": manifest_bytes,
            },
            "stats": dict(stats),
            "failures": failures,
            "unusedTwSourceFiles": unused_tw_paths,
            "deferredPartialTwSourceFiles": sorted(deferred_tw_paths),
            "twOnlyWithoutJpSourceFiles": sorted(tw_only_paths),
            "noTextTwSourceFiles": sorted(no_text_tw_paths),
            "unexpectedUnusedTwSourceFiles": unexpected_unused,
        }

        if not stats["official_tw_groups"]:
            raise RuntimeError("没有生成任何台服官方中文剧情组")
        if stats["failed_groups"]:
            print(
                "TW_IMPORT_FAILURE_SAMPLES "
                + json.dumps(failures[:20], ensure_ascii=False)
            )
            raise RuntimeError(f"台服导入结构失败：{stats['failed_groups']}")
        if stats["tw_source_files_unexpected_unused"]:
            raise RuntimeError(
                "存在无法归类的台服 Scenario："
                f"{stats['tw_source_files_unexpected_unused']}"
            )
        if not dry_run:
            replace_directory(staged_root, tw.CN_ROOT)
            artifacts.mkdir(exist_ok=True)

            def write_atomic(path: Path, payload: dict[str, Any]) -> None:
                temporary_path = path.with_suffix(path.suffix + ".tmp")
                temporary_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                os.replace(temporary_path, path)

            write_atomic(existing_report_path, value)
            write_atomic(
                artifacts / "tw_official_metadata.generated.json",
                {
                    "version": 2,
                    "sourceProvider": provider,
                    "sourceContract": contract_evidence,
                    "scenarioTreeSha256": scenario_sha256,
                    "manifestTreeSha256": manifest_sha256,
                    "stories": metadata,
                },
            )

    return value
