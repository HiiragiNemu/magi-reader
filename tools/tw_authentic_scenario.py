#!/usr/bin/env python3
"""Canonical Exedra speaker localization and safe JSON/TXT materialization."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICTIONARY = ROOT / "website/app/config/dictionary.ts"
TEXT_ACTIONS = frozenset({"talk", "narration", "charactertalk", "onlytext"})
NARRATION_SPEAKERS = frozenset(
    {"Narration", "ナレーション", "旁白", "旁白（无角色）"}
)
TS_PAIR_RE = re.compile(r'"((?:\\.|[^"\\])*)"\s*:\s*"((?:\\.|[^"\\])*)"')
MULTI_SPEAKER_RE = re.compile(r"\s*[＆&]\s*")
SPEAKER_SEPARATOR_RE = re.compile(r"[:：﹕︰︓]")
JAPANESE_SCRIPT_RE = re.compile(r"[\u3040-\u30ff]")


@dataclass(frozen=True)
class LocalizedEvent:
    speaker: str
    text: str
    action: str
    sheet_index: int
    row_number: Any


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _decode_ts_string(value: str) -> str:
    return json.loads(f'"{value}"')


def normalize_speaker(value: str) -> str:
    return (
        unicodedata.normalize("NFC", str(value))
        .replace("\u0000", "")
        .replace("\ufeff", "")
        .strip()
    )


def normalize_display_punctuation(value: str) -> str:
    return re.sub(r"[・･‧•．]", "·", normalize_speaker(value))


def speaker_lookup_key(value: str) -> str:
    return re.sub(
        r"[ \t\u3000]+",
        "",
        normalize_display_punctuation(value),
    )


def load_name_translation_map(path: Path = DEFAULT_DICTIONARY) -> dict[str, str]:
    source = path.read_text(encoding="utf-8-sig")
    marker = "export const NAME_TRANSLATE_MAP"
    start = source.find(marker)
    end = source.find("\n};", start)
    if start < 0 or end < 0:
        raise RuntimeError(f"NAME_TRANSLATE_MAP is missing or unterminated: {path}")

    candidates: dict[str, str] = {}
    ambiguous: set[str] = set()

    def register(alias: str, canonical: str) -> None:
        key = speaker_lookup_key(alias)
        canonical = normalize_display_punctuation(canonical)
        if not key or not canonical or key in ambiguous:
            return
        previous = candidates.get(key)
        if previous is not None and previous != canonical:
            candidates.pop(key, None)
            ambiguous.add(key)
            return
        candidates[key] = canonical

    for match in TS_PAIR_RE.finditer(source[start:end]):
        alias = _decode_ts_string(match.group(1))
        canonical = _decode_ts_string(match.group(2))
        register(alias, canonical)
        register(canonical, canonical)

    for alias in NARRATION_SPEAKERS:
        register(alias, "旁白")
    if not candidates:
        raise RuntimeError(f"No speaker mappings parsed from {path}")
    return candidates


EXEDRA_ADDITIONAL_SPEAKER_ALIASES = {
    "いろはちゃん": "小彩羽",
    "美树さやか": "美树沙耶香",
    "美樹さやか": "美树沙耶香",
    "环いろは": "环彩羽",
    "環いろは": "环彩羽",
    "环うい": "环忧",
    "環うい": "环忧",
    "爱生まばゆ": "爱生眩",
    "愛生まばゆ": "爱生眩",
    "御园かりん": "御园花凛",
    "御園かりん": "御园花凛",
    "アシュリー": "阿什莉",
    "アルティメットまどか": "终极圆",
    "リズ・ホークウッド": "莉兹·霍克伍德",
    "リズ･ホークウッド": "莉兹·霍克伍德",
    "鹿目タツヤ": "鹿目达也",
    "人见リナ": "人见莉奈",
    "人見リナ": "人见莉奈",
    "キュぅべえ": "丘比",
    "キュゥべえたち": "丘比们",
    "キューブ": "丘布",
    "すみれの母": "堇的母亲",
    "すみれの父": "堇的父亲",
    "すみれの祖母": "堇的祖母",
    "なぎさの母": "渚的母亲",
    "まばゆの母": "眩的母亲",
    "みふゆの母": "美冬的母亲",
    "やちよの祖母": "八千代的祖母",
    "キリカの友人A": "纪里香的朋友A",
    "キリカの友人B": "纪里香的朋友B",
    "キリカの友人Ａ": "纪里香的朋友A",
    "キリカの友人Ｂ": "纪里香的朋友B",
    "呉キリカの友人A": "吴纪里香的朋友A",
    "呉キリカの友人B": "吴纪里香的朋友B",
    "呉キリカの友人Ａ": "吴纪里香的朋友A",
    "呉キリカの友人Ｂ": "吴纪里香的朋友B",
    "小乃花の元彼氏": "小乃花的前男友",
    "小乃花の友人": "小乃花的朋友",
    "幼いメリッサ": "幼年梅丽莎",
    "幼いメリッサ？": "幼年梅丽莎？",
    "過去のメリッサ？": "过去的梅丽莎？",
    "タルトの父": "塔鲁特的父亲",
    "タルトの母": "塔鲁特的母亲",
    "幼い織莉子": "幼年织莉子",
    "幼い织莉子": "幼年织莉子",
    "織莉子の母": "织莉子的母亲",
    "织莉子の母": "织莉子的母亲",
    "織莉子の伯父": "织莉子的伯父",
    "织莉子の伯父": "织莉子的伯父",
    "織莉子の父の手帳": "织莉子父亲的手账",
    "织莉子の父の手帐": "织莉子父亲的手账",
    "ウワサ小": "小型传闻",
    "チビ魔女": "小魔女",
    "チンピラＡ": "混混A",
    "チンピラＢ": "混混B",
    "チンピラA": "混混A",
    "チンピラB": "混混B",
    "ホストA": "男公关A",
    "ホストB": "男公关B",
    "ホストＡ": "男公关A",
    "ホストＢ": "男公关B",
    "女の子": "女孩",
    "男の子": "男孩",
    "子ども": "孩子",
    "不審な男": "可疑男子",
    "工場長の男": "工厂长",
    "工场长の男": "工厂长",
    "伪街の子供たち": "伪街的孩子们",
    "偽街の子供たち": "伪街的孩子们",
    "羊の魔女": "羊之魔女",
    "羊の魔女の使い魔": "羊之魔女的使魔",
    "振り子の魔女": "钟摆魔女",
    "蔷薇の魔女": "蔷薇魔女",
    "薔薇の魔女": "蔷薇魔女",
    "ハコの魔女の手下": "箱之魔女的手下",
    "うさぎのキーホルダー": "兔子钥匙扣",
    "キリカの使い魔たち": "纪里香的使魔们",
    "ひび割れたキリカのソウルジェム": "出现裂痕的纪里香灵魂宝石",
    "蒼海幇メンバーA": "苍海帮成员A",
    "蒼海幇メンバーB": "苍海帮成员B",
    "蒼海幇メンバーＡ": "苍海帮成员A",
    "蒼海幇メンバーＢ": "苍海帮成员B",
    "蒼海幇メンバーＣ": "苍海帮成员C",
    "蒼海幇メンバーＤ": "苍海帮成员D",
    "蒼海幇メンバーＥ": "苍海帮成员E",
    "蒼海幇メンバーＦ": "苍海帮成员F",
    "蒼海幇メンバーＧ": "苍海帮成员G",
    "蒼海幇メンバーＨ": "苍海帮成员H",
    "エイミー": "艾米",
    "オスヴァルト": "奥斯瓦尔德",
    "カトリーヌ": "卡特琳",
    "サントライユ": "桑特莱伊",
    "ザッバイ": "扎拜",
    "ナマエ": "名字",
    "フィリッポ·マリーア·ヴィスコンティ": "菲利波·马里亚·维斯康蒂",
    "フィリッポ・マリーア・ヴィスコンティ": "菲利波·马里亚·维斯康蒂",
    "ベベ": "贝贝",
    "マチビト馬": "待人马",
    "ラ·イル": "拉·海尔",
    "ラ・イル": "拉·海尔",
}
EXEDRA_ADDITIONAL_SPEAKER_LOOKUP = {
    speaker_lookup_key(key): value
    for key, value in EXEDRA_ADDITIONAL_SPEAKER_ALIASES.items()
}
EXEDRA_RELATION_SUFFIXES = (
    ("の父の手帳", "父亲的手账"),
    ("の父の手帐", "父亲的手账"),
    ("の使い魔たち", "的使魔们"),
    ("の子供たち", "的孩子们"),
    ("の元彼氏", "的前男友"),
    ("のキーホルダー", "的钥匙扣"),
    ("のソウルジェム", "的灵魂宝石"),
    ("のメッセージ", "的信息"),
    ("の友人Ａ", "的朋友A"),
    ("の友人Ｂ", "的朋友B"),
    ("の友人A", "的朋友A"),
    ("の友人B", "的朋友B"),
    ("の使い魔", "的使魔"),
    ("の祖母", "的祖母"),
    ("の伯父", "的伯父"),
    ("の手下", "的手下"),
    ("の母", "的母亲"),
    ("の父", "的父亲"),
    ("の友人", "的朋友"),
    ("の魔女", "之魔女"),
    ("の声", "的声音"),
    ("の歌", "的歌"),
)


def _translate_speaker_component(
    value: str,
    mapping: dict[str, str],
) -> str:
    normalized = normalize_display_punctuation(value)
    key = speaker_lookup_key(normalized)
    direct = mapping.get(key) or EXEDRA_ADDITIONAL_SPEAKER_LOOKUP.get(key)
    if direct is not None:
        return direct

    punctuation = ""
    while normalized and normalized[-1] in "?？!！":
        punctuation = normalized[-1] + punctuation
        normalized = normalized[:-1]
    if punctuation:
        translated = _translate_speaker_component(normalized, mapping)
        if translated != normalized:
            return translated + punctuation

    for prefix, replacement in (
        ("ひび割れた", "出现裂痕的"),
        ("過去の", "过去的"),
        ("幼い", "幼年"),
    ):
        if normalized.startswith(prefix) and len(normalized) > len(prefix):
            return replacement + _translate_speaker_component(
                normalized[len(prefix):],
                mapping,
            )

    for suffix, replacement in EXEDRA_RELATION_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            return (
                _translate_speaker_component(
                    normalized[:-len(suffix)],
                    mapping,
                )
                + replacement
            )

    if normalized.endswith("たち") and len(normalized) > 2:
        return _translate_speaker_component(normalized[:-2], mapping) + "们"

    compact = speaker_lookup_key(normalized)
    # Replace only dictionary aliases that contain Japanese kana. This repairs
    # mixed official labels such as 美树さやか without touching ordinary Chinese.
    for alias in sorted(mapping, key=len, reverse=True):
        if alias == compact or len(alias) < 2 or JAPANESE_SCRIPT_RE.search(alias) is None:
            continue
        replacement = mapping[alias]
        if JAPANESE_SCRIPT_RE.search(replacement) is not None:
            continue
        if alias in compact:
            compact = compact.replace(alias, replacement)
    compact = (
        compact
        .replace("メンバー", "成员")
        .replace("キーホルダー", "钥匙扣")
        .replace("ソウルジェム", "灵魂宝石")
        .replace("使い魔", "使魔")
        .replace("子供", "孩子")
        .replace("子ども", "孩子")
        .replace("友人", "朋友")
        .replace("手帳", "手账")
        .replace("の", "的")
    )
    final_key = speaker_lookup_key(compact)
    return (
        mapping.get(final_key)
        or EXEDRA_ADDITIONAL_SPEAKER_LOOKUP.get(final_key)
        or compact
    )


def translate_speaker(value: str, mapping: dict[str, str]) -> str:
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


def contains_japanese_script(value: str) -> bool:
    return JAPANESE_SCRIPT_RE.search(value) is not None


def _header_indices(sheet: dict[str, Any]) -> dict[str, int]:
    header = sheet.get("headerRow")
    cells = header.get("cellList") if isinstance(header, dict) else None
    if not isinstance(cells, list):
        return {}
    names = [str(value or "").strip().casefold() for value in cells]
    return {name: index for index, name in enumerate(names) if name}


def _cell(cells: list[Any], index: int | None) -> Any:
    if index is None or index < 0 or index >= len(cells):
        return ""
    return cells[index]


def extract_text_events(document: dict[str, Any]) -> list[dict[str, Any]]:
    sheets = document.get("sheetList")
    if not isinstance(sheets, list):
        raise RuntimeError("Exedra JSON is missing sheetList")

    result: list[dict[str, Any]] = []
    fingerprints: set[str] = set()
    for sheet_index, sheet in enumerate(sheets):
        if not isinstance(sheet, dict):
            continue
        indices = _header_indices(sheet)
        action_index = indices.get("actiontype")
        comment_index = indices.get("comment")
        name_index = indices.get("name")
        rows = sheet.get("contentRowList")
        if action_index is None or comment_index is None or not isinstance(rows, list):
            continue

        sheet_rows: list[dict[str, Any]] = []
        for fallback_row, row in enumerate(rows, start=2):
            cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(cells, list):
                continue
            action = str(_cell(cells, action_index) or "").strip()
            comment = _cell(cells, comment_index)
            if (
                action.casefold() not in TEXT_ACTIONS
                or not isinstance(comment, str)
                or not comment.strip()
            ):
                continue
            speaker = str(_cell(cells, name_index) or "").strip()
            sheet_rows.append(
                {
                    "sheet_index": sheet_index,
                    "row_number": (
                        row.get("rowNumber", fallback_row)
                        if isinstance(row, dict)
                        else fallback_row
                    ),
                    "action": action,
                    "speaker": speaker,
                    "text": comment.strip(),
                }
            )

        fingerprint = json.dumps(
            [
                (item["action"], item["speaker"], item["text"])
                for item in sheet_rows
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if fingerprint in fingerprints:
            continue
        fingerprints.add(fingerprint)
        result.extend(sheet_rows)
    return result


def _text_sheet_groups(
    document: dict[str, Any],
) -> list[tuple[list[tuple[list[Any], int]], list[list[tuple[list[Any], int]]]]]:
    groups: list[
        tuple[list[tuple[list[Any], int]], list[list[tuple[list[Any], int]]]]
    ] = []
    fingerprints: dict[str, int] = {}
    sheets = document.get("sheetList")
    if not isinstance(sheets, list):
        raise RuntimeError("Exedra JSON is missing sheetList")
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        indices = _header_indices(sheet)
        action_index = indices.get("actiontype")
        comment_index = indices.get("comment")
        name_index = indices.get("name")
        rows = sheet.get("contentRowList")
        if action_index is None or comment_index is None or not isinstance(rows, list):
            continue
        refs: list[tuple[list[Any], int]] = []
        fingerprint_rows: list[tuple[str, str, str]] = []
        for row in rows:
            cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(cells, list):
                continue
            action = str(_cell(cells, action_index) or "").strip()
            comment = _cell(cells, comment_index)
            if (
                action.casefold() not in TEXT_ACTIONS
                or not isinstance(comment, str)
                or not comment.strip()
            ):
                continue
            speaker = str(_cell(cells, name_index) or "").strip()
            refs.append((cells, comment_index))
            fingerprint_rows.append((action, speaker, comment.strip()))
        if not refs:
            continue
        fingerprint = json.dumps(
            fingerprint_rows,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        previous = fingerprints.get(fingerprint)
        if previous is None:
            fingerprints[fingerprint] = len(groups)
            groups.append((refs, []))
        else:
            groups[previous][1].append(refs)
    return groups


def _canonicalize_name_cells(
    document: dict[str, Any],
    mapping: dict[str, str],
    *,
    convert: Callable[[str], str] | None = None,
) -> tuple[int, int]:
    total = 0
    changed = 0
    sheets = document.get("sheetList")
    if not isinstance(sheets, list):
        raise RuntimeError("Exedra JSON is missing sheetList")
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        name_index = _header_indices(sheet).get("name")
        rows = sheet.get("contentRowList")
        if name_index is None or not isinstance(rows, list):
            continue
        for row in rows:
            cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(cells, list) or name_index >= len(cells):
                continue
            value = cells[name_index]
            if not isinstance(value, str) or not value:
                continue
            total += 1
            converted = convert(value) if convert is not None else value
            canonical = translate_speaker(converted, mapping)
            if canonical != value:
                changed += 1
                cells[name_index] = canonical
    return total, changed


def materialize_tw_json(
    source: Path,
    destination: Path,
    convert: Callable[[str], str],
    mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Copy authentic TW JSON and localize only Name/playable Comment cells."""

    speaker_map = mapping or load_name_translation_map()
    document = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict):
        raise RuntimeError(f"TW JSON root is not an object: {source}")
    original = copy.deepcopy(document)
    original_events = extract_text_events(original)
    name_cells, name_changes = _canonicalize_name_cells(
        document,
        speaker_map,
        convert=convert,
    )

    comment_cells = 0
    comment_changes = 0
    sheets = document.get("sheetList")
    if not isinstance(sheets, list):
        raise RuntimeError(f"TW JSON is missing sheetList: {source}")
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        indices = _header_indices(sheet)
        action_index = indices.get("actiontype")
        comment_index = indices.get("comment")
        rows = sheet.get("contentRowList")
        if action_index is None or comment_index is None or not isinstance(rows, list):
            continue
        for row in rows:
            cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(cells, list):
                continue
            action = str(_cell(cells, action_index) or "").strip().casefold()
            if action not in TEXT_ACTIONS or comment_index >= len(cells):
                continue
            value = cells[comment_index]
            if not isinstance(value, str) or not value:
                continue
            comment_cells += 1
            converted = convert(value)
            if converted != value:
                comment_changes += 1
                cells[comment_index] = converted

    localized_events = extract_text_events(document)
    if len(localized_events) != len(original_events):
        raise RuntimeError(
            f"TW event count changed while localizing {source.name}: "
            f"{len(original_events)} -> {len(localized_events)}"
        )

    original_sheets = original.get("sheetList")
    localized_sheets = document.get("sheetList")
    if (
        not isinstance(original_sheets, list)
        or not isinstance(localized_sheets, list)
        or len(original_sheets) != len(localized_sheets)
    ):
        raise RuntimeError(f"TW sheetList changed while localizing {source.name}")
    for sheet_index, (before_sheet, after_sheet) in enumerate(
        zip(original_sheets, localized_sheets),
        start=1,
    ):
        if not isinstance(before_sheet, dict) or not isinstance(after_sheet, dict):
            if before_sheet != after_sheet:
                raise RuntimeError(
                    f"TW sheet changed at {source.name} sheet {sheet_index}"
                )
            continue
        before_indices = _header_indices(before_sheet)
        after_indices = _header_indices(after_sheet)
        if before_indices != after_indices:
            raise RuntimeError(
                f"TW headers changed at {source.name} sheet {sheet_index}"
            )
        before_rows = before_sheet.get("contentRowList")
        after_rows = after_sheet.get("contentRowList")
        if (
            not isinstance(before_rows, list)
            or not isinstance(after_rows, list)
            or len(before_rows) != len(after_rows)
        ):
            raise RuntimeError(
                f"TW row count changed at {source.name} sheet {sheet_index}"
            )
        name_index = before_indices.get("name")
        action_index = before_indices.get("actiontype")
        comment_index = before_indices.get("comment")
        for row_index, (before_row, after_row) in enumerate(
            zip(before_rows, after_rows),
            start=1,
        ):
            before_cells = (
                before_row.get("cellList")
                if isinstance(before_row, dict)
                else None
            )
            after_cells = (
                after_row.get("cellList")
                if isinstance(after_row, dict)
                else None
            )
            if not isinstance(before_cells, list) or not isinstance(after_cells, list):
                if before_row != after_row:
                    raise RuntimeError(
                        f"TW row changed at {source.name} "
                        f"sheet {sheet_index} row {row_index}"
                    )
                continue
            if len(before_cells) != len(after_cells):
                raise RuntimeError(
                    f"TW cell count changed at {source.name} "
                    f"sheet {sheet_index} row {row_index}"
                )
            if name_index is not None and name_index < len(before_cells):
                before_name = before_cells[name_index]
                after_name = after_cells[name_index]
                expected_name = (
                    translate_speaker(convert(before_name), speaker_map)
                    if isinstance(before_name, str) and before_name
                    else before_name
                )
                if after_name != expected_name:
                    raise RuntimeError(
                        "TW Name was not canonicalized exactly at "
                        f"{source.name} sheet {sheet_index} row {row_index}: "
                        f"before={before_name!r} expected={expected_name!r} "
                        f"after={after_name!r}"
                    )
            action = (
                str(before_cells[action_index] or "").strip().casefold()
                if action_index is not None and action_index < len(before_cells)
                else ""
            )
            if (
                action in TEXT_ACTIONS
                and comment_index is not None
                and comment_index < len(before_cells)
            ):
                before_comment = before_cells[comment_index]
                after_comment = after_cells[comment_index]
                expected_comment = (
                    convert(before_comment)
                    if isinstance(before_comment, str) and before_comment
                    else before_comment
                )
                if after_comment != expected_comment:
                    raise RuntimeError(
                        "TW playable Comment was not simplified exactly at "
                        f"{source.name} sheet {sheet_index} row {row_index}"
                    )

    before_redacted = copy.deepcopy(original)
    after_redacted = copy.deepcopy(document)
    _redact_localized_fields(before_redacted)
    _redact_localized_fields(after_redacted)
    if before_redacted != after_redacted:
        raise RuntimeError(
            f"TW localization changed fields outside Name/playable Comment: {source.name}"
        )

    encoded = json_bytes(document)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encoded)
    return {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "eventCount": len(localized_events),
        "nameCells": name_cells,
        "nameChanges": name_changes,
        "commentCells": comment_cells,
        "commentChanges": comment_changes,
    }


def materialize_human_json(
    jp_json: Path,
    texts: Sequence[str],
    destination: Path,
    mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Use JP playback structure while canonicalizing Name and replacing Comment."""

    speaker_map = mapping or load_name_translation_map()
    document = json.loads(jp_json.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict):
        raise RuntimeError(f"JP JSON root is not an object: {jp_json}")
    groups = _text_sheet_groups(document)
    flattened = [ref for refs, _duplicates in groups for ref in refs]
    if len(flattened) != len(texts):
        raise RuntimeError(
            f"JP JSON/human text event count differs: {jp_json.name}: "
            f"JSON={len(flattened)} translated={len(texts)}"
        )
    name_cells, name_changes = _canonicalize_name_cells(document, speaker_map)
    offset = 0
    for refs, duplicates in groups:
        segment = list(texts[offset : offset + len(refs)])
        if any(not str(text).strip() for text in segment):
            raise RuntimeError(f"Human translation contains empty text: {jp_json.name}")
        for target_refs in [refs, *duplicates]:
            if len(target_refs) != len(segment):
                raise RuntimeError(f"Duplicate sheet structure differs: {jp_json.name}")
            for (cells, comment_index), text in zip(target_refs, segment):
                cells[comment_index] = str(text)
        offset += len(refs)

    encoded = json_bytes(document)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encoded)
    return {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "eventCount": len(texts),
        "nameCells": name_cells,
        "nameChanges": name_changes,
    }


def _redact_localized_fields(document: dict[str, Any]) -> tuple[int, int]:
    name_cells = 0
    comment_cells = 0
    sheets = document.get("sheetList")
    if not isinstance(sheets, list):
        raise RuntimeError("Exedra JSON is missing sheetList")
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        indices = _header_indices(sheet)
        name_index = indices.get("name")
        action_index = indices.get("actiontype")
        comment_index = indices.get("comment")
        rows = sheet.get("contentRowList")
        if not isinstance(rows, list):
            continue
        for row in rows:
            cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(cells, list):
                continue
            if name_index is not None and name_index < len(cells):
                if isinstance(cells[name_index], str) and cells[name_index]:
                    name_cells += 1
                    cells[name_index] = "__MAGIREADER_LOCALIZED_NAME__"
            if action_index is None or comment_index is None:
                continue
            action = str(_cell(cells, action_index) or "").strip().casefold()
            value = _cell(cells, comment_index)
            if (
                action in TEXT_ACTIONS
                and isinstance(value, str)
                and value.strip()
                and comment_index < len(cells)
            ):
                comment_cells += 1
                cells[comment_index] = "__MAGIREADER_LOCALIZED_COMMENT__"
    return name_cells, comment_cells


def validate_human_json(
    jp_json: Path,
    cn_json: Path,
    expected_texts: Sequence[str],
    mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    speaker_map = mapping or load_name_translation_map()
    jp_document = json.loads(jp_json.read_text(encoding="utf-8-sig"))
    cn_document = json.loads(cn_json.read_text(encoding="utf-8-sig"))
    if not isinstance(jp_document, dict) or not isinstance(cn_document, dict):
        raise RuntimeError(f"Exedra JSON root is not an object: {jp_json.name}")

    jp_redacted = copy.deepcopy(jp_document)
    cn_redacted = copy.deepcopy(cn_document)
    jp_names, jp_comments = _redact_localized_fields(jp_redacted)
    cn_names, cn_comments = _redact_localized_fields(cn_redacted)
    if (jp_names, jp_comments) != (cn_names, cn_comments):
        raise RuntimeError(f"Localized cell counts differ: {jp_json.name}")
    if jp_redacted != cn_redacted:
        raise RuntimeError(
            f"Human-localized JSON changed fields outside Name/Comment: {jp_json.name}"
        )
    cn_rows = extract_text_events(cn_document)
    actual_texts = [str(row.get("text") or "") for row in cn_rows]
    if actual_texts != list(expected_texts):
        raise RuntimeError(f"Human Comment sequence differs: {jp_json.name}")
    for row in cn_rows:
        speaker = str(row.get("speaker") or "")
        if speaker and translate_speaker(speaker, speaker_map) != speaker:
            raise RuntimeError(f"CN JSON contains a noncanonical Name: {speaker}")
    return {
        "nonLocalizedFieldsMatch": True,
        "canonicalNameFields": True,
        "playableCommentSequenceMatches": True,
        "mutableNameCellCount": cn_names,
        "mutableCommentCellCount": cn_comments,
        "canonicalEventCount": len(actual_texts),
    }


def localize_events(
    tw_rows: Sequence[dict[str, Any]],
    jp_lines: Sequence[Any],
    convert: Callable[[str], str],
    speaker_map: dict[str, str],
) -> tuple[list[LocalizedEvent], dict[str, int]]:
    if len(tw_rows) != len(jp_lines):
        raise RuntimeError(
            f"TW/JP event count mismatch: {len(tw_rows)} != {len(jp_lines)}"
        )
    events: list[LocalizedEvent] = []
    stats = {
        "officialTwSpeakerEvents": 0,
        "dictionaryFallbackSpeakerEvents": 0,
        "narrationSpeakerEvents": 0,
    }
    for index, (row, jp_line) in enumerate(zip(tw_rows, jp_lines), start=1):
        action = str(row.get("action") or "").strip()
        text = convert(str(row.get("text") or "").strip())
        if not text:
            raise RuntimeError(f"TW event {index} has empty localized text")
        source_speaker = convert(str(row.get("speaker") or "").strip())
        if source_speaker:
            speaker = translate_speaker(source_speaker, speaker_map)
            stats["officialTwSpeakerEvents"] += 1
        elif action.casefold() in {"narration", "onlytext"}:
            speaker = "旁白"
            stats["narrationSpeakerEvents"] += 1
        else:
            fallback = str(getattr(jp_line, "speaker", "") or "旁白")
            speaker = translate_speaker(fallback, speaker_map)
            stats["dictionaryFallbackSpeakerEvents"] += 1
        events.append(
            LocalizedEvent(
                speaker=speaker or "旁白",
                text=text,
                action=action,
                sheet_index=int(row.get("sheet_index") or 0),
                row_number=row.get("row_number"),
            )
        )
    return events, stats


def _escape_text(value: str) -> str:
    return (
        str(value).strip()
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", r"\n")
    )


def render_human_cn(
    sections: Sequence[Any],
    translated: Sequence[Sequence[str]],
    mapping: dict[str, str] | None = None,
) -> str:
    speaker_map = mapping or load_name_translation_map()
    if len(sections) != len(translated):
        raise RuntimeError("Section count differs")
    output: list[str] = []
    for section, texts in zip(sections, translated):
        lines = getattr(section, "lines", ())
        if len(lines) != len(texts):
            raise RuntimeError(f"Section {section.number} event count differs")
        output.append(
            f"--- [Section {section.number}] (Source: {section.source}) ---"
        )
        for jp_line, text in zip(lines, texts):
            speaker = translate_speaker(
                str(getattr(jp_line, "speaker", "") or "旁白"),
                speaker_map,
            )
            escaped = _escape_text(str(text))
            if not escaped:
                raise RuntimeError(f"Section {section.number} contains empty text")
            output.append(f"{speaker}：{escaped}")
        output.append("")
    return "\n".join(output).strip() + "\n"


def canonicalize_txt_text(
    content: str,
    mapping: dict[str, str],
) -> tuple[str, int, set[str]]:
    normalized = content.removeprefix("\ufeff").replace("\r\n", "\n").replace(
        "\r", "\n"
    )
    output: list[str] = []
    changes = 0
    remaining_japanese: set[str] = set()
    for raw_line in normalized.split("\n"):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("---"):
            output.append(raw_line)
            continue
        match = SPEAKER_SEPARATOR_RE.search(raw_line)
        if match is None or match.start() <= 0 or match.start() > 96:
            output.append(raw_line)
            continue
        prefix = raw_line[: match.start()]
        leading = prefix[: len(prefix) - len(prefix.lstrip())]
        speaker = prefix.strip()
        canonical = translate_speaker(speaker, mapping)
        if canonical != speaker:
            changes += 1
        if contains_japanese_script(canonical):
            remaining_japanese.add(canonical)
        output.append(leading + canonical + raw_line[match.start() :])
    result = "\n".join(output)
    if normalized.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result, changes, remaining_japanese


def canonicalize_txt_path(
    path: Path,
    mapping: dict[str, str],
) -> tuple[int, set[str]]:
    original = path.read_text(encoding="utf-8-sig")
    updated, changes, remaining = canonicalize_txt_text(original, mapping)
    normalized_original = original.removeprefix("\ufeff").replace(
        "\r\n", "\n"
    ).replace("\r", "\n")
    if updated != normalized_original:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return changes, remaining


def canonicalize_json_names_path(
    path: Path,
    mapping: dict[str, str],
) -> tuple[int, int]:
    """Canonicalize every Name column cell and report unresolved kana.

    Exedra uses Name on Put/Disp and other non-dialogue rows as well as on
    playable Talk/Narration rows.  Those cells are part of the published
    Chinese scenario JSON and must follow the same dictionary contract.
    """

    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict):
        raise RuntimeError(f"Exedra JSON root is not an object: {path}")

    changes = 0
    remaining = 0
    sheets = document.get("sheetList")
    if not isinstance(sheets, list):
        raise RuntimeError(f"Exedra JSON is missing sheetList: {path}")

    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        name_index = _header_indices(sheet).get("name")
        rows = sheet.get("contentRowList")
        if name_index is None or not isinstance(rows, list):
            continue
        for row in rows:
            cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(cells, list) or name_index >= len(cells):
                continue
            value = cells[name_index]
            if not isinstance(value, str) or not value.strip():
                continue
            canonical = translate_speaker(value, mapping)
            if canonical != value:
                cells[name_index] = canonical
                changes += 1
            if contains_japanese_script(canonical):
                remaining += 1

    if changes:
        path.write_bytes(json_bytes(document))
    return changes, remaining

def dictionary_sha256(path: Path = DEFAULT_DICTIONARY) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
