#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request

REPO = os.environ["GITHUB_REPOSITORY"]
SITE = "https://magireader-exedra-cn-test.crynetsystemscell.workers.dev"
EXPECTED_TOTAL = 507


def github_json(path: str) -> dict:
    output = subprocess.check_output(
        ["gh", "api", path], text=True, encoding="utf-8"
    )
    return json.loads(output)


def get_json(path: str) -> dict:
    request = urllib.request.Request(
        SITE + path,
        headers={"User-Agent": "magi-reader-trusted-live-verifier"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {path}")
        return json.loads(response.read().decode("utf-8"))


def get_text(path: str) -> str:
    request = urllib.request.Request(
        SITE + path,
        headers={"User-Agent": "magi-reader-trusted-live-verifier"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {path}")
        return response.read().decode("utf-8", "replace")


def main() -> int:
    expected_commit = github_json(
        f"repos/{REPO}/git/ref/heads/EXEDRA-TEST"
    )["object"]["sha"]
    last = ""
    for attempt in range(1, 91):
        try:
            config = get_json("/api/proofreading/config")
            machine = get_json("/api/proofreading/machine-status")
            ready = (
                config.get("source_revision") == expected_commit
                and machine.get("total") == EXPECTED_TOTAL
                and machine.get("definition")
                == "magireco_cn_txt_absent_from_trusted_main"
                and machine.get("remaining")
                == EXPECTED_TOTAL - machine.get("verified", 0)
                and len(machine.get("machine_translation_ids", []))
                == EXPECTED_TOTAL
            )
            last = (
                f"source={config.get('source_revision')} "
                f"total={machine.get('total')} "
                f"definition={machine.get('definition')}"
            )
            if ready:
                break
        except Exception as exc:  # propagation/transient network errors
            last = repr(exc)
        if attempt == 90:
            raise SystemExit(
                f"Merged EXEDRA Worker did not propagate: expected={expected_commit} last={last}"
            )
        time.sleep(5)

    stories = get_json("/story_index.json")
    machine_ids = set(map(str, machine.get("machine_translation_ids", [])))
    forbidden = [
        {
            "id": str(story.get("id")),
            "category": story.get("category"),
            "title": story.get("title"),
        }
        for story in stories
        if str(story.get("id")) in machine_ids
        and story.get("category") in {"main_story", "scene0_main"}
    ]
    if forbidden:
        raise SystemExit(f"Main-line stories remain machine-marked: {forbidden[:20]}")
    if "states" in machine:
        raise SystemExit("Public API leaked private review states")
    if len(get_text("/")) < 500 or len(get_text("/review/machine-translations")) < 500:
        raise SystemExit("Live page content is incomplete")

    print(
        "MERGED_EXEDRA_LIVE_OK "
        f"commit={expected_commit} total={machine['total']} "
        f"verified={machine['verified']} remaining={machine['remaining']} "
        f"main_line_intersection={len(forbidden)} stories={len(stories)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
