#!/usr/bin/env python3
"""Materialize and verify deploy-only physical chunks for split full-text search.

The canonical payload remains under ``artifacts/search-split`` and is ignored by
Git.  The committed v2 manifests already describe exact 1 MiB logical chunks.
This tool writes those same bytes to ``website/public/search-chunks`` only for a
Cloudflare build, or verifies a local/deployed chunk tree against the committed
manifest.  No search text is transformed here.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PUBLIC_ROOT = ROOT / "website/public"
PAYLOAD_ROOT = ROOT / "artifacts/search-split"
SCOPES = ("magireco", "exedra")
PART_NAME_WIDTH = 4
MAX_HTTP_WORKERS = 8


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(root: Path, scope: str) -> dict[str, Any]:
    path = root / f"search_index_manifest.{scope}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != 2:
        raise RuntimeError(f"{scope} 搜索清单必须是 v2：{path}")
    sha256 = str(value.get("sha256") or "").lower()
    object_key = str(value.get("object_key") or "")
    if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
        raise RuntimeError(f"{scope} 搜索清单 sha256 无效")
    if object_key != f"search/{scope}/{sha256}.json":
        raise RuntimeError(f"{scope} 搜索清单 object_key 无效：{object_key!r}")
    total_bytes = value.get("bytes")
    chunk_bytes = value.get("chunk_bytes")
    chunks = value.get("chunks")
    if (
        not isinstance(total_bytes, int)
        or isinstance(total_bytes, bool)
        or total_bytes <= 0
        or chunk_bytes != 1024 * 1024
        or not isinstance(chunks, list)
        or not chunks
        or len(chunks) != (total_bytes + chunk_bytes - 1) // chunk_bytes
    ):
        raise RuntimeError(f"{scope} 搜索清单分块结构无效")
    running = 0
    for index, chunk in enumerate(chunks):
        final = index == len(chunks) - 1
        if not isinstance(chunk, dict):
            raise RuntimeError(f"{scope} 第 {index + 1} 块不是对象")
        size = chunk.get("bytes")
        digest = str(chunk.get("sha256") or "").lower()
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
            or size > chunk_bytes
            or (not final and size != chunk_bytes)
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise RuntimeError(f"{scope} 第 {index + 1} 块清单无效")
        running += size
    if running != total_bytes:
        raise RuntimeError(f"{scope} 分块总大小与清单不一致：{running} != {total_bytes}")
    return value


def part_name(index: int) -> str:
    return f"{index:0{PART_NAME_WIDTH}d}.part"


def expected_part_path(root: Path, scope: str, sha256: str, index: int) -> Path:
    return root / "search-chunks" / scope / sha256 / part_name(index)


def materialize_scope(public_root: Path, staging_root: Path, scope: str) -> tuple[int, int, str]:
    manifest = load_manifest(public_root, scope)
    payload = PAYLOAD_ROOT / f"search_content.{scope}.json"
    if not payload.is_file() or payload.is_symlink():
        raise RuntimeError(f"缺少 {scope} 搜索大文件：{payload}")

    expected_total = int(manifest["bytes"])
    expected_global = str(manifest["sha256"])
    target = staging_root / scope / expected_global
    target.mkdir(parents=True, exist_ok=False)
    overall = hashlib.sha256()
    total = 0

    with payload.open("rb") as handle:
        for index, chunk in enumerate(manifest["chunks"]):
            size = int(chunk["bytes"])
            data = handle.read(size)
            if len(data) != size:
                raise RuntimeError(
                    f"{scope} 搜索大文件提前结束：chunk={index + 1} {len(data)} != {size}"
                )
            digest = sha256_bytes(data)
            if digest != chunk["sha256"]:
                raise RuntimeError(
                    f"{scope} 第 {index + 1} 块哈希不一致：{digest} != {chunk['sha256']}"
                )
            (target / part_name(index)).write_bytes(data)
            overall.update(data)
            total += size
        if handle.read(1):
            raise RuntimeError(f"{scope} 搜索大文件存在清单之外的尾部数据")

    if total != expected_total or overall.hexdigest() != expected_global:
        raise RuntimeError(
            f"{scope} 搜索大文件总校验失败：bytes={total}/{expected_total} "
            f"sha={overall.hexdigest()}/{expected_global}"
        )
    return len(manifest["chunks"]), total, expected_global


def materialize(public_root: Path) -> None:
    public_root = public_root.resolve(strict=True)
    target = public_root / "search-chunks"
    if target.is_symlink():
        raise RuntimeError(f"拒绝替换符号链接搜索分块目录：{target}")

    with tempfile.TemporaryDirectory(
        prefix=".search-chunks-staging-",
        dir=public_root,
    ) as temporary:
        staging = Path(temporary) / "search-chunks"
        staging.mkdir()
        summaries = []
        for scope in SCOPES:
            summaries.append((scope, *materialize_scope(public_root, staging, scope)))

        incoming = public_root / ".search-chunks-incoming"
        if incoming.exists():
            if incoming.is_symlink():
                raise RuntimeError(f"拒绝删除符号链接：{incoming}")
            shutil.rmtree(incoming)
        shutil.copytree(staging, incoming)
        if target.exists():
            shutil.rmtree(target)
        os.replace(incoming, target)

    for scope, chunks, total, digest in summaries:
        print(
            f"SEARCH_CHUNKS_MATERIALIZED scope={scope} chunks={chunks} "
            f"bytes={total} sha256={digest}"
        )


def verify_scope_tree(root: Path, scope: str) -> tuple[int, int, str]:
    manifest = load_manifest(root, scope)
    overall = hashlib.sha256()
    total = 0
    expected_dir = root / "search-chunks" / scope / manifest["sha256"]
    if not expected_dir.is_dir() or expected_dir.is_symlink():
        raise RuntimeError(f"缺少 {scope} 搜索分块目录：{expected_dir}")

    expected_names = {part_name(index) for index in range(len(manifest["chunks"]))}
    actual_names = {path.name for path in expected_dir.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise RuntimeError(
            f"{scope} 搜索分块文件集合不一致："
            f"missing={sorted(expected_names - actual_names)[:5]} "
            f"extra={sorted(actual_names - expected_names)[:5]}"
        )

    for index, chunk in enumerate(manifest["chunks"]):
        path = expected_part_path(root, scope, manifest["sha256"], index)
        data = path.read_bytes()
        if len(data) != chunk["bytes"]:
            raise RuntimeError(f"{scope} 第 {index + 1} 块大小不一致")
        digest = sha256_bytes(data)
        if digest != chunk["sha256"]:
            raise RuntimeError(f"{scope} 第 {index + 1} 块哈希不一致")
        overall.update(data)
        total += len(data)

    if total != manifest["bytes"] or overall.hexdigest() != manifest["sha256"]:
        raise RuntimeError(f"{scope} 分块树全局校验失败")
    return len(manifest["chunks"]), total, overall.hexdigest()


def verify_tree(root: Path) -> None:
    root = root.resolve(strict=True)
    for scope in SCOPES:
        chunks, total, digest = verify_scope_tree(root, scope)
        print(
            f"SEARCH_CHUNKS_TREE_OK scope={scope} chunks={chunks} "
            f"bytes={total} sha256={digest}"
        )


def _download_one(
    *,
    base_url: str,
    scope: str,
    global_sha: str,
    index: int,
    expected: dict[str, Any],
    output: Path,
) -> None:
    relative = f"search-chunks/{scope}/{global_sha}/{part_name(index)}"
    base = base_url.rstrip("/") + "/"
    url = urllib.parse.urljoin(base, relative)
    last_error: Exception | None = None
    for attempt in range(1, 9):
        request_url = f"{url}?verify={time.time_ns()}-{attempt}"
        request = urllib.request.Request(
            request_url,
            headers={
                "User-Agent": "MagiReader-search-chunk-verifier/1",
                "Cache-Control": "no-cache",
            },
        )
        try:
            digest = hashlib.sha256()
            total = 0
            with urllib.request.urlopen(request, timeout=90) as response, output.open("wb") as handle:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) != int(expected["bytes"]):
                    raise RuntimeError(
                        f"Content-Length {declared} != {expected['bytes']}"
                    )
                while True:
                    data = response.read(256 * 1024)
                    if not data:
                        break
                    total += len(data)
                    if total > int(expected["bytes"]):
                        raise RuntimeError("远端分块超过清单大小")
                    digest.update(data)
                    handle.write(data)
            if total != int(expected["bytes"]):
                raise RuntimeError(f"远端分块大小 {total} != {expected['bytes']}")
            if digest.hexdigest() != expected["sha256"]:
                raise RuntimeError("远端分块 SHA-256 不一致")
            return
        except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
            last_error = exc
            output.unlink(missing_ok=True)
            if attempt < 8:
                time.sleep(min(2 * attempt, 10))
    raise RuntimeError(f"下载 {relative} 失败：{last_error}")


def verify_http(base_url: str, manifest_root: Path) -> None:
    manifest_root = manifest_root.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="magi-search-http-verify-") as temporary:
        temp = Path(temporary)
        for scope in SCOPES:
            manifest = load_manifest(manifest_root, scope)
            global_sha = str(manifest["sha256"])
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(MAX_HTTP_WORKERS, len(manifest["chunks"]))
            ) as executor:
                futures = []
                for index, expected in enumerate(manifest["chunks"]):
                    futures.append(
                        executor.submit(
                            _download_one,
                            base_url=base_url,
                            scope=scope,
                            global_sha=global_sha,
                            index=index,
                            expected=expected,
                            output=temp / f"{scope}-{part_name(index)}",
                        )
                    )
                for future in concurrent.futures.as_completed(futures):
                    future.result()

            overall = hashlib.sha256()
            total = 0
            for index in range(len(manifest["chunks"])):
                data = (temp / f"{scope}-{part_name(index)}").read_bytes()
                overall.update(data)
                total += len(data)
            if total != manifest["bytes"] or overall.hexdigest() != global_sha:
                raise RuntimeError(f"{scope} 远端分块重组后全局 SHA-256 不一致")
            print(
                f"SEARCH_CHUNKS_HTTP_OK scope={scope} chunks={len(manifest['chunks'])} "
                f"bytes={total} sha256={global_sha} base={base_url.rstrip('/')}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    materialize_parser = sub.add_parser("materialize")
    materialize_parser.add_argument("--root", type=Path, default=DEFAULT_PUBLIC_ROOT)

    verify_parser = sub.add_parser("verify-tree")
    verify_parser.add_argument("--root", type=Path, default=DEFAULT_PUBLIC_ROOT)

    http_parser = sub.add_parser("verify-http")
    http_parser.add_argument("--base-url", required=True)
    http_parser.add_argument(
        "--manifest-root",
        type=Path,
        default=DEFAULT_PUBLIC_ROOT,
    )

    args = parser.parse_args()
    if args.command == "materialize":
        materialize(args.root)
    elif args.command == "verify-tree":
        verify_tree(args.root)
    elif args.command == "verify-http":
        verify_http(args.base_url, args.manifest_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
