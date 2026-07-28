#!/usr/bin/env python3
"""Reconstruct a GitHub branch through REST tree/blob endpoints.

Use this when `git clone` or `codeload.github.com` is blocked but
`api.github.com` remains reachable. No GitHub Actions and no third-party
packages are required.

Examples:
    py tools/github_api_checkout.py HiiragiNemu/magi-reader \
      --ref feature/exedra-cn-and-magireco-voice --output D:\work\magi-reader

    py tools/github_api_checkout.py HiiragiNemu/magi-reader \
      --ref feature/exedra-cn-and-magireco-voice --output D:\work\website-only \
      --include website --include package.json --zip D:\work\website-only.zip

Authentication is read from GH_TOKEN or GITHUB_TOKEN. Public repositories can
be downloaded without a token, but authenticated requests have a larger rate
limit.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
import shutil
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

DEFAULT_API_ROOT = "https://api.github.com"
MAX_BLOB_BYTES = 100 * 1024 * 1024
DEFAULT_WORKERS = 8


class CheckoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class TreeEntry:
    path: str
    mode: str
    kind: str
    sha: str
    size: int | None


class GitHubApi:
    def __init__(self, api_root: str, token: str, retries: int = 4) -> None:
        self.api_root = api_root.rstrip("/")
        self.token = token.strip()
        self.retries = retries

    def request_json(self, path: str) -> Any:
        url = path if path.startswith("http") else f"{self.api_root}{path}"
        last_error: Exception | None = None
        for attempt in range(self.retries):
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "MagiReader-GitHub-API-checkout/1",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    body = response.read()
                return json.loads(body.decode("utf-8"))
            except urllib.error.HTTPError as error:
                body = error.read().decode("utf-8", errors="replace")[:1000]
                if error.code in {403, 429, 500, 502, 503, 504} and attempt + 1 < self.retries:
                    retry_after = error.headers.get("Retry-After")
                    delay = int(retry_after) if retry_after and retry_after.isdigit() else min(30, 2**attempt)
                    time.sleep(delay)
                    last_error = CheckoutError(f"GitHub API HTTP {error.code}: {body}")
                    continue
                raise CheckoutError(f"GitHub API HTTP {error.code}: {url}: {body}") from error
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                last_error = error
                if attempt + 1 < self.retries:
                    time.sleep(min(30, 2**attempt))
                    continue
                break
        raise CheckoutError(f"GitHub API request failed: {url}: {last_error}")

    def blob(self, owner: str, repo: str, sha: str) -> bytes:
        value = self.request_json(f"/repos/{owner}/{repo}/git/blobs/{sha}")
        if not isinstance(value, dict) or value.get("encoding") != "base64":
            raise CheckoutError(f"Unexpected blob response: {sha}")
        encoded = value.get("content")
        if not isinstance(encoded, str):
            raise CheckoutError(f"Blob has no content: {sha}")
        try:
            data = base64.b64decode(encoded, validate=False)
        except ValueError as error:
            raise CheckoutError(f"Invalid base64 blob: {sha}") from error
        if len(data) > MAX_BLOB_BYTES:
            raise CheckoutError(f"Blob exceeds 100 MiB: {sha}")
        git_sha = hashlib.sha1(
            f"blob {len(data)}\0".encode("ascii") + data,
            usedforsecurity=False,
        ).hexdigest()
        if git_sha != sha:
            raise CheckoutError(f"Blob SHA mismatch: expected {sha}, got {git_sha}")
        return data


def parse_repo(value: str) -> tuple[str, str]:
    parts = value.strip().strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        raise CheckoutError("repository must be owner/name")
    return parts[0], parts[1]


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise CheckoutError(f"Unsafe Git tree path: {value!r}")
    if "\\" in value or "\x00" in value:
        raise CheckoutError(f"Unsafe Git tree path: {value!r}")
    return path


def included(path: str, prefixes: tuple[str, ...]) -> bool:
    if not prefixes:
        return True
    normalized = path.strip("/")
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}/")
        for prefix in prefixes
    )


def commit_tree_sha(api: GitHubApi, owner: str, repo: str, ref: str) -> tuple[str, str]:
    escaped = urllib.parse.quote(ref, safe="")
    value = api.request_json(f"/repos/{owner}/{repo}/commits/{escaped}")
    if not isinstance(value, dict):
        raise CheckoutError("Unexpected commit response")
    commit_sha = value.get("sha")
    commit = value.get("commit")
    tree = commit.get("tree") if isinstance(commit, dict) else None
    tree_sha = tree.get("sha") if isinstance(tree, dict) else None
    if not isinstance(commit_sha, str) or not isinstance(tree_sha, str):
        raise CheckoutError("Commit response has no commit/tree SHA")
    return commit_sha, tree_sha


def parse_tree_entries(value: Any) -> tuple[list[TreeEntry], bool]:
    if not isinstance(value, dict) or not isinstance(value.get("tree"), list):
        raise CheckoutError("Unexpected tree response")
    entries: list[TreeEntry] = []
    for raw in value["tree"]:
        if not isinstance(raw, dict):
            raise CheckoutError("Tree entry is not an object")
        path = raw.get("path")
        mode = raw.get("mode")
        kind = raw.get("type")
        sha = raw.get("sha")
        size = raw.get("size")
        if not all(isinstance(item, str) for item in (path, mode, kind, sha)):
            raise CheckoutError("Tree entry is incomplete")
        safe_relative(path)
        entries.append(TreeEntry(path, mode, kind, sha, size if isinstance(size, int) else None))
    return entries, bool(value.get("truncated"))


def recursive_tree(api: GitHubApi, owner: str, repo: str, tree_sha: str) -> list[TreeEntry]:
    value = api.request_json(f"/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1")
    entries, truncated = parse_tree_entries(value)
    if not truncated:
        return entries

    result: list[TreeEntry] = []

    def walk(sha: str, prefix: str = "") -> None:
        current, current_truncated = parse_tree_entries(
            api.request_json(f"/repos/{owner}/{repo}/git/trees/{sha}")
        )
        if current_truncated:
            raise CheckoutError(f"Non-recursive Git tree unexpectedly truncated: {sha}")
        for entry in current:
            full_path = f"{prefix}/{entry.path}" if prefix else entry.path
            if entry.kind == "tree":
                walk(entry.sha, full_path)
            else:
                result.append(
                    TreeEntry(full_path, entry.mode, entry.kind, entry.sha, entry.size)
                )

    walk(tree_sha)
    return result


def destination(root: Path, relative: PurePosixPath) -> Path:
    candidate = root.joinpath(*relative.parts)
    root_resolved = root.resolve()
    candidate_parent = candidate.parent.resolve(strict=False)
    try:
        candidate_parent.relative_to(root_resolved)
    except ValueError as error:
        raise CheckoutError(f"Destination escapes output root: {relative}") from error
    return candidate


def write_regular(path: Path, data: bytes, executable: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(data)
    mode = 0o755 if executable else 0o644
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def write_symlink(path: Path, data: bytes, output_root: Path) -> None:
    try:
        target_text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CheckoutError(f"Symlink target is not UTF-8: {path}") from error
    target = PurePosixPath(target_text)
    if target.is_absolute() or any(part == ".." for part in target.parts):
        raise CheckoutError(f"Unsafe symlink target: {path}: {target_text!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    try:
        os.symlink(target_text, path)
    except (OSError, NotImplementedError):
        # Windows without Developer Mode: preserve the target in a deterministic sidecar.
        write_regular(path.with_suffix(path.suffix + ".symlink"), data, False)


def zip_tree(root: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                archive.writestr(path.relative_to(root).as_posix() + ".symlink", os.readlink(path))
            elif path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    os.replace(temporary, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", help="owner/name")
    parser.add_argument("--ref", default="main")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include", action="append", default=[], help="path prefix; repeatable")
    parser.add_argument("--zip", dest="zip_path", type=Path)
    parser.add_argument("--api-root", default=DEFAULT_API_ROOT)
    parser.add_argument("--token", default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    owner, repo = parse_repo(args.repository)
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        if not args.force:
            raise CheckoutError(f"Output directory is not empty: {output}; use --force")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    prefixes = tuple(
        safe_relative(value.strip("/")).as_posix()
        for value in args.include
    )
    api = GitHubApi(args.api_root, args.token)
    commit_sha, tree_sha = commit_tree_sha(api, owner, repo, args.ref)
    entries = [
        entry
        for entry in recursive_tree(api, owner, repo, tree_sha)
        if included(entry.path, prefixes)
    ]
    blobs = [entry for entry in entries if entry.kind == "blob"]
    submodules = [entry for entry in entries if entry.kind == "commit" or entry.mode == "160000"]
    if submodules:
        names = ", ".join(entry.path for entry in submodules[:5])
        raise CheckoutError(f"Submodules are not supported: {names}")

    print(f"commit={commit_sha} tree={tree_sha} files={len(blobs)}")

    def fetch(entry: TreeEntry) -> tuple[TreeEntry, bytes]:
        if entry.size is not None and entry.size > MAX_BLOB_BYTES:
            raise CheckoutError(f"Blob exceeds 100 MiB: {entry.path}")
        return entry, api.blob(owner, repo, entry.sha)

    workers = min(32, max(1, args.workers))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch, entry) for entry in blobs]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            entry, data = future.result()
            path = destination(output, safe_relative(entry.path))
            if entry.mode == "120000":
                write_symlink(path, data, output)
            else:
                write_regular(path, data, entry.mode == "100755")
            if index % 250 == 0 or index == len(blobs):
                print(f"written {index}/{len(blobs)}")

    metadata = {
        "version": 1,
        "repository": f"{owner}/{repo}",
        "ref": args.ref,
        "commit": commit_sha,
        "tree": tree_sha,
        "fileCount": len(blobs),
        "includes": list(prefixes),
    }
    (output / ".github-api-checkout.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.zip_path:
        zip_tree(output, args.zip_path.resolve())
        print(f"zip={args.zip_path.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckoutError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
