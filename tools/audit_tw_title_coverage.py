#!/usr/bin/env python3
"""Report which official-TW stories have deterministic display titles.

This is an audit only.  It never translates or guesses a title.  Structural
chapter names and gallery-title tables are accepted only when included in the
validated TW metadata; unresolved technical folder names remain explicitly
listed for human/source-provider follow-up.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "website/public/story_index.json"
DEFAULT_OUTPUT = ROOT / "artifacts/tw_title_coverage.audit.json"
TECHNICAL = re.compile(
    r"^(?:sub|main|portrait|character|reaction|act|contents|map|pp|play|flashback)[ _-]",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--story-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    stories = json.loads(args.story_index.read_text(encoding="utf-8-sig"))
    official = [
        story for story in stories
        if isinstance(story, dict)
        and str(story.get("category") or "").startswith("exedra_")
        and story.get("official_tw") is True
    ]
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for story in official:
        title = str(story.get("title") or "").strip()
        folder = str(story.get("folder") or "").strip()
        item = {
            "id": story.get("id"),
            "category": story.get("category"),
            "sourceIdentity": story.get("source_identity"),
            "title": title,
            "folder": folder,
            "officialStoryTitles": story.get("official_tw_story_titles") or [],
            "officialChapterTitle": story.get("official_tw_chapter_title") or "",
            "reason": "",
        }
        if item["officialStoryTitles"] or item["officialChapterTitle"]:
            item["reason"] = "official_tw_manifest_title"
            resolved.append(item)
        elif title and not TECHNICAL.match(title.replace("_", " ")):
            item["reason"] = "existing_non_technical_title_preserved"
            resolved.append(item)
        else:
            item["reason"] = "tw_bundle_missing_gallery_title_manifest"
            unresolved.append(item)
    report = {
        "version": 1,
        "policy": "exact_tw_manifest_titles_only_no_guessing",
        "storyIndex": str(args.story_index.resolve()),
        "storyIndexSha256": sha256(args.story_index),
        "counts": {
            "officialTwStories": len(official),
            "resolvedDisplayTitles": len(resolved),
            "unresolvedDisplayTitles": len(unresolved),
        },
        "resolved": resolved,
        "unresolved": unresolved,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "TW_TITLE_AUDIT_OK "
        f"official={len(official)} resolved={len(resolved)} unresolved={len(unresolved)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
