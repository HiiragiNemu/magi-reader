#!/usr/bin/env python3
"""Stage only the generated paths owned by one Reader source workflow."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import PurePosixPath


COMMON_PREFIXES = (
    "website/public/data/",
)
COMMON_EXACT = frozenset(
    {
        "website/public/story_index.json",
        "website/public/search_index_manifest.exedra.json",
        "website/public/search_index_manifest.magireco.json",
        "artifacts/search-split/split_search_report.json",
    }
)
MODE_PREFIXES = {
    "tw": ("magiraexedra-translate-data-master/Scenarios_full/",),
    "jp": ("magiraexedra-source-master/Scenarios_full/",),
}
MODE_EXACT = {
    "tw": frozenset(
        {
            "artifacts/exedra_official_tw_import_report.json",
            "artifacts/tw_official_metadata.generated.json",
        }
    ),
    "jp": frozenset({"artifacts/exedra_jp_source_receipt.v1.json"}),
}


class StageError(RuntimeError):
    pass


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def _paths(payload: bytes) -> set[str]:
    return {
        item.decode("utf-8", errors="strict").replace("\\", "/")
        for item in payload.split(b"\0")
        if item
    }


def changed_paths() -> set[str]:
    tracked = _paths(_git("diff", "--name-only", "-z", "HEAD", "--"))
    untracked = _paths(_git("ls-files", "--others", "--exclude-standard", "-z"))
    return tracked | untracked


def allowed(path: str, mode: str) -> bool:
    normalized = PurePosixPath(path).as_posix()
    exact = COMMON_EXACT | MODE_EXACT[mode]
    prefixes = COMMON_PREFIXES + MODE_PREFIXES[mode]
    return normalized in exact or any(normalized.startswith(prefix) for prefix in prefixes)


def stage(mode: str) -> list[str]:
    before = changed_paths()
    rejected = sorted(path for path in before if not allowed(path, mode))
    if rejected:
        raise StageError(
            "workflow produced changes outside its machine-output allowlist: "
            + ", ".join(rejected[:20])
        )

    if not before:
        return []
    # Stage the already validated, exact changed paths.  This also records
    # deletions while avoiding Git errors for allowlisted roots that a small
    # fixture or a future source mode does not materialize.
    subprocess.run(["git", "add", "-A", "--", *sorted(before)], check=True)
    staged = sorted(_paths(_git("diff", "--cached", "--name-only", "-z")))
    rejected_staged = [path for path in staged if not allowed(path, mode)]
    if rejected_staged:
        raise StageError(
            "staged paths escaped the machine-output allowlist: "
            + ", ".join(rejected_staged[:20])
        )
    return staged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=tuple(MODE_PREFIXES))
    args = parser.parse_args(argv)
    try:
        staged = stage(args.mode)
    except (OSError, UnicodeError, subprocess.CalledProcessError, StageError) as exc:
        print(f"READER_AUTOMATION_STAGE_ERROR {exc}")
        return 1
    print(
        f"READER_AUTOMATION_STAGE_OK mode={args.mode} "
        f"paths={len(staged)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
