#!/usr/bin/env python3
"""Resolve and strictly validate Wiki-to-Reader update events."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

TRUSTED_PRODUCER = "madoka-exedra-wiki/ma-ex-data"
TW_EVENT_TYPE = "exedra_tw_source_v1"
JP_EVENT_TYPE = "exedra_jp_source_v1"
TW_RELEASE_RE = re.compile(
    r"^/madoka-exedra-wiki/ma-ex-data/releases/download/"
    r"(tw-wiki-source-v1-[0-9a-f]{64})/(exedra-tw-wiki-source-v1\.zip)$"
)
TW_CONTRACT_RE = re.compile(
    r"^/madoka-exedra-wiki/ma-ex-data/releases/download/"
    r"(tw-wiki-source-v1-[0-9a-f]{64})/(exedra-tw-sp-handoff\.v1\.json)$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class UpdateEventError(RuntimeError):
    """Raised when an event cannot be trusted by the Reader workflow."""


def _require_exact_keys(value: Mapping[str, Any], expected: set[str]) -> None:
    if set(value) != expected:
        raise UpdateEventError(
            f"payload fields differ: actual={sorted(value)} expected={sorted(expected)}"
        )


def _require_text(value: Any, field: str, *, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise UpdateEventError(f"{field} must be non-empty text <= {maximum} chars")
    return value.strip()


def _require_sha256(value: Any, field: str) -> str:
    result = _require_text(value, field, maximum=64)
    if result != result.lower() or SHA256_RE.fullmatch(result) is None:
        raise UpdateEventError(f"{field} must be a lowercase SHA-256")
    return result


def _require_commit(value: Any, field: str) -> str:
    result = _require_text(value, field, maximum=40)
    if result != result.lower() or COMMIT_RE.fullmatch(result) is None:
        raise UpdateEventError(f"{field} must be a full lowercase Git commit SHA")
    return result


def _require_tw_url(value: Any) -> str:
    result = _require_text(value, "source_url", maximum=2048)
    parsed = urlsplit(result)
    if (
        parsed.scheme != "https"
        or parsed.netloc.casefold() != "github.com"
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or TW_RELEASE_RE.fullmatch(parsed.path) is None
    ):
        raise UpdateEventError(
            "source_url must be the canonical immutable ma-ex-data TW v1 Release asset"
        )
    return result


def _tw_release_parts(source_url: str) -> tuple[str, str, str]:
    parts = urlsplit(source_url).path.strip("/").split("/")
    # owner/repository/releases/download/tag/asset
    return (f"{parts[0]}/{parts[1]}", parts[4], parts[5])


def _require_canonical_url(value: Any, field: str, expected_path: str) -> str:
    result = _require_text(value, field, maximum=2048)
    parsed = urlsplit(result)
    if (
        parsed.scheme != "https"
        or parsed.netloc.casefold() != "github.com"
        or parsed.path != expected_path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise UpdateEventError(f"{field} is not the canonical immutable GitHub URL")
    return result


def resolve_tw_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    expected = {
        "schemaVersion", "releaseUrl", "archiveUrl", "archiveSha256",
        "contractUrl", "contractSha256", "sourceRevisions",
    }
    _require_exact_keys(payload, expected)
    if payload.get("schemaVersion") != 1:
        raise UpdateEventError("schemaVersion must be 1")
    archive_url = _require_tw_url(payload.get("archiveUrl"))
    source_repository, release_tag, asset_name = _tw_release_parts(archive_url)
    archive_sha = _require_sha256(payload.get("archiveSha256"), "archiveSha256")
    if release_tag != f"tw-wiki-source-v1-{archive_sha}":
        raise UpdateEventError("Release tag is not content-addressed by archiveSha256")
    release_url = _require_canonical_url(
        payload.get("releaseUrl"),
        "releaseUrl",
        f"/{TRUSTED_PRODUCER}/releases/tag/{release_tag}",
    )
    contract_url = _require_canonical_url(
        payload.get("contractUrl"),
        "contractUrl",
        f"/{TRUSTED_PRODUCER}/releases/download/{release_tag}/exedra-tw-sp-handoff.v1.json",
    )
    if TW_CONTRACT_RE.fullmatch(urlsplit(contract_url).path) is None:
        raise UpdateEventError("contractUrl is not the canonical v1 contract asset")
    revisions = payload.get("sourceRevisions")
    if not isinstance(revisions, Mapping):
        raise UpdateEventError("sourceRevisions must be an object")
    _require_exact_keys(revisions, {"sp", "scenarios", "manifests"})
    return {
        "release_url": release_url,
        "archive_url": archive_url,
        "source_repository": source_repository,
        "release_tag": release_tag,
        "asset_name": asset_name,
        "archive_sha256": archive_sha,
        "contract_url": contract_url,
        "contract_sha256": _require_sha256(payload.get("contractSha256"), "contractSha256"),
        "sp_revision": _require_text(revisions.get("sp"), "sourceRevisions.sp"),
        "scenario_revision": _require_text(revisions.get("scenarios"), "sourceRevisions.scenarios"),
        "manifest_revision": _require_text(revisions.get("manifests"), "sourceRevisions.manifests"),
    }


def resolve_jp_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    expected = {
        "schemaVersion", "commitUrl", "archiveUrl", "commitSha", "sourceRevision",
    }
    _require_exact_keys(payload, expected)
    if payload.get("schemaVersion") != 1:
        raise UpdateEventError("schemaVersion must be 1")
    commit = _require_commit(payload.get("commitSha"), "commitSha")
    revision = _require_commit(payload.get("sourceRevision"), "sourceRevision")
    if revision != commit:
        raise UpdateEventError("sourceRevision must equal commitSha")
    commit_url = _require_canonical_url(
        payload.get("commitUrl"), "commitUrl", f"/{TRUSTED_PRODUCER}/commit/{commit}"
    )
    archive_url = _require_canonical_url(
        payload.get("archiveUrl"), "archiveUrl", f"/{TRUSTED_PRODUCER}/archive/{commit}.zip"
    )
    return {
        "source_repository": TRUSTED_PRODUCER,
        "commit_url": commit_url,
        "archive_url": archive_url,
        "source_commit": commit,
        "source_revision": revision,
    }


def load_dispatch_payload(event_path: Path, expected_action: str) -> dict[str, Any]:
    value = json.loads(event_path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or value.get("action") != expected_action:
        raise UpdateEventError(f"repository_dispatch action must be {expected_action}")
    payload = value.get("client_payload")
    if not isinstance(payload, dict):
        raise UpdateEventError("repository_dispatch client_payload must be an object")
    return payload


def write_github_output(path: Path, values: Mapping[str, str]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as output:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise UpdateEventError(f"output contains a newline: {key}")
            output.write(f"{key}={value}\n")


def _manual_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.mode == "tw":
        return {
            "schemaVersion": 1,
            "releaseUrl": args.release_url,
            "archiveUrl": args.archive_url,
            "archiveSha256": args.archive_sha256,
            "contractUrl": args.contract_url,
            "contractSha256": args.contract_sha256,
            "sourceRevisions": {
                "sp": args.sp_revision,
                "scenarios": args.scenario_revision,
                "manifests": args.manifest_revision,
            },
        }
    return {
        "schemaVersion": 1,
        "commitUrl": args.commit_url,
        "archiveUrl": args.archive_url,
        "commitSha": args.source_commit,
        "sourceRevision": args.source_commit,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("tw", "jp"))
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--event-path", type=Path)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--release-url")
    parser.add_argument("--archive-url")
    parser.add_argument("--archive-sha256")
    parser.add_argument("--contract-url")
    parser.add_argument("--contract-sha256")
    parser.add_argument("--sp-revision")
    parser.add_argument("--scenario-revision")
    parser.add_argument("--manifest-revision")
    parser.add_argument("--source-commit")
    parser.add_argument("--commit-url")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        expected_action = TW_EVENT_TYPE if args.mode == "tw" else JP_EVENT_TYPE
        if args.event_name == "repository_dispatch":
            if args.event_path is None:
                raise UpdateEventError("--event-path is required for repository_dispatch")
            payload = load_dispatch_payload(args.event_path, expected_action)
        elif args.event_name == "workflow_dispatch":
            payload = _manual_payload(args)
        else:
            raise UpdateEventError(f"unsupported event: {args.event_name}")
        result = resolve_tw_payload(payload) if args.mode == "tw" else resolve_jp_payload(payload)
        if args.github_output is not None:
            write_github_output(args.github_output, result)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except (OSError, json.JSONDecodeError, UpdateEventError) as exc:
        print(f"READER_UPDATE_EVENT_ERROR {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
