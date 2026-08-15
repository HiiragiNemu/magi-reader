#!/usr/bin/env python3
"""Derive exact JP->CN Exedra speaker aliases from aligned published corpora.

Only evidence from paired CN/JP TXT events or same-row JSON Name cells is used.
Ambiguous evidence is never guessed. The resulting exact aliases are written to
NAME_TRANSLATE_MAP so Reader display and JP-only translation editing share the
same deterministic speaker dictionary.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
JP_ROOT = ROOT / "magiraexedra-source-master" / "Scenarios_full"
CN_ROOT = ROOT / "magiraexedra-translate-data-master" / "Scenarios_full"
DICTIONARY = ROOT / "website" / "app" / "config" / "dictionary.ts"

PAIR_RE = re.compile(r'"((?:\\.|[^"\\])*)"\s*:\s*"((?:\\.|[^"\\])*)"')
SOURCE_RE = re.compile(r"\(Source:\s*([^()\r\n]+?\.json)\s*\)", re.I)
SEPARATOR_RE = re.compile(r"[:：﹕︰︓]")
KANA_RE = re.compile(r"[\u3040-\u30ff\uff66-\uff9f]")
CONTROL_RE = re.compile(r"[\u0000-\u001f\u007f\u200b-\u200f\u202a-\u202e\u2060\ufeff]+")
DOT_RE = re.compile(r"[・･‧•．]")
NARRATION = {
    "",
    "Narration",
    "ナレーション",
    "旁白",
    "旁白（无角色）",
}


def decode_ts(value: str) -> str:
    return json.loads(f'"{value}"')


def normalize(value: str) -> str:
    return CONTROL_RE.sub(" ", unicodedata.normalize("NFC", value)).strip()


def display_normalize(value: str) -> str:
    value = DOT_RE.sub("·", normalize(value)).replace("&", "＆")
    value = re.sub(r"\s*＆\s*", "＆", value)
    return value


def compact(value: str) -> str:
    return re.sub(r"[ \t\u3000]+", "", display_normalize(value))


def has_japanese(value: str) -> bool:
    return KANA_RE.search(value) is not None


def dictionary_state(source: str) -> tuple[int, int, str, dict[str, str], dict[str, str]]:
    marker = "export const NAME_TRANSLATE_MAP"
    start = source.find(marker)
    end = source.find("\n};", start)
    if start < 0 or end < 0:
        raise RuntimeError("dictionary.ts NAME_TRANSLATE_MAP is missing or unterminated")
    block = source[start:end]
    exact: dict[str, str] = {}
    compact_values: dict[str, str] = {}
    compact_ambiguous: set[str] = set()
    for match in PAIR_RE.finditer(block):
        key = normalize(decode_ts(match.group(1)))
        value = display_normalize(decode_ts(match.group(2)))
        if not key:
            continue
        exact[key] = value
        lookup = compact(key)
        previous = compact_values.get(lookup)
        if previous is not None and previous != value:
            compact_values.pop(lookup, None)
            compact_ambiguous.add(lookup)
        elif lookup not in compact_ambiguous:
            compact_values[lookup] = value
    return start, end, block, exact, compact_values


def current_translation(raw: str, exact: dict[str, str], compact_values: dict[str, str]) -> str:
    normalized = normalize(raw)
    return exact.get(normalized) or compact_values.get(compact(normalized)) or normalized


def unique_by_name(root: Path, suffix: str) -> dict[str, Path]:
    buckets: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(root.rglob(f"*{suffix}")):
        if path.is_file():
            buckets[path.name.casefold()].append(path)
    return {
        name: paths[0]
        for name, paths in buckets.items()
        if len(paths) == 1
    }


def counterpart(
    cn_path: Path,
    *,
    expected_name: str,
    unique_index: dict[str, Path],
) -> Path | None:
    relative = cn_path.relative_to(CN_ROOT)
    same_parent = JP_ROOT / relative.parent / expected_name
    if same_parent.is_file():
        return same_parent
    return unique_index.get(expected_name.casefold())


def report_priority(path: Path) -> int:
    reports = sorted(path.parent.glob("*_cn.import-report.json"))
    for report in reports:
        try:
            value = json.loads(report.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        provenance = value.get("provenance") if isinstance(value, dict) else None
        if provenance == "official_tw_human":
            return 30
        if provenance == "trusted_human":
            return 20
    return 10


def txt_events(path: Path) -> list[tuple[str, int, str]]:
    events: list[tuple[str, int, str]] = []
    source_name = ""
    event_index = 0
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("---"):
            match = SOURCE_RE.search(line)
            if match is None:
                raise RuntimeError(f"Unrecognized Exedra Section header: {path}: {line}")
            source_name = Path(match.group(1)).name
            event_index = 0
            continue
        match = SEPARATOR_RE.search(raw)
        speaker = (
            raw[: match.start()].strip()
            if match is not None and 0 < match.start() <= 96
            else "旁白"
        )
        events.append((source_name, event_index, speaker))
        event_index += 1
    return events


def json_name_rows(path: Path) -> dict[tuple[int, Any, str], str]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or not isinstance(value.get("sheetList"), list):
        return {}
    result: dict[tuple[int, Any, str], str] = {}
    for sheet_index, sheet in enumerate(value["sheetList"]):
        if not isinstance(sheet, dict):
            continue
        header = sheet.get("headerRow")
        headers = header.get("cellList") if isinstance(header, dict) else None
        rows = sheet.get("contentRowList")
        if not isinstance(headers, list) or not isinstance(rows, list):
            continue
        folded = [str(item or "").strip().casefold() for item in headers]
        try:
            name_index = folded.index("name")
        except ValueError:
            continue
        action_index = folded.index("actiontype") if "actiontype" in folded else -1
        for row_index, row in enumerate(rows):
            cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(cells, list) or name_index >= len(cells):
                continue
            speaker = str(cells[name_index] or "").strip()
            if not speaker:
                continue
            action = (
                str(cells[action_index] or "").strip().casefold()
                if 0 <= action_index < len(cells)
                else ""
            )
            row_number = row.get("rowNumber", row_index + 2) if isinstance(row, dict) else row_index + 2
            key = (sheet_index, row_number, action)
            previous = result.get(key)
            if previous is not None and previous != speaker:
                raise RuntimeError(f"Duplicate JSON row identity with different Name: {path}: {key}")
            result[key] = speaker
    return result


def main() -> int:
    if not JP_ROOT.is_dir() or not CN_ROOT.is_dir():
        raise RuntimeError("Exedra JP/CN roots are missing")
    source = DICTIONARY.read_text(encoding="utf-8-sig")
    start, end, block, exact, compact_values = dictionary_state(source)

    # raw JP label -> priority -> canonical CN candidates
    evidence: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    evidence_locations = 0

    def add(raw: str, candidate: str, priority: int) -> None:
        nonlocal evidence_locations
        raw_name = normalize(raw)
        cn_name = display_normalize(candidate)
        if raw_name in NARRATION or cn_name in NARRATION:
            return
        if not has_japanese(raw_name) or has_japanese(cn_name):
            return
        if raw_name == cn_name:
            return
        evidence[raw_name][priority].add(cn_name)
        evidence_locations += 1

    jp_txt_index = unique_by_name(JP_ROOT, "_jp.txt")
    for cn_path in sorted(CN_ROOT.rglob("*_cn.txt")):
        expected_name = cn_path.name[:-7] + "_jp.txt"
        jp_path = counterpart(
            cn_path,
            expected_name=expected_name,
            unique_index=jp_txt_index,
        )
        if jp_path is None:
            continue
        jp_events = txt_events(jp_path)
        cn_events = txt_events(cn_path)
        if len(jp_events) != len(cn_events):
            continue
        priority = report_priority(cn_path)
        for jp_event, cn_event in zip(jp_events, cn_events):
            if jp_event[:2] != cn_event[:2]:
                continue
            add(jp_event[2], cn_event[2], priority)

    jp_json_index = unique_by_name(JP_ROOT, ".json")
    for cn_path in sorted(CN_ROOT.rglob("*.json")):
        folded = cn_path.name.casefold()
        if folded.endswith("_cn.import-report.json") or folded.endswith("_cn.provenance.json"):
            continue
        jp_path = counterpart(
            cn_path,
            expected_name=cn_path.name,
            unique_index=jp_json_index,
        )
        if jp_path is None:
            continue
        try:
            jp_rows = json_name_rows(jp_path)
            cn_rows = json_name_rows(cn_path)
        except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError):
            continue
        priority = report_priority(cn_path)
        for key in sorted(set(jp_rows) & set(cn_rows), key=repr):
            add(jp_rows[key], cn_rows[key], priority)

    additions: dict[str, str] = {}
    updates: dict[str, str] = {}
    conflicts: dict[str, list[str]] = {}
    already_resolved = 0
    for raw in sorted(evidence):
        by_priority = evidence[raw]
        priority = max(by_priority)
        candidates = sorted(by_priority[priority])
        translated = current_translation(raw, exact, compact_values)
        if not has_japanese(translated):
            already_resolved += 1
            continue
        if len(candidates) != 1:
            conflicts[raw] = candidates
            continue
        candidate = candidates[0]
        if raw in exact:
            if has_japanese(exact[raw]):
                updates[raw] = candidate
            continue
        additions[raw] = candidate

    # Update any pre-existing exact mapping that still contains Japanese.
    matches = list(PAIR_RE.finditer(block))
    for match in reversed(matches):
        key = normalize(decode_ts(match.group(1)))
        candidate = updates.get(key)
        if candidate is None:
            continue
        replacement = (
            f"{json.dumps(key, ensure_ascii=False)}: "
            f"{json.dumps(candidate, ensure_ascii=False)}"
        )
        block = block[: match.start()] + replacement + block[match.end() :]

    if additions:
        lines = [
            "",
            "  // Exact aliases derived from event-aligned Exedra JP/CN evidence.",
        ]
        lines.extend(
            "  "
            + json.dumps(raw, ensure_ascii=False)
            + ": "
            + json.dumps(candidate, ensure_ascii=False)
            + ","
            for raw, candidate in sorted(additions.items())
        )
        block += "\n".join(lines) + "\n"

    DICTIONARY.write_text(
        source[:start] + block + source[end:],
        encoding="utf-8",
        newline="\n",
    )

    for raw, candidates in list(sorted(conflicts.items()))[:100]:
        print("AMBIGUOUS_EXEDRA_SPEAKER_EVIDENCE", repr(raw), candidates)
    print(
        "EXEDRA_SPEAKER_ALIASES_DERIVED "
        f"evidence_labels={len(evidence)} evidence_locations={evidence_locations} "
        f"already_resolved={already_resolved} additions={len(additions)} "
        f"updates={len(updates)} ambiguous={len(conflicts)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
