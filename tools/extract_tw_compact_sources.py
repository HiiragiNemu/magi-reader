#!/usr/bin/env python3
"""Rebuild minimal official TW source trees from committed compact payloads."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import lzma
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import generate_story_index as pipeline  # noqa: E402

JP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"
JP_MANIFEST = JP_ROOT / "exedra_manifest.json"
SCENARIO_ARCHIVE_SHA256 = "64c86700651b845b484f6100fed61a8c2b860028cda8130456a57979ee907452"
MANIFEST_ARCHIVE_SHA256 = "9125ae75d02ac69572fafc08fe2c1479ff872f6394d03b77f5bd046471ebda74"
PART_RE = re.compile(r"^(?P<prefix>.+\.xz\.b64)\.part(?P<number>\d+)$")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_payloads(source_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    grouped: dict[str, list[tuple[int, Path]]] = defaultdict(list)
    for path in sorted(source_dir.glob("*.part*")):
        match = PART_RE.fullmatch(path.name)
        if match:
            grouped[match.group("prefix")].append((int(match.group("number")), path))

    scenario: dict[str, Any] | None = None
    names: dict[str, Any] | None = None
    diagnostics: list[str] = []
    for prefix, parts in sorted(grouped.items()):
        ordered = [path for _number, path in sorted(parts)]
        encoded = "".join(path.read_text(encoding="ascii").strip() for path in ordered)
        try:
            compressed = base64.b64decode(encoded, validate=True)
            raw = lzma.decompress(compressed)
            value = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"紧凑来源无法解码：{prefix}: {exc}") from exc
        if not isinstance(value, dict):
            raise RuntimeError(f"紧凑来源顶层不是对象：{prefix}")
        diagnostics.append(
            f"{prefix}: xz_sha256={hashlib.sha256(compressed).hexdigest()} "
            f"json_bytes={len(raw)} keys={sorted(value)[:8]}"
        )
        if isinstance(value.get("files"), dict):
            if scenario is not None:
                raise RuntimeError("存在多个 Scenario 紧凑来源")
            scenario = value
        if isinstance(value.get("titles"), dict):
            if names is not None:
                raise RuntimeError("存在多个命名紧凑来源")
            names = value

    print("\n".join(diagnostics))
    if scenario is None:
        raise RuntimeError("没有找到包含 files 的台服 Scenario 紧凑来源")
    if names is None:
        raise RuntimeError("没有找到包含 titles 的台服命名紧凑来源")
    if scenario.get("sourceArchiveSha256") != SCENARIO_ARCHIVE_SHA256:
        raise RuntimeError("Scenario 来源压缩包哈希不匹配")
    if names.get("sourceArchiveSha256") != MANIFEST_ARCHIVE_SHA256:
        raise RuntimeError("Manifest 来源压缩包哈希不匹配")
    return scenario, names


def safe_relative_path(value: str) -> Path:
    if not value or "\\" in value or "\x00" in value:
        raise RuntimeError(f"来源路径非法：{value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeError(f"来源路径非法：{value!r}")
    if path.suffix.casefold() != ".json":
        raise RuntimeError(f"来源不是 JSON：{value!r}")
    return Path(*path.parts)


def build_jp_source_map() -> dict[str, Path]:
    manifest = load_json(JP_MANIFEST)
    groups = manifest.get("groups") if isinstance(manifest, dict) else None
    if not isinstance(groups, list):
        raise RuntimeError("日服 Exedra manifest 无效")
    result: dict[str, Path] = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        category = str(group.get("category") or "")
        group_key = str(group.get("groupKey") or "")
        sources = group.get("sources")
        if not category or not group_key or not isinstance(sources, list):
            continue
        for source in sources:
            source_path = str(source)
            key = PurePosixPath(source_path).as_posix().casefold()
            target = JP_ROOT / category / group_key / PurePosixPath(source_path).name
            if key in result and result[key] != target:
                raise RuntimeError(f"日服来源路径重复：{source_path}")
            result[key] = target
    return result


def rows_from_jp(relative_name: str, texts: list[Any], source_map: dict[str, Path]) -> list[list[Any]]:
    key = PurePosixPath(relative_name).as_posix().casefold()
    jp_path = source_map.get(key)
    if jp_path is None:
        raise RuntimeError(f"日服 manifest 不含台服来源路径：{relative_name}")
    document = load_json(jp_path)
    if not isinstance(document, dict):
        raise RuntimeError(f"日服 JSON 顶层无效：{jp_path}")
    jp_rows, diagnostics = pipeline.extract_exedra_dialogue_rows(document)
    serious = [item for item in diagnostics if "重复" not in item]
    if serious:
        raise RuntimeError(f"日服 JSON 结构诊断失败：{relative_name}: {serious[:3]}")
    if len(jp_rows) != len(texts):
        raise RuntimeError(
            f"台服正文/日服事件数不同：{relative_name}: "
            f"TW={len(texts)} JP={len(jp_rows)}"
        )
    rows: list[list[Any]] = []
    for index, (jp_row, text) in enumerate(zip(jp_rows, texts), 1):
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(f"台服正文为空：{relative_name}#{index}")
        rows.append(
            [
                int(jp_row.get("sheet_index") or 0),
                int(jp_row.get("row_number") or 0),
                str(jp_row.get("action") or ""),
                str(jp_row.get("speaker") or ""),
                text,
            ]
        )
    return rows


def materialize_scenarios(value: dict[str, Any], output: Path) -> None:
    files = value.get("files")
    if not isinstance(files, dict) or len(files) != 2780:
        raise RuntimeError(
            f"Scenario 紧凑文件数异常：{len(files) if isinstance(files, dict) else 'invalid'}"
        )
    source_map = build_jp_source_map()
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)
    row_total = 0
    for relative_name, record in sorted(files.items()):
        if not isinstance(relative_name, str):
            raise RuntimeError("Scenario 紧凑来源名无效")
        if isinstance(record, dict):
            rows = record.get("rows")
        elif isinstance(record, list):
            rows = rows_from_jp(relative_name, record, source_map)
        else:
            raise RuntimeError(f"Scenario 紧凑记录格式无效：{relative_name}")
        if not isinstance(rows, list):
            raise RuntimeError(f"Scenario 紧凑记录缺少 rows：{relative_name}")

        sheets: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for position, row in enumerate(rows, 1):
            if not isinstance(row, list) or len(row) != 5:
                raise RuntimeError(f"Scenario 紧凑行无效：{relative_name}#{position}")
            sheet_index, row_number, action, speaker, text = row
            if (
                not isinstance(sheet_index, int)
                or sheet_index < 0
                or not isinstance(row_number, int)
                or row_number < 1
                or not isinstance(action, str)
                or not isinstance(speaker, str)
                or not isinstance(text, str)
                or not text.strip()
            ):
                raise RuntimeError(f"Scenario 紧凑行字段无效：{relative_name}#{position}")
            sheets[sheet_index].append(
                {
                    "rowNumber": row_number,
                    "cellList": [action, speaker, text],
                    "isHeader": False,
                    "isComment": False,
                    "isBlank": False,
                }
            )
            row_total += 1
        document = {
            "origin": 0,
            "spreadsheetId": "tw-official-compact",
            "bookTitle": PurePosixPath(relative_name).stem,
            "sheetList": [
                {
                    "sheetName": f"script_{sheet_index}",
                    "headerRow": {
                        "rowNumber": 1,
                        "cellList": ["ActionType", "Name", "Comment"],
                        "isHeader": True,
                        "isComment": False,
                        "isBlank": False,
                    },
                    "contentRowList": sorted(
                        sheet_rows,
                        key=lambda item: int(item["rowNumber"]),
                    ),
                }
                for sheet_index, sheet_rows in sorted(sheets.items())
            ],
        }
        target = output / safe_relative_path(relative_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    if row_total != 96107:
        raise RuntimeError(f"Scenario 正文行数异常：{row_total}")
    print(f"TW_COMPACT_SCENARIOS_OK files={len(files)} rows={row_total}")


def mst_wrapper(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"payload": {"mstList": rows}}


def materialize_names(value: dict[str, Any], output: Path) -> None:
    titles = value.get("titles")
    if not isinstance(titles, dict) or len(titles) != 1608:
        raise RuntimeError(
            f"官方命名数量异常：{len(titles) if isinstance(titles, dict) else 'invalid'}"
        )
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)
    adv_rows: list[dict[str, Any]] = []
    stage_rows: dict[int, dict[str, Any]] = {}
    link_rows: list[dict[str, Any]] = []
    for resource, item in sorted(titles.items()):
        if not isinstance(resource, str) or not isinstance(item, dict):
            raise RuntimeError("官方命名记录格式无效")
        adv_id = int(item.get("advMstId") or 0)
        stage_id = int(item.get("fieldStageMstId") or 0)
        if adv_id <= 0:
            raise RuntimeError(f"advMstId 无效：{resource}")
        adv_rows.append(
            {
                "advMstId": adv_id,
                "advTitleMstId": int(item.get("advTitleMstId") or 0),
                "advResourceName": resource,
                "name": str(item.get("name") or ""),
                "subName": str(item.get("subName") or ""),
            }
        )
        if stage_id > 0:
            chapter_title = str(item.get("chapterTitle") or "").strip()
            stage_rows.setdefault(
                stage_id,
                {
                    "fieldStageMstId": stage_id,
                    "fieldSeriesMstId": int(item.get("fieldSeriesMstId") or 0),
                    "difficulty": 1,
                    "subTitle": "",
                    "name": chapter_title,
                },
            )
            link_rows.append(
                {"objectType": 6, "objectId": adv_id, "fieldStageMstId": stage_id}
            )
    outputs = {
        "getAdvMstList.json": mst_wrapper(adv_rows),
        "getFieldStageMstList.json": mst_wrapper(
            [stage_rows[key] for key in sorted(stage_rows)]
        ),
        "getCollectionConditionMstList.json": mst_wrapper(link_rows),
    }
    for name, document in outputs.items():
        (output / name).write_text(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    print(
        f"TW_COMPACT_NAMES_OK adv={len(adv_rows)} stages={len(stage_rows)} links={len(link_rows)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--scenario-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    args = parser.parse_args()
    scenario, names = load_payloads(args.source_dir.resolve(strict=True))
    materialize_scenarios(scenario, args.scenario_output.resolve())
    materialize_names(names, args.manifest_output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
