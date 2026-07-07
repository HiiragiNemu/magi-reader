#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rebuild TXT only for Scene0 main/sub folders in magireco-source-master and
magireco-translate-data-master.

Default is dry-run. Use --write to modify files.
Use --format plain for current website-compatible output.
Use --format extended to preserve Scene0 command/position metadata for the patched website parser.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

TARGET_REL_DIRS = (
    "magireco-source-master/Scenarios_full",
    "magireco-translate-data-master/Scenarios_full",
)

POS_ORDER = ("Left", "Right", "Center")
POS_TO_VALUE = {"Left": 0, "Center": 1, "Right": 2}
VALUE_TO_POS = {0: "Left", 1: "Center", 2: "Right"}
INTERVIEW_MARKERS = ("取材記録", "采访记录", "取材记录", "取材録")
S0_PREFIX = "@S0\t"


def natural_key(s: str) -> List[Any]:
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", s)]


def decode_hash_u(s: str) -> str:
    """Decode path fragments such as #U4e3b#U7ebf to 主线."""
    def repl(m: re.Match[str]) -> str:
        try:
            return chr(int(m.group(1), 16))
        except ValueError:
            return m.group(0)
    return re.sub(r"#U([0-9a-fA-F]{4,6})", repl, s)


def is_scene0_path(path: Path) -> bool:
    decoded = decode_hash_u(path.as_posix()).lower()
    if "scene0" not in decoded:
        return False
    return any(token in decoded for token in ("主线", "支线", "main", "sub"))


def clean_and_format_content(text: Any) -> str:
    if not isinstance(text, str):
        return ""

    # Keep literal \n because the current website parser already converts it to real line breaks.
    text = text.replace("@", "\\n").replace("[br]", "\\n")
    text = text.replace("「textBlack:", "[textBlack:").replace("『textBlack:", "[textBlack:")

    # Keep color information in the format already supported by the website reader.
    for color in ("Red", "Blue", "Yellow", "Black"):
        tag = color.lower()
        text = re.sub(
            rf"\[text{color}:(.*?)\]",
            rf"<{tag}>\1</{tag}>",
            text,
            flags=re.DOTALL,
        )

    # Remove remaining control tags that are not directly useful in TXT reading mode.
    text = re.sub(r"\[.*?\]", "", text)
    return text.strip()


def is_interview_marker(text: str) -> bool:
    return bool(text) and any(marker in text for marker in INTERVIEW_MARKERS)


def extract_interview_names(cleaned_text: str) -> List[str]:
    names: List[str] = []
    for part in cleaned_text.split("\\n"):
        part = re.sub(r"<black>(.*?)</black>", r"\1", part).strip()
        if part and "记录" not in part and "記録" not in part and "―" not in part:
            names.append(part)
    return names


def get_section_no(filename: str) -> str:
    # 901101-010_homura.json -> 010; 901304-020.json -> 020
    m = re.search(r"[-_](\d+)(?:[_\.]|$)", filename)
    return m.group(1) if m else "?"


def get_story_base_and_section(filename: str) -> Tuple[Optional[str], Optional[str]]:
    m = re.match(r"^(\d+)[-_](\d+)", filename)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def make_target_name(json_files: List[Path]) -> str:
    first_base, first_sec = get_story_base_and_section(json_files[0].name)
    last_base, last_sec = get_story_base_and_section(json_files[-1].name)
    base = first_base or json_files[0].stem
    first_sec = first_sec or "1"
    last_sec = last_sec or first_sec

    if first_sec == last_sec:
        return f"{base}_{first_sec}.txt"
    return f"{base}_{first_sec}-{last_sec}.txt"


def sort_group_names(story: Dict[str, Any]) -> List[str]:
    groups = [k for k, v in story.items() if k.startswith("group_") and isinstance(v, list)]
    return sorted(groups, key=natural_key)


def format_line(
    *,
    output_format: str,
    kind: str,
    speaker: str,
    text: str,
    command: str,
    position: Optional[str] = None,
) -> str:
    speaker = speaker or "旁白"
    if output_format == "extended":
        payload = {
            "kind": kind,
            "speaker": speaker,
            "text": text,
            "command": command,
        }
        if position:
            payload["position"] = position.lower()
        return S0_PREFIX + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    return f"{speaker}: {text}\n"


def build_txt_from_json(json_path: Path, output_format: str, counters: Counter) -> str:
    try:
        data = json.loads(json_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"  ❌ JSON读取失败: {json_path}: {exc}")
        return ""

    story = data.get("story", {})
    if not isinstance(story, dict):
        return ""

    fname = json_path.name
    sec_no = get_section_no(fname)
    output: List[str] = []

    for group_name in sort_group_names(story):
        group = story[group_name]
        if not isinstance(group, list):
            continue

        lines: List[str] = []
        pos_to_id: Dict[str, Optional[str]] = {"Left": None, "Right": None, "Center": None}
        explicit_name_for_pos: Dict[str, Optional[str]] = {"Left": None, "Right": None, "Center": None}
        global_id_name: Dict[str, str] = {}
        sticky_narration_name = "旁白"
        sticky_fnarration_name = "旁白"

        for item in group:
            if not isinstance(item, dict):
                continue

            # Track current character ID per position. Scene0 chara pos is 0/1/2.
            chara = item.get("chara")
            if isinstance(chara, list):
                for c in chara:
                    if not isinstance(c, dict):
                        continue
                    cid = c.get("id")
                    if cid is None or "pos" not in c:
                        continue
                    p_key = VALUE_TO_POS.get(c.get("pos"))
                    if not p_key:
                        continue
                    cid_s = str(cid)
                    old_id = pos_to_id[p_key]
                    pos_to_id[p_key] = cid_s
                    if old_id and old_id != cid_s:
                        explicit_name_for_pos[p_key] = None

            # Track explicit names. Scene0 uses nameAvXxx; old scripts only handled nameXxx.
            for pos in POS_ORDER:
                for n_key in (f"nameAv{pos}", f"name{pos}"):
                    if n_key in item:
                        name = item.get(n_key)
                        if isinstance(name, str) and name:
                            explicit_name_for_pos[pos] = name
                            if pos_to_id[pos]:
                                global_id_name[pos_to_id[pos] or ""] = name

            # Choices / branches.
            if isinstance(item.get("select"), list):
                for opt in item["select"]:
                    if not isinstance(opt, dict):
                        continue
                    sel_text = clean_and_format_content(opt.get("textSelect", ""))
                    sel_group = opt.get("group", "")
                    if sel_text:
                        lines.append(f"选项: 【{sel_text}】→ {sel_group}\n")
                        counters["select"] += 1
                continue

            # Interview marker for normal narration.
            if "narration" in item and is_interview_marker(str(item.get("narration", ""))):
                cleaned = clean_and_format_content(item.get("narration", ""))
                if cleaned:
                    lines.append("\n―― 取材记录 ――\n")
                    for name in extract_interview_names(cleaned):
                        lines.append(format_line(
                            output_format=output_format,
                            kind="narration",
                            speaker="旁白",
                            text=name,
                            command="interviewMarker",
                        ))
                sticky_narration_name = "旁白"
                sticky_fnarration_name = "旁白"
                counters["interview"] += 1
                continue

            # Scene0 film narration. Must be checked before normal narration.
            fnarration_key = None
            if "Fnarration" in item:
                fnarration_key = "Fnarration"
            elif "progressFnarration" in item:
                fnarration_key = "progressFnarration"

            if fnarration_key:
                raw = item.get(fnarration_key)
                name = item.get("nameFnarration")
                if isinstance(name, str):
                    sticky_fnarration_name = name or "旁白"
                speaker = sticky_fnarration_name
                cleaned = clean_and_format_content(raw)
                if cleaned:
                    lines.append(format_line(
                        output_format=output_format,
                        kind="fnarration",
                        speaker=speaker,
                        text=cleaned,
                        command=fnarration_key,
                    ))
                    counters[fnarration_key] += 1
                continue

            # Normal narration / progressNarration.
            narration_key = None
            if "narration" in item:
                narration_key = "narration"
            elif "progressNarration" in item:
                narration_key = "progressNarration"

            if narration_key:
                raw = item.get(narration_key)
                name = item.get("nameNarration")
                if isinstance(name, str):
                    sticky_narration_name = name or "旁白"
                speaker = sticky_narration_name
                cleaned = clean_and_format_content(raw)
                if cleaned:
                    lines.append(format_line(
                        output_format=output_format,
                        kind="narration",
                        speaker=speaker,
                        text=cleaned,
                        command=narration_key,
                    ))
                    counters[narration_key] += 1
                continue

            # Dialogue. Scene0 uses textAvLeft/Right/Center + nameAvLeft/Right/Center.
            for pos in POS_ORDER:
                command = None
                if f"textAv{pos}" in item:
                    command = f"textAv{pos}"
                elif f"text{pos}" in item:
                    command = f"text{pos}"
                if not command:
                    continue

                raw = item.get(command)
                speaker = (
                    item.get(f"nameAv{pos}")
                    or item.get(f"name{pos}")
                    or explicit_name_for_pos[pos]
                    or (global_id_name.get(pos_to_id[pos] or "") if pos_to_id[pos] else None)
                    or "旁白"
                )
                cleaned = clean_and_format_content(raw)
                if cleaned:
                    lines.append(format_line(
                        output_format=output_format,
                        kind="dialogue",
                        speaker=str(speaker),
                        text=cleaned,
                        command=command,
                        position=pos,
                    ))
                    counters[command] += 1
                sticky_narration_name = "旁白"
                break

        if not lines:
            continue

        if group_name == "group_1":
            output.append(f"\n--- [Section {sec_no}] (Source: {fname}) ---\n")
        else:
            branch_no = group_name.replace("group_", "Branch ")
            output.append(f"\n--- [Section {sec_no} - {branch_no}] (Source: {fname}) ---\n")
        output.extend(lines)

    return "".join(output)


def iter_scene0_dirs(root: Path) -> Iterable[Path]:
    for base_rel in TARGET_REL_DIRS:
        base = root / base_rel
        if not base.exists():
            continue
        for current, dirs, files in os.walk(base):
            p = Path(current)
            if not is_scene0_path(p):
                # Prune non-Scene0 top-level branches for speed.
                dirs[:] = [d for d in dirs if is_scene0_path(p / d) or "scene0" in decode_hash_u(d).lower()]
                continue
            if any(f.endswith(".json") for f in files):
                yield p


def rebuild_scene0(root: Path, output_format: str, write: bool, backup: bool) -> None:
    stats = Counter()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    for folder in sorted(set(iter_scene0_dirs(root)), key=lambda x: natural_key(x.as_posix())):
        json_files = sorted(folder.glob("*.json"), key=lambda x: natural_key(x.name))
        if not json_files:
            continue

        groups: Dict[str, List[Path]] = defaultdict(list)
        for jp in json_files:
            base, _sec = get_story_base_and_section(jp.name)
            if not base:
                continue
            groups[base].append(jp)

        for _base, group_files in sorted(groups.items(), key=lambda kv: natural_key(kv[0])):
            group_files = sorted(group_files, key=lambda x: natural_key(x.name))
            target = folder / make_target_name(group_files)
            counters = Counter()
            content = "".join(build_txt_from_json(p, output_format, counters) for p in group_files)
            if not content.strip():
                continue

            existed = target.exists()
            old = target.read_text(encoding="utf-8-sig") if existed else None
            changed = old != content

            stats["json"] += len(group_files)
            stats["txt_target"] += 1
            stats.update(counters)

            rel = target.relative_to(root)
            if not changed:
                print(f"  ⏭️ 无变化: {rel}")
                stats["unchanged"] += 1
                continue

            if not write:
                action = "更新" if existed else "新建"
                print(f"  DRY-RUN {action}: {rel} <= {len(group_files)} JSON")
                stats["dry_changed"] += 1
                continue

            if existed and backup:
                bak = target.with_name(target.name + f".bak-s0-{timestamp}")
                if not bak.exists():
                    shutil.copy2(target, bak)
            target.write_text(content, encoding="utf-8")
            print(f"  ✅ {'更新' if existed else '新建'}: {rel} <= {len(group_files)} JSON")
            stats["written"] += 1

    print("\n=== Scene0 重建报告 ===")
    for key in (
        "txt_target", "json", "written", "dry_changed", "unchanged",
        "textAvLeft", "textAvCenter", "textAvRight", "Fnarration", "progressFnarration",
        "narration", "progressNarration", "select",
    ):
        if stats.get(key):
            print(f"{key}: {stats[key]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="repository root, default: current directory")
    parser.add_argument("--write", action="store_true", help="actually write files; default is dry-run")
    parser.add_argument("--no-backup", action="store_true", help="do not create .bak-s0-TIMESTAMP backups")
    parser.add_argument(
        "--format",
        choices=("plain", "extended"),
        default="plain",
        help="plain is current-reader-compatible; extended preserves S0 metadata for patched reader",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    rebuild_scene0(root=root, output_format=args.format, write=args.write, backup=not args.no_backup)


if __name__ == "__main__":
    main()
