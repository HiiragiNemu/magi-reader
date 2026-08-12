#!/usr/bin/env python3
"""Build an auditable, read-only inventory for DeepSeek retranslation.

The utility never calls a model and never mutates scenario data. It joins the
trusted-main delta manifest to the published catalogue, proves every queued
Japanese/Chinese source by SHA-256 and separates protected human material from
machine-derived work and records that still need a source decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MACHINE_MANIFEST = ROOT / "website/public/data/machine_translation_manifest.generated.json"
DEFAULT_STORY_INDEX = ROOT / "website/public/story_index.json"
DEFAULT_JSON_OUTPUT = ROOT / "artifacts/deepseek-retranslation/retranslation-inventory.v1.json"
DEFAULT_MARKDOWN_OUTPUT = ROOT / "artifacts/deepseek-retranslation/retranslation-inventory.v1.md"

HEADER_RE = re.compile(
    r"^---\s*\[Section\s+[^\]]+\].*?\(Source:\s*([^()\r\n]+\.json)\s*\)\s*---$"
)
HONORIFIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("romanized_honorific", re.compile(r"(?i)(?:-|\b)(?:chan|san|sama|kun|senpai)(?:\b|s\b)")),
    ("ui_jiang", re.compile(r"忧酱")),
    ("ui_chan_literal", re.compile(r"忧\s*-?\s*chan", re.I)),
    ("japanese_kana", re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")),
)
PROTECTED_DECLARED_CATEGORIES = frozenset({"main_story", "scene0_main"})


class InventoryError(RuntimeError):
    """Raised when the inventory cannot be proved complete."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def safe_repo_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in value
    ):
        raise InventoryError(f"unsafe repository path: {value!r}")
    return path


def absolute_repo_path(root: Path, value: str) -> Path:
    return root.joinpath(*safe_repo_path(value).parts)


def text_metrics(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    headers: list[str] = []
    content_rows = 0
    issues: list[dict[str, Any]] = []
    issue_counts: Counter[str] = Counter()
    for number, line in enumerate(text.splitlines(), 1):
        match = HEADER_RE.match(line.strip())
        if match:
            headers.append(match.group(1))
            continue
        if not line.strip():
            continue
        content_rows += 1
        for code, pattern in HONORIFIC_PATTERNS:
            if pattern.search(line):
                issue_counts[code] += 1
                if len(issues) < 12:
                    issues.append({"code": code, "line": number, "text": line[:240]})
    return {
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "section_count": len(headers),
        "source_names": headers,
        "content_row_count": content_rows,
        "quality_issue_counts": dict(sorted(issue_counts.items())),
        "quality_issue_examples": issues,
    }


def git_paths_at_ref(root: Path, ref: str, paths: Iterable[str]) -> set[str]:
    unique = sorted(set(paths))
    if not unique:
        return set()
    expressions = "".join(f"{ref}:{path}\n" for path in unique)
    process = subprocess.run(
        ["git", "cat-file", "--batch-check=%(objectname) %(objecttype)"],
        cwd=root,
        input=expressions,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode:
        raise InventoryError(f"git cat-file failed ({process.returncode}): {process.stderr.strip()}")
    lines = process.stdout.splitlines()
    if len(lines) != len(unique):
        raise InventoryError("git cat-file result count mismatch")
    present: set[str] = set()
    for path, line in zip(unique, lines, strict=True):
        if line.endswith(" blob"):
            present.add(path)
        elif not line.endswith(" missing"):
            raise InventoryError(f"unexpected git cat-file result for {path}: {line}")
    return present


def canonical_cn_path(story: dict[str, Any]) -> str | None:
    category = story.get("category")
    folder = story.get("folder")
    filename = story.get("filename_cn")
    if not all(isinstance(item, str) and item for item in (category, folder, filename)):
        return None
    return (
        PurePosixPath("magireco-translate-data-master/Scenarios_full")
        / category
        / folder
        / filename
    ).as_posix()


def atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def exedra_provenance(root: Path) -> tuple[dict[str, int], list[str]]:
    base = root / "magiraexedra-translate-data-master/Scenarios_full"
    counts: Counter[str] = Counter()
    machine: list[str] = []
    if not base.is_dir():
        return {}, []
    for path in sorted(base.rglob("*_cn.provenance.json")):
        record = load_json(path)
        provenance = str(record.get("provenance") or record.get("sourceType") or "unknown")
        counts[provenance] += 1
        if provenance == "machine_translation":
            machine.append(path.relative_to(root).as_posix())
    return dict(sorted(counts.items())), machine


def build_inventory(root: Path, machine_manifest_path: Path, story_index_path: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest = load_json(machine_manifest_path)
    stories = load_json(story_index_path)
    if not isinstance(stories, list):
        raise InventoryError("story index must be a list")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or manifest.get("total") != len(entries):
        raise InventoryError("machine manifest total does not match entries")
    if manifest.get("protected_human_overwrite_count") != 0 or manifest.get("protected_human_deletion_count") != 0:
        raise InventoryError("trusted human baseline is not intact")

    story_by_id = {
        str(story.get("id")): story
        for story in stories
        if isinstance(story, dict) and story.get("game") == "magireco"
    }
    pending_ids = {str(entry.get("story_id")) for entry in entries}
    if len(pending_ids) != len(entries):
        raise InventoryError("machine manifest contains duplicate story IDs")

    candidate_paths = [path for story in story_by_id.values() if (path := canonical_cn_path(story))]
    baseline_ref = str(manifest.get("trusted_baseline") or "")
    if not baseline_ref:
        raise InventoryError("machine manifest lacks trusted_baseline")
    baseline_paths = git_paths_at_ref(root, baseline_ref, candidate_paths)

    queue: list[dict[str, Any]] = []
    aggregate_issues: Counter[str] = Counter()
    for entry in entries:
        story_id = str(entry.get("story_id"))
        story = story_by_id.get(story_id)
        if story is None:
            raise InventoryError(f"queued story missing from public catalogue: {story_id}")
        cn_relative = str(entry.get("repository_path_cn") or "")
        if not cn_relative:
            raise InventoryError(f"queued story lacks repository_path_cn: {story_id}")
        jp_relative = cn_relative.replace("magireco-translate-data-master/", "magireco-source-master/", 1)
        cn_path = absolute_repo_path(root, cn_relative)
        jp_path = absolute_repo_path(root, jp_relative)
        if not cn_path.is_file() or not jp_path.is_file():
            raise InventoryError(f"queued TXT pair is incomplete: {story_id}")
        cn_metrics = text_metrics(cn_path)
        jp_metrics = text_metrics(jp_path)
        structure_issues: list[str] = []
        if cn_metrics["source_names"] != jp_metrics["source_names"]:
            structure_issues.append("section_source_sequence_mismatch")
            aggregate_issues["section_source_sequence_mismatch"] += 1
        if cn_metrics["content_row_count"] != jp_metrics["content_row_count"]:
            structure_issues.append("cn_jp_content_row_count_mismatch")
            aggregate_issues["cn_jp_content_row_count_mismatch"] += 1
        aggregate_issues.update(cn_metrics["quality_issue_counts"])
        queue.append(
            {
                "story_id": story_id,
                "category": entry.get("category"),
                "folder": entry.get("folder"),
                "title": entry.get("title"),
                "classification": "pending_retranslation",
                "classification_evidence": [
                    f"manifest-v{manifest.get('version')}",
                    str(manifest.get("definition")),
                    "canonical-cn-txt-absent-from-trusted-main",
                ],
                "provenance": entry.get("provenance"),
                "cn_txt": cn_relative,
                "jp_txt": jp_relative,
                "cn": cn_metrics,
                "jp": jp_metrics,
                "legacy_structure_issues": structure_issues,
                "json_sources_cn": story.get("json_sources_cn", []),
                "json_sources_jp": story.get("json_sources_jp", []),
                "review_status": "not_started",
            }
        )

    protected: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for story_id, story in sorted(story_by_id.items()):
        if story_id in pending_ids or not story.get("has_cn"):
            continue
        path = canonical_cn_path(story)
        classification = "source_unknown_review"
        evidence: list[str] = []
        if path and path in baseline_paths:
            classification = "official_or_human_protected"
            evidence.append(f"blob-present-in-trusted-main:{baseline_ref}")
        elif story.get("category") in PROTECTED_DECLARED_CATEGORIES:
            classification = "official_or_human_protected"
            evidence.append("user-declared-main-or-scene0-human-policy")
        else:
            evidence.append("not-in-machine-manifest-and-not-proved-in-trusted-main")
        item = {
            "story_id": story_id,
            "category": story.get("category"),
            "folder": story.get("folder"),
            "title": story.get("title"),
            "classification": classification,
            "classification_evidence": evidence,
            "cn_txt": path,
        }
        (protected if classification == "official_or_human_protected" else unknown).append(item)

    exedra_counts, exedra_machine = exedra_provenance(root)
    result = {
        "schema_version": 1,
        "model_policy": {
            "translation_worker": "deepseek-v4-flash",
            "transport": "claude-code-cli-json",
            "codex_generates_translation": False,
        },
        "trusted_baseline": baseline_ref,
        "machine_manifest": {
            "path": machine_manifest_path.resolve().relative_to(root).as_posix(),
            "sha256": sha256_file(machine_manifest_path),
            "version": manifest.get("version"),
            "definition": manifest.get("definition"),
            "protected_human_overwrite_count": manifest.get("protected_human_overwrite_count"),
            "protected_human_deletion_count": manifest.get("protected_human_deletion_count"),
        },
        "story_index": {
            "path": story_index_path.resolve().relative_to(root).as_posix(),
            "sha256": sha256_file(story_index_path),
            "magireco_story_count": len(story_by_id),
        },
        "counts": {
            "pending_retranslation": len(queue),
            "official_or_human_protected": len(protected),
            "source_unknown_review": len(unknown),
            "exedra_machine_translation": len(exedra_machine),
        },
        "quality_issue_counts_in_pending_cn": dict(sorted(aggregate_issues.items())),
        "exedra_provenance_counts": exedra_counts,
        "exedra_machine_translation_sidecars": exedra_machine,
        "pending_retranslation": sorted(queue, key=lambda item: item["story_id"]),
        "official_or_human_protected": protected,
        "source_unknown_review": unknown,
    }
    if result["counts"]["pending_retranslation"] != manifest.get("total"):
        raise InventoryError("pending queue count does not close against manifest")
    return result


def render_markdown(inventory: dict[str, Any]) -> str:
    counts = inventory["counts"]
    issues = inventory["quality_issue_counts_in_pending_cn"]
    unknown = inventory["source_unknown_review"]
    lines = [
        "# DeepSeek 重译库存 v1",
        "",
        "本清单只盘点、哈希和分类，不调用模型，也不改写剧情。",
        "",
        "## 精确计数",
        "",
        f"- 待从日文原文重译：**{counts['pending_retranslation']}**",
        f"- 官方／人工保护：**{counts['official_or_human_protected']}**",
        f"- 来源不明待审：**{counts['source_unknown_review']}**",
        f"- Exedra 明确机翻：**{counts['exedra_machine_translation']}**",
        "",
        "## 旧中文自动质量信号",
        "",
    ]
    lines.extend(f"- `{key}`：{value}" for key, value in sorted(issues.items()))
    if not issues:
        lines.append("- 未发现已配置的敬称／日文残留信号。")
    lines.extend(["", "## 来源不明待审", ""])
    lines.extend(
        f"- `{item['story_id']}` {item.get('category')} / {item.get('folder')}"
        for item in unknown
    )
    if not unknown:
        lines.append("- 无。")
    lines.extend([
        "",
        "每个待重译条目的日中 TXT、JSON 来源、Section/Source 序列、字节数与 SHA-256 见 JSON 清单。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--machine-manifest", type=Path, default=DEFAULT_MACHINE_MANIFEST)
    parser.add_argument("--story-index", type=Path, default=DEFAULT_STORY_INDEX)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    args = parser.parse_args()
    try:
        inventory = build_inventory(args.repo_root, args.machine_manifest, args.story_index)
        atomic_write(args.json_output, json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")
        atomic_write(args.markdown_output, render_markdown(inventory))
    except (InventoryError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    counts = inventory["counts"]
    print(
        "RETRANSLATION_INVENTORY_OK "
        f"pending={counts['pending_retranslation']} "
        f"protected={counts['official_or_human_protected']} "
        f"unknown={counts['source_unknown_review']} "
        f"exedra_machine={counts['exedra_machine_translation']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
