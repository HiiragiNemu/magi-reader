#!/usr/bin/env python3
"""Create support files required by shared Reader code in public archive mode.

The public story archive deliberately disables machine-translation review and
submission management.  Shared TypeScript modules still import the generated
manifest at compile time, so the public build writes an explicit empty manifest
instead of carrying private/review workflow state into the deployed site.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$", re.I)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, default=Path("website/public"))
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()

    if not COMMIT_RE.fullmatch(args.commit):
        raise RuntimeError("--commit must be an immutable 40-character Git SHA")

    public = args.public.resolve()
    data = public / "data"
    data.mkdir(parents=True, exist_ok=True)
    target = data / "machine_translation_manifest.generated.json"
    manifest = {
        "version": 3,
        "definition": "Public read-only story archive; machine-translation review is disabled.",
        "source_commit": args.commit,
        "translation_commit": args.commit,
        "total": 0,
        "entries": [],
        "unreferenced_changed_json_count": 0,
        "unreferenced_changed_json_paths": [],
        "unmatched_changed_txt_identities": [],
        "missing_repository_txt_paths": [],
        "unmatched_source_identities": [],
    }
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    loaded = json.loads(target.read_text(encoding="utf-8"))
    if loaded.get("total") != 0 or loaded.get("entries") != []:
        raise RuntimeError(f"invalid public machine-translation manifest: {loaded}")
    print(json.dumps({"path": str(target), **manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
