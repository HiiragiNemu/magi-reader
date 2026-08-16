#!/usr/bin/env python3
"""Prove every JP Exedra speaker that may enter Chinese editing is mapped."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from tw_authentic_scenario import (  # noqa: E402
    contains_japanese_script,
    load_name_translation_map,
    translate_speaker,
)

SOURCE = ROOT / 'magiraexedra-source-master/Scenarios_full'
SEPARATOR = re.compile(r'[:：﹕︰︓]')


def main() -> int:
    mapping = load_name_translation_map()
    failures: dict[str, set[str]] = {}
    txt_labels = 0
    json_labels = 0

    def check(raw: str, location: str) -> None:
        nonlocal txt_labels, json_labels
        speaker = raw.strip()
        if not speaker:
            return
        canonical = translate_speaker(speaker, mapping)
        if location.endswith('.txt'):
            txt_labels += 1
        else:
            json_labels += 1
        if contains_japanese_script(canonical):
            failures.setdefault(speaker, set()).add(location)

    for path in sorted(SOURCE.rglob('*_jp.txt')):
        for number, raw in enumerate(
            path.read_text(encoding='utf-8-sig').splitlines(),
            start=1,
        ):
            line = raw.strip()
            if not line or line.startswith('---'):
                continue
            match = SEPARATOR.search(raw)
            if match is None or match.start() <= 0 or match.start() > 96:
                continue
            check(raw[:match.start()], f'{path.as_posix()}:{number}.txt')

    for path in sorted(SOURCE.rglob('*.json')):
        try:
            value = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        sheets = value.get('sheetList')
        if not isinstance(sheets, list):
            continue
        for sheet_index, sheet in enumerate(sheets):
            if not isinstance(sheet, dict):
                continue
            header = sheet.get('headerRow')
            headers = header.get('cellList') if isinstance(header, dict) else None
            rows = sheet.get('contentRowList')
            if not isinstance(headers, list) or not isinstance(rows, list):
                continue
            folded = [str(item or '').strip().casefold() for item in headers]
            try:
                name_index = folded.index('name')
            except ValueError:
                continue
            for row_index, row in enumerate(rows):
                cells = row.get('cellList') if isinstance(row, dict) else None
                if not isinstance(cells, list) or name_index >= len(cells):
                    continue
                value = cells[name_index]
                if isinstance(value, str) and value.strip():
                    check(
                        value,
                        f'{path.as_posix()}:{sheet_index}:{row_index}.json',
                    )

    if failures:
        for speaker, locations in sorted(failures.items())[:300]:
            canonical = translate_speaker(speaker, mapping)
            print(
                'UNMAPPED_EXEDRA_JP_SPEAKER',
                repr(speaker),
                '->',
                repr(canonical),
                sorted(locations)[:5],
            )
        raise SystemExit(
            'dictionary.ts does not cover every JP Exedra speaker used by '
            f'Chinese editing: {len(failures)} unique labels'
        )

    print(
        'EXEDRA_JP_SPEAKER_DICTIONARY_COMPLETE '
        f'txt_labels={txt_labels} json_labels={json_labels} '
        f'mapping_entries={len(mapping)}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
