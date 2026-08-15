#!/usr/bin/env python3
"""Second-stage repair for authentic TW data and canonical Exedra speakers."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED_MODULE = '#!/usr/bin/env python3\n"""Canonical Exedra speaker localization and safe JSON/TXT materialization."""\nfrom __future__ import annotations\n\nimport copy\nimport hashlib\nimport json\nimport re\nimport unicodedata\nfrom dataclasses import dataclass\nfrom pathlib import Path\nfrom typing import Any, Callable, Sequence\n\nROOT = Path(__file__).resolve().parents[1]\nDEFAULT_DICTIONARY = ROOT / "website/app/config/dictionary.ts"\nTEXT_ACTIONS = frozenset({"talk", "narration", "charactertalk", "onlytext"})\nNARRATION_SPEAKERS = frozenset(\n    {"Narration", "ナレーション", "旁白", "旁白（无角色）"}\n)\nTS_PAIR_RE = re.compile(r\'"((?:\\\\.|[^"\\\\])*)"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"\')\nMULTI_SPEAKER_RE = re.compile(r"\\s*[＆&]\\s*")\nSPEAKER_SEPARATOR_RE = re.compile(r"[:：﹕︰︓]")\nJAPANESE_SCRIPT_RE = re.compile(r"[\\u3040-\\u30ff]")\n\n\n@dataclass(frozen=True)\nclass LocalizedEvent:\n    speaker: str\n    text: str\n    action: str\n    sheet_index: int\n    row_number: Any\n\n\ndef json_bytes(value: Any) -> bytes:\n    return (json.dumps(value, ensure_ascii=False, indent=2) + "\\n").encode("utf-8")\n\n\ndef _decode_ts_string(value: str) -> str:\n    return json.loads(f\'"{value}"\')\n\n\ndef normalize_speaker(value: str) -> str:\n    return (\n        unicodedata.normalize("NFC", str(value))\n        .replace("\\u0000", "")\n        .replace("\\ufeff", "")\n        .strip()\n    )\n\n\ndef normalize_display_punctuation(value: str) -> str:\n    return re.sub(r"[・･‧•．]", "·", normalize_speaker(value))\n\n\ndef speaker_lookup_key(value: str) -> str:\n    return re.sub(\n        r"[ \\t\\u3000]+",\n        "",\n        normalize_display_punctuation(value),\n    )\n\n\ndef load_name_translation_map(path: Path = DEFAULT_DICTIONARY) -> dict[str, str]:\n    source = path.read_text(encoding="utf-8-sig")\n    marker = "export const NAME_TRANSLATE_MAP"\n    start = source.find(marker)\n    end = source.find("\\n};", start)\n    if start < 0 or end < 0:\n        raise RuntimeError(f"NAME_TRANSLATE_MAP is missing or unterminated: {path}")\n\n    candidates: dict[str, str] = {}\n    ambiguous: set[str] = set()\n\n    def register(alias: str, canonical: str) -> None:\n        key = speaker_lookup_key(alias)\n        canonical = normalize_display_punctuation(canonical)\n        if not key or not canonical or key in ambiguous:\n            return\n        previous = candidates.get(key)\n        if previous is not None and previous != canonical:\n            candidates.pop(key, None)\n            ambiguous.add(key)\n            return\n        candidates[key] = canonical\n\n    for match in TS_PAIR_RE.finditer(source[start:end]):\n        alias = _decode_ts_string(match.group(1))\n        canonical = _decode_ts_string(match.group(2))\n        register(alias, canonical)\n        register(canonical, canonical)\n\n    for alias in NARRATION_SPEAKERS:\n        register(alias, "旁白")\n    if not candidates:\n        raise RuntimeError(f"No speaker mappings parsed from {path}")\n    return candidates\n\n\ndef translate_speaker(value: str, mapping: dict[str, str]) -> str:\n    normalized = normalize_display_punctuation(value)\n    if not normalized or normalized in NARRATION_SPEAKERS:\n        return "旁白"\n    parts = tuple(part for part in MULTI_SPEAKER_RE.split(normalized) if part)\n    if len(parts) > 1:\n        return "＆".join(translate_speaker(part, mapping) for part in parts)\n    return mapping.get(speaker_lookup_key(normalized), normalized)\n\n\ndef contains_japanese_script(value: str) -> bool:\n    return JAPANESE_SCRIPT_RE.search(value) is not None\n\n\ndef _header_indices(sheet: dict[str, Any]) -> dict[str, int]:\n    header = sheet.get("headerRow")\n    cells = header.get("cellList") if isinstance(header, dict) else None\n    if not isinstance(cells, list):\n        return {}\n    names = [str(value or "").strip().casefold() for value in cells]\n    return {name: index for index, name in enumerate(names) if name}\n\n\ndef _cell(cells: list[Any], index: int | None) -> Any:\n    if index is None or index < 0 or index >= len(cells):\n        return ""\n    return cells[index]\n\n\ndef extract_text_events(document: dict[str, Any]) -> list[dict[str, Any]]:\n    sheets = document.get("sheetList")\n    if not isinstance(sheets, list):\n        raise RuntimeError("Exedra JSON is missing sheetList")\n\n    result: list[dict[str, Any]] = []\n    fingerprints: set[str] = set()\n    for sheet_index, sheet in enumerate(sheets):\n        if not isinstance(sheet, dict):\n            continue\n        indices = _header_indices(sheet)\n        action_index = indices.get("actiontype")\n        comment_index = indices.get("comment")\n        name_index = indices.get("name")\n        rows = sheet.get("contentRowList")\n        if action_index is None or comment_index is None or not isinstance(rows, list):\n            continue\n\n        sheet_rows: list[dict[str, Any]] = []\n        for fallback_row, row in enumerate(rows, start=2):\n            cells = row.get("cellList") if isinstance(row, dict) else None\n            if not isinstance(cells, list):\n                continue\n            action = str(_cell(cells, action_index) or "").strip()\n            comment = _cell(cells, comment_index)\n            if (\n                action.casefold() not in TEXT_ACTIONS\n                or not isinstance(comment, str)\n                or not comment.strip()\n            ):\n                continue\n            speaker = str(_cell(cells, name_index) or "").strip()\n            sheet_rows.append(\n                {\n                    "sheet_index": sheet_index,\n                    "row_number": (\n                        row.get("rowNumber", fallback_row)\n                        if isinstance(row, dict)\n                        else fallback_row\n                    ),\n                    "action": action,\n                    "speaker": speaker,\n                    "text": comment.strip(),\n                }\n            )\n\n        fingerprint = json.dumps(\n            [\n                (item["action"], item["speaker"], item["text"])\n                for item in sheet_rows\n            ],\n            ensure_ascii=False,\n            separators=(",", ":"),\n        )\n        if fingerprint in fingerprints:\n            continue\n        fingerprints.add(fingerprint)\n        result.extend(sheet_rows)\n    return result\n\n\ndef _text_sheet_groups(\n    document: dict[str, Any],\n) -> list[tuple[list[tuple[list[Any], int]], list[list[tuple[list[Any], int]]]]]:\n    groups: list[\n        tuple[list[tuple[list[Any], int]], list[list[tuple[list[Any], int]]]]\n    ] = []\n    fingerprints: dict[str, int] = {}\n    sheets = document.get("sheetList")\n    if not isinstance(sheets, list):\n        raise RuntimeError("Exedra JSON is missing sheetList")\n    for sheet in sheets:\n        if not isinstance(sheet, dict):\n            continue\n        indices = _header_indices(sheet)\n        action_index = indices.get("actiontype")\n        comment_index = indices.get("comment")\n        name_index = indices.get("name")\n        rows = sheet.get("contentRowList")\n        if action_index is None or comment_index is None or not isinstance(rows, list):\n            continue\n        refs: list[tuple[list[Any], int]] = []\n        fingerprint_rows: list[tuple[str, str, str]] = []\n        for row in rows:\n            cells = row.get("cellList") if isinstance(row, dict) else None\n            if not isinstance(cells, list):\n                continue\n            action = str(_cell(cells, action_index) or "").strip()\n            comment = _cell(cells, comment_index)\n            if (\n                action.casefold() not in TEXT_ACTIONS\n                or not isinstance(comment, str)\n                or not comment.strip()\n            ):\n                continue\n            speaker = str(_cell(cells, name_index) or "").strip()\n            refs.append((cells, comment_index))\n            fingerprint_rows.append((action, speaker, comment.strip()))\n        if not refs:\n            continue\n        fingerprint = json.dumps(\n            fingerprint_rows,\n            ensure_ascii=False,\n            separators=(",", ":"),\n        )\n        previous = fingerprints.get(fingerprint)\n        if previous is None:\n            fingerprints[fingerprint] = len(groups)\n            groups.append((refs, []))\n        else:\n            groups[previous][1].append(refs)\n    return groups\n\n\ndef _canonicalize_name_cells(\n    document: dict[str, Any],\n    mapping: dict[str, str],\n    *,\n    convert: Callable[[str], str] | None = None,\n) -> tuple[int, int]:\n    total = 0\n    changed = 0\n    sheets = document.get("sheetList")\n    if not isinstance(sheets, list):\n        raise RuntimeError("Exedra JSON is missing sheetList")\n    for sheet in sheets:\n        if not isinstance(sheet, dict):\n            continue\n        name_index = _header_indices(sheet).get("name")\n        rows = sheet.get("contentRowList")\n        if name_index is None or not isinstance(rows, list):\n            continue\n        for row in rows:\n            cells = row.get("cellList") if isinstance(row, dict) else None\n            if not isinstance(cells, list) or name_index >= len(cells):\n                continue\n            value = cells[name_index]\n            if not isinstance(value, str) or not value:\n                continue\n            total += 1\n            converted = convert(value) if convert is not None else value\n            canonical = translate_speaker(converted, mapping)\n            if canonical != value:\n                changed += 1\n                cells[name_index] = canonical\n    return total, changed\n\n\ndef materialize_tw_json(\n    source: Path,\n    destination: Path,\n    convert: Callable[[str], str],\n    mapping: dict[str, str] | None = None,\n) -> dict[str, Any]:\n    """Copy authentic TW JSON and localize only Name/playable Comment cells."""\n\n    speaker_map = mapping or load_name_translation_map()\n    document = json.loads(source.read_text(encoding="utf-8-sig"))\n    if not isinstance(document, dict):\n        raise RuntimeError(f"TW JSON root is not an object: {source}")\n    original = copy.deepcopy(document)\n    original_events = extract_text_events(original)\n    name_cells, name_changes = _canonicalize_name_cells(\n        document,\n        speaker_map,\n        convert=convert,\n    )\n\n    comment_cells = 0\n    comment_changes = 0\n    sheets = document.get("sheetList")\n    if not isinstance(sheets, list):\n        raise RuntimeError(f"TW JSON is missing sheetList: {source}")\n    for sheet in sheets:\n        if not isinstance(sheet, dict):\n            continue\n        indices = _header_indices(sheet)\n        action_index = indices.get("actiontype")\n        comment_index = indices.get("comment")\n        rows = sheet.get("contentRowList")\n        if action_index is None or comment_index is None or not isinstance(rows, list):\n            continue\n        for row in rows:\n            cells = row.get("cellList") if isinstance(row, dict) else None\n            if not isinstance(cells, list):\n                continue\n            action = str(_cell(cells, action_index) or "").strip().casefold()\n            if action not in TEXT_ACTIONS or comment_index >= len(cells):\n                continue\n            value = cells[comment_index]\n            if not isinstance(value, str) or not value:\n                continue\n            comment_cells += 1\n            converted = convert(value)\n            if converted != value:\n                comment_changes += 1\n                cells[comment_index] = converted\n\n    localized_events = extract_text_events(document)\n    if len(localized_events) != len(original_events):\n        raise RuntimeError(\n            f"TW event count changed while localizing {source.name}: "\n            f"{len(original_events)} -> {len(localized_events)}"\n        )\n    for index, (before, after) in enumerate(\n        zip(original_events, localized_events), start=1\n    ):\n        before_structure = (\n            before["sheet_index"],\n            before["row_number"],\n            str(before["action"]).casefold(),\n        )\n        after_structure = (\n            after["sheet_index"],\n            after["row_number"],\n            str(after["action"]).casefold(),\n        )\n        if before_structure != after_structure:\n            raise RuntimeError(\n                f"TW event structure changed at {source.name} event {index}"\n            )\n        if after["text"] != convert(str(before["text"])):\n            raise RuntimeError(\n                f"TW Comment was not simplified exactly at {source.name} event {index}"\n            )\n        expected_speaker = (\n            translate_speaker(convert(str(before["speaker"])), speaker_map)\n            if str(before["speaker"]).strip()\n            else ""\n        )\n        if after["speaker"] != expected_speaker:\n            raise RuntimeError(\n                f"TW Name was not canonicalized exactly at {source.name} event {index}"\n            )\n\n    encoded = json_bytes(document)\n    destination.parent.mkdir(parents=True, exist_ok=True)\n    destination.write_bytes(encoded)\n    return {\n        "sha256": hashlib.sha256(encoded).hexdigest(),\n        "eventCount": len(localized_events),\n        "nameCells": name_cells,\n        "nameChanges": name_changes,\n        "commentCells": comment_cells,\n        "commentChanges": comment_changes,\n    }\n\n\ndef materialize_human_json(\n    jp_json: Path,\n    texts: Sequence[str],\n    destination: Path,\n    mapping: dict[str, str] | None = None,\n) -> dict[str, Any]:\n    """Use JP playback structure while canonicalizing Name and replacing Comment."""\n\n    speaker_map = mapping or load_name_translation_map()\n    document = json.loads(jp_json.read_text(encoding="utf-8-sig"))\n    if not isinstance(document, dict):\n        raise RuntimeError(f"JP JSON root is not an object: {jp_json}")\n    groups = _text_sheet_groups(document)\n    flattened = [ref for refs, _duplicates in groups for ref in refs]\n    if len(flattened) != len(texts):\n        raise RuntimeError(\n            f"JP JSON/human text event count differs: {jp_json.name}: "\n            f"JSON={len(flattened)} translated={len(texts)}"\n        )\n    name_cells, name_changes = _canonicalize_name_cells(document, speaker_map)\n    offset = 0\n    for refs, duplicates in groups:\n        segment = list(texts[offset : offset + len(refs)])\n        if any(not str(text).strip() for text in segment):\n            raise RuntimeError(f"Human translation contains empty text: {jp_json.name}")\n        for target_refs in [refs, *duplicates]:\n            if len(target_refs) != len(segment):\n                raise RuntimeError(f"Duplicate sheet structure differs: {jp_json.name}")\n            for (cells, comment_index), text in zip(target_refs, segment):\n                cells[comment_index] = str(text)\n        offset += len(refs)\n\n    encoded = json_bytes(document)\n    destination.parent.mkdir(parents=True, exist_ok=True)\n    destination.write_bytes(encoded)\n    return {\n        "sha256": hashlib.sha256(encoded).hexdigest(),\n        "eventCount": len(texts),\n        "nameCells": name_cells,\n        "nameChanges": name_changes,\n    }\n\n\ndef _redact_localized_fields(document: dict[str, Any]) -> tuple[int, int]:\n    name_cells = 0\n    comment_cells = 0\n    sheets = document.get("sheetList")\n    if not isinstance(sheets, list):\n        raise RuntimeError("Exedra JSON is missing sheetList")\n    for sheet in sheets:\n        if not isinstance(sheet, dict):\n            continue\n        indices = _header_indices(sheet)\n        name_index = indices.get("name")\n        action_index = indices.get("actiontype")\n        comment_index = indices.get("comment")\n        rows = sheet.get("contentRowList")\n        if not isinstance(rows, list):\n            continue\n        for row in rows:\n            cells = row.get("cellList") if isinstance(row, dict) else None\n            if not isinstance(cells, list):\n                continue\n            if name_index is not None and name_index < len(cells):\n                if isinstance(cells[name_index], str) and cells[name_index]:\n                    name_cells += 1\n                    cells[name_index] = "__MAGIREADER_LOCALIZED_NAME__"\n            if action_index is None or comment_index is None:\n                continue\n            action = str(_cell(cells, action_index) or "").strip().casefold()\n            value = _cell(cells, comment_index)\n            if (\n                action in TEXT_ACTIONS\n                and isinstance(value, str)\n                and value.strip()\n                and comment_index < len(cells)\n            ):\n                comment_cells += 1\n                cells[comment_index] = "__MAGIREADER_LOCALIZED_COMMENT__"\n    return name_cells, comment_cells\n\n\ndef validate_human_json(\n    jp_json: Path,\n    cn_json: Path,\n    expected_texts: Sequence[str],\n    mapping: dict[str, str] | None = None,\n) -> dict[str, Any]:\n    speaker_map = mapping or load_name_translation_map()\n    jp_document = json.loads(jp_json.read_text(encoding="utf-8-sig"))\n    cn_document = json.loads(cn_json.read_text(encoding="utf-8-sig"))\n    if not isinstance(jp_document, dict) or not isinstance(cn_document, dict):\n        raise RuntimeError(f"Exedra JSON root is not an object: {jp_json.name}")\n\n    jp_redacted = copy.deepcopy(jp_document)\n    cn_redacted = copy.deepcopy(cn_document)\n    jp_names, jp_comments = _redact_localized_fields(jp_redacted)\n    cn_names, cn_comments = _redact_localized_fields(cn_redacted)\n    if (jp_names, jp_comments) != (cn_names, cn_comments):\n        raise RuntimeError(f"Localized cell counts differ: {jp_json.name}")\n    if jp_redacted != cn_redacted:\n        raise RuntimeError(\n            f"Human-localized JSON changed fields outside Name/Comment: {jp_json.name}"\n        )\n    cn_rows = extract_text_events(cn_document)\n    actual_texts = [str(row.get("text") or "") for row in cn_rows]\n    if actual_texts != list(expected_texts):\n        raise RuntimeError(f"Human Comment sequence differs: {jp_json.name}")\n    for row in cn_rows:\n        speaker = str(row.get("speaker") or "")\n        if speaker and translate_speaker(speaker, speaker_map) != speaker:\n            raise RuntimeError(f"CN JSON contains a noncanonical Name: {speaker}")\n    return {\n        "nonLocalizedFieldsMatch": True,\n        "canonicalNameFields": True,\n        "playableCommentSequenceMatches": True,\n        "mutableNameCellCount": cn_names,\n        "mutableCommentCellCount": cn_comments,\n        "canonicalEventCount": len(actual_texts),\n    }\n\n\ndef localize_events(\n    tw_rows: Sequence[dict[str, Any]],\n    jp_lines: Sequence[Any],\n    convert: Callable[[str], str],\n    speaker_map: dict[str, str],\n) -> tuple[list[LocalizedEvent], dict[str, int]]:\n    if len(tw_rows) != len(jp_lines):\n        raise RuntimeError(\n            f"TW/JP event count mismatch: {len(tw_rows)} != {len(jp_lines)}"\n        )\n    events: list[LocalizedEvent] = []\n    stats = {\n        "officialTwSpeakerEvents": 0,\n        "dictionaryFallbackSpeakerEvents": 0,\n        "narrationSpeakerEvents": 0,\n    }\n    for index, (row, jp_line) in enumerate(zip(tw_rows, jp_lines), start=1):\n        action = str(row.get("action") or "").strip()\n        text = convert(str(row.get("text") or "").strip())\n        if not text:\n            raise RuntimeError(f"TW event {index} has empty localized text")\n        source_speaker = convert(str(row.get("speaker") or "").strip())\n        if source_speaker:\n            speaker = translate_speaker(source_speaker, speaker_map)\n            stats["officialTwSpeakerEvents"] += 1\n        elif action.casefold() in {"narration", "onlytext"}:\n            speaker = "旁白"\n            stats["narrationSpeakerEvents"] += 1\n        else:\n            fallback = str(getattr(jp_line, "speaker", "") or "旁白")\n            speaker = translate_speaker(fallback, speaker_map)\n            stats["dictionaryFallbackSpeakerEvents"] += 1\n        events.append(\n            LocalizedEvent(\n                speaker=speaker or "旁白",\n                text=text,\n                action=action,\n                sheet_index=int(row.get("sheet_index") or 0),\n                row_number=row.get("row_number"),\n            )\n        )\n    return events, stats\n\n\ndef _escape_text(value: str) -> str:\n    return (\n        str(value).strip()\n        .replace("\\r\\n", "\\n")\n        .replace("\\r", "\\n")\n        .replace("\\n", r"\\n")\n    )\n\n\ndef render_human_cn(\n    sections: Sequence[Any],\n    translated: Sequence[Sequence[str]],\n    mapping: dict[str, str] | None = None,\n) -> str:\n    speaker_map = mapping or load_name_translation_map()\n    if len(sections) != len(translated):\n        raise RuntimeError("Section count differs")\n    output: list[str] = []\n    for section, texts in zip(sections, translated):\n        lines = getattr(section, "lines", ())\n        if len(lines) != len(texts):\n            raise RuntimeError(f"Section {section.number} event count differs")\n        output.append(\n            f"--- [Section {section.number}] (Source: {section.source}) ---"\n        )\n        for jp_line, text in zip(lines, texts):\n            speaker = translate_speaker(\n                str(getattr(jp_line, "speaker", "") or "旁白"),\n                speaker_map,\n            )\n            escaped = _escape_text(str(text))\n            if not escaped:\n                raise RuntimeError(f"Section {section.number} contains empty text")\n            output.append(f"{speaker}：{escaped}")\n        output.append("")\n    return "\\n".join(output).strip() + "\\n"\n\n\ndef canonicalize_txt_text(\n    content: str,\n    mapping: dict[str, str],\n) -> tuple[str, int, set[str]]:\n    normalized = content.removeprefix("\\ufeff").replace("\\r\\n", "\\n").replace(\n        "\\r", "\\n"\n    )\n    output: list[str] = []\n    changes = 0\n    remaining_japanese: set[str] = set()\n    for raw_line in normalized.split("\\n"):\n        stripped = raw_line.strip()\n        if not stripped or stripped.startswith("---"):\n            output.append(raw_line)\n            continue\n        match = SPEAKER_SEPARATOR_RE.search(raw_line)\n        if match is None or match.start() <= 0 or match.start() > 96:\n            output.append(raw_line)\n            continue\n        prefix = raw_line[: match.start()]\n        leading = prefix[: len(prefix) - len(prefix.lstrip())]\n        speaker = prefix.strip()\n        canonical = translate_speaker(speaker, mapping)\n        if canonical != speaker:\n            changes += 1\n        if contains_japanese_script(canonical):\n            remaining_japanese.add(canonical)\n        output.append(leading + canonical + raw_line[match.start() :])\n    result = "\\n".join(output)\n    if normalized.endswith("\\n") and not result.endswith("\\n"):\n        result += "\\n"\n    return result, changes, remaining_japanese\n\n\ndef canonicalize_txt_path(\n    path: Path,\n    mapping: dict[str, str],\n) -> tuple[int, set[str]]:\n    original = path.read_text(encoding="utf-8-sig")\n    updated, changes, remaining = canonicalize_txt_text(original, mapping)\n    normalized_original = original.removeprefix("\\ufeff").replace(\n        "\\r\\n", "\\n"\n    ).replace("\\r", "\\n")\n    if updated != normalized_original:\n        path.write_text(updated, encoding="utf-8", newline="\\n")\n    return changes, remaining\n\n\ndef canonicalize_json_names_path(\n    path: Path,\n    mapping: dict[str, str],\n) -> tuple[int, int]:\n    document = json.loads(path.read_text(encoding="utf-8-sig"))\n    if not isinstance(document, dict):\n        raise RuntimeError(f"Exedra JSON root is not an object: {path}")\n    total, changes = _canonicalize_name_cells(document, mapping)\n    if changes:\n        path.write_bytes(json_bytes(document))\n    return total, changes\n\n\ndef dictionary_sha256(path: Path = DEFAULT_DICTIONARY) -> str:\n    return hashlib.sha256(path.read_bytes()).hexdigest()\n'
CANONICALIZER = '#!/usr/bin/env python3\n"""Canonicalize every Exedra CN speaker in TXT/JSON and rebind reports."""\nfrom __future__ import annotations\n\nimport argparse\nimport hashlib\nimport json\nimport sys\nfrom collections import Counter\nfrom pathlib import Path\nfrom typing import Any\n\nROOT = Path(__file__).resolve().parents[1]\nsys.path[:0] = [str(ROOT), str(ROOT / "tools")]\n\nimport generate_story_index as pipeline  # noqa: E402\nimport import_exedra_official_tw as common  # noqa: E402\nfrom tw_authentic_scenario import (  # noqa: E402\n    canonicalize_json_names_path,\n    canonicalize_txt_path,\n    dictionary_sha256,\n    extract_text_events,\n    load_name_translation_map,\n    translate_speaker,\n)\n\nJP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"\nCN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"\nMANIFEST = JP_ROOT / "exedra_manifest.json"\nAUDIT_PATH = ROOT / "artifacts/exedra_speaker_canonicalization_report.json"\n\n\ndef sha256_file(path: Path) -> str:\n    digest = hashlib.sha256()\n    with path.open("rb") as handle:\n        for chunk in iter(lambda: handle.read(1024 * 1024), b""):\n            digest.update(chunk)\n    return digest.hexdigest()\n\n\ndef sha256_text(path: Path) -> str:\n    return hashlib.sha256(\n        path.read_text(encoding="utf-8-sig").encode("utf-8")\n    ).hexdigest()\n\n\ndef atomic_json(path: Path, value: Any) -> None:\n    temporary = path.with_suffix(path.suffix + ".tmp")\n    temporary.write_text(\n        json.dumps(value, ensure_ascii=False, indent=2) + "\\n",\n        encoding="utf-8",\n        newline="\\n",\n    )\n    temporary.replace(path)\n\n\ndef load_manifest_groups() -> list[dict[str, Any]]:\n    value = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))\n    groups = value.get("groups") if isinstance(value, dict) else None\n    if not isinstance(groups, list):\n        raise RuntimeError("Exedra manifest is missing groups")\n    result = [group for group in groups if isinstance(group, dict)]\n    if len(result) != len(groups):\n        raise RuntimeError("Exedra manifest contains non-object groups")\n    return result\n\n\ndef update_source_metadata(\n    entries: list[dict[str, Any]],\n    group_dir: Path,\n) -> list[dict[str, Any]]:\n    updated: list[dict[str, Any]] = []\n    for item in entries:\n        if not isinstance(item, dict):\n            raise RuntimeError(f"Invalid sourceJson entry in {group_dir}")\n        next_item = dict(item)\n        source = str(next_item.get("source") or "")\n        path = group_dir / source\n        if source and path.is_file():\n            digest = sha256_file(path)\n            next_item["cnSha256"] = digest\n            if "simplifiedJsonSha256" in next_item:\n                next_item["simplifiedJsonSha256"] = digest\n            document = json.loads(path.read_text(encoding="utf-8-sig"))\n            if not isinstance(document, dict):\n                raise RuntimeError(f"Invalid content JSON: {path}")\n            rows = extract_text_events(document)\n            next_item["eventCount"] = len(rows)\n            next_item["canonicalNameFields"] = True\n            next_item["speakerPolicy"] = (\n                "dictionary.ts-exact-or-unambiguous-canonical-chinese"\n            )\n            proof = next_item.get("mutationProof")\n            if isinstance(proof, dict):\n                proof = dict(proof)\n                proof.pop("nonCommentFieldsMatch", None)\n                proof.update(\n                    {\n                        "nonLocalizedFieldsMatch": True,\n                        "canonicalNameFields": True,\n                        "playableCommentSequenceMatches": True,\n                        "canonicalEventCount": len(rows),\n                    }\n                )\n                next_item["mutationProof"] = proof\n        updated.append(next_item)\n    return updated\n\n\ndef rebuild_report(\n    old: dict[str, Any],\n    *,\n    category: str,\n    key: str,\n    jp_txt: Path,\n    cn_txt: Path,\n    group_dir: Path,\n    dictionary_digest: str,\n    txt_changes: int,\n    json_changes: int,\n) -> dict[str, Any]:\n    source_json = old.get("sourceJson")\n    if not isinstance(source_json, list):\n        source_json = []\n    source_json = update_source_metadata(source_json, group_dir)\n    source_label = str(old.get("sourceRoot") or "canonicalized-existing-human")\n    rebuilt = common.build_report(\n        category,\n        key,\n        jp_txt,\n        cn_txt,\n        source_label,\n        source_json,\n    )\n    preserved = dict(old)\n    for field in (\n        "schemaVersion",\n        "status",\n        "sourceRoot",\n        "group",\n        "validation",\n        "mismatches",\n        "jp",\n        "cn",\n        "sections",\n        "sourceJson",\n    ):\n        preserved[field] = rebuilt[field]\n    if old.get("provenance"):\n        preserved["provenance"] = old["provenance"]\n    preserved["speakerCanonicalization"] = {\n        "policy": "dictionary.ts-exact-or-unambiguous-canonical-chinese",\n        "dictionarySha256": dictionary_digest,\n        "txtSpeakerLabelsChanged": txt_changes,\n        "jsonNameCellsChanged": json_changes,\n    }\n    return preserved\n\n\ndef update_sidecar(\n    path: Path,\n    *,\n    cn_txt: Path,\n    group_dir: Path,\n    dictionary_digest: str,\n    txt_changes: int,\n    json_changes: int,\n) -> None:\n    if not path.is_file():\n        return\n    value = json.loads(path.read_text(encoding="utf-8-sig"))\n    if not isinstance(value, dict):\n        raise RuntimeError(f"Invalid provenance sidecar: {path}")\n    value["cnSha256"] = sha256_text(cn_txt)\n    for field in ("sourceJson", "episodes"):\n        entries = value.get(field)\n        if isinstance(entries, list):\n            value[field] = update_source_metadata(entries, group_dir)\n    value["speakerCanonicalization"] = {\n        "policy": "dictionary.ts-exact-or-unambiguous-canonical-chinese",\n        "dictionarySha256": dictionary_digest,\n        "txtSpeakerLabelsChanged": txt_changes,\n        "jsonNameCellsChanged": json_changes,\n    }\n    atomic_json(path, value)\n\n\ndef main() -> int:\n    parser = argparse.ArgumentParser(description=__doc__)\n    parser.add_argument("--check", action="store_true")\n    args = parser.parse_args()\n\n    mapping = load_name_translation_map()\n    dictionary_digest = dictionary_sha256()\n    stats: Counter[str] = Counter()\n    remaining_japanese: set[str] = set()\n    groups_audited: list[dict[str, Any]] = []\n\n    for group in load_manifest_groups():\n        category = str(group.get("category") or "")\n        key = str(group.get("groupKey") or "")\n        text_file = str(group.get("textFile") or "")\n        if not category or not key or not text_file:\n            raise RuntimeError("Invalid Exedra manifest group")\n        group_dir = CN_ROOT / category / key\n        cn_txt = group_dir / f"{key}_cn.txt"\n        if not cn_txt.is_file():\n            continue\n        jp_txt = JP_ROOT / text_file\n        if not jp_txt.is_file():\n            raise RuntimeError(f"JP TXT missing: {jp_txt}")\n\n        txt_changes, remaining = canonicalize_txt_path(cn_txt, mapping)\n        remaining_japanese.update(remaining)\n        stats["cn_groups"] += 1\n        stats["txt_speaker_labels_changed"] += txt_changes\n\n        source_names = [\n            Path(str(value)).name\n            for value in group.get("sources", [])\n            if isinstance(value, str)\n        ]\n        present_json = [\n            group_dir / name\n            for name in source_names\n            if (group_dir / name).is_file()\n        ]\n        if present_json and len(present_json) != len(source_names):\n            raise RuntimeError(\n                f"Partial CN JSON set for {category}/{key}: "\n                f"{len(present_json)}/{len(source_names)}"\n            )\n        group_json_changes = 0\n        for json_path in present_json:\n            total, changes = canonicalize_json_names_path(json_path, mapping)\n            stats["json_name_cells"] += total\n            stats["json_name_cells_changed"] += changes\n            group_json_changes += changes\n\n        report_path = group_dir / f"{key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}"\n        if not report_path.is_file():\n            raise RuntimeError(f"CN import report missing: {report_path}")\n        old_report = json.loads(report_path.read_text(encoding="utf-8-sig"))\n        if not isinstance(old_report, dict):\n            raise RuntimeError(f"Invalid CN import report: {report_path}")\n        report = rebuild_report(\n            old_report,\n            category=category,\n            key=key,\n            jp_txt=jp_txt,\n            cn_txt=cn_txt,\n            group_dir=group_dir,\n            dictionary_digest=dictionary_digest,\n            txt_changes=txt_changes,\n            json_changes=group_json_changes,\n        )\n        atomic_json(report_path, report)\n        update_sidecar(\n            group_dir / f"{key}_cn.provenance.json",\n            cn_txt=cn_txt,\n            group_dir=group_dir,\n            dictionary_digest=dictionary_digest,\n            txt_changes=txt_changes,\n            json_changes=group_json_changes,\n        )\n\n        jp_sections = pipeline._exedra_alignment_sections(jp_txt)\n        cn_sections = pipeline._exedra_alignment_sections(cn_txt)\n        pipeline._validate_exedra_cn_import_report(\n            group=pipeline.OrganizedExedraGroup(\n                manifest_id=str(group.get("id") or ""),\n                raw_category=category,\n                category=pipeline.EXEDRA_CATEGORY_MAP[category],\n                group_key=key,\n                output_dir=Path(category, key),\n                text_file=Path(text_file),\n                source_paths=tuple(\n                    str(value) for value in group.get("sources", [])\n                ),\n                source_names=tuple(\n                    Path(str(value)).name\n                    for value in group.get("sources", [])\n                ),\n                title="",\n            ),\n            jp_path=jp_txt,\n            cn_path=cn_txt,\n            jp_sections=jp_sections,\n            cn_sections=cn_sections,\n        )\n        groups_audited.append(\n            {\n                "group": f"{category}/{key}",\n                "provenance": report.get("provenance"),\n                "txtSpeakerLabelsChanged": txt_changes,\n                "jsonNameCellsChanged": group_json_changes,\n                "canonicalBlocks": sum(\n                    item.reader_block_count for item in cn_sections\n                ),\n            }\n        )\n\n    uncanonicalized: set[str] = set()\n    for group in groups_audited:\n        category, key = str(group["group"]).split("/", 1)\n        path = CN_ROOT / category / key / f"{key}_cn.txt"\n        for line in path.read_text(encoding="utf-8-sig").splitlines():\n            stripped = line.strip()\n            if not stripped or stripped.startswith("---"):\n                continue\n            separator = min(\n                (\n                    position\n                    for position in (line.find(":"), line.find("："))\n                    if position > 0\n                ),\n                default=-1,\n            )\n            if separator <= 0:\n                continue\n            speaker = line[:separator].strip()\n            canonical = translate_speaker(speaker, mapping)\n            if canonical != speaker:\n                uncanonicalized.add(speaker)\n    if uncanonicalized:\n        raise RuntimeError(\n            "Dictionary-known Exedra CN speakers remain uncanonicalized: "\n            + ", ".join(sorted(uncanonicalized)[:40])\n        )\n\n    audit = {\n        "version": 1,\n        "policy": "dictionary.ts-exact-or-unambiguous-canonical-chinese",\n        "dictionarySha256": dictionary_digest,\n        "stats": dict(stats),\n        "remainingJapaneseLabels": sorted(remaining_japanese),\n        "groups": groups_audited,\n    }\n    if not args.check:\n        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)\n        atomic_json(AUDIT_PATH, audit)\n    print(\n        "EXEDRA_SPEAKER_CANONICALIZATION_OK "\n        f"groups={stats[\'cn_groups\']} "\n        f"txt_changes={stats[\'txt_speaker_labels_changed\']} "\n        f"json_changes={stats[\'json_name_cells_changed\']} "\n        f"remaining_japanese_labels={len(remaining_japanese)}"\n    )\n    if remaining_japanese:\n        print(\n            "EXEDRA_REMAINING_JAPANESE_LABEL_SAMPLES "\n            + json.dumps(\n                sorted(remaining_japanese)[:80],\n                ensure_ascii=False,\n            )\n        )\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
GENERIC_BUILD_REPORT = 'def build_report(\n    category: str,\n    group_key: str,\n    jp_path: Path,\n    cn_path: Path,\n    source_label: str,\n    json_meta: list[dict[str, Any]],\n) -> dict[str, Any]:\n    jp_sections = pipeline._exedra_alignment_sections(jp_path)\n    cn_sections = pipeline._exedra_alignment_sections(cn_path)\n    if len(jp_sections) != len(cn_sections):\n        raise RuntimeError(f"导入后 Section 数量不一致：{group_key}")\n    authentic_tw = any(\n        item.get("schemaSource") == "official_tw_json"\n        for item in json_meta\n        if isinstance(item, dict)\n    )\n    sections = []\n    for jp, cn in zip(jp_sections, cn_sections):\n        if (\n            jp.number != cn.number\n            or jp.source_name != cn.source_name\n            or jp.reader_block_count != cn.reader_block_count\n            or jp.speaker_sequence_sha256 != cn.speaker_sequence_sha256\n        ):\n            raise RuntimeError(\n                f"导入后规范中文说话人/事件块结构证明失败："\n                f"{group_key} Section {jp.number}"\n            )\n        match = EPISODE_RE.search(jp.source_name)\n        sections.append(\n            {\n                "section": jp.number,\n                "source": jp.source_name,\n                "wikiEpisode": int(match.group(1)) if match else jp.number - 1,\n                "readerNormalizedBlocks": {\n                    "jp": jp.reader_block_count,\n                    "cn": cn.reader_block_count,\n                    "matches": True,\n                },\n                "speakerSequenceSha256": {\n                    "jp": jp.speaker_sequence_sha256,\n                    "cn": cn.speaker_sequence_sha256,\n                },\n                "speakerSequenceMatches": True,\n            }\n        )\n    speaker_policy = (\n        "official_tw_name_column_tw2sp"\n        if authentic_tw\n        else "dictionary_canonicalized_jp_name"\n    )\n    return {\n        "schemaVersion": 1,\n        "status": "validated",\n        "provenance": (\n            "official_tw_human" if authentic_tw else "trusted_human"\n        ),\n        "sourceRoot": source_label,\n        "group": {"category": category, "groupKey": group_key},\n        "validation": {\n            "passed": True,\n            "mismatchCount": 0,\n            "usesLcs": False,\n            "usesFuzzyMatching": False,\n            "allowsReordering": False,\n            "structurePolicy": "same-section-source-count-action-row",\n            "speakerPolicy": speaker_policy,\n            "speakerSequencesMayDiffer": authentic_tw,\n            "speakerSequencesCanonicalized": True,\n            "twSchemaPreserved": authentic_tw,\n        },\n        "mismatches": [],\n        "jp": {\n            "contentSha256": pipeline._sha256_utf8_text_file(jp_path),\n            "sectionCount": len(jp_sections),\n            "readerNormalizedBlockCount": sum(\n                item.reader_block_count for item in jp_sections\n            ),\n        },\n        "cn": {\n            "renderedSha256": pipeline._sha256_utf8_text_file(cn_path),\n            "sectionCount": len(cn_sections),\n            "readerNormalizedBlockCount": sum(\n                item.reader_block_count for item in cn_sections\n            ),\n        },\n        "sections": sections,\n        "sourceJson": json_meta,\n    }\n'
TEST_LOCALIZATION = 'from __future__ import annotations\n\nimport json\nimport tempfile\nimport unittest\nfrom pathlib import Path\n\nfrom tools.tw_authentic_scenario import (\n    load_name_translation_map,\n    materialize_human_json,\n    render_human_cn,\n    translate_speaker,\n    validate_human_json,\n)\nfrom tools.import_exedra_official_tw import Line, Section\n\n\nclass ExedraSpeakerLocalizationTests(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls) -> None:\n        cls.mapping = load_name_translation_map(\n            Path("website/app/config/dictionary.ts")\n        )\n\n    def test_dictionary_canonicalizes_japanese_and_tw_punctuation(self) -> None:\n        self.assertEqual(\n            translate_speaker("アリナ・グレイ", self.mapping),\n            "阿莉娜·格雷",\n        )\n        self.assertEqual(\n            translate_speaker("阿莉娜‧格雷", self.mapping),\n            "阿莉娜·格雷",\n        )\n        self.assertEqual(\n            translate_speaker("水波レナ＆秋野かえで", self.mapping),\n            "水波玲奈＆秋野枫",\n        )\n\n    def test_human_json_localizes_name_and_comment_only(self) -> None:\n        fixture = {\n            "bookTitle": "fixture",\n            "sheetList": [{\n                "headerRow": {\n                    "cellList": [\n                        "ActionType", "Name", "Comment", "AssetID", "PositionID"\n                    ]\n                },\n                "contentRowList": [{\n                    "rowNumber": 2,\n                    "cellList": [\n                        "Talk", "水波レナ", "日本語", "100201", "Center"\n                    ],\n                }],\n            }],\n        }\n        with tempfile.TemporaryDirectory() as temporary:\n            root = Path(temporary)\n            jp = root / "jp.json"\n            cn = root / "cn.json"\n            jp.write_text(\n                json.dumps(fixture, ensure_ascii=False),\n                encoding="utf-8",\n            )\n            result = materialize_human_json(\n                jp,\n                ["简体正文"],\n                cn,\n                self.mapping,\n            )\n            value = json.loads(cn.read_text(encoding="utf-8"))\n            row = value["sheetList"][0]["contentRowList"][0]["cellList"]\n            self.assertEqual(row[1], "水波玲奈")\n            self.assertEqual(row[2], "简体正文")\n            self.assertEqual(row[3:], ["100201", "Center"])\n            self.assertEqual(result["eventCount"], 1)\n            proof = validate_human_json(\n                jp,\n                cn,\n                ["简体正文"],\n                self.mapping,\n            )\n            self.assertTrue(proof["canonicalNameFields"])\n\n    def test_human_txt_uses_dictionary_speakers(self) -> None:\n        sections = (\n            Section(\n                1,\n                "fixture.json",\n                (\n                    Line("リズ・ホークウッド", "x", "dialogue"),\n                    Line("Narration", "y", "narration"),\n                ),\n            ),\n        )\n        rendered = render_human_cn(\n            sections,\n            [["正文", "旁白正文"]],\n            self.mapping,\n        )\n        self.assertIn("莉兹·霍克伍德：正文", rendered)\n        self.assertIn("旁白：旁白正文", rendered)\n\n\nif __name__ == "__main__":\n    unittest.main()\n'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


def replace_block(
    path: str,
    start_marker: str,
    end_marker: str,
    replacement: str,
) -> None:
    source = read(path)
    start = source.find(start_marker)
    if start < 0:
        raise RuntimeError(f"{path}: block start not found: {start_marker!r}")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise RuntimeError(f"{path}: block end not found: {end_marker!r}")
    write(path, source[:start] + replacement + source[end:])


def patch_pipeline() -> None:
    path = "generate_story_index.py"
    source = read(path)
    import_block = (
        "from tools.tw_authentic_scenario import (\n"
        "    load_name_translation_map as _load_exedra_name_translation_map,\n"
        "    translate_speaker as _translate_exedra_speaker,\n"
        ")\n"
    )
    if import_block not in source:
        marker = "from typing import Any, Iterable, Mapping, MutableMapping, Sequence\n"
        if marker not in source:
            raise RuntimeError("generate_story_index.py typing import marker missing")
        source = source.replace(marker, marker + "\n" + import_block, 1)

    old_identity = """def _exedra_speaker_identity(speaker: str) -> tuple[str, ...]:
    if speaker in EXEDRA_NARRATION_SPEAKERS:
        return ("@narration",)
    return tuple(part for part in re.split(r"[＆&]", speaker) if part)
"""
    new_identity = """_EXEDRA_NAME_TRANSLATION_MAP: dict[str, str] | None = None


def _canonical_exedra_speaker(value: str) -> str:
    global _EXEDRA_NAME_TRANSLATION_MAP
    if _EXEDRA_NAME_TRANSLATION_MAP is None:
        _EXEDRA_NAME_TRANSLATION_MAP = _load_exedra_name_translation_map(
            SCRIPT_DIR / "website/app/config/dictionary.ts"
        )
    return _translate_exedra_speaker(
        _normalize_exedra_speaker(value),
        _EXEDRA_NAME_TRANSLATION_MAP,
    )


def _exedra_speaker_identity(speaker: str) -> tuple[str, ...]:
    canonical = _canonical_exedra_speaker(speaker)
    if canonical in EXEDRA_NARRATION_SPEAKERS or canonical == "旁白":
        return ("@narration",)
    return tuple(part for part in re.split(r"[＆&]", canonical) if part)
"""
    if old_identity in source:
        source = source.replace(old_identity, new_identity, 1)
    elif new_identity not in source:
        raise RuntimeError("generate_story_index.py speaker identity block missing")

    old_alignment = """                kind = (
                    "narration"
                    if speaker in EXEDRA_NARRATION_SPEAKERS
                    else "dialogue"
                )
                if speaker != previous_speaker:
                    signatures.append(
                        (kind, _exedra_speaker_identity(speaker))
                    )
                    previous_speaker = speaker
"""
    new_alignment = """                canonical_speaker = _canonical_exedra_speaker(speaker)
                kind = (
                    "narration"
                    if canonical_speaker in EXEDRA_NARRATION_SPEAKERS
                    or canonical_speaker == "旁白"
                    else "dialogue"
                )
                if canonical_speaker != previous_speaker:
                    signatures.append(
                        (kind, _exedra_speaker_identity(canonical_speaker))
                    )
                    previous_speaker = canonical_speaker
"""
    if old_alignment in source:
        source = source.replace(old_alignment, new_alignment, 1)
    elif new_alignment not in source:
        raise RuntimeError("generate_story_index.py alignment block missing")

    start_marker = (
        '        authentic_tw = report.get("provenance") == "official_tw_human"\n'
    )
    start = source.find(start_marker)
    if start < 0:
        raise RuntimeError("generate_story_index.py authentic TW JSON block missing")
    end_marker = "\n\n\ndef load_exedra_manifest("
    end = source.find(end_marker, start)
    if end < 0:
        raise RuntimeError("generate_story_index.py manifest marker missing")
    replacement = """        authentic_tw = report.get("provenance") == "official_tw_human"
        if authentic_tw:
            if (
                report_source.get("schemaSource") != "official_tw_json"
                or report_source.get("speakerPolicy")
                != "official_tw_name_column_tw2sp"
                or report_source.get("twSchemaPreserved") is not True
                or not _valid_sha256(report_source.get("twSha256"))
            ):
                raise PipelineError(
                    "Exedra 台服 JSON 缺少真实来源/说话人策略证明: "
                    f"{group.manifest_id} #{index}"
                )

        def canonical_structure(rows: Sequence[Mapping[str, Any]]):
            return [
                (
                    int(row.get("sheet_index") or 0),
                    row.get("row_number"),
                    str(row["action"]).casefold(),
                    _canonical_exedra_speaker(
                        str(row.get("speaker") or "旁白")
                    ),
                )
                for row in rows
            ]

        jp_structure = canonical_structure(jp_rows)
        cn_structure = canonical_structure(cn_rows)
        if jp_structure != cn_structure:
            raise PipelineError(
                "Exedra 中日 JSON 的 ActionType/工作表/行位置/"
                "规范中文说话人顺序不一致: "
                f"{group.manifest_id} #{index}"
            )
"""
    source = source[:start] + replacement + source[end:]
    write(path, source)


def patch_common_report() -> None:
    replace_block(
        "tools/import_exedra_official_tw.py",
        "\ndef build_report(",
        "\ndef commit_staged_group(",
        "\n" + GENERIC_BUILD_REPORT + "\n",
    )


def patch_human_importer() -> None:
    path = "tools/import_exedra_human_text.py"
    source = read(path)
    import_block = """from tw_authentic_scenario import (  # noqa: E402
    load_name_translation_map,
    materialize_human_json,
    render_human_cn,
    validate_human_json,
)

SPEAKER_MAP = load_name_translation_map()
"""
    marker = "import import_exedra_official_tw as common  # noqa: E402\n"
    if import_block not in source:
        if marker not in source:
            raise RuntimeError("human importer common import missing")
        source = source.replace(marker, marker + import_block, 1)

    start = source.find("\ndef validate_only_comment_changed(")
    end = source.find("\ndef import_group(", start)
    if start < 0 or end < 0:
        raise RuntimeError("human importer validation markers missing")
    wrapper = """
def validate_only_comment_changed(
    jp_json: Path,
    cn_json: Path,
    expected_texts: list[str],
) -> dict[str, Any]:
    \"\"\"Compatibility wrapper for Name+Comment localization proof.\"\"\"

    return validate_human_json(
        jp_json,
        cn_json,
        expected_texts,
        SPEAKER_MAP,
    )

"""
    source = source[:start] + wrapper + source[end:]

    old_apply = """            output_sha = common.apply_translated_texts(
                jp_json,
                texts,
                destination,
            )
"""
    new_apply = """            output_sha = materialize_human_json(
                jp_json,
                texts,
                destination,
                SPEAKER_MAP,
            )["sha256"]
"""
    if old_apply not in source:
        raise RuntimeError("human importer apply call missing")
    source = source.replace(old_apply, new_apply, 1)

    old_render = """        staged_cn.write_text(
            common.render_cn(sections, translations),
            encoding="utf-8",
        )
"""
    new_render = """        staged_cn.write_text(
            render_human_cn(sections, translations, SPEAKER_MAP),
            encoding="utf-8",
        )
"""
    if old_render not in source:
        raise RuntimeError("human importer render call missing")
    source = source.replace(old_render, new_render, 1)
    write(path, source)


def patch_wiki_importer() -> None:
    path = "import_exedra_wiki_translation.py"
    source = read(path)
    old_signature = """def render_translation(
    sections: Sequence[StorySection], episodes: Sequence[WikiEpisode]
) -> str:
"""
    new_signature = """def render_translation(
    sections: Sequence[StorySection],
    episodes: Sequence[WikiEpisode],
    speaker_map: dict[str, str],
) -> str:
"""
    if old_signature in source:
        source = source.replace(old_signature, new_signature, 1)
    elif new_signature not in source:
        raise RuntimeError("wiki importer render signature missing")

    old_line = """                f"{normalize_speaker(event.speaker)}: "
                f"{escape_output_text(event.text)}"
"""
    new_line = """                f"{normalize_speaker(
                    speaker_map.get(
                        normalize_speaker(event.speaker),
                        event.speaker,
                    )
                )}: "
                f"{escape_output_text(event.text)}"
"""
    if old_line in source:
        source = source.replace(old_line, new_line, 1)
    elif new_line not in source:
        raise RuntimeError("wiki importer speaker render line missing")

    old_call = "        render_translation(sections, episodes)\n"
    new_call = "        render_translation(sections, episodes, speaker_map)\n"
    if old_call in source:
        source = source.replace(old_call, new_call, 1)
    elif new_call not in source:
        raise RuntimeError("wiki importer render call missing")
    write(path, source)


def patch_tests() -> None:
    path = "tests/test_tw_authentic_scenario.py"
    source = read(path)
    source = source.replace(
        'self.assertEqual(row[1], "阿莉娜‧格雷")',
        'self.assertEqual(row[1], "阿莉娜·格雷")',
    )
    write(path, source)
    write(
        "tests/test_exedra_speaker_localization.py",
        TEST_LOCALIZATION,
    )


def main() -> int:
    write("tools/tw_authentic_scenario.py", SHARED_MODULE)
    patch_pipeline()
    patch_common_report()
    patch_human_importer()
    patch_wiki_importer()
    write("tools/canonicalize_exedra_cn_speakers.py", CANONICALIZER)
    patch_tests()
    print("AUTHENTIC_TW_REPAIR_V2_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
