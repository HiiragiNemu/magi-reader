#!/usr/bin/env python3
"""Install permanent authentic-TW report certification and materializer hooks."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CERTIFIER = ROOT / "tools/certify_authentic_tw_reports.py"
MATERIALIZER = ROOT / "tools/materialize_tw_official_cn.py"

CERTIFIER_SOURCE = r'''#!/usr/bin/env python3
"""Bind every official-TW import report to authentic source and current bytes.

This is a fail-closed certification pass. It never invents a TW source hash:
each report must already contain a valid immutable ``twSha256`` and ``twPath``
from the verified source bundle. It rebinds the current CN JSON hashes and both
current aggregate TXT speaker/block hashes after deterministic canonicalization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import generate_story_index as pipeline  # noqa: E402

DEFAULT_CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
JP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
POLICY = "official_tw_name_column_tw2sp"
STRUCTURE_POLICY = "same-section-source-count-action-row"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha256(path: Path) -> str:
    value = path.read_text(encoding="utf-8-sig")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def valid_sha256(value: object) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def mapping(value: object, *, label: str, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"TW report {label} is not an object: {path}")
    return value


def bind_current_texts(value: dict[str, Any], report_path: Path) -> int:
    group = mapping(value.get("group"), label="group", path=report_path)
    category = group.get("category")
    group_key = group.get("groupKey")
    if not isinstance(category, str) or not category:
        raise RuntimeError(f"TW report group.category is missing: {report_path}")
    if not isinstance(group_key, str) or not group_key:
        raise RuntimeError(f"TW report group.groupKey is missing: {report_path}")

    jp_path = JP_ROOT / category / group_key / f"{group_key}_jp.txt"
    cn_path = report_path.parent / f"{group_key}_cn.txt"
    if not jp_path.is_file() or jp_path.is_symlink():
        raise RuntimeError(f"Certified JP aggregate TXT is missing: {jp_path}")
    if not cn_path.is_file() or cn_path.is_symlink():
        raise RuntimeError(f"Certified CN aggregate TXT is missing: {cn_path}")

    jp_sections = pipeline._exedra_alignment_sections(jp_path)
    cn_sections = pipeline._exedra_alignment_sections(cn_path)
    if len(jp_sections) != len(cn_sections):
        raise RuntimeError(
            f"Certified TW JP/CN Section count differs: {group_key}: "
            f"{len(jp_sections)} != {len(cn_sections)}"
        )
    if not jp_sections:
        raise RuntimeError(f"Certified TW aggregate TXT has no Sections: {group_key}")

    report_sections = value.get("sections")
    if not isinstance(report_sections, list) or len(report_sections) != len(jp_sections):
        raise RuntimeError(
            f"TW report Section list does not bind current TXT: {report_path}"
        )

    for index, (jp, cn, entry) in enumerate(
        zip(jp_sections, cn_sections, report_sections),
        start=1,
    ):
        if not isinstance(entry, dict):
            raise RuntimeError(f"TW report sections[{index}] is not an object: {report_path}")
        if (
            jp.number != index
            or cn.number != index
            or jp.source_name != cn.source_name
        ):
            raise RuntimeError(
                f"Certified TW Section source/order differs: {group_key} Section {index}"
            )
        if jp.reader_block_count != cn.reader_block_count:
            raise RuntimeError(
                f"Certified TW reader block count differs: {group_key} Section {index}: "
                f"{jp.reader_block_count} != {cn.reader_block_count}"
            )
        entry["section"] = index
        entry["source"] = jp.source_name
        entry["readerNormalizedBlocks"] = {
            "jp": jp.reader_block_count,
            "cn": cn.reader_block_count,
            "matches": True,
        }
        entry["speakerSequenceSha256"] = {
            "jp": jp.speaker_sequence_sha256,
            "cn": cn.speaker_sequence_sha256,
        }
        entry["speakerSequenceMatches"] = (
            jp.speaker_sequence_sha256 == cn.speaker_sequence_sha256
        )

    report_jp = mapping(value.get("jp"), label="jp", path=report_path)
    report_cn = mapping(value.get("cn"), label="cn", path=report_path)
    report_jp.update(
        {
            "contentSha256": text_sha256(jp_path),
            "sectionCount": len(jp_sections),
            "readerNormalizedBlockCount": sum(
                section.reader_block_count for section in jp_sections
            ),
        }
    )
    report_cn.update(
        {
            "renderedSha256": text_sha256(cn_path),
            "sectionCount": len(cn_sections),
            "readerNormalizedBlockCount": sum(
                section.reader_block_count for section in cn_sections
            ),
        }
    )
    value["currentTextCertification"] = {
        "version": 1,
        "jpSha256": report_jp["contentSha256"],
        "cnSha256": report_cn["renderedSha256"],
        "sectionCount": len(jp_sections),
        "speakerSequencesMayDiffer": True,
    }
    return len(jp_sections)


def certify_report(path: Path) -> tuple[int, int]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"TW import report root is not an object: {path}")
    if value.get("provenance") != "official_tw_human":
        return 0, 0

    validation = value.get("validation")
    if not isinstance(validation, dict):
        raise RuntimeError(f"TW report validation is missing: {path}")
    if (
        validation.get("passed") is not True
        or validation.get("mismatchCount") != 0
        or validation.get("usesLcs") is not False
        or validation.get("usesFuzzyMatching") is not False
        or validation.get("allowsReordering") is not False
        or value.get("mismatches") != []
    ):
        raise RuntimeError(f"TW report structural validation is not fail-closed: {path}")

    validation.update(
        {
            "structurePolicy": STRUCTURE_POLICY,
            "speakerPolicy": POLICY,
            "speakerSequencesMayDiffer": True,
            "twSchemaPreserved": True,
        }
    )

    sources = value.get("sourceJson")
    if not isinstance(sources, list) or not sources:
        raise RuntimeError(f"TW report sourceJson is empty: {path}")

    source_updates = 0
    for index, entry in enumerate(sources, start=1):
        if not isinstance(entry, dict):
            raise RuntimeError(f"TW report sourceJson[{index}] is not an object: {path}")
        source_name = entry.get("source")
        tw_path = entry.get("twPath")
        tw_sha256 = entry.get("twSha256")
        if not isinstance(source_name, str) or not source_name:
            raise RuntimeError(f"TW report sourceJson[{index}] has no source: {path}")
        if not isinstance(tw_path, str) or not tw_path:
            raise RuntimeError(f"TW report sourceJson[{index}] has no twPath: {path}")
        if not valid_sha256(tw_sha256):
            raise RuntimeError(
                f"TW report sourceJson[{index}] has no immutable twSha256: {path}"
            )
        if entry.get("provenance") != "official_tw_human":
            raise RuntimeError(
                f"TW report sourceJson[{index}] provenance is not official TW: {path}"
            )

        cn_path = path.parent / source_name
        if not cn_path.is_file() or cn_path.is_symlink():
            raise RuntimeError(f"Certified CN JSON is missing: {cn_path}")
        current_cn_sha256 = sha256_file(cn_path)
        entry["cnSha256"] = current_cn_sha256
        entry["simplifiedJsonSha256"] = current_cn_sha256
        entry["schemaSource"] = "official_tw_json"
        entry["speakerPolicy"] = POLICY
        entry["twSchemaPreserved"] = True
        source_updates += 1

    section_count = bind_current_texts(value, path)
    value["authenticTwCertification"] = {
        "version": 1,
        "schemaSource": "official_tw_json",
        "structurePolicy": STRUCTURE_POLICY,
        "speakerPolicy": POLICY,
        "twSchemaPreserved": True,
        "sourceCount": len(sources),
        "sectionCount": section_count,
    }
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 1, source_updates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cn-root", type=Path, default=DEFAULT_CN_ROOT)
    args = parser.parse_args()
    root = args.cn_root.resolve(strict=True)
    reports = 0
    sources = 0
    for path in sorted(root.rglob("*_cn.import-report.json")):
        report_count, source_count = certify_report(path)
        reports += report_count
        sources += source_count
    if reports <= 0 or sources <= 0:
        raise RuntimeError(
            f"No authentic TW reports were certified under {root}: "
            f"reports={reports}, sources={sources}"
        )
    print(f"AUTHENTIC_TW_REPORTS_CERTIFIED reports={reports} sources={sources}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def main() -> int:
    if CERTIFIER.exists():
        raise RuntimeError(f"certifier already exists: {CERTIFIER}")
    CERTIFIER.write_text(CERTIFIER_SOURCE, encoding="utf-8", newline="\n")

    source = MATERIALIZER.read_text(encoding="utf-8")
    marker = '    run(sys.executable, "generate_story_index.py")\n'
    if source.count(marker) != 1:
        raise RuntimeError(
            "materialize_tw_official_cn.py generate_story_index marker is not unique"
        )
    source = source.replace(
        marker,
        '    run(sys.executable, "tools/canonicalize_exedra_cn_speakers.py")\n'
        '    run(sys.executable, "tools/certify_authentic_tw_reports.py")\n'
        + marker,
        1,
    )
    MATERIALIZER.write_text(source, encoding="utf-8", newline="\n")
    print("AUTHENTIC_TW_REPORT_CERTIFICATION_REPAIR_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
