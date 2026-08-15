#!/usr/bin/env python3
"""Repair final JavaScript deployment and Exedra event-alignment tests."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOUDFLARE_TEST = ROOT / "website/tests/cloudflare-deployment.test.mjs"
EVENT_TEST = ROOT / "website/tests/exedra-event-alignment.test.mjs"


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
        CLOUDFLARE_TEST,
        "  assert.match(workflow, /access-control-allow-origin/u);\n",
        "  assert.match(\n"
        "    workflow,\n"
        "    /cross-origin-resource-policy: same-origin/u,\n"
        "  );\n",
    )
    replace_once(
        EVENT_TEST,
        "  assert.match(reader, /isExedraStory,\n\\s*\\]\\);/u);\n",
        "  assert.match(reader, /isExedraStory,\\s*\\]\\);/u);\n",
    )
    print("AUTHENTIC_TW_JAVASCRIPT_TEST_REPAIR_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
