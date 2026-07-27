#!/usr/bin/env python3
from __future__ import annotations

import collections
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import PurePosixPath

MAIN = "origin/main"
CURRENT = "origin/EXEDRA-TEST"
MAGIRECO = "magireco-translate-data-master/Scenarios_full/"
EXEDRA_PREFIXES = (
    "magiraexedra-source-master/",
    "magiraexedra-translate-data-master/",
)


def git_bytes(*args: str) -> bytes:
    proc = subprocess.run(["git", *args], check=False, capture_output=True)
    if proc.returncode:
        raise SystemExit(proc.stderr.decode("utf-8", "replace"))
    return proc.stdout


def tree(ref: str, prefix: str) -> dict[str, str]:
    raw = git_bytes(
        "ls-tree", "-r", "-z", "--format=%(objectname)\t%(path)", ref, "--", prefix
    )
    result: dict[str, str] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        sha, path = record.decode("utf-8").split("\t", 1)
        result[path] = sha
    return result


def ext_counts(paths: list[str]) -> dict[str, int]:
    return dict(
        sorted(
            collections.Counter(
                PurePosixPath(path).suffix.lower() or "<none>" for path in paths
            ).items()
        )
    )


def main() -> int:
    archive_path = sys.argv[1]
    main_tree = tree(MAIN, MAGIRECO)
    current_tree = tree(CURRENT, MAGIRECO)
    main_paths = set(main_tree)
    current_paths = set(current_tree)
    added = sorted(current_paths - main_paths)
    deleted = sorted(main_paths - current_paths)
    overwritten = sorted(
        path
        for path in main_paths & current_paths
        if main_tree[path] != current_tree[path]
    )
    unchanged = sorted(
        path
        for path in main_paths & current_paths
        if main_tree[path] == current_tree[path]
    )

    summary = {
        "main_ref": MAIN,
        "current_ref": CURRENT,
        "magireco_main_total": len(main_tree),
        "magireco_current_total": len(current_tree),
        "unchanged_trusted": len(unchanged),
        "added_machine_candidates": len(added),
        "overwritten_human_untrusted": len(overwritten),
        "deleted_human_untrusted": len(deleted),
        "added_extensions": ext_counts(added),
        "overwritten_extensions": ext_counts(overwritten),
        "deleted_extensions": ext_counts(deleted),
        "added_main_story": sum("/main_story/" in path for path in added),
        "overwritten_main_story": sum("/main_story/" in path for path in overwritten),
        "deleted_main_story": sum("/main_story/" in path for path in deleted),
    }

    with zipfile.ZipFile(archive_path) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        magireco_members: list[tuple[zipfile.ZipInfo, str]] = []
        exedra_members = []
        other_members = []
        for info in members:
            name = info.filename.replace("\\", "/")
            pos = name.find(MAGIRECO)
            if pos >= 0:
                magireco_members.append((info, name[pos:]))
            elif any(prefix in name for prefix in EXEDRA_PREFIXES):
                exedra_members.append(info)
            else:
                other_members.append(info)

        provenance = collections.Counter()
        for info, path in magireco_members:
            data = archive.read(info)
            digest = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
            if path in main_tree and digest == main_tree[path]:
                provenance["main_exact"] += 1
            elif path in current_tree and digest == current_tree[path]:
                provenance["current_exact_not_main"] += 1
            elif path in main_tree or path in current_tree:
                provenance["known_path_content_mismatch"] += 1
            else:
                provenance["unknown_path"] += 1

        summary.update(
            {
                "release_member_total": len(members),
                "release_magireco_members": len(magireco_members),
                "release_exedra_members": len(exedra_members),
                "release_other_members": len(other_members),
                "release_provenance": dict(sorted(provenance.items())),
            }
        )

    subprocess.run(["git", "merge-base", "--is-ancestor", MAIN, CURRENT], check=True)
    if not added:
        raise SystemExit("No Magia Record additions found")

    print("TRUST_AUDIT_JSON=" + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print("OVERWRITTEN_HUMAN_SAMPLE_BEGIN")
    for path in overwritten[:25]:
        print(path)
    print("OVERWRITTEN_HUMAN_SAMPLE_END")
    print("ADDED_MACHINE_SAMPLE_BEGIN")
    for path in added[:25]:
        print(path)
    print("ADDED_MACHINE_SAMPLE_END")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
