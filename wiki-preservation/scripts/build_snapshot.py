#!/usr/bin/env python3
"""Build a deployable static snapshot of magireco.moe from the MediaWiki API.

The output is deliberately split into small deterministic JSON shards.  It is
safe to publish as a static site and does not require MediaWiki, a database, or
server-side application code after the build finishes.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

API_CANDIDATES = (
    "https://magireco.moe/api.php",
    "https://www.magireco.moe/api.php",
)
USER_AGENT = (
    "MagirecoChinesePreservationReader/3.0 "
    "(https://github.com/HiiragiNemu/magi-reader; archival build)"
)
DEFAULT_NAMESPACES = (0, 4, 8, 10, 12, 14, 828, 3000, 3002)
NAMESPACE_LABELS = {
    0: "正文",
    4: "项目",
    8: "MediaWiki",
    10: "模板",
    12: "帮助",
    14: "分类",
    828: "模块",
    3000: "圆环记录",
    3002: "Game",
}
HEADING_RE = re.compile(r"(?m)^(={2,6})\s*(.*?)\s*\1\s*$")
CATEGORY_RE = re.compile(r"\[\[(?:Category|分类|分類):([^|\]]+)", re.I)
REDIRECT_RE = re.compile(r"^\s*#(?:REDIRECT|重定向)\s*\[\[([^\]]+)\]\]", re.I)
COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
TAG_RE = re.compile(r"<[^>]+>")
TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
LINK_RE = re.compile(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]")
EXTERNAL_RE = re.compile(r"\[(?:https?://\S+)(?:\s+([^\]]+))?\]")
WHITESPACE_RE = re.compile(r"\s+")

PORTALS: dict[str, dict[str, Any]] = {
    "characters": {
        "title": "魔法少女与人物",
        "keywords": ("魔法少女", "角色", "人物", "组织", "学校", "神滨市", "二木市"),
    },
    "story": {
        "title": "剧情与活动",
        "keywords": ("剧情", "活动", "主线", "支线", "故事", "章节", "event"),
    },
    "memoria": {
        "title": "记忆结晶与道具",
        "keywords": ("记忆结晶", "素材", "道具", "商店", "装备", "技能", "效果"),
    },
    "doppel": {
        "title": "Doppel、魔女与传言",
        "keywords": ("doppel", "魔女", "使魔", "传言", "魔女文字", "符文"),
    },
    "system": {
        "title": "游戏与战斗系统",
        "keywords": ("游戏系统", "战斗", "属性", "disc", "magia", "connect", "关卡", "养成", "镜层"),
    },
    "world": {
        "title": "世界观与术语",
        "keywords": ("术语", "世界观", "地点", "时间线", "概念", "神滨", "魔法少女系统"),
    },
    "media": {
        "title": "动画、音乐与出版物",
        "keywords": ("动画", "漫画", "歌曲", "音乐", "广播", "画集", "出版", "magirepo"),
    },
    "technical": {
        "title": "模板与技术档案",
        "namespaces": (4, 8, 10, 12, 14, 828),
        "keywords": ("模板", "模块", "分类", "帮助", "规范", "翻译"),
    },
}


class SnapshotError(RuntimeError):
    pass


@dataclass(slots=True)
class ApiClient:
    endpoint: str
    pause: float = 0.08
    retries: int = 6

    def request(self, **params: Any) -> dict[str, Any]:
        payload = {
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
            **{key: value for key, value in params.items() if value is not None},
        }
        url = f"{self.endpoint}?{urllib.parse.urlencode(payload, doseq=True)}"
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                    },
                )
                with urllib.request.urlopen(request, timeout=90) as response:
                    raw = response.read()
                    if response.headers.get("Content-Encoding", "").lower() == "gzip":
                        import gzip

                        raw = gzip.decompress(raw)
                data = json.loads(raw.decode("utf-8"))
                if "error" in data:
                    error = data["error"]
                    if error.get("code") == "maxlag":
                        raise SnapshotError(f"MediaWiki maxlag: {error}")
                    raise SnapshotError(f"MediaWiki API error: {error}")
                time.sleep(self.pause)
                return data
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, SnapshotError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                time.sleep(min(30.0, 1.8**attempt))
        raise SnapshotError(f"API request failed after {self.retries} attempts: {last_error}\n{url}")


def select_api() -> tuple[ApiClient, dict[str, Any]]:
    errors: list[str] = []
    for endpoint in API_CANDIDATES:
        client = ApiClient(endpoint)
        try:
            info = client.request(
                action="query",
                meta="siteinfo",
                siprop="general|namespaces|namespacealiases|statistics",
            )
            return client, info
        except Exception as exc:  # noqa: BLE001 - preserve diagnostics for all candidates
            errors.append(f"{endpoint}: {exc}")
    raise SnapshotError("No usable MediaWiki API endpoint:\n" + "\n".join(errors))


def atomic_json(path: Path, value: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    if pretty:
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def sha_bucket(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:2]


def chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def normalize(value: Any) -> str:
    return WHITESPACE_RE.sub(" ", str(value or "").casefold()).strip()


def plain_preview(wikitext: str, limit: int = 420) -> str:
    value = COMMENT_RE.sub(" ", wikitext)
    previous = None
    for _ in range(4):
        if value == previous:
            break
        previous = value
        value = TEMPLATE_RE.sub(" ", value)
    value = LINK_RE.sub(lambda match: match.group(1), value)
    value = EXTERNAL_RE.sub(lambda match: match.group(1) or " ", value)
    value = TAG_RE.sub(" ", value)
    value = value.replace("'''", "").replace("''", "")
    value = re.sub(r"(?m)^={2,6}\s*(.*?)\s*={2,6}$", r" \1 ", value)
    value = re.sub(r"(?m)^[*#;:|!{}]+", " ", value)
    value = html.unescape(value)
    value = WHITESPACE_RE.sub(" ", value).strip()
    return value[:limit]


def portal_ids(namespace: int, title: str, categories: list[str], headings: list[dict[str, Any]], preview: str) -> list[str]:
    haystack = normalize(" ".join([title, *categories, *(item["text"] for item in headings), preview]))
    matches: list[str] = []
    for portal_id, portal in PORTALS.items():
        namespaces = tuple(portal.get("namespaces", ()))
        if portal_id == "technical" and namespace in namespaces:
            matches.append(portal_id)
            continue
        if any(normalize(keyword) in haystack for keyword in portal["keywords"]):
            matches.append(portal_id)
    return matches


def enumerate_pages(client: ApiClient, namespaces: tuple[int, ...]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for namespace in namespaces:
        continuation: dict[str, Any] = {}
        namespace_count = 0
        while True:
            data = client.request(
                action="query",
                list="allpages",
                apnamespace=str(namespace),
                aplimit="max",
                apfilterredir="all",
                **continuation,
            )
            batch = data.get("query", {}).get("allpages", [])
            pages.extend(batch)
            namespace_count += len(batch)
            if "continue" not in data:
                break
            continuation = data["continue"]
        print(f"namespace {namespace:>4}: {namespace_count:>6} pages", flush=True)
    pages.sort(key=lambda item: (int(item.get("ns", 0)), str(item.get("title", "")).casefold()))
    return pages


def revision_content(revision: dict[str, Any]) -> str:
    slots = revision.get("slots")
    if isinstance(slots, dict):
        main = slots.get("main") or {}
        for key in ("content", "*", "text"):
            if isinstance(main.get(key), str):
                return main[key]
    for key in ("content", "*", "text"):
        if isinstance(revision.get(key), str):
            return revision[key]
    return ""


def fetch_page_batch(client: ApiClient, pageids: list[int]) -> list[dict[str, Any]]:
    base = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "ids|timestamp|content",
        "pageids": "|".join(str(value) for value in pageids),
    }
    try:
        data = client.request(**base, rvslots="main")
    except SnapshotError as exc:
        if "rvslots" not in str(exc).lower() and "slots" not in str(exc).lower():
            raise
        data = client.request(**base)
    return data.get("query", {}).get("pages", [])


def build_archive(client: ApiClient, pages: list[dict[str, Any]], data_dir: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    shard_records: dict[str, dict[str, Any]] = defaultdict(dict)
    index: list[dict[str, Any]] = []
    portal_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    namespace_counts: Counter[int] = Counter()
    content_bytes = 0

    page_meta = {int(item["pageid"]): item for item in pages if "pageid" in item}
    page_ids = sorted(page_meta)
    total_batches = (len(page_ids) + 19) // 20

    for batch_number, batch_ids in enumerate(chunks(page_ids, 20), start=1):
        query_pages = fetch_page_batch(client, batch_ids)
        by_id = {int(item.get("pageid", -1)): item for item in query_pages}
        for pageid in batch_ids:
            meta = page_meta[pageid]
            page = by_id.get(pageid, meta)
            title = str(page.get("title") or meta.get("title") or "")
            namespace = int(page.get("ns", meta.get("ns", 0)))
            revisions = page.get("revisions") or []
            revision = revisions[0] if revisions else {}
            text = revision_content(revision)
            encoded = text.encode("utf-8")
            content_bytes += len(encoded)
            headings = [
                {"level": len(match.group(1)), "text": match.group(2).strip()}
                for match in HEADING_RE.finditer(text)
            ]
            categories = sorted({value.strip() for value in CATEGORY_RE.findall(text) if value.strip()})
            redirect_match = REDIRECT_RE.match(text)
            redirect_to = redirect_match.group(1).strip() if redirect_match else None
            preview = plain_preview(text)
            record_id = f"{namespace}:{title}"
            shard = sha_bucket(record_id)
            portals = portal_ids(namespace, title, categories, headings, preview)
            for portal in portals:
                portal_counts[portal] += 1
            category_counts.update(categories)
            namespace_counts[namespace] += 1

            shard_records[shard][record_id] = {
                "id": record_id,
                "pageid": pageid,
                "namespace": namespace,
                "title": title,
                "revision": revision.get("revid"),
                "parentRevision": revision.get("parentid"),
                "timestamp": revision.get("timestamp"),
                "wikitext": text,
            }
            index.append(
                {
                    "id": record_id,
                    "pageid": pageid,
                    "namespace": namespace,
                    "namespaceLabel": NAMESPACE_LABELS.get(namespace, f"命名空间 {namespace}"),
                    "title": title,
                    "shard": shard,
                    "textBytes": len(encoded),
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                    "revision": revision.get("revid"),
                    "timestamp": revision.get("timestamp"),
                    "redirectTo": redirect_to,
                    "categories": categories,
                    "headings": headings,
                    "preview": preview,
                    "portals": portals,
                }
            )
        if batch_number == 1 or batch_number % 20 == 0 or batch_number == total_batches:
            print(f"page content: batch {batch_number}/{total_batches}", flush=True)

    for shard, records in sorted(shard_records.items()):
        atomic_json(data_dir / "archive" / f"{shard}.json", records)

    index.sort(key=lambda item: (item["namespace"], item["title"].casefold()))
    atomic_json(data_dir / "archive-index.json", index)
    atomic_json(
        data_dir / "category-index.json",
        [{"name": name, "count": count} for name, count in category_counts.most_common()],
    )
    atomic_json(
        data_dir / "portal-index.json",
        [
            {
                "id": portal_id,
                "title": portal["title"],
                "count": portal_counts[portal_id],
                "keywords": list(portal["keywords"]),
            }
            for portal_id, portal in PORTALS.items()
        ],
    )
    stats = {
        "pages": len(index),
        "contentBytes": content_bytes,
        "shards": len(shard_records),
        "categories": len(category_counts),
        "namespaces": len(namespace_counts),
    }
    return index, stats


def enumerate_media(client: ApiClient, data_dir: Path) -> dict[str, int]:
    records: list[dict[str, Any]] = []
    continuation: dict[str, Any] = {}
    while True:
        data = client.request(
            action="query",
            list="allimages",
            ailimit="max",
            aisort="name",
            aiprop="timestamp|url|size|sha1|mime|mediatype",
            **continuation,
        )
        records.extend(data.get("query", {}).get("allimages", []))
        print(f"media metadata: {len(records):>6} files", flush=True)
        if "continue" not in data:
            break
        continuation = data["continue"]

    compact: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    total_bytes = 0
    for item in records:
        mime = str(item.get("mime") or "application/octet-stream")
        media_type = "audio" if mime.startswith("audio/") else "image" if mime.startswith("image/") else "other"
        size = int(item.get("size") or 0)
        total_bytes += size
        type_counts[media_type] += 1
        compact.append(
            {
                "name": item.get("name"),
                "url": item.get("url"),
                "descriptionUrl": item.get("descriptionurl"),
                "mime": mime,
                "mediaType": media_type,
                "size": size,
                "width": item.get("width"),
                "height": item.get("height"),
                "sha1": item.get("sha1"),
                "timestamp": item.get("timestamp"),
            }
        )
    compact.sort(key=lambda item: str(item.get("name") or "").casefold())
    atomic_json(data_dir / "media-index.json", compact)
    return {
        "media": len(compact),
        "images": type_counts["image"],
        "audio": type_counts["audio"],
        "otherMedia": type_counts["other"],
        "mediaBytes": total_bytes,
    }


def copy_static(static_dir: Path, output: Path) -> None:
    if not static_dir.is_dir():
        raise SnapshotError(f"Static directory is missing: {static_dir}")
    for source in static_dir.rglob("*"):
        if source.is_dir():
            continue
        relative = source.relative_to(static_dir)
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--static", type=Path)
    parser.add_argument("--namespaces", default=",".join(str(value) for value in DEFAULT_NAMESPACES))
    parser.add_argument("--skip-media", action="store_true")
    args = parser.parse_args()

    script_root = Path(__file__).resolve().parents[1]
    static_dir = args.static or script_root / "static"
    output = args.output.resolve()
    namespaces = tuple(int(value.strip()) for value in args.namespaces.split(",") if value.strip())

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    data_dir = output / "data"
    data_dir.mkdir()

    client, siteinfo = select_api()
    general = siteinfo.get("query", {}).get("general", {})
    statistics = siteinfo.get("query", {}).get("statistics", {})
    print(f"using API: {client.endpoint}", flush=True)
    print(f"site: {general.get('sitename')} / {general.get('base')}", flush=True)

    pages = enumerate_pages(client, namespaces)
    if len(pages) < 1000:
        raise SnapshotError(f"Refusing incomplete snapshot: only {len(pages)} pages enumerated")
    _, archive_stats = build_archive(client, pages, data_dir)
    media_stats = {} if args.skip_media else enumerate_media(client, data_dir)

    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest = {
        "schemaVersion": 3,
        "generatedAt": generated_at,
        "source": {
            "api": client.endpoint,
            "siteName": general.get("sitename"),
            "base": general.get("base"),
            "generator": general.get("generator"),
            "server": general.get("server"),
            "statistics": statistics,
        },
        "namespaces": list(namespaces),
        "counts": {**archive_stats, **media_stats},
        "features": [
            "full-wikitext-archive",
            "readable-wikitext",
            "internal-link-routing",
            "category-and-heading-search",
            "thematic-portals",
            "media-index",
            "offline-shell",
        ],
    }
    atomic_json(data_dir / "runtime-manifest.json", manifest, pretty=True)
    atomic_json(
        output / "health.json",
        {
            "status": "ok",
            "site": "magireco-cn-reader",
            "readerVersion": 3,
            "generatedAt": generated_at,
            "counts": manifest["counts"],
        },
        pretty=True,
    )
    copy_static(static_dir, output)
    (output / ".nojekyll").touch()
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc}", file=sys.stderr, flush=True)
        raise
