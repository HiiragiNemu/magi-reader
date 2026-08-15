#!/usr/bin/env python3
"""Infer exact JP→CN Exedra speaker aliases from the aligned corpus."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools/tw_authentic_scenario.py"
SYNC = ROOT / "tools/synchronize_exedra_speaker_dictionary.py"

OLD_TRANSLATOR = '''def translate_speaker(value: str, mapping: dict[str, str]) -> str:
    normalized = normalize_display_punctuation(value)
    if not normalized or normalized in NARRATION_SPEAKERS:
        return "旁白"
    parts = tuple(part for part in MULTI_SPEAKER_RE.split(normalized) if part)
    if len(parts) > 1:
        return "＆".join(translate_speaker(part, mapping) for part in parts)
    return _translate_speaker_component(normalized, mapping)
'''

NEW_TRANSLATOR = '''def translate_speaker(value: str, mapping: dict[str, str]) -> str:
    normalized = normalize_display_punctuation(value)
    if not normalized or normalized in NARRATION_SPEAKERS:
        return "旁白"
    # Exact corpus aliases take precedence over component heuristics. This is
    # required for ensemble labels, historical names and role descriptions
    # whose individual fragments are not independently meaningful.
    key = speaker_lookup_key(normalized)
    direct = mapping.get(key) or EXEDRA_ADDITIONAL_SPEAKER_LOOKUP.get(key)
    if direct is not None and not contains_japanese_script(direct):
        return normalize_display_punctuation(direct)
    parts = tuple(part for part in MULTI_SPEAKER_RE.split(normalized) if part)
    if len(parts) > 1:
        return "＆".join(translate_speaker(part, mapping) for part in parts)
    return _translate_speaker_component(normalized, mapping)
'''

SYNC_SOURCE = r'''#!/usr/bin/env python3
"""Synchronize dictionary.ts from exact aligned Exedra JP/CN speaker pairs.

The script never translates prose. It learns only unambiguous speaker aliases
already proven by the repository's paired Japanese and Chinese scenario data,
then writes those exact aliases into NAME_TRANSLATE_MAP for both browser display
and JP-only Chinese editing.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tw_authentic_scenario import (  # noqa: E402
    contains_japanese_script,
    load_name_translation_map,
    normalize_display_punctuation,
    speaker_lookup_key,
    translate_speaker,
)

JP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"
CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
DICTIONARY = ROOT / "website/app/config/dictionary.ts"
PAIR_RE = re.compile(r'"((?:\\.|[^"\\])*)"\s*:\s*"((?:\\.|[^"\\])*)"')
SEPARATOR_RE = re.compile(r'[:：﹕︰︓]')
BEGIN = "  // EXEDRA_CORPUS_SYNCED_SPEAKER_ALIASES_BEGIN\n"
END = "  // EXEDRA_CORPUS_SYNCED_SPEAKER_ALIASES_END\n"
SKIP_JSON_SUFFIXES = (
    ".import-report.json",
    ".provenance.json",
    "exedra_manifest.json",
)


def decode(value: str) -> str:
    return json.loads(f'"{value}"')


def canonical_target(value: str) -> str:
    return normalize_display_punctuation(value).strip()


def add_candidate(
    candidates: dict[str, Counter[str]],
    spellings: dict[str, set[str]],
    jp: str,
    cn: str,
) -> None:
    jp = normalize_display_punctuation(jp).strip()
    cn = canonical_target(cn)
    if not jp or not cn or not contains_japanese_script(jp):
        return
    if contains_japanese_script(cn):
        return
    key = speaker_lookup_key(jp)
    if not key:
        return
    candidates[key][cn] += 1
    spellings[key].add(jp)


def text_speakers(path: Path) -> list[str]:
    result: list[str] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("---"):
            continue
        match = SEPARATOR_RE.search(raw)
        if match is None or match.start() <= 0 or match.start() > 96:
            continue
        result.append(raw[:match.start()].strip())
    return result


def collect_txt_pairs(
    candidates: dict[str, Counter[str]],
    spellings: dict[str, set[str]],
) -> tuple[int, int]:
    pairs = events = 0
    for jp_path in sorted(JP_ROOT.rglob("*_jp.txt")):
        relative = jp_path.relative_to(JP_ROOT)
        name = relative.name
        cn_path = CN_ROOT / relative.with_name(name[:-7] + "_cn.txt")
        if not cn_path.is_file():
            continue
        jp = text_speakers(jp_path)
        cn = text_speakers(cn_path)
        if len(jp) != len(cn):
            raise RuntimeError(
                f"JP/CN TXT event count differs: {relative}: {len(jp)}/{len(cn)}"
            )
        pairs += 1
        events += len(jp)
        for jp_speaker, cn_speaker in zip(jp, cn):
            add_candidate(candidates, spellings, jp_speaker, cn_speaker)
    return pairs, events


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def row_speakers(document: dict[str, Any]) -> dict[tuple[int, Any, str], str]:
    result: dict[tuple[int, Any, str], str] = {}
    sheets = document.get("sheetList")
    if not isinstance(sheets, list):
        return result
    for sheet_index, sheet in enumerate(sheets):
        if not isinstance(sheet, dict):
            continue
        header = sheet.get("headerRow")
        headers = header.get("cellList") if isinstance(header, dict) else None
        rows = sheet.get("contentRowList")
        if not isinstance(headers, list) or not isinstance(rows, list):
            continue
        folded = [str(item or "").strip().casefold() for item in headers]
        try:
            action_index = folded.index("actiontype")
            name_index = folded.index("name")
        except ValueError:
            continue
        for fallback_row, row in enumerate(rows, start=2):
            cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(cells, list) or max(action_index, name_index) >= len(cells):
                continue
            action = str(cells[action_index] or "").strip().casefold()
            speaker = str(cells[name_index] or "").strip()
            row_number = (
                row.get("rowNumber", fallback_row)
                if isinstance(row, dict)
                else fallback_row
            )
            key = (sheet_index, row_number, action)
            if key in result and result[key] != speaker:
                # Duplicate structural identities are not safe training data.
                result.pop(key, None)
                continue
            result[key] = speaker
    return result


def collect_json_pairs(
    candidates: dict[str, Counter[str]],
    spellings: dict[str, set[str]],
) -> tuple[int, int]:
    pairs = rows = 0
    for jp_path in sorted(JP_ROOT.rglob("*.json")):
        if jp_path.name.casefold().endswith(SKIP_JSON_SUFFIXES):
            continue
        relative = jp_path.relative_to(JP_ROOT)
        cn_path = CN_ROOT / relative
        if not cn_path.is_file():
            continue
        jp_document = load_json(jp_path)
        cn_document = load_json(cn_path)
        if jp_document is None or cn_document is None:
            continue
        jp_names = row_speakers(jp_document)
        cn_names = row_speakers(cn_document)
        common = sorted(set(jp_names) & set(cn_names), key=repr)
        if not common:
            continue
        pairs += 1
        rows += len(common)
        for key in common:
            add_candidate(
                candidates,
                spellings,
                jp_names[key],
                cn_names[key],
            )
    return pairs, rows


def parse_dictionary_block(source: str) -> tuple[int, int, list[tuple[str, str]]]:
    marker = "export const NAME_TRANSLATE_MAP"
    start = source.find(marker)
    end = source.find("\n};", start)
    if start < 0 or end < 0:
        raise RuntimeError("dictionary.ts NAME_TRANSLATE_MAP is missing")
    pairs = [
        (decode(match.group(1)), decode(match.group(2)))
        for match in PAIR_RE.finditer(source[start:end])
    ]
    return start, end, pairs


def replace_exact_value(source: str, raw: str, target: str) -> tuple[str, int]:
    encoded_raw = json.dumps(raw, ensure_ascii=False)
    encoded_target = json.dumps(target, ensure_ascii=False)
    pattern = re.compile(
        rf'({re.escape(encoded_raw)}\s*:\s*)"(?:\\.|[^"\\])*"'
    )
    return pattern.subn(rf'\g<1>{encoded_target}', source)


def choose_aliases(
    candidates: dict[str, Counter[str]],
    spellings: dict[str, set[str]],
) -> dict[str, str]:
    aliases: dict[str, str] = {}
    conflicts: list[tuple[str, Counter[str]]] = []
    for key, counts in sorted(candidates.items()):
        if len(counts) != 1:
            conflicts.append((key, counts))
            continue
        target = next(iter(counts))
        for raw in sorted(spellings[key]):
            aliases[raw] = target
    if conflicts:
        for key, counts in conflicts[:100]:
            print("AMBIGUOUS_EXEDRA_SPEAKER", repr(key), dict(counts))
        raise RuntimeError(
            f"Aligned corpus has {len(conflicts)} ambiguous JP speaker identities"
        )
    return aliases


def synchronize() -> dict[str, int]:
    candidates: dict[str, Counter[str]] = defaultdict(Counter)
    spellings: dict[str, set[str]] = defaultdict(set)
    txt_pairs, txt_events = collect_txt_pairs(candidates, spellings)
    json_pairs, json_rows = collect_json_pairs(candidates, spellings)
    aliases = choose_aliases(candidates, spellings)

    source = DICTIONARY.read_text(encoding="utf-8")
    if BEGIN in source or END in source:
        raise RuntimeError("Corpus-synchronized alias block already exists")
    _start, end, existing_pairs = parse_dictionary_block(source)
    existing_by_key: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for raw, value in existing_pairs:
        existing_by_key[speaker_lookup_key(raw)].append((raw, value))

    updated = 0
    additions: dict[str, str] = {}
    for raw, target in sorted(aliases.items()):
        key = speaker_lookup_key(raw)
        matching = existing_by_key.get(key, [])
        if matching:
            for existing_raw, existing_value in matching:
                if canonical_target(existing_value) == target:
                    continue
                source, count = replace_exact_value(
                    source,
                    existing_raw,
                    target,
                )
                if count != 1:
                    raise RuntimeError(
                        f"Could not update dictionary alias {existing_raw!r}"
                    )
                updated += 1
            continue
        additions[raw] = target

    # Re-resolve the object boundary after in-place replacements.
    _start, end, _pairs = parse_dictionary_block(source)
    block = BEGIN + "".join(
        f"  {json.dumps(raw, ensure_ascii=False)}: "
        f"{json.dumps(target, ensure_ascii=False)},\n"
        for raw, target in sorted(additions.items())
    ) + END
    source = source[:end] + "\n" + block + source[end:]
    DICTIONARY.write_text(source, encoding="utf-8", newline="\n")

    mapping = load_name_translation_map(DICTIONARY)
    unresolved = {
        raw: translate_speaker(raw, mapping)
        for raw in aliases
        if contains_japanese_script(translate_speaker(raw, mapping))
    }
    if unresolved:
        for raw, value in sorted(unresolved.items())[:100]:
            print("UNRESOLVED_SYNCED_ALIAS", repr(raw), "->", repr(value))
        raise RuntimeError(
            f"Synchronized dictionary still leaves {len(unresolved)} aliases Japanese"
        )
    return {
        "txtPairs": txt_pairs,
        "txtEvents": txt_events,
        "jsonPairs": json_pairs,
        "jsonRows": json_rows,
        "candidateKeys": len(candidates),
        "aliasSpellings": len(aliases),
        "updated": updated,
        "added": len(additions),
    }


def main() -> int:
    stats = synchronize()
    print(
        "EXEDRA_SPEAKER_DICTIONARY_SYNCHRONIZED "
        + " ".join(f"{key}={value}" for key, value in stats.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def main() -> int:
    source = MODULE.read_text(encoding="utf-8")
    count = source.count(OLD_TRANSLATOR)
    if count != 1:
        raise RuntimeError(
            f"tw_authentic_scenario translate_speaker count={count}; expected 1"
        )
    MODULE.write_text(
        source.replace(OLD_TRANSLATOR, NEW_TRANSLATOR, 1),
        encoding="utf-8",
        newline="\n",
    )
    SYNC.write_text(SYNC_SOURCE, encoding="utf-8", newline="\n")
    print("AUTHENTIC_TW_REPAIR_V18_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
