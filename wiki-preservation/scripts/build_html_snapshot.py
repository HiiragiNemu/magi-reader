#!/usr/bin/env python3
"""Create a static preservation snapshot by crawling ordinary rendered Wiki pages.

magireco.moe deliberately blocks api.php and Special:Export for cloud/bot
traffic. Ordinary article and category pages remain public. This crawler walks
the public link/category graph at a conservative rate and stores both:

* sanitized rendered HTML for convenient reading;
* the exact original inner HTML as a fidelity layer.

No authentication, editing, special pages, or private information are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlparse, urlunparse

import bleach
import requests
from bs4 import BeautifulSoup, Tag

BASE = "https://magireco.moe"
HOME_TITLE = "首页"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/138.0 Safari/537.36 "
    "MagirecoChinesePreservationReader/3.0"
)
ALLOWED_NAMESPACES = {0, 4, 8, 10, 12, 14, 828, 3000, 3002}
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
EXCLUDED_PREFIXES = (
    "Special:", "特殊:",
    "User:", "用户:", "使用者:",
    "User talk:", "用户讨论:", "使用者討論:",
    "Talk:", "讨论:", "討論:",
    "File:", "Image:", "文件:", "图像:", "圖像:", "档案:", "檔案:",
)
PAGINATION_KEYS = {"pagefrom", "subcatfrom", "filefrom", "until", "from"}
SCRIPT_CONFIG_RE = {
    "namespace": re.compile(r'"wgNamespaceNumber"\s*:\s*(-?\d+)'),
    "pageid": re.compile(r'"wgArticleId"\s*:\s*(\d+)'),
    "revision": re.compile(r'"wgCurRevisionId"\s*:\s*(\d+)'),
    "page_name": re.compile(r'"wgPageName"\s*:\s*"((?:\\.|[^"\\])*)"'),
}

PORTALS: dict[str, dict[str, Any]] = {
    "characters": {"title": "魔法少女与人物", "keywords": ("魔法少女", "角色", "人物", "组织", "学校", "神滨市", "二木市")},
    "story": {"title": "剧情与活动", "keywords": ("剧情", "活动", "主线", "支线", "故事", "章节", "event")},
    "memoria": {"title": "记忆结晶与道具", "keywords": ("记忆结晶", "素材", "道具", "商店", "装备", "技能", "效果")},
    "doppel": {"title": "Doppel、魔女与传言", "keywords": ("doppel", "魔女", "使魔", "传言", "魔女文字", "符文")},
    "system": {"title": "游戏与战斗系统", "keywords": ("游戏系统", "战斗", "属性", "disc", "magia", "connect", "关卡", "养成", "镜层")},
    "world": {"title": "世界观与术语", "keywords": ("术语", "世界观", "地点", "时间线", "概念", "神滨", "魔法少女系统")},
    "media": {"title": "动画、音乐与出版物", "keywords": ("动画", "漫画", "歌曲", "音乐", "广播", "画集", "出版", "magirepo")},
    "technical": {"title": "模板与技术档案", "namespaces": (4, 8, 10, 12, 14, 828), "keywords": ("模板", "模块", "分类", "帮助", "规范", "翻译")},
}

SEED_TITLES = (
    "首页",
    "Category:魔法纪录",
    "Category:模板总览",
    "Category:圆环记录攻略组",
    "Category:魔法纪录剧情",
    "Category:魔法纪录活动",
    "Category:魔法纪录登场角色",
    "Category:魔法纪录战斗系统",
    "Category:魔法纪录游戏系统",
    "Category:魔法纪录歌曲",
    "Category:魔法纪录动画",
    "Category:记忆结晶",
    "Category:魔女",
    "Category:Doppel",
    "剧情汉化",
    "魔法少女",
    "记忆结晶",
    "魔女化身",
    "魔女、谣列表",
    "Game:游戏公告",
)

ALLOWED_TAGS = {
    "a", "abbr", "article", "audio", "b", "big", "blockquote", "br", "caption", "center", "cite", "code", "dd", "del", "details", "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins", "kbd", "li", "math", "ol", "p", "pre", "q", "rb", "rp", "rt", "ruby", "s", "section", "small", "source", "span", "strong", "sub", "summary", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul", "var",
}
ALLOWED_ATTRIBUTES = {
    "*": ["class", "id", "title", "lang", "dir", "aria-label", "aria-hidden"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height", "loading", "decoding"],
    "audio": ["src", "controls", "preload"],
    "source": ["src", "type"],
    "td": ["colspan", "rowspan", "headers"],
    "th": ["colspan", "rowspan", "scope", "headers"],
}


def dump_json(path: Path, value: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":"), sort_keys=pretty) + "\n"
    path.write_text(text, encoding="utf-8")


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def title_url(title: str) -> str:
    return f"{BASE}/wiki/{quote(title.replace(' ', '_'), safe=':()!$&\'*,;=@~+-._')}"


def clean_title(value: str) -> str:
    return unquote(value).replace("_", " ").strip().lstrip(":")


def excluded_title(title: str) -> bool:
    folded = title.casefold()
    return any(folded.startswith(prefix.casefold()) for prefix in EXCLUDED_PREFIXES)


def normalize_crawl_url(url: str) -> tuple[str, str] | None:
    parsed = urlparse(urljoin(BASE, url))
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"magireco.moe", "www.magireco.moe"}:
        return None
    query = parse_qs(parsed.query)
    if any(key in query for key in ("action", "oldid", "diff", "printable", "variant", "redlink", "direction")):
        return None
    title = ""
    if parsed.path.startswith("/wiki/"):
        title = clean_title(parsed.path[len("/wiki/"):])
    elif parsed.path.endswith("/index.php") and query.get("title"):
        title = clean_title(query["title"][0])
    else:
        return None
    if not title or excluded_title(title):
        return None
    kept = {key: values[-1] for key, values in query.items() if key in PAGINATION_KEYS and values}
    canonical = title_url(title)
    if kept:
        canonical = f"{canonical}?{urlencode(sorted(kept.items()))}"
    return canonical, title


def page_config(raw_html: str, soup: BeautifulSoup) -> tuple[int, int, int, str]:
    def number(name: str, default: int = 0) -> int:
        match = SCRIPT_CONFIG_RE[name].search(raw_html)
        return int(match.group(1)) if match else default

    title_match = SCRIPT_CONFIG_RE["page_name"].search(raw_html)
    if title_match:
        try:
            page_name = json.loads(f'"{title_match.group(1)}"').replace("_", " ")
        except json.JSONDecodeError:
            page_name = title_match.group(1).replace("_", " ")
    else:
        heading = soup.select_one("#firstHeading")
        page_name = heading.get_text(" ", strip=True) if heading else ""
    return number("namespace"), number("pageid"), number("revision"), page_name


def record_portals(namespace: int, title: str, categories: list[str], headings: list[dict[str, Any]], preview: str) -> list[str]:
    haystack = normalize(" ".join([title, *categories, *(item["text"] for item in headings), preview]))
    result: list[str] = []
    for portal_id, portal in PORTALS.items():
        if portal_id == "technical" and namespace in portal.get("namespaces", ()):
            result.append(portal_id)
        elif any(normalize(keyword) in haystack for keyword in portal["keywords"]):
            result.append(portal_id)
    return result


def media_type(url: str, tag: Tag | None = None) -> str:
    mime = mimetypes.guess_type(urlparse(url).path)[0] or ""
    if mime.startswith("audio/") or urlparse(url).path.casefold().endswith((".mp3", ".ogg", ".wav", ".m4a")):
        return "audio"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("image/") or tag and tag.name == "img":
        return "image"
    return "other"


def media_name(url: str) -> str:
    return clean_title(urlparse(url).path.rsplit("/", 1)[-1])


def sanitize_content(raw_inner: str, title_to_id: dict[str, str], media_records: dict[str, dict[str, Any]]) -> str:
    soup = BeautifulSoup(raw_inner, "lxml")
    for selector in ("script", "style", "form", "noscript", ".mw-editsection", ".printfooter", ".catlinks", ".mw-jump-link", ".noprint"):
        for node in soup.select(selector):
            node.decompose()

    for tag in soup.find_all(True):
        for attribute in list(tag.attrs):
            if attribute.casefold().startswith("on") or attribute.casefold() in {"style", "srcset"}:
                del tag.attrs[attribute]

        if tag.name in {"img", "audio", "source"}:
            source = tag.get("src") or tag.get("data-src")
            if source:
                absolute = urljoin(BASE, source)
                tag["src"] = absolute
                tag["loading"] = "lazy"
                name = media_name(absolute)
                key = normalize(name)
                media_records.setdefault(key, {
                    "name": name,
                    "url": absolute,
                    "mediaType": media_type(absolute, tag),
                    "mime": mimetypes.guess_type(urlparse(absolute).path)[0] or "application/octet-stream",
                    "size": 0,
                    "width": tag.get("width"),
                    "height": tag.get("height"),
                })

        if tag.name == "a" and tag.get("href"):
            href = str(tag["href"])
            target = normalize_crawl_url(href)
            if target:
                _, linked_title = target
                record_id = title_to_id.get(normalize(linked_title))
                if record_id:
                    tag["href"] = f"#/article/{quote(record_id, safe='')}"
                else:
                    tag["href"] = title_url(linked_title)
                    tag["target"] = "_blank"
                    tag["rel"] = "noreferrer"
            else:
                absolute = urljoin(BASE, href)
                tag["href"] = absolute
                if urlparse(absolute).hostname not in {"magireco.moe", "www.magireco.moe"}:
                    tag["target"] = "_blank"
                    tag["rel"] = "noreferrer"
                kind = media_type(absolute)
                if kind in {"audio", "image", "video"}:
                    name = media_name(absolute)
                    media_records.setdefault(normalize(name), {
                        "name": name,
                        "url": absolute,
                        "mediaType": kind,
                        "mime": mimetypes.guess_type(urlparse(absolute).path)[0] or "application/octet-stream",
                        "size": 0,
                        "width": None,
                        "height": None,
                    })

    body = soup.body or soup
    cleaned = bleach.clean(
        "".join(str(child) for child in body.contents),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols={"http", "https"},
        strip=True,
        strip_comments=True,
    )
    return cleaned


class Crawler:
    def __init__(self, *, pause: float, max_pages: int, max_requests: int, timeout: float) -> None:
        self.pause = pause
        self.max_pages = max_pages
        self.max_requests = max_requests
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        })
        self.queue: deque[str] = deque()
        self.seen_urls: set[str] = set()
        self.records: dict[str, dict[str, Any]] = {}
        self.failed: list[dict[str, Any]] = []
        self.requests = 0
        self.media: dict[str, dict[str, Any]] = {}

    def enqueue(self, url: str) -> None:
        normalized = normalize_crawl_url(url)
        if not normalized:
            return
        canonical, _ = normalized
        if canonical not in self.seen_urls:
            self.seen_urls.add(canonical)
            self.queue.append(canonical)

    def warm(self) -> None:
        try:
            self.session.get(title_url(HOME_TITLE), timeout=self.timeout)
        except requests.RequestException:
            pass

    def get(self, url: str) -> requests.Response | None:
        for attempt in range(1, 5):
            self.requests += 1
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                if response.status_code == 200 and "text/html" in response.headers.get("content-type", ""):
                    time.sleep(self.pause)
                    return response
                if response.status_code == 403:
                    self.warm()
                if response.status_code in {403, 408, 425, 429, 500, 502, 503, 504}:
                    time.sleep(min(20, 1.6**attempt))
                    continue
                self.failed.append({"url": url, "status": response.status_code})
                return None
            except requests.RequestException as exc:
                if attempt == 4:
                    self.failed.append({"url": url, "error": str(exc)})
                    return None
                time.sleep(min(20, 1.6**attempt))
        return None

    def extract_links(self, soup: BeautifulSoup) -> None:
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href") or "")
            normalized = normalize_crawl_url(href)
            if normalized:
                self.enqueue(normalized[0])
            else:
                absolute = urljoin(BASE, href)
                kind = media_type(absolute)
                if kind in {"audio", "image", "video"} and urlparse(absolute).hostname in {"magireco.moe", "www.magireco.moe"}:
                    name = media_name(absolute)
                    self.media.setdefault(normalize(name), {
                        "name": name,
                        "url": absolute,
                        "mediaType": kind,
                        "mime": mimetypes.guess_type(urlparse(absolute).path)[0] or "application/octet-stream",
                        "size": 0,
                        "width": None,
                        "height": None,
                    })
        for image in soup.select("img"):
            source = image.get("src") or image.get("data-src")
            if not source:
                continue
            absolute = urljoin(BASE, str(source))
            name = media_name(absolute)
            self.media.setdefault(normalize(name), {
                "name": name,
                "url": absolute,
                "mediaType": "image",
                "mime": mimetypes.guess_type(urlparse(absolute).path)[0] or "image/*",
                "size": 0,
                "width": image.get("width"),
                "height": image.get("height"),
            })

    def crawl(self) -> None:
        self.warm()
        for title in SEED_TITLES:
            self.enqueue(title_url(title))

        started = time.monotonic()
        while self.queue and len(self.records) < self.max_pages and self.requests < self.max_requests:
            url = self.queue.popleft()
            response = self.get(url)
            if response is None:
                continue
            raw_html = response.text
            soup = BeautifulSoup(raw_html, "lxml")
            self.extract_links(soup)
            namespace, pageid, revision, page_name = page_config(raw_html, soup)
            if not page_name:
                continue
            if namespace not in ALLOWED_NAMESPACES or excluded_title(page_name):
                continue
            record_id = f"{namespace}:{page_name}"
            if record_id in self.records:
                continue
            content = soup.select_one("#mw-content-text")
            if content is None:
                continue
            parser_output = content.select_one(".mw-parser-output") or content
            categories = [
                anchor.get_text(" ", strip=True)
                for anchor in soup.select("#mw-normal-catlinks ul a")
                if anchor.get_text(" ", strip=True)
            ]
            headings = [
                {"level": int(node.name[1]), "text": node.get_text(" ", strip=True)}
                for node in parser_output.select("h2,h3,h4,h5,h6")
                if node.get_text(" ", strip=True)
            ]
            text = parser_output.get_text("\n", strip=True)
            preview = re.sub(r"\s+", " ", text).strip()[:520]
            raw_inner = "".join(str(child) for child in parser_output.contents)
            redirect = soup.select_one(".redirectMsg a")
            portals = record_portals(namespace, page_name, categories, headings, preview)
            self.records[record_id] = {
                "id": record_id,
                "pageid": pageid or None,
                "namespace": namespace,
                "namespaceLabel": NAMESPACE_LABELS.get(namespace, f"命名空间 {namespace}"),
                "title": page_name,
                "revision": revision or None,
                "sourceUrl": response.url,
                "rawHtml": raw_inner,
                "text": text,
                "preview": preview,
                "categories": categories,
                "headings": headings,
                "redirectTo": redirect.get_text(" ", strip=True) if redirect else None,
                "portals": portals,
            }
            count = len(self.records)
            if count == 1 or count % 100 == 0:
                elapsed = time.monotonic() - started
                print(f"stored={count} requests={self.requests} queued={len(self.queue)} failed={len(self.failed)} elapsed={elapsed/60:.1f}m", flush=True)


def build_output(crawler: Crawler, output: Path, static_dir: Path) -> dict[str, Any]:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    data_dir = output / "data"
    data_dir.mkdir()

    records = list(crawler.records.values())
    title_to_id: dict[str, str] = {}
    for record in records:
        key = normalize(record["title"])
        current = title_to_id.get(key)
        if current is None or (not current.startswith("0:") and record["namespace"] == 0):
            title_to_id[key] = record["id"]

    shards: dict[str, dict[str, Any]] = defaultdict(dict)
    index: list[dict[str, Any]] = []
    categories: Counter[str] = Counter()
    portal_counts: Counter[str] = Counter()
    content_bytes = 0

    for number, record in enumerate(records, start=1):
        clean_html = sanitize_content(record["rawHtml"], title_to_id, crawler.media)
        raw_bytes = record["rawHtml"].encode("utf-8")
        content_bytes += len(raw_bytes)
        record_id = record["id"]
        shard = hashlib.sha1(record_id.encode("utf-8")).hexdigest()[:2]
        shards[shard][record_id] = {
            "id": record_id,
            "pageid": record["pageid"],
            "namespace": record["namespace"],
            "title": record["title"],
            "revision": record["revision"],
            "sourceUrl": record["sourceUrl"],
            "html": clean_html,
            "rawHtml": record["rawHtml"],
            "text": record["text"],
        }
        categories.update(record["categories"])
        portal_counts.update(record["portals"])
        index.append({
            "id": record_id,
            "pageid": record["pageid"],
            "namespace": record["namespace"],
            "namespaceLabel": record["namespaceLabel"],
            "title": record["title"],
            "shard": shard,
            "textBytes": len(raw_bytes),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "revision": record["revision"],
            "sourceUrl": record["sourceUrl"],
            "redirectTo": record["redirectTo"],
            "categories": record["categories"],
            "headings": record["headings"],
            "preview": record["preview"],
            "portals": record["portals"],
        })
        if number % 250 == 0:
            print(f"rendered {number}/{len(records)}", flush=True)

    for shard, values in sorted(shards.items()):
        dump_json(data_dir / "archive" / f"{shard}.json", values)

    index.sort(key=lambda item: (item["namespace"], item["title"].casefold()))
    media = sorted(crawler.media.values(), key=lambda item: item["name"].casefold())
    media_counts = Counter(item["mediaType"] for item in media)
    dump_json(data_dir / "archive-index.json", index)
    dump_json(data_dir / "media-index.json", media)
    dump_json(data_dir / "category-index.json", [{"name": name, "count": count} for name, count in categories.most_common()])
    dump_json(data_dir / "portal-index.json", [{"id": key, "title": value["title"], "count": portal_counts[key], "keywords": list(value["keywords"])} for key, value in PORTALS.items()])
    dump_json(data_dir / "crawl-failures.json", crawler.failed, pretty=True)

    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    counts = {
        "pages": len(index),
        "shards": len(shards),
        "categories": len(categories),
        "contentBytes": content_bytes,
        "media": len(media),
        "images": media_counts["image"],
        "audio": media_counts["audio"],
        "video": media_counts["video"],
        "crawlRequests": crawler.requests,
        "crawlFailures": len(crawler.failed),
    }
    manifest = {
        "schemaVersion": 3,
        "snapshotMode": "rendered-html-link-graph",
        "generatedAt": generated_at,
        "source": {"siteName": "魔法纪录中文Wiki", "base": BASE, "apiBlocked": True},
        "counts": counts,
        "features": ["rendered-html-fidelity", "raw-inner-html", "internal-link-routing", "category-and-heading-search", "thematic-portals", "media-index", "offline-shell"],
    }
    dump_json(data_dir / "runtime-manifest.json", manifest, pretty=True)
    dump_json(output / "health.json", {"status": "ok", "site": "magireco-cn-reader", "readerVersion": 3, "generatedAt": generated_at, "counts": counts}, pretty=True)

    for source in static_dir.rglob("*"):
        if source.is_file():
            destination = output / source.relative_to(static_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    app_path = output / "app.js"
    app_text = app_path.read_text(encoding="utf-8")
    app_text = app_text.replace("${renderWikitext(record.wikitext)}", "${record.html || renderWikitext(record.wikitext)}")
    app_text = app_text.replace("record.wikitext || '（空页面）'", "record.rawHtml || record.wikitext || '（空页面）'")
    app_text = app_text.replace("record.wikitext || ''", "record.rawHtml || record.wikitext || ''")
    app_text = app_text.replace("复制原始 wikitext", "复制原始渲染HTML")
    app_text = app_text.replace("查看完整原始 wikitext（保真层）", "查看完整原始渲染HTML（保真层）")
    app_path.write_text(app_text, encoding="utf-8")
    (output / ".nojekyll").touch()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--static", type=Path)
    parser.add_argument("--pause", type=float, default=0.12)
    parser.add_argument("--max-pages", type=int, default=8000)
    parser.add_argument("--max-requests", type=int, default=14000)
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    static_dir = args.static or root / "static"
    crawler = Crawler(pause=args.pause, max_pages=args.max_pages, max_requests=args.max_requests, timeout=args.timeout)
    crawler.crawl()
    if len(crawler.records) < 1000:
        raise RuntimeError(f"Crawl graph is unexpectedly small: {len(crawler.records)} pages")
    manifest = build_output(crawler, output, static_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
