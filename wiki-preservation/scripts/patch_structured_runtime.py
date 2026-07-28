#!/usr/bin/env python3
"""Apply deterministic runtime fixes to structured-ui.js.

The structured layer coexists with the preservation reader. The patch makes
legacy navigation upgrades idempotent, cancels stale debounced list renders
when leaving a route, and renders a structured destination immediately after
changing the hash instead of relying solely on listener ordering.
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
    value = replace_once(
        value,
        "function routeStructured(path) {\n  const next = `#/${String(path).replace(/^\\/+/, '')}`;\n  if (location.hash === next) void renderStructuredRoute();\n  else location.hash = next;\n  scrollTo({ top: 0, behavior: 'smooth' });\n}",
        "function routeStructured(path) {\n  clearTimeout(window.__structuredCharacterTimer);\n  clearTimeout(window.__structuredVoiceTimer);\n  clearTimeout(window.__structuredLineTimer);\n  const next = `#/${String(path).replace(/^\\/+/, '')}`;\n  if (location.hash === next) {\n    void renderStructuredRoute();\n  } else {\n    location.hash = next;\n    queueMicrotask(() => void renderStructuredRoute());\n  }\n  scrollTo({ top: 0, behavior: 'smooth' });\n}",
    )
    marker = "const STRUCTURED_UI_VERSION = '5.0';"
    value = replace_once(
        value,
        marker,
        marker + "\nconst STRUCTURED_RUNTIME_REVISION = '5.1-idempotent-navigation;5.2-route-timer-isolation';",
    )
    path.write_text(value, encoding="utf-8")


if __name__ == "__main__":
    main()
