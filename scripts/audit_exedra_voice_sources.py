#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "website/public/data/machine_translation_manifest.generated.json"


def github_json(path: str):
    token = os.environ.get("GH_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "magi-reader-source-audit",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"https://api.github.com/{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def repo_tree(repo: str):
    try:
        meta = github_json(f"repos/{repo}")
        branch = meta["default_branch"]
        ref = github_json(f"repos/{repo}/git/ref/heads/{urllib.parse.quote(branch, safe='')}")
        commit = github_json(f"repos/{repo}/git/commits/{ref['object']['sha']}")
        tree = github_json(f"repos/{repo}/git/trees/{commit['tree']['sha']}?recursive=1")
        return {
            "ok": True,
            "default_branch": branch,
            "tree": tree.get("tree", []),
            "tree_truncated": bool(tree.get("truncated")),
        }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code}", "tree": []}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tree": []}


def count_local_exedra():
    result = {}
    for language, base in {
        "jp": ROOT / "magiraexedra-source-master/Scenarios_full",
        "cn": ROOT / "magiraexedra-translate-data-master/Scenarios_full",
    }.items():
        files = [p for p in base.rglob("*") if p.is_file()] if base.exists() else []
        result[language] = {
            "files": len(files),
            "json": sum(p.suffix.lower() == ".json" for p in files),
            "txt": sum(p.suffix.lower() == ".txt" for p in files),
            "directories": len({p.parent.relative_to(base).as_posix() for p in files}),
        }
    return result


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = manifest["entries"]
    magireco_dirs = {(e["category"], e["folder"]) for e in entries}
    directory_counts = Counter(category for category, _folder in magireco_dirs)

    tot = repo_tree("HiiragiNemu/io.kamihama.totentanz")
    general = [
        item for item in tot["tree"]
        if item.get("type") == "blob" and "/scenario/general/" in f"/{item.get('path','')}".lower()
    ]
    if not general:
        general = [
            item for item in tot["tree"]
            if item.get("type") == "blob"
            and "scenario" in item.get("path", "").lower()
            and "general" in item.get("path", "").lower()
        ]

    viewer = repo_tree("HiiragiNemu/MagiaExedraLive2DViewerPersonal")
    voice_candidates = [
        item["path"] for item in viewer["tree"]
        if item.get("type") == "blob"
        and any(key in item.get("path", "").lower() for key in ("voice", "scenario", "board"))
    ]

    report = {
        "magireco_machine_story_total": len(entries),
        "magireco_machine_directory_total": len(magireco_dirs),
        "magireco_machine_stories_by_category": dict(Counter(e["category"] for e in entries)),
        "magireco_machine_directories_by_category": dict(directory_counts),
        "local_exedra": count_local_exedra(),
        "totentanz": {
            **{k: v for k, v in tot.items() if k != "tree"},
            "scenario_general_file_total": len(general),
            "scenario_general_extensions": dict(Counter(Path(i["path"]).suffix.lower() or "<none>" for i in general)),
            "scenario_general_sample": [i["path"] for i in general[:40]],
        },
        "live2d_viewer": {
            **{k: v for k, v in viewer.items() if k != "tree"},
            "voice_candidate_total": len(voice_candidates),
            "voice_candidate_sample": voice_candidates[:80],
        },
    }
    output = ROOT / "artifacts/exedra_voice_source_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
