#!/usr/bin/env python3
"""Parallel rendered-HTML snapshot builder with a global polite rate limit.

Network waits are handled concurrently, while parsing, graph expansion and all
state mutations remain in the main thread.  The global request interval keeps
total request frequency bounded regardless of worker count.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

import build_html_snapshot as H


class ParallelCrawler(H.Crawler):
    def __init__(
        self,
        *,
        pause: float,
        max_pages: int,
        max_requests: int,
        timeout: float,
        workers: int,
        retries: int,
    ) -> None:
        super().__init__(
            pause=pause,
            max_pages=max_pages,
            max_requests=max_requests,
            timeout=timeout,
        )
        self.workers = max(1, workers)
        self.retries = max(1, retries)
        self._thread_local = threading.local()
        self._request_lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._next_request_at = 0.0

    def _session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "User-Agent": H.USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
                    "Connection": "keep-alive",
                }
            )
            self._thread_local.session = session
        return session

    def _reserve_request(self) -> bool:
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

    def _warm_session(self, session: requests.Session) -> None:
        if not self._reserve_request():
            return
        try:
            session.get(H.title_url(H.HOME_TITLE), timeout=self.timeout, allow_redirects=True)
        except requests.RequestException:
            pass

    def get(self, url: str) -> requests.Response | None:
        session = self._session()
        last_error: str | None = None
        last_status: int | None = None
        for attempt in range(1, self.retries + 1):
            if not self._reserve_request():
                break
            try:
                response = session.get(url, timeout=self.timeout, allow_redirects=True)
                last_status = response.status_code
                if response.status_code == 200 and "text/html" in response.headers.get("content-type", ""):
                    return response
                if response.status_code == 403:
                    self._warm_session(session)
                if response.status_code not in {403, 408, 425, 429, 500, 502, 503, 504}:
                    break
                time.sleep(min(6.0, 0.8 * (2 ** (attempt - 1))))
            except requests.RequestException as exc:
                last_error = str(exc)
                time.sleep(min(6.0, 0.8 * (2 ** (attempt - 1))))
        failure: dict[str, Any] = {"url": url}
        if last_status is not None:
            failure["status"] = last_status
        if last_error:
            failure["error"] = last_error
        self.failed.append(failure)
        return None

    def _store_response(self, url: str, response: requests.Response) -> None:
        raw_html = response.text
        soup = BeautifulSoup(raw_html, "lxml")
        self.extract_links(soup)
        namespace, pageid, revision, page_name = H.page_config(raw_html, soup)
        if not page_name:
            return
        if namespace not in H.ALLOWED_NAMESPACES or H.excluded_title(page_name):
            return
        record_id = f"{namespace}:{page_name}"
        if record_id in self.records:
            return
        content = soup.select_one("#mw-content-text")
        if content is None:
            return
        parser_output = content.select_one(".mw-parser-output") or content
        categories = [
            anchor.get_text(" ", strip=True)
            for anchor in soup.select("#mw-normal-catlinks ul a")
            if anchor.get_text(" ", strip=True)
        ]
        headings = []
        for node in parser_output.select("h2,h3,h4,h5,h6"):
            text = node.get_text(" ", strip=True)
            if not text:
                continue
            identifier = node.get("id")
            if not identifier:
                child = node.select_one("[id]")
                identifier = child.get("id") if child else None
            headings.append(
                {
                    "level": int(node.name[1]),
                    "text": text,
                    "id": identifier,
                }
            )
        text = parser_output.get_text("\n", strip=True)
        preview = H.re.sub(r"\s+", " ", text).strip()[:520]
        raw_inner = "".join(str(child) for child in parser_output.contents)
        redirect = soup.select_one(".redirectMsg a")
        portals = H.record_portals(namespace, page_name, categories, headings, preview)
        self.records[record_id] = {
            "id": record_id,
            "pageid": pageid or None,
            "namespace": namespace,
            "namespaceLabel": H.NAMESPACE_LABELS.get(namespace, f"命名空间 {namespace}"),
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

    def crawl(self) -> None:
        for title in H.SEED_TITLES:
            self.enqueue(H.title_url(title))

        started = time.monotonic()
        next_report = 100
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="wiki-fetch") as pool:
            while self.queue and len(self.records) < self.max_pages and self.requests < self.max_requests:
                remaining = self.max_pages - len(self.records)
                batch_size = min(self.workers, len(self.queue), max(1, remaining))
                batch: list[str] = [self.queue.popleft() for _ in range(batch_size)]
                futures: dict[Future[requests.Response | None], str] = {
                    pool.submit(self.get, url): url for url in batch
                }
                for future in as_completed(futures):
                    url = futures[future]
                    try:
                        response = future.result()
                    except Exception as exc:  # noqa: BLE001
                        self.failed.append({"url": url, "error": f"worker: {exc}"})
                        continue
                    if response is not None and len(self.records) < self.max_pages:
                        self._store_response(url, response)
                    if len(self.records) >= next_report:
                        elapsed = time.monotonic() - started
                        print(
                            f"stored={len(self.records)} requests={self.requests} "
                            f"queued={len(self.queue)} failed={len(self.failed)} "
                            f"elapsed={elapsed / 60:.1f}m rate={len(self.records) / max(elapsed, 0.001):.2f} pages/s",
                            flush=True,
                        )
                        next_report += 100
                    if len(self.records) >= self.max_pages:
                        break


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--static", type=Path)
    parser.add_argument("--pause", type=float, default=0.12, help="global seconds between request starts")
    parser.add_argument("--max-pages", type=int, default=8000)
    parser.add_argument("--max-requests", type=int, default=16000)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--minimum-pages", type=int, default=1000)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    static_dir = args.static or root / "static"
    crawler = ParallelCrawler(
        pause=args.pause,
        max_pages=args.max_pages,
        max_requests=args.max_requests,
        timeout=args.timeout,
        workers=args.workers,
        retries=args.retries,
    )
    crawler.crawl()
    if len(crawler.records) < args.minimum_pages:
        raise RuntimeError(
            f"Crawl graph is unexpectedly small: {len(crawler.records)} pages; "
            f"requests={crawler.requests}, failures={len(crawler.failed)}"
        )
    manifest = H.build_output(crawler, output, static_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
