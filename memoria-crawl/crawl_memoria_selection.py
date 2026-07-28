#!/usr/bin/env python3
"""Crawl one recoverable selection of ordinary Memoria article pages.

Selections can be an offset/limit slice of the verified 1,042-entry snapshot
catalog or an explicit newline/JSON title list generated from a prior failure
manifest.  Every selected catalog member is written even when its network page
fails, so batch artifacts are mergeable and resumable.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_memoria_from_snapshot as B  # noqa: E402
import build_memoria_snapshot as M  # noqa: E402
import run_resilient_memoria  # noqa: F401,E402  # patches M.PoliteFetcher


def read_titles(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                title = item.get("title") or item.get("articleTitle")
                if title:
                    result.append(str(title))
        return result
    raise RuntimeError(f"unsupported title selection document: {path}")


def select_seeds(args: argparse.Namespace) -> tuple[list[dict[str, Any]], int]:
    all_seeds = B.enumerate_snapshot_articles(args.snapshot.resolve())
    total = len(all_seeds)
    if args.titles_file:
        requested = read_titles(args.titles_file.resolve())
        by_article = {item["articleTitle"]: item for item in all_seeds}
        by_key = {item["key"]: item for item in all_seeds}
        selected: list[dict[str, Any]] = []
        missing: list[str] = []
        for title in requested:
            item = by_article.get(title) or by_key.get(title.removeprefix(M.ARTICLE_PREFIX))
            if item and item not in selected:
                selected.append(item)
            elif not item:
                missing.append(title)
        if missing:
            raise RuntimeError(f"selection contains titles absent from verified catalog: {missing[:20]}")
        return selected, total

    start = max(0, args.start)
    stop = total if args.limit == 0 else min(total, start + args.limit)
    return all_seeds[start:stop], total


def build(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    selected, catalog_total = select_seeds(args)
    if not selected:
        raise RuntimeError("empty Memoria selection")

    fetcher = M.PoliteFetcher(
        pause=args.pause,
        timeout=args.timeout,
        retries=args.retries,
        max_requests=args.max_requests,
    )
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="memoria-selection") as pool:
        futures: dict[Future[M.FetchResult], dict[str, Any]] = {
            pool.submit(fetcher.fetch, seed["articleUrl"]): seed for seed in selected
        }
        for future in as_completed(futures):
            seed = futures[future]
            result = future.result()
            item, error = B.parse_article(seed, result)
            records.append(item)
            if error:
                failures.append({
                    "stage": "article",
                    "title": seed["articleTitle"],
                    "url": result.url,
                    "status": result.status,
                    "error": error,
                })

    for item in records:
        item["searchText"] = " ".join(
            str(value or "")
            for value in (
                item.get("number"), item.get("nameJa"), item.get("nameZh"), item.get("artist"),
                item.get("rarity"), item.get("type"), item.get("equipLimit"), item.get("skillName"),
                item.get("skillNameMax"), item.get("effect"), item.get("effectMax"), item.get("effectDetail"),
                item.get("effectDetailMax"), item.get("obtain"), item.get("descZh"), item.get("descJa"),
            )
        )
    records.sort(key=lambda item: ((item.get("number") is None), item.get("number") or 10**9, str(item.get("nameJa") or item.get("key")).casefold()))

    number_groups: dict[str, list[str]] = {}
    for item in records:
        if item.get("number") is not None:
            number_groups.setdefault(str(item["number"]), []).append(str(item["key"]))

    manifest = {
        "schemaVersion": 4,
        "source": "recoverable-ordinary-article-selection",
        "snapshotArticleMembers": catalog_total,
        "selectionMode": "titles" if args.titles_file else "slice",
        "selectionStart": None if args.titles_file else args.start,
        "selectionLimit": None if args.titles_file else args.limit,
        "selectedArticlePages": len(selected),
        "records": len(records),
        "uniqueNumbers": len(number_groups),
        "withImage": sum(bool(item.get("imageUrl")) for item in records),
        "withChineseName": sum(bool(item.get("nameZh")) for item in records),
        "withChineseDescription": sum(bool(item.get("descZh")) for item in records),
        "withJapaneseDescription": sum(bool(item.get("descJa")) for item in records),
        "withStats": sum(all(item.get(key) is not None for key in ("hpMin", "hpMax", "atkMin", "atkMax", "defMin", "defMax")) for item in records),
        "requests": fetcher.requests,
        "failures": len(failures),
        "elapsedSeconds": round(time.monotonic() - started, 3),
    }
    M.dump_json(output / "memoria.json", records)
    M.dump_json(output / "number-groups.json", number_groups)
    M.dump_json(output / "manifest.json", manifest, pretty=True)
    M.dump_json(output / "failures.json", failures, pretty=True)
    M.dump_json(output / "selection.json", [item["articleTitle"] for item in selected], pretty=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)

    if len(records) != len(selected):
        raise RuntimeError(f"selection membership loss: {manifest}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--titles-file", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--pause", type=float, default=0.45)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--max-requests", type=int, default=500)
    args = parser.parse_args()
    if args.titles_file and (args.start or args.limit):
        raise RuntimeError("--titles-file cannot be combined with --start/--limit")
    build(args)


if __name__ == "__main__":
    main()
