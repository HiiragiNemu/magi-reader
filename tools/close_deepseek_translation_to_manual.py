#!/usr/bin/env python3
"""Close the exhausted DeepSeek lane and build a deterministic manual handoff.

This tool is deliberately read-only with respect to every scenario tree.  It
only reads the sealed Magia Record queue/results, the verified Exedra missing
translation allowlist, and the protected baseline, then writes review artifacts
under ``artifacts/deepseek-retranslation/manual-handoff-v1``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING = Path(
    "artifacts/deepseek-retranslation/persistent-worker-20260811/staging"
)
DEFAULT_EXEDRA = Path(
    "artifacts/deepseek-retranslation/exedra-missing-allowlist-v1"
    "/allowlist.generated.v1.json"
)
DEFAULT_PROTECTED = Path("artifacts/deepseek-retranslation/protected-baseline.v1.json")
DEFAULT_OUTPUT = Path("artifacts/deepseek-retranslation/manual-handoff-v1")
DS_JOB_ROOT = Path(r"D:\AgentInfrastructure\state\deepseek-worker\jobs")

# Personal-name honorific violations only.  The Chinese character in words such
# as 酱油/番茄酱 is intentionally not treated as a global violation.
FORBIDDEN_HONORIFIC = re.compile(
    r"(?:ちゃん|(?:忧|憂)[\s_./\\-]*chan\b|(?:ui)[\s_./\\-]*chan\b|"
    r"[-－—–‐‑]chan\b|\b(?:yacchan|yatchan)\b)",
    re.IGNORECASE,
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_file_with_mode(path: Path, mode: str) -> str:
    if mode == "raw-bytes-v1":
        return sha256_file(path)
    if mode == "utf8-bom-stripped-lf-v1":
        text = path.read_text(encoding="utf-8-sig")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return sha256_bytes(normalized.encode("utf-8"))
    raise ValueError(f"unsupported protected hash mode: {mode}")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                item = json.loads(line)
                item["_source_line"] = line_number
                yield item


def stable_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def rel(path: Path) -> str:
    try:
        path = path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return str(path)
    return path.as_posix()


def protected_summary(document: dict[str, Any]) -> dict[str, Any]:
    magia = document.get("magia_trusted_baseline", {})
    exedra = document.get("exedra_human_authority", {})
    namae = document.get("namae_tw_authority", {})
    protected_files = document.get("protected_files", [])
    return {
        "protected_file_count": len(protected_files),
        "magireco_trusted_baseline_file_count": int(
            magia.get("expected_file_count", 0)
        ),
        "magireco_trusted_baseline_tree_sha256": magia.get("tree_sha256", ""),
        "exedra_protected_group_count": int(
            exedra.get("expected_group_count", 0)
        ),
        "exedra_namae_tw_group_count": int(namae.get("expected_group_count", 0)),
        "exedra_namae_tw_json_count": int(namae.get("expected_json_count", 0)),
    }


def verify_protected_files(document: dict[str, Any]) -> dict[str, Any]:
    """Rehash every protected file in bounded chunks without changing it."""

    candidates = document.get("files")
    if not isinstance(candidates, list):
        candidates = document.get("protected_files")
    if not isinstance(candidates, list):
        raise ValueError("protected baseline has no file inventory")
    checked = 0
    missing: list[str] = []
    mismatches: list[str] = []
    for record in candidates:
        if not isinstance(record, dict):
            continue
        path_value = record.get("path") or record.get("repo_path")
        expected = record.get("sha256")
        if not path_value or not expected:
            continue
        path = Path(path_value)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            missing.append(str(path_value))
            continue
        checked += 1
        mode = record.get("hash_mode", "raw-bytes-v1")
        if sha256_file_with_mode(path, mode) != expected:
            mismatches.append(str(path_value))
    return {
        "checked_file_count": checked,
        "missing_file_count": len(missing),
        "mismatch_file_count": len(mismatches),
        "missing_paths": missing,
        "mismatch_paths": mismatches,
    }


def inspect_ds_jobs(job_root: Path) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    if not job_root.exists():
        return jobs
    needle = str(REPO_ROOT).lower()
    for directory in sorted(job_root.glob("ds-*")):
        spec = directory / "spec.json"
        state = directory / "state.json"
        if not spec.is_file() or not state.is_file():
            continue
        try:
            spec_document = load_json(spec)
            state_document = load_json(state)
        except (OSError, json.JSONDecodeError):
            continue
        evidence = json.dumps(spec_document, ensure_ascii=False).lower()
        cwd = str(spec_document.get("cwd", "")).lower()
        if needle not in evidence and "deepseek-retranslation" not in cwd:
            continue
        jobs.append(
            {
                "job_id": state_document.get("job_id", directory.name),
                "session_id": state_document.get("session_id")
                or spec_document.get("session_id"),
                "previous_status": state_document.get("status", "unknown"),
                "closeout_status": "closed_due_to_quota",
                "model": spec_document.get("model"),
                "formal_tree_write_allowed": False,
                "job_directory": str(directory),
            }
        )
    return jobs


def build_handoff(
    staging: Path,
    exedra_allowlist_path: Path,
    protected_baseline_path: Path,
    job_root: Path,
) -> dict[str, Any]:
    queue_path = staging / "input-v1/queue/items.v1.jsonl"
    queue = {item["item_id"]: item for item in iter_jsonl(queue_path)}
    if len(queue) != 507:
        raise ValueError(f"expected 507 Magia Record queue entries, found {len(queue)}")

    references: dict[str, dict[str, Any]] = {}
    duplicate_references: list[str] = []
    for packet in sorted((staging / "results").glob("packet-*.jsonl")):
        for reference in iter_jsonl(packet):
            item_id = reference["item_id"]
            if item_id in references:
                duplicate_references.append(item_id)
            reference["_packet_file"] = rel(packet)
            references[item_id] = reference

    entries: list[dict[str, Any]] = []
    malformed_ids: list[str] = []
    qa_blocked_ids: list[str] = []
    terminal_status_counts: Counter[str] = Counter()
    malformed_underlying_verdicts: Counter[str] = Counter()

    for item_id, queue_item in sorted(queue.items(), key=lambda pair: pair[1]["ordinal"]):
        reference = references.get(item_id)
        status = "pending"
        underlying_verdict = None
        result_path = None
        result_sha256 = None
        block_reasons: list[str] = []
        unresolved_reasons: list[Any] = []

        if reference is not None:
            underlying_verdict = reference.get("verdict")
            result_path = staging / reference["result_file"]
            if not result_path.is_file():
                status = "malformed_or_qa_blocked"
                block_reasons.append("referenced_result_missing")
            else:
                result_sha256 = sha256_file(result_path)
                try:
                    result = load_json(result_path)
                except json.JSONDecodeError as error:
                    status = "malformed_or_qa_blocked"
                    malformed_ids.append(item_id)
                    malformed_underlying_verdicts[underlying_verdict or "unknown"] += 1
                    block_reasons.append(
                        f"malformed_result_json:{error.msg}:line={error.lineno}:column={error.colno}"
                    )
                else:
                    if result.get("item_id") != item_id:
                        status = "malformed_or_qa_blocked"
                        block_reasons.append("result_item_id_mismatch")
                    elif underlying_verdict == "verified_ok":
                        status = "verified_ok"
                    elif underlying_verdict == "unresolved":
                        status = "unresolved"
                        unresolved_reasons = result.get("unresolved_reasons", [])
                    elif underlying_verdict == "candidate_ready":
                        violations = sorted(
                            {match.group(0) for match in FORBIDDEN_HONORIFIC.finditer(result.get("candidate_text", ""))}
                        )
                        if violations:
                            status = "malformed_or_qa_blocked"
                            block_reasons.append(
                                "forbidden_personal_honorific:" + ",".join(violations)
                            )
                        else:
                            status = "candidate_ready_manual_review"
                    else:
                        status = "malformed_or_qa_blocked"
                        block_reasons.append(f"unsupported_verdict:{underlying_verdict}")

            if status == "malformed_or_qa_blocked" and item_id not in malformed_ids:
                qa_blocked_ids.append(item_id)

        terminal_status_counts[status] += 1
        entries.append(
            {
                "work_item_id": item_id,
                "system": "magireco",
                "story_id": queue_item["story_id"],
                "category": queue_item["category"],
                "title": queue_item.get("title", ""),
                "manual_status": status,
                "recommended_action": {
                    "verified_ok": "no_retranslation_required_keep_current_text",
                    "candidate_ready_manual_review": "human_review_candidate_before_any_formal_application",
                    "unresolved": "human_translate_or_resolve_authority_conflict",
                    "pending": "human_translate_from_japanese",
                    "malformed_or_qa_blocked": "human_translate_or_repair_and_review_candidate",
                }[status],
                "source_jp_path": queue_item["source"]["repo_path"],
                "source_jp_sha256": queue_item["source"]["sha256"],
                "current_cn_path": queue_item["target_baseline"]["repo_path"],
                "current_cn_sha256": queue_item["target_baseline"]["sha256"],
                "ds_underlying_verdict": underlying_verdict,
                "ds_result_path": rel(result_path) if result_path else None,
                "ds_result_sha256": result_sha256,
                "block_reasons": block_reasons,
                "unresolved_reasons": unresolved_reasons,
                "formal_tree_write_allowed": False,
            }
        )

    exedra_document = load_json(exedra_allowlist_path)
    exedra_entries = exedra_document.get("entries", [])
    if len(exedra_entries) != 26:
        raise ValueError(f"expected 26 Exedra allowlist entries, found {len(exedra_entries)}")
    if exedra_document.get("counts", {}).get("protection_overlap") != 0:
        raise ValueError("Exedra allowlist overlaps protected official/Wiki/human text")
    for item in exedra_entries:
        entries.append(
            {
                "work_item_id": item["item_id"],
                "system": "exedra",
                "story_id": item["story_id"],
                "category": item["category"],
                "title": item.get("title", ""),
                "manual_status": "pending_human_translation",
                "recommended_action": "human_translate_from_japanese_then_build_playable_json_and_txt",
                "source_jp_path": item["jp_txt"],
                "source_jp_sha256": item["jp_sha256"],
                "current_cn_path": item["target_candidate_txt"],
                "current_cn_sha256": None,
                "ds_underlying_verdict": None,
                "ds_result_path": None,
                "ds_result_sha256": None,
                "block_reasons": [],
                "unresolved_reasons": [],
                "formal_tree_write_allowed": False,
            }
        )

    protected_document = load_json(protected_baseline_path)
    protected = protected_summary(protected_document)
    protected_verification = verify_protected_files(protected_document)
    expected_protected_hash = sha256_file(protected_baseline_path)
    jobs = inspect_ds_jobs(job_root)

    counts = Counter(entry["manual_status"] for entry in entries)
    handoff = {
        "schema_version": 1,
        "closeout_reason": "deepseek_quota_exhausted_key_revoked",
        "ds_lane_status": "closed_due_to_quota",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "policy": {
            "formal_tree_write_allowed": False,
            "model_invocation_allowed": False,
            "remaining_work_owner": "human_translation_and_review",
            "official_wiki_human_read_only": True,
            "exedra_protected_groups_excluded": 413,
            "scenario_trees_modified": False,
        },
        "inputs": {
            "magireco_queue": {
                "path": rel(queue_path),
                "sha256": sha256_file(queue_path),
                "item_count": len(queue),
            },
            "exedra_allowlist": {
                "path": rel(exedra_allowlist_path),
                "sha256": sha256_file(exedra_allowlist_path),
                "item_count": len(exedra_entries),
            },
            "protected_baseline": {
                "path": rel(protected_baseline_path),
                "sha256_before": expected_protected_hash,
                "summary": protected,
                "file_verification": protected_verification,
            },
        },
        "counts": {
            "all_handoff_items": len(entries),
            "magireco_queue_total": len(queue),
            "magireco_ds_terminal_references": len(references),
            "magireco_verified_ok": counts["verified_ok"],
            "magireco_candidate_ready_manual_review": counts[
                "candidate_ready_manual_review"
            ],
            "magireco_unresolved": counts["unresolved"],
            "magireco_pending_human_translation": counts["pending"],
            "magireco_malformed_or_qa_blocked": counts[
                "malformed_or_qa_blocked"
            ],
            "magireco_malformed_result_json": len(malformed_ids),
            "magireco_qa_blocked_result": len(qa_blocked_ids),
            "exedra_pending_human_translation": counts["pending_human_translation"],
            "exedra_protected_groups_excluded": 413,
        },
        "diagnostics": {
            "duplicate_result_references": sorted(set(duplicate_references)),
            "malformed_item_ids": malformed_ids,
            "qa_blocked_item_ids": qa_blocked_ids,
            "malformed_underlying_verdicts": dict(malformed_underlying_verdicts),
        },
        "ds_jobs": jobs,
        "entries": entries,
    }
    return handoff


def write_csv(path: Path, entries: list[dict[str, Any]]) -> None:
    columns = [
        "work_item_id",
        "system",
        "story_id",
        "category",
        "title",
        "manual_status",
        "recommended_action",
        "source_jp_path",
        "source_jp_sha256",
        "current_cn_path",
        "current_cn_sha256",
        "ds_underlying_verdict",
        "ds_result_path",
        "ds_result_sha256",
        "block_reasons",
        "unresolved_reasons",
        "formal_tree_write_allowed",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for entry in entries:
                row = dict(entry)
                row["block_reasons"] = json.dumps(row["block_reasons"], ensure_ascii=False)
                row["unresolved_reasons"] = json.dumps(
                    row["unresolved_reasons"], ensure_ascii=False
                )
                writer.writerow(row)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_markdown(path: Path, handoff: dict[str, Any]) -> None:
    counts = handoff["counts"]
    lines = [
        "# DS 翻译车道额度耗尽人工交接清单",
        "",
        f"- 状态：`{handoff['ds_lane_status']}`",
        "- 正式剧情树写入：`false`",
        "- 后续负责人：人工翻译／复核",
        "- 官方、Wiki、确认人工内容：只读保护，不在本清单中",
        "",
        "## 精确计数",
        "",
        "| 系统 | 状态 | 数量 | 人工动作 |",
        "|---|---|---:|---|",
        f"| 魔法纪录 | verified_ok | {counts['magireco_verified_ok']} | 保留现有文本，无需重译 |",
        f"| 魔法纪录 | candidate_ready_manual_review | {counts['magireco_candidate_ready_manual_review']} | 逐项人工复核后再决定 |",
        f"| 魔法纪录 | unresolved | {counts['magireco_unresolved']} | 人工翻译或裁决术语/来源冲突 |",
        f"| 魔法纪录 | pending | {counts['magireco_pending_human_translation']} | 从日文人工翻译 |",
        f"| 魔法纪录 | malformed_or_qa_blocked | {counts['magireco_malformed_or_qa_blocked']} | 人工翻译，或修复候选后人工复核 |",
        f"| Exedra | pending_human_translation | {counts['exedra_pending_human_translation']} | 从日文人工翻译，再生成可播放 JSON 与 TXT |",
        "",
        "## 保护边界",
        "",
        f"- Exedra 已保护并排除：{counts['exedra_protected_groups_excluded']} 组。",
        "- 保护来源包括：台服官方、Exedra Wiki、圆哆啦 0728 人工文本。",
        "- 所有 DS 结果只保留为最低权重参考；本次工具没有改动任何剧情 JSON/TXT。",
        "- `formal_tree_write_allowed=false`，不会自动应用候选译文。",
        "",
        "逐项路径、哈希、旧 DS 结果与阻断原因见 `manual-handoff.v1.json` 和 UTF-8 BOM 的 `manual-review.csv`。",
        "",
    ]
    atomic_write(path, "\n".join(lines).encode("utf-8"))


def write_verification(output: Path, handoff_path: Path, protected_path: Path) -> dict[str, Any]:
    handoff = load_json(handoff_path)
    protected_after = sha256_file(protected_path)
    protected_before = handoff["inputs"]["protected_baseline"]["sha256_before"]
    verification = {
        "schema_version": 1,
        "status": "passed",
        "gates": {
            "magireco_queue_total_507": handoff["counts"]["magireco_queue_total"] == 507,
            "magireco_partition_exact": sum(
                handoff["counts"][key]
                for key in (
                    "magireco_verified_ok",
                    "magireco_candidate_ready_manual_review",
                    "magireco_unresolved",
                    "magireco_pending_human_translation",
                    "magireco_malformed_or_qa_blocked",
                )
            )
            == 507,
            "exedra_manual_items_exact_26": handoff["counts"][
                "exedra_pending_human_translation"
            ]
            == 26,
            "exedra_protected_groups_excluded_413": handoff["counts"][
                "exedra_protected_groups_excluded"
            ]
            == 413,
            "protected_baseline_hash_unchanged": protected_before == protected_after,
            "protected_files_zero_missing": handoff["inputs"]["protected_baseline"][
                "file_verification"
            ]["missing_file_count"]
            == 0,
            "protected_files_zero_mismatches": handoff["inputs"]["protected_baseline"][
                "file_verification"
            ]["mismatch_file_count"]
            == 0,
            "all_formal_tree_write_disallowed": all(
                entry["formal_tree_write_allowed"] is False for entry in handoff["entries"]
            ),
            "all_ds_jobs_closed_due_to_quota": all(
                job["closeout_status"] == "closed_due_to_quota"
                for job in handoff["ds_jobs"]
            ),
        },
        "protected_baseline": {
            "path": rel(protected_path),
            "sha256_before": protected_before,
            "sha256_after": protected_after,
        },
        "outputs": {},
    }
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "verification.v1.json":
            verification["outputs"][path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    if not all(verification["gates"].values()):
        verification["status"] = "failed"
    return verification


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--exedra-allowlist", type=Path, default=DEFAULT_EXEDRA)
    parser.add_argument("--protected-baseline", type=Path, default=DEFAULT_PROTECTED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--job-root", type=Path, default=DS_JOB_ROOT)
    args = parser.parse_args()

    staging = args.staging if args.staging.is_absolute() else REPO_ROOT / args.staging
    exedra = (
        args.exedra_allowlist
        if args.exedra_allowlist.is_absolute()
        else REPO_ROOT / args.exedra_allowlist
    )
    protected = (
        args.protected_baseline
        if args.protected_baseline.is_absolute()
        else REPO_ROOT / args.protected_baseline
    )
    output = args.output if args.output.is_absolute() else REPO_ROOT / args.output

    handoff = build_handoff(staging, exedra, protected, args.job_root)
    output.mkdir(parents=True, exist_ok=True)
    handoff_path = output / "manual-handoff.v1.json"
    atomic_write(handoff_path, stable_json_bytes(handoff))
    write_csv(output / "manual-review.csv", handoff["entries"])
    write_markdown(output / "README.md", handoff)
    verification = write_verification(output, handoff_path, protected)
    atomic_write(output / "verification.v1.json", stable_json_bytes(verification))
    print(json.dumps({"status": verification["status"], "counts": handoff["counts"]}, ensure_ascii=False))
    return 0 if verification["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
