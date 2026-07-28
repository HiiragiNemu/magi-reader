#!/usr/bin/env python3
"""Patch structured-ui.js to make legacy-navigation upgrades idempotent.

Assigning ``textContent`` inside a MutationObserver callback creates another
mutation even when the visible string is unchanged.  The original v5 bridge
therefore kept its observer busy indefinitely.  This build-time patch changes
those writes into guarded, idempotent updates.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(f"structured runtime patch target not found: {old[:120]}")
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    path = args.path.resolve()
    value = path.read_text(encoding="utf-8")
    value = replace_once(
        value,
        "if (wiki && wiki.closest('nav')) wiki.textContent = 'Wiki正文';",
        "if (wiki && wiki.closest('nav') && wiki.textContent !== 'Wiki正文') wiki.textContent = 'Wiki正文';",
    )
    value = replace_once(
        value,
        "if (people) {\n    people.dataset.route = 'characters';\n    people.textContent = '人物';\n  }",
        "if (people) {\n    if (people.dataset.route !== 'characters') people.dataset.route = 'characters';\n    if (people.textContent !== '人物') people.textContent = '人物';\n  }",
    )
    marker = "const STRUCTURED_UI_VERSION = '5.0';"
    value = replace_once(
        value,
        marker,
        marker + "\nconst STRUCTURED_RUNTIME_REVISION = '5.1-idempotent-navigation';",
    )
    path.write_text(value, encoding="utf-8")


if __name__ == "__main__":
    main()
