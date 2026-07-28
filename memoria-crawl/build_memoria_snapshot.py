#!/usr/bin/env python3
"""Build a structured memoria dataset from ordinary rendered Wiki pages.

The Wiki blocks api.php and Special:Export for cloud traffic, but ordinary
category, template and article pages remain readable.  This crawler enumerates
``Template:记忆数据表/*`` through both the template root page and the paginated
``Category:数据模板`` graph, then parses each rendered data table.  The matching
``记忆结晶/*`` article is used for the bilingual description when available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

BASE = "https://magireco.moe"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/138.0 Safari/537.36 "
    "MagirecoMemoriaPreservation/1.0"
)
TEMPLATE_PREFIX = "Template:记忆数据表/"
ARTICLE_PREFIX = "记忆结晶/"
UTILITY_NAMES = {
    "Get", "doc", "empty", "icon", "icon-SC", "icon-TC", "icon-simp", "icon-small",
    "list", "list-SC", "list-TC", "name", "nameZh", "row-initial", "row-initial-SC",
    "row-initial-TC", "row-mlb", "row-mlb-SC", "row-mlb-TC", "row-related", "sandbox",
}
RETRYABLE = {403, 408, 425, 429, 500, 502, 503, 504}


def dump_json(path: Path, value: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
            sort_keys=pretty,
        )
        + "\n",
        encoding="utf-8",
    )


def page_url(title: str) -> str:
    return f"{BASE}/wiki/{quote(title.replace(' ', '_'), safe=':()!$&\'*,;=@~+-._')}"


def clean_title(value: str) -> str:
    return unquote(value).replace("_", " ").strip().lstrip(":")


def title_from_href(href: str) -> str | None:
    parsed = urlparse(urljoin(BASE, href))
    if parsed.hostname not in {"magireco.moe", "www.magireco.moe"}:
        return None
    if parsed.path.startswith("/wiki/"):
        return clean_title(parsed.path[len("/wiki/"):])
    if parsed.path.endswith("/index.php"):
        query = parse_qs(parsed.query)
        if query.get("title"):
            return clean_title(query["title"][0])
    return None


def visible_text(node: Tag | None, separator: str = "\n") -> str:
    if node is None:
        return ""
    value = node.get_text(separator, strip=True)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def parse_pair(value: str) -> tuple[int | None, int | None]:
    match = re.search(r"(-?\d+)\s*(?:→|->|～|~)\s*(-?\d+)", value)
    if match:
        return int(match.group(1)), int(match.group(2))
    number = re.search(r"-?\d+", value)
    if number:
        parsed = int(number.group(0))
        return parsed, parsed
    return None, None


def split_arrow(value: str) -> tuple[str, str]:
    parts = re.split(r"\s*(?:→|->)\s*", value, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    clean = value.strip()
    return clean, clean


def japanese_score(value: str) -> int:
    return len(re.findall(r"[\u3040-\u30ff]", value))


def extract_section_paragraphs(soup: BeautifulSoup, heading_name: str) -> list[str]:
    heading = next(
        (node for node in soup.select("h2,h3,h4") if heading_name in visible_text(node, " ")),
        None,
    )
    if heading is None:
        return []
    level = int(heading.name[1])
    values: list[str] = []
    node = heading.next_sibling
    while node:
        name = getattr(node, "name", None)
        if name and re.fullmatch(r"h[1-6]", name) and int(name[1]) <= level:
            break
        if isinstance(node, Tag):
            if node.name == "p":
                value = visible_text(node)
                if value:
                    values.append(value)
            else:
                for paragraph in node.select(":scope > p"):
                    value = visible_text(paragraph)
                    if value:
                        values.append(value)
        node = node.next_sibling
    return values


@dataclass
class FetchResult:
    url: str
    status: int | None
    text: str | None
    error: str | None


class PoliteFetcher:
    def __init__(self, *, pause: float, timeout: float, retries: int, max_requests: int) -> None:
        self.pause = max(0.02, pause)
        self.timeout = timeout
        self.retries = retries
        self.max_requests = max_requests
        self.requests = 0
        self._request_lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._next_request_at = 0.0
        self._local = threading.local()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update({
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.7,en;q=0.4",
                "Connection": "keep-alive",
            })
            self._local.session = session
        return session

    def _reserve(self) -> bool:
        with self._request_lock:
            if self.requests >= self.max_requests:
                return False
            self.requests += 1
        with self._rate_lock:
            now = time.monotonic()
            slot = max(now, self._next_request_at)
            self._next_request_at = slot + self.pause
            delay = slot - now
        if delay > 0:
            time.sleep(delay)
        return True

    def fetch(self, url: str) -> FetchResult:
        last_status: int | None = None
        last_error: str | None = None
        session = self._session()
        for attempt in range(1, self.retries + 1):
            if not self._reserve():
                return FetchResult(url, None, None, "request budget exhausted")
            try:
                response = session.get(url, timeout=self.timeout, allow_redirects=True)
                last_status = response.status_code
                if response.status_code == 200 and "text/html" in response.headers.get("content-type", ""):
                    return FetchResult(response.url, response.status_code, response.text, None)
                if response.status_code not in RETRYABLE:
                    return FetchResult(response.url, response.status_code, None, None)
            except requests.RequestException as exc:
                last_error = str(exc)
            time.sleep(min(5.0, 0.7 * (2 ** (attempt - 1))))
        return FetchResult(url, last_status, None, last_error)


def enumerate_template_titles(fetcher: PoliteFetcher) -> tuple[list[str], list[dict[str, Any]]]:
    titles: set[str] = set()
    failures: list[dict[str, Any]] = []

    def collect(html: str) -> None:
        soup = BeautifulSoup(html, "lxml")
        for anchor in soup.select("a[href]"):
            title = title_from_href(str(anchor.get("href") or ""))
            if not title or not title.startswith(TEMPLATE_PREFIX):
                continue
            name = title[len(TEMPLATE_PREFIX):].strip()
            if name and name not in UTILITY_NAMES:
                titles.add(title)

    root = fetcher.fetch(page_url("Template:记忆数据表"))
    if root.text:
        collect(root.text)
    else:
        failures.append({"stage": "template-root", "url": root.url, "status": root.status, "error": root.error})

    queue = [page_url("Category:数据模板")]
    seen: set[str] = set()
    while queue and len(seen) < 30:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        result = fetcher.fetch(url)
        if not result.text:
            failures.append({"stage": "category", "url": url, "status": result.status, "error": result.error})
            continue
        collect(result.text)
        soup = BeautifulSoup(result.text, "lxml")
        pages = soup.select_one("#mw-pages") or soup
        for anchor in pages.select("a[href]"):
            label = visible_text(anchor, " ")
            href = str(anchor.get("href") or "")
            absolute = urljoin(BASE, href)
            parsed = urlparse(absolute)
            query = parse_qs(parsed.query)
            if (
                title_from_href(href) == "Category:数据模板"
                and any(key in query for key in ("pagefrom", "from", "subcatfrom"))
                and ("下一页" in label or "next" in label.casefold())
                and absolute not in seen
            ):
                queue.append(absolute)
    return sorted(titles, key=str.casefold), failures


def choose_data_table(content: Tag) -> Tag | None:
    candidates: list[tuple[int, Tag]] = []
    for table in content.select("table"):
        value = visible_text(table, " ")
        score = sum(token in value for token in ("稀有度", "HP", "ATK", "DEF", "效果", "效果详细"))
        if score >= 4:
            candidates.append((score, table))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def direct_rows(table: Tag) -> list[Tag]:
    body = table.find("tbody", recursive=False)
    return list(body.find_all("tr", recursive=False)) if body else []


def row_cells(row: Tag) -> list[str]:
    return [visible_text(cell) for cell in row.find_all(["th", "td"], recursive=False)]


def parse_number(content: Tag) -> int | None:
    for anchor in content.select("a[href]"):
        href = str(anchor.get("href") or "")
        if "记忆结晶" not in unquote(href):
            continue
        match = re.search(r"#(\d{3,6})(?:$|[^\d])", href)
        if match:
            return int(match.group(1))
    return None


def choose_image(content: Tag, page_name: str) -> str | None:
    candidates: list[tuple[int, str]] = []
    for image in content.select("img"):
        source = image.get("src") or image.get("data-src")
        if not source:
            continue
        absolute = urljoin(BASE, str(source))
        parsed = urlparse(absolute)
        if parsed.hostname not in {"magireco.moe", "www.magireco.moe", "cdn.mfjl.wiki"}:
            continue
        if any(part in parsed.path for part in ("/skins/", "/resources/", "PoweredBy", "button")):
            continue
        width = int(re.sub(r"\D", "", str(image.get("width") or "0")) or 0)
        alt = str(image.get("alt") or "")
        score = width + (400 if page_name in unquote(parsed.path) or page_name in alt else 0)
        candidates.append((score, absolute))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def parse_template(title: str, result: FetchResult) -> dict[str, Any]:
    if not result.text:
        raise RuntimeError(f"template fetch failed: HTTP {result.status} {result.error or ''}")
    page_name = title[len(TEMPLATE_PREFIX):]
    soup = BeautifulSoup(result.text, "lxml")
    content = soup.select_one("#mw-content-text .mw-parser-output") or soup.select_one("#mw-content-text")
    if content is None:
        raise RuntimeError("missing mw-content-text")
    table = choose_data_table(content)
    if table is None:
        raise RuntimeError("memory data table not found")
    rows = direct_rows(table)
    parsed_rows = [row_cells(row) for row in rows]

    name_ja = page_name
    name_zh = ""
    intro_text = visible_text(content, "\n")
    name_match = re.search(re.escape(name_ja) + r"\s*[（(]([^）)\n]+)[）)]", intro_text)
    if name_match:
        name_zh = name_match.group(1).strip()

    artist = ""
    artist_match = re.search(r"画师[：:]\s*([^\n]+)", intro_text)
    if artist_match:
        artist = artist_match.group(1).strip()

    rarity: int | None = None
    level_min: int | None = None
    level_max: int | None = None
    equip_limit = ""
    hp_min = hp_max = atk_min = atk_max = def_min = def_max = None
    memory_type = ""
    skill_name = skill_name_max = ""
    effect = effect_max = ""
    effect_detail = effect_detail_max = ""
    cooldown = cooldown_max = None

    for index, cells in enumerate(parsed_rows):
        compact = [value.replace("\n", " ").strip() for value in cells]
        joined = " | ".join(compact)
        if "稀有度" in compact and index + 1 < len(parsed_rows):
            values = parsed_rows[index + 1]
            if values:
                rarity = len(re.findall(r"[✸★☆]", values[0])) or None
            if len(values) >= 2:
                level_min, level_max = parse_pair(values[1])
            if len(values) >= 3:
                equip_limit = values[2].strip()
        if compact[:3] == ["HP", "ATK", "DEF"] and index + 1 < len(parsed_rows):
            values = parsed_rows[index + 1]
            if len(values) >= 3:
                hp_min, hp_max = parse_pair(values[0])
                atk_min, atk_max = parse_pair(values[1])
                def_min, def_max = parse_pair(values[2])
        if compact and compact[0] == "效果" and index + 1 < len(parsed_rows):
            if len(compact) >= 2:
                memory_type = compact[-1]
            skill_values = parsed_rows[index + 1]
            if skill_values:
                skill_name, skill_name_max = split_arrow(skill_values[0])
            if len(skill_values) >= 2:
                cooldown, cooldown_max = parse_pair(skill_values[1])
            if index + 2 < len(parsed_rows):
                effect_values = parsed_rows[index + 2]
                if effect_values:
                    effect, effect_max = split_arrow(effect_values[0])
        if "效果详细" in joined:
            for later in parsed_rows[index + 1:index + 5]:
                if not later:
                    continue
                label = later[0].replace("\n", " ").strip()
                value = later[-1].strip()
                if "初始" in label:
                    effect_detail = value
                elif "满破" in label or "滿破" in label:
                    effect_detail_max = value

    obtain = ""
    obtain_match = re.search(r"入手方式[：:]\s*([^\n]+)", intro_text)
    if obtain_match:
        obtain = obtain_match.group(1).strip()
    notes = ""
    note_lines = [line for line in intro_text.splitlines() if line.startswith("注：") or line.startswith("注:")]
    if note_lines:
        notes = "\n".join(note_lines)

    raw_table_html = str(table)
    return {
        "key": page_name,
        "templateTitle": title,
        "articleTitle": ARTICLE_PREFIX + page_name,
        "templateUrl": result.url,
        "articleUrl": page_url(ARTICLE_PREFIX + page_name),
        "number": parse_number(content),
        "nameJa": name_ja,
        "nameZh": name_zh,
        "artist": artist,
        "rarity": rarity,
        "levelMin": level_min,
        "levelMax": level_max,
        "equipLimit": equip_limit,
        "hpMin": hp_min,
        "hpMax": hp_max,
        "atkMin": atk_min,
        "atkMax": atk_max,
        "defMin": def_min,
        "defMax": def_max,
        "type": memory_type,
        "skillName": skill_name,
        "skillNameMax": skill_name_max,
        "effect": effect,
        "effectMax": effect_max,
        "effectDetail": effect_detail,
        "effectDetailMax": effect_detail_max,
        "cooldown": cooldown,
        "cooldownMax": cooldown_max,
        "obtain": obtain,
        "notes": notes,
        "imageUrl": choose_image(content, page_name),
        "rawTableHtml": raw_table_html,
        "rawTableSha256": hashlib.sha256(raw_table_html.encode("utf-8")).hexdigest(),
        "revision": None,
        "descZh": "",
        "descJa": "",
        "descriptionHtml": "",
    }


def enrich_article(item: dict[str, Any], result: FetchResult) -> None:
    if not result.text:
        item["articleStatus"] = result.status
        item["articleError"] = result.error
        return
    soup = BeautifulSoup(result.text, "lxml")
    content = soup.select_one("#mw-content-text .mw-parser-output") or soup.select_one("#mw-content-text")
    if content is None:
        item["articleError"] = "missing mw-content-text"
        return
    paragraphs = extract_section_paragraphs(soup, "简介")
    split_at = next((index for index, value in enumerate(paragraphs) if japanese_score(value) >= 2), len(paragraphs))
    item["descZh"] = "\n\n".join(paragraphs[:split_at]).strip()
    item["descJa"] = "\n\n".join(paragraphs[split_at:]).strip()
    heading = next((node for node in soup.select("h2,h3") if "简介" in visible_text(node, " ")), None)
    description_nodes: list[str] = []
    if heading:
        level = int(heading.name[1])
        node = heading.next_sibling
        while node:
            name = getattr(node, "name", None)
            if name and re.fullmatch(r"h[1-6]", name) and int(name[1]) <= level:
                break
            if isinstance(node, Tag):
                description_nodes.append(str(node))
            node = node.next_sibling
    item["descriptionHtml"] = "".join(description_nodes)
    item["articleUrl"] = result.url
    config = re.search(r'"wgCurRevisionId"\s*:\s*(\d+)', result.text)
    item["revision"] = int(config.group(1)) if config else None


def build(args: argparse.Namespace) -> dict[str, Any]:
    output: Path = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fetcher = PoliteFetcher(
        pause=args.pause,
        timeout=args.timeout,
        retries=args.retries,
        max_requests=args.max_requests,
    )
    titles, failures = enumerate_template_titles(fetcher)
    discovered = len(titles)
    if discovered < args.minimum_discovered:
        raise RuntimeError(f"template enumeration unexpectedly small: {discovered}")
    selected = titles[: args.limit] if args.limit else titles
    if args.include:
        for name in args.include:
            title = TEMPLATE_PREFIX + name
            if title in titles and title not in selected:
                selected.append(title)

    records: list[dict[str, Any]] = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="memoria-template") as pool:
        futures: dict[Future[FetchResult], str] = {
            pool.submit(fetcher.fetch, page_url(title)): title for title in selected
        }
        for future in as_completed(futures):
            title = futures[future]
            result = future.result()
            try:
                records.append(parse_template(title, result))
            except Exception as exc:  # noqa: BLE001
                failures.append({"stage": "template", "title": title, "url": result.url, "status": result.status, "error": str(exc)})
            if len(records) and len(records) % 100 == 0:
                print(f"templates={len(records)}/{len(selected)} requests={fetcher.requests} failures={len(failures)}", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="memoria-article") as pool:
        futures = {pool.submit(fetcher.fetch, item["articleUrl"]): item for item in records}
        for future in as_completed(futures):
            item = futures[future]
            result = future.result()
            enrich_article(item, result)

    for item in records:
        item["searchText"] = " ".join(
            str(value or "")
            for value in (
                item["number"], item["nameJa"], item["nameZh"], item["artist"], item["rarity"], item["type"],
                item["equipLimit"], item["skillName"], item["skillNameMax"], item["effect"], item["effectMax"],
                item["effectDetail"], item["effectDetailMax"], item["obtain"], item["descZh"], item["descJa"],
            )
        )
    records.sort(key=lambda item: ((item["number"] is None), item["number"] or 10**9, item["nameJa"].casefold()))
    number_groups: dict[str, list[str]] = {}
    for item in records:
        if item["number"] is not None:
            number_groups.setdefault(str(item["number"]), []).append(item["key"])

    elapsed = time.monotonic() - started
    manifest = {
        "schemaVersion": 1,
        "source": "rendered-template-and-article-pages",
        "discoveredTemplatePages": discovered,
        "selectedTemplatePages": len(selected),
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
    dump_json(output / "memoria.json", records)
    dump_json(output / "number-groups.json", number_groups)
    dump_json(output / "manifest.json", manifest, pretty=True)
    dump_json(output / "failures.json", failures, pretty=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0, help="0 means all discovered templates")
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--minimum-discovered", type=int, default=1200)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--pause", type=float, default=0.18, help="global seconds between request starts")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--max-requests", type=int, default=6000)
    args = parser.parse_args()
    manifest = build(args)
    minimum_records = min(args.limit or args.minimum_discovered, args.minimum_discovered)
    if args.limit and manifest["records"] < max(1, args.limit - 3):
        raise RuntimeError(f"sample parse coverage too small: {manifest}")
    if not args.limit and manifest["records"] < minimum_records:
        raise RuntimeError(f"full parse coverage too small: {manifest}")


if __name__ == "__main__":
    main()
