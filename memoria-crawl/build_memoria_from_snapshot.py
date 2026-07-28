#!/usr/bin/env python3
"""Build the Memoria catalog from the verified preservation snapshot.

The protected ``Template:记忆数据表/*`` namespace cannot be fetched reliably
from cloud runners.  The verified 500-page snapshot already contains the full
``记忆结晶`` index page with 1,042 unique ordinary article links and images.
Ordinary ``记忆结晶/*`` pages expand the same data table, so they are used as
the network detail source while the offline snapshot remains the authoritative
catalog membership source.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

import build_memoria_snapshot as M
import run_resilient_memoria  # noqa: F401  # patches M.PoliteFetcher


INDEX_TITLE = "记忆结晶"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_index_record(snapshot: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    archive = load_json(snapshot / "data" / "archive-index.json")
    item = next((entry for entry in archive if entry.get("title") == INDEX_TITLE and entry.get("namespace") == 0), None)
    if not item:
        raise RuntimeError("verified snapshot does not contain the 记忆结晶 index article")
    shard = load_json(snapshot / "data" / "archive" / f"{item['shard']}.json")
    record = shard.get(item["id"])
    if not record:
        raise RuntimeError(f"snapshot shard lacks index record: {item['id']}")
    return item, record


def clean_title_pair(value: str, fallback: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", value).strip()
    match = re.match(r"^(.*?)\s*[（(]([^）)]+)[）)]$", text)
    if match:
        return match.group(1).strip() or fallback, match.group(2).strip()
    return fallback, ""


def closest_tab(anchor: Tag) -> str:
    tab = anchor.find_parent(class_="tabbertab")
    return str(tab.get("title") or "") if tab else ""


def choose_index_image(anchor: Tag) -> str | None:
    image = anchor.find("img")
    if not image:
        return None
    source = image.get("src") or image.get("data-src")
    return urljoin(M.BASE, str(source)) if source else None


def enumerate_snapshot_articles(snapshot: Path) -> list[dict[str, Any]]:
    _, record = load_index_record(snapshot)
    raw = str(record.get("rawHtml") or record.get("html") or "")
    if not raw:
        raise RuntimeError("记忆结晶 index article has no preserved HTML")
    soup = BeautifulSoup(raw, "lxml")
    entries: dict[str, dict[str, Any]] = {}

    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "")
        title = M.title_from_href(href)
        if not title or not title.startswith(M.ARTICLE_PREFIX):
            continue
        name = title[len(M.ARTICLE_PREFIX):].strip()
        if not name or name in M.UTILITY_NAMES:
            continue
        absolute = urljoin(M.BASE, href)
        parsed = urlparse(absolute)
        if parsed.hostname not in {"magireco.moe", "www.magireco.moe"}:
            continue
        label = str(anchor.get("title") or "")
        image = anchor.find("img")
        if image and image.get("alt"):
            label = str(image.get("alt") or label)
        label = re.sub(r"\s+_s\.png$", "", label, flags=re.I)
        name_ja, name_zh = clean_title_pair(label, name)
        entry = entries.setdefault(
            title,
            {
                "key": name,
                "articleTitle": title,
                "articleUrl": absolute,
                "nameJa": name_ja,
                "nameZh": name_zh,
                "indexImageUrl": choose_index_image(anchor),
                "sourceTabs": [],
            },
        )
        tab = closest_tab(anchor)
        if tab and tab not in entry["sourceTabs"]:
            entry["sourceTabs"].append(tab)
        if not entry.get("indexImageUrl"):
            entry["indexImageUrl"] = choose_index_image(anchor)
        if not entry.get("nameZh") and name_zh:
            entry["nameZh"] = name_zh

    values = sorted(entries.values(), key=lambda item: item["nameJa"].casefold())
    if len(values) < 1000:
        raise RuntimeError(f"snapshot Memoria article membership unexpectedly small: {len(values)}")
    return values


def minimal_record(seed: dict[str, Any]) -> dict[str, Any]:
    return {
        **seed,
        "templateTitle": "",
        "templateUrl": "",
        "number": None,
        "artist": "",
        "rarity": None,
        "levelMin": None,
        "levelMax": None,
        "equipLimit": "",
        "hpMin": None,
        "hpMax": None,
        "atkMin": None,
        "atkMax": None,
        "defMin": None,
        "defMax": None,
        "type": "",
        "skillName": "",
        "skillNameMax": "",
        "effect": "",
        "effectMax": "",
        "effectDetail": "",
        "effectDetailMax": "",
        "cooldown": None,
        "cooldownMax": None,
        "obtain": "",
        "notes": "",
        "imageUrl": seed.get("indexImageUrl"),
        "rawTableHtml": "",
        "rawTableSha256": "",
        "revision": None,
        "descZh": "",
        "descJa": "",
        "descriptionHtml": "",
        "articleStatus": None,
        "articleError": None,
    }


def parse_article(seed: dict[str, Any], result: M.FetchResult) -> tuple[dict[str, Any], str | None]:
    item = minimal_record(seed)
    if not result.text:
        item["articleStatus"] = result.status
        item["articleError"] = result.error or f"HTTP {result.status}"
        return item, item["articleError"]
    try:
        synthetic_template = M.TEMPLATE_PREFIX + seed["key"]
        parsed = M.parse_template(synthetic_template, result)
        parsed["key"] = seed["key"]
        parsed["articleTitle"] = seed["articleTitle"]
        parsed["articleUrl"] = result.url
        parsed["templateTitle"] = ""
        parsed["templateUrl"] = ""
        parsed["sourceTabs"] = seed.get("sourceTabs", [])
        parsed["indexImageUrl"] = seed.get("indexImageUrl")
        if not parsed.get("imageUrl"):
            parsed["imageUrl"] = seed.get("indexImageUrl")
        if not parsed.get("nameZh"):
            parsed["nameZh"] = seed.get("nameZh", "")
        if not parsed.get("nameJa"):
            parsed["nameJa"] = seed.get("nameJa", seed["key"])
        M.enrich_article(parsed, result)
        parsed["articleStatus"] = result.status
        parsed["articleError"] = None
        return parsed, None
    except Exception as exc:  # noqa: BLE001
        item["articleStatus"] = result.status
        item["articleError"] = str(exc)
        # The article itself is still a valid catalog member even when its
        # current rendered table cannot be interpreted.
        try:
            M.enrich_article(item, result)
        except Exception:  # noqa: BLE001
            pass
        return item, str(exc)


def build(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    all_seeds = enumerate_snapshot_articles(args.snapshot.resolve())
    discovered = len(all_seeds)
    selected = all_seeds[: args.limit] if args.limit else list(all_seeds)
    if args.include:
        by_name = {item["key"]: item for item in all_seeds}
        by_ja = {item["nameJa"]: item for item in all_seeds}
        for value in args.include:
            item = by_name.get(value) or by_ja.get(value)
            if item and item not in selected:
                selected.append(item)

    fetcher = M.PoliteFetcher(
        pause=args.pause,
        timeout=args.timeout,
        retries=args.retries,
        max_requests=args.max_requests,
    )
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="memoria-article") as pool:
        futures: dict[Future[M.FetchResult], dict[str, Any]] = {
            pool.submit(fetcher.fetch, seed["articleUrl"]): seed for seed in selected
        }
        for future in as_completed(futures):
            seed = futures[future]
            result = future.result()
            item, error = parse_article(seed, result)
            records.append(item)
            if error:
                failures.append({
                    "stage": "article",
                    "title": seed["articleTitle"],
                    "url": result.url,
                    "status": result.status,
                    "error": error,
                })
            if len(records) and len(records) % 100 == 0:
                print(f"articles={len(records)}/{len(selected)} requests={fetcher.requests} failures={len(failures)}", flush=True)

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
    records.sort(key=lambda item: ((item.get("number") is None), item.get("number") or 10**9, item["nameJa"].casefold()))

    number_groups: dict[str, list[str]] = {}
    for item in records:
        if item.get("number") is not None:
            number_groups.setdefault(str(item["number"]), []).append(item["key"])

    elapsed = time.monotonic() - started
    manifest = {
        "schemaVersion": 2,
        "source": "verified-snapshot-membership-and-ordinary-article-pages",
        "snapshotArticleMembers": discovered,
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
        "elapsedSeconds": round(elapsed, 3),
    }
    M.dump_json(output / "memoria.json", records)
    M.dump_json(output / "number-groups.json", number_groups)
    M.dump_json(output / "manifest.json", manifest, pretty=True)
    M.dump_json(output / "failures.json", failures, pretty=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0, help="0 means all snapshot article members")
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--pause", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--max-requests", type=int, default=5000)
    args = parser.parse_args()
    manifest = build(args)
    expected = args.limit or manifest["snapshotArticleMembers"]
    if manifest["records"] != expected:
        raise RuntimeError(f"catalog membership loss: {manifest}")
    if args.limit and manifest["withStats"] < max(1, args.limit - 5):
        raise RuntimeError(f"sample ordinary-article parse coverage too small: {manifest}")


if __name__ == "__main__":
    main()
