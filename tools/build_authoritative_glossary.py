#!/usr/bin/env python3
"""Build an evidence-backed glossary for the DeepSeek retranslation lane.

The generator never calls a model and never edits scenario data.  Static terms
are accepted only when the cited Japanese/Chinese lines still contain the
expected evidence.  Character names are additionally derived from paired
trusted directory names and aligned official main-story speaker rows.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
JP_ROOT = Path("magireco-source-master/Scenarios_full")
CN_ROOT = Path("magireco-translate-data-master/Scenarios_full")
DEFAULT_JSON = Path("artifacts/deepseek-retranslation/authoritative-glossary.v1.json")
DEFAULT_MD = Path("artifacts/deepseek-retranslation/authoritative-glossary.v1.md")
POLICY_PATH = Path("docs/DEEPSEEK_RETRANSLATION_POLICY.md")

FOLDER_NAME_RE = re.compile(r"^(\d+)\s+-\s+(.+?)（(.+?)）$")
SPEAKER_RE = re.compile(r"^([^:@\r\n][^:\r\n]{0,80}):\s?(.*)$")


def evidence(path: str, line: int, jp: str, cn: str) -> dict[str, Any]:
    return {"path": path, "line": line, "jp_contains": jp, "cn_contains": cn}


STATIC_TERMS: tuple[dict[str, Any], ...] = (
    {
        "jp": "魔法少女", "cn": "魔法少女", "kind": "world_term",
        "works": ["magireco", "exedra"], "context": "契约者与作品通用称谓",
        "confidence": "authoritative", "conflict": "",
        "evidence": [evidence("main_story/0000-00 - 第I部 序章/000001_1-1.txt", 3, "魔法少女", "魔法少女")],
    },
    {
        "jp": "魔女", "cn": "魔女", "kind": "world_term",
        "works": ["magireco", "exedra"], "context": "作品通用敌对存在",
        "confidence": "authoritative", "conflict": "",
        "evidence": [evidence("main_story/0000-00 - 第I部 序章/000001_1-1.txt", 7, "魔女", "魔女")],
    },
    {
        "jp": "使い魔", "cn": "使魔", "kind": "world_term",
        "works": ["magireco", "exedra"], "context": "魔女眷属",
        "confidence": "authoritative", "conflict": "",
        "evidence": [evidence("main_story/1011-01 - 第I部 第1章/101101_1-7.txt", 23, "使い魔", "使魔")],
    },
    {
        "jp": "神浜市", "cn": "神滨市", "kind": "place",
        "works": ["magireco", "exedra"], "context": "城市名",
        "confidence": "authoritative", "conflict": "",
        "evidence": [evidence("main_story/0000-00 - 第I部 序章/000003_1-5.txt", 53, "神浜市", "神滨市")],
    },
    {
        "jp": "見滝原", "cn": "见泷原", "kind": "place",
        "works": ["magireco", "exedra"], "context": "城市/地区名；原文带 市 时仍采用见泷原市",
        "confidence": "trusted_human", "conflict": "",
        "evidence": [evidence("Scene0支线/film1/902117_010-030.txt", 27, "見滝原", "见泷原")],
    },
    {
        "jp": "ソウルジェム", "cn": "灵魂宝石", "kind": "item",
        "works": ["magireco", "exedra"], "context": "契约后生成的宝石",
        "confidence": "authoritative", "conflict": "",
        "evidence": [evidence("main_story/0000-00 - 第I部 序章/000001_1-1.txt", 6, "ソウルジェム", "灵魂宝石")],
    },
    {
        "jp": "グリーフシード", "cn": "悲叹之种", "kind": "item",
        "works": ["magireco", "exedra"], "context": "魔女掉落物",
        "confidence": "authoritative", "conflict": "",
        "evidence": [evidence("main_story/1012-02 - 第I部 第2章/101204_1-7.txt", 53, "グリーフシード", "悲叹之种")],
    },
    {
        "jp": "調整屋", "cn": "调整专家", "kind": "role",
        "works": ["magireco"], "context": "神滨的魔力调整职业/人物称呼",
        "confidence": "authoritative", "conflict": "部分社群文本使用调整屋；正式官方基线采用调整专家",
        "evidence": [evidence("main_story/1011-01 - 第I部 第1章/101102_1-8.txt", 31, "調整屋", "调整专家")],
    },
    {
        "jp": "うわさ", "cn": "传闻", "kind": "world_term",
        "works": ["magireco", "exedra"], "context": "普通传闻及神滨传闻；专名需结合说话人/标签",
        "confidence": "authoritative", "conflict": "作为实体名时可出现传闻的××等完整专名",
        "evidence": [evidence("main_story/1012-02 - 第I部 第2章/101201_1-7.txt", 130, "うわさ", "传闻")],
    },
    {
        "jp": "ドッペル", "cn": "魔女化身", "kind": "world_term",
        "works": ["magireco", "exedra"], "context": "魔法少女在神滨显现的力量",
        "confidence": "authoritative", "conflict": "不得仅按外来语音译",
        "evidence": [evidence("main_story/1014-04 - 第I部 第4章/101405_1-14.txt", 232, "ドッペル", "魔女化身")],
    },
    {
        "jp": "マギウスの翼", "cn": "玛吉斯之翼", "kind": "organization",
        "works": ["magireco", "exedra"], "context": "组织名",
        "confidence": "authoritative", "conflict": "",
        "evidence": [evidence("main_story/1014-04 - 第I部 第4章/101404_1-10.txt", 227, "マギウスの翼", "玛吉斯之翼")],
    },
    {
        "jp": "神浜マギアユニオン", "cn": "神滨魔法联盟", "kind": "organization",
        "works": ["magireco", "exedra"], "context": "组织名",
        "confidence": "authoritative", "conflict": "",
        "evidence": [evidence("main_story/1022-12 - 第II部 第1章 - 集結の百禍編/102201_1-15.txt", 129, "神浜マギアユニオン", "神滨魔法联盟")],
    },
    {
        "jp": "キュゥべえ", "cn": "丘比", "kind": "character",
        "works": ["magireco", "exedra"], "context": "角色/种族通用译名",
        "confidence": "authoritative", "conflict": "",
        "evidence": [evidence("main_story/0000-00 - 第I部 序章/000001_1-1.txt", 3, "キュゥべえ", "丘比")],
    },
    {
        "jp": "ういちゃん", "cn": "小忧", "kind": "nickname_honorific",
        "works": ["magireco", "exedra"], "context": "人名うい后的ちゃん；仅限新生成译文",
        "confidence": "user_mandated", "conflict": "官方保护文本常省略敬称写作忧；保护文本不改，新译文按政策写小忧",
        "evidence": [
            evidence("main_story/1013-03 - 第I部 第3章/101301_1-4.txt", 65, "ういちゃん", "忧"),
            {"path": POLICY_PATH.as_posix(), "contains": "`ういちゃん` / `忧ちゃん` 采用“小忧”"},
        ],
    },
    {
        "jp": "いろはちゃん", "cn": "小彩羽", "kind": "nickname_honorific",
        "works": ["magireco", "exedra"], "context": "人名いろは后的ちゃん；仅限新生成译文",
        "confidence": "user_mandated", "conflict": "官方保护文本常省略敬称写作彩羽；保护文本不改",
        "evidence": [
            evidence("main_story/1011-01 - 第I部 第1章/101102_1-8.txt", 55, "いろはちゃん", "彩羽"),
            {"path": POLICY_PATH.as_posix(), "contains": "`いろはちゃん` 采用“小彩羽”"},
        ],
    },
    {
        "jp": "灯花ちゃん", "cn": "小灯花", "kind": "nickname_honorific",
        "works": ["magireco", "exedra"], "context": "人名灯花后的ちゃん；仅限新生成译文",
        "confidence": "user_mandated", "conflict": "官方保护文本常省略敬称写作灯花；保护文本不改",
        "evidence": [
            evidence("main_story/1012-02 - 第I部 第2章/101201_1-7.txt", 14, "灯花ちゃん", "灯花"),
            {"path": POLICY_PATH.as_posix(), "contains": "`灯花ちゃん` 采用“小灯花”"},
        ],
    },
    {
        "jp": "ねむちゃん", "cn": "小音梦", "kind": "nickname_honorific",
        "works": ["magireco", "exedra"], "context": "人名ねむ后的ちゃん；仅限新生成译文",
        "confidence": "user_mandated", "conflict": "官方保护文本常省略敬称写作音梦；保护文本不改",
        "evidence": [
            evidence("main_story/1012-02 - 第I部 第2章/101201_1-7.txt", 14, "ねむちゃん", "音梦"),
            {"path": POLICY_PATH.as_posix(), "contains": "`ねむちゃん` 采用“小音梦”"},
        ],
    },
    {
        "jp": "姉さん", "cn": "姐姐", "kind": "kinship",
        "works": ["magireco", "exedra"], "context": "说话人称呼年长女性；具体姓名需结合人物关系",
        "confidence": "authoritative", "conflict": "不能据此推断被称呼者身份",
        "evidence": [evidence("main_story/1014-04 - 第I部 第4章/101407_1-4.txt", 118, "お姉さん", "姐姐")],
    },
)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8-sig").splitlines()


def validate_evidence(repo_root: Path, item: dict[str, Any]) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for record in item["evidence"]:
        relative = Path(record["path"])
        if "line" not in record:
            full = repo_root / relative
            text = full.read_text(encoding="utf-8-sig")
            if record["contains"] not in text:
                raise ValueError(f"policy evidence missing: {relative}: {record['contains']}")
            verified.append({**record, "sha256": sha256_bytes(full.read_bytes())})
            continue
        jp_path = repo_root / JP_ROOT / relative
        cn_path = repo_root / CN_ROOT / relative
        jp_lines = read_lines(jp_path)
        cn_lines = read_lines(cn_path)
        line = int(record["line"])
        if line < 1 or line > len(jp_lines) or line > len(cn_lines):
            raise ValueError(f"evidence line out of range: {relative}:{line}")
        jp_line = jp_lines[line - 1]
        cn_line = cn_lines[line - 1]
        if record["jp_contains"] not in jp_line or record["cn_contains"] not in cn_line:
            raise ValueError(
                f"evidence drift: {relative}:{line}\nJP={jp_line}\nCN={cn_line}"
            )
        verified.append(
            {
                "jp_path": (JP_ROOT / relative).as_posix(),
                "cn_path": (CN_ROOT / relative).as_posix(),
                "line": line,
                "jp_excerpt": jp_line,
                "cn_excerpt": cn_line,
                "jp_sha256": sha256_bytes(jp_path.read_bytes()),
                "cn_sha256": sha256_bytes(cn_path.read_bytes()),
            }
        )
    return verified


def paired_character_directories(repo_root: Path) -> list[dict[str, Any]]:
    jp_parent = repo_root / JP_ROOT / "character_story"
    cn_parent = repo_root / CN_ROOT / "character_story"
    records: list[dict[str, Any]] = []
    for path in sorted(jp_parent.iterdir(), key=lambda value: value.name):
        if not path.is_dir():
            continue
        match = FOLDER_NAME_RE.fullmatch(path.name)
        if not match or not (cn_parent / path.name).is_dir():
            continue
        identifier, cn_name, jp_name = match.groups()
        records.append(
            {
                "id": identifier,
                "jp": jp_name.strip(),
                "cn": cn_name.strip(),
                "kind": "character_full_name",
                "works": ["magireco"],
                "context": "角色剧情目录的中日显式映射",
                "confidence": "paired_trusted_directory",
                "conflict": "",
                "evidence": [
                    {
                        "jp_path": (JP_ROOT / "character_story" / path.name).as_posix(),
                        "cn_path": (CN_ROOT / "character_story" / path.name).as_posix(),
                        "directory_name": path.name,
                    }
                ],
            }
        )
    return records


def aligned_speaker_mappings(repo_root: Path) -> list[dict[str, Any]]:
    jp_parent = repo_root / JP_ROOT / "main_story"
    cn_parent = repo_root / CN_ROOT / "main_story"
    counts: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    examples: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for jp_path in sorted(jp_parent.rglob("*.txt"), key=lambda value: value.as_posix()):
        relative = jp_path.relative_to(jp_parent)
        cn_path = cn_parent / relative
        if not cn_path.is_file():
            continue
        jp_lines = read_lines(jp_path)
        cn_lines = read_lines(cn_path)
        if len(jp_lines) != len(cn_lines):
            continue
        for line_number, (jp_line, cn_line) in enumerate(zip(jp_lines, cn_lines), 1):
            jp_match = SPEAKER_RE.match(jp_line)
            cn_match = SPEAKER_RE.match(cn_line)
            if not jp_match or not cn_match:
                continue
            jp_speaker = jp_match.group(1).strip()
            cn_speaker = cn_match.group(1).strip()
            if not jp_speaker or not cn_speaker:
                continue
            counts[jp_speaker][cn_speaker] += 1
            key = (jp_speaker, cn_speaker)
            if len(examples[key]) < 3:
                examples[key].append(
                    {
                        "jp_path": (JP_ROOT / "main_story" / relative).as_posix(),
                        "cn_path": (CN_ROOT / "main_story" / relative).as_posix(),
                        "line": line_number,
                        "jp_excerpt": jp_line,
                        "cn_excerpt": cn_line,
                    }
                )
    records: list[dict[str, Any]] = []
    for jp_speaker in sorted(counts):
        candidates = counts[jp_speaker]
        total = sum(candidates.values())
        cn_speaker, top_count = candidates.most_common(1)[0]
        ratio = top_count / total
        status = "approved" if top_count >= 2 and ratio >= 0.95 else "review"
        records.append(
            {
                "jp": jp_speaker,
                "cn": cn_speaker,
                "kind": "speaker_name",
                "works": ["magireco"],
                "context": "可信主线中同一行的说话人映射",
                "confidence": "authoritative" if status == "approved" else "conflicted",
                "status": status,
                "occurrences": top_count,
                "total_occurrences": total,
                "agreement_ratio": round(ratio, 6),
                "conflict": "" if status == "approved" else json.dumps(candidates, ensure_ascii=False, sort_keys=True),
                "evidence": examples[(jp_speaker, cn_speaker)],
            }
        )
    return records


def build(repo_root: Path) -> dict[str, Any]:
    static: list[dict[str, Any]] = []
    for definition in STATIC_TERMS:
        item = {key: value for key, value in definition.items() if key != "evidence"}
        item["status"] = "approved"
        item["evidence"] = validate_evidence(repo_root, definition)
        static.append(item)
    folders = paired_character_directories(repo_root)
    speakers = aligned_speaker_mappings(repo_root)
    approved_speakers = sum(item["status"] == "approved" for item in speakers)
    return {
        "schema_version": 1,
        "policy": {
            "path": POLICY_PATH.as_posix(),
            "sha256": sha256_bytes((repo_root / POLICY_PATH).read_bytes()),
            "authority_order": [
                "official_chinese_human",
                "user_provided_cross_verified_human",
                "consistent_local_human",
                "unresolved",
            ],
            "translation_worker": "deepseek-v4-flash",
            "worker_repository_tools": False,
        },
        "counts": {
            "static_terms": len(static),
            "paired_character_names": len(folders),
            "speaker_mappings": len(speakers),
            "approved_speaker_mappings": approved_speakers,
            "speaker_mappings_needing_review": len(speakers) - approved_speakers,
        },
        "static_terms": static,
        "paired_character_names": folders,
        "speaker_mappings": speakers,
    }


def markdown(document: dict[str, Any]) -> str:
    counts = document["counts"]
    lines = [
        "# DeepSeek 重译权威术语库 v1",
        "",
        "本清单由本地官方/人工语料证据生成；它不调用模型，也不修改剧情。",
        "",
        f"- 核心术语：{counts['static_terms']}",
        f"- 成对角色目录译名：{counts['paired_character_names']}",
        f"- 主线说话人映射：{counts['speaker_mappings']}",
        f"- 可直接采用的说话人映射：{counts['approved_speaker_mappings']}",
        f"- 待人工核实的说话人映射：{counts['speaker_mappings_needing_review']}",
        "",
        "## 核心术语",
        "",
        "| 日文 | 采用译法 | 类型 | 置信度 | 冲突说明 |",
        "|---|---|---|---|---|",
    ]
    for item in document["static_terms"]:
        conflict = item["conflict"].replace("|", "\\|") or "—"
        lines.append(
            f"| {item['jp']} | {item['cn']} | {item['kind']} | {item['confidence']} | {conflict} |"
        )
    lines.extend(["", "## 待核实的说话人映射", ""])
    pending = [item for item in document["speaker_mappings"] if item["status"] != "approved"]
    if not pending:
        lines.append("无。")
    else:
        for item in pending:
            lines.append(
                f"- `{item['jp']}` → `{item['cn']}`：{item['occurrences']}/{item['total_occurrences']}，候选 {item['conflict']}"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    document = build(repo_root)
    json_output = args.json_output if args.json_output.is_absolute() else repo_root / args.json_output
    md_output = args.markdown_output if args.markdown_output.is_absolute() else repo_root / args.markdown_output
    json_raw = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    md_raw = markdown(document).encode("utf-8")
    atomic_write(json_output, json_raw)
    atomic_write(md_output, md_raw)
    print(
        "AUTHORITATIVE_GLOSSARY_OK "
        f"static={document['counts']['static_terms']} "
        f"character_names={document['counts']['paired_character_names']} "
        f"speakers={document['counts']['speaker_mappings']} "
        f"approved_speakers={document['counts']['approved_speaker_mappings']} "
        f"json_sha256={sha256_bytes(json_raw)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
