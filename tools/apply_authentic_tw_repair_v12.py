#!/usr/bin/env python3
"""Repair final regression tests and canonical speaker import plumbing."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUMAN_IMPORTER = ROOT / "tools/import_exedra_human_text.py"
TW_TEST = ROOT / "tests/test_tw_authentic_scenario.py"


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} replacement count={count}; expected 1"
        )
    path.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")


def main() -> int:
    replace_once(
        HUMAN_IMPORTER,
        "import import_exedra_official_tw as common  # noqa: E402\n",
        "import import_exedra_official_tw as common  # noqa: E402\n"
        "from tw_authentic_scenario import (  # noqa: E402\n"
        "    translate_speaker as canonicalize_speaker,\n"
        ")\n",
    )
    replace_once(
        HUMAN_IMPORTER,
        "                        common.translate_speaker(jp_name, mapping)\n",
        "                        canonicalize_speaker(jp_name, mapping)\n",
    )
    replace_once(
        TW_TEST,
        '            self.assertNotEqual(hashes["jp"], hashes["cn"])\n',
        '            self.assertEqual(hashes["jp"], hashes["cn"])\n'
        '            self.assertTrue(\n'
        '                report["sections"][0]["speakerSequenceMatches"]\n'
        '            )\n',
    )
    print("AUTHENTIC_TW_FINAL_REGRESSION_REPAIR_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
