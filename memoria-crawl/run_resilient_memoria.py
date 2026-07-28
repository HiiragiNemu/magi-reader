#!/usr/bin/env python3
"""Run the memoria crawler with resilient direct or edge-proxied fetching.

Direct GitHub-hosted runners may receive HTTP 403 from the Wiki after the first
category request.  When ``MAGIRECO_FETCH_PROXY`` is present, every approved
source URL is sent through a temporary token-protected Cloudflare Pages Worker;
otherwise the proven per-thread home-page warm-up strategy is used directly.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any
from urllib.parse import quote

import requests

import build_memoria_snapshot as M


M.USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/138.0 Safari/537.36 "
    "MagirecoChinesePreservationReader/3.0"
)


class ResilientPoliteFetcher(M.PoliteFetcher):
    """PoliteFetcher with per-thread warm-up, 403 recovery and optional proxy."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._warm_lock = threading.Lock()
        self.proxy = os.environ.get("MAGIRECO_FETCH_PROXY", "").rstrip("/")
        self.proxy_token = os.environ.get("MAGIRECO_PROXY_TOKEN", "")
        if bool(self.proxy) != bool(self.proxy_token):
            raise RuntimeError("MAGIRECO_FETCH_PROXY and MAGIRECO_PROXY_TOKEN must be supplied together")

    def _request(self, session: requests.Session, source_url: str) -> requests.Response:
        request_url = source_url
        headers = {"Referer": M.page_url("首页")}
        if self.proxy:
            request_url = f"{self.proxy}/?url={quote(source_url, safe='')}"
            headers["x-magireco-proxy-token"] = self.proxy_token
        return session.get(
            request_url,
            timeout=self.timeout,
            allow_redirects=True,
            headers=headers,
        )

    def _source_url(self, response: requests.Response, fallback: str) -> str:
        return response.headers.get("x-magireco-source-url") or fallback

    def _warm_session(self, session: requests.Session, *, force: bool = False) -> None:
        if not force and getattr(self._local, "warmed", False):
            return
        with self._warm_lock:
            if not force and getattr(self._local, "warmed", False):
                return
            if not self._reserve():
                return
            try:
                response = self._request(session, M.page_url("首页"))
                if response.status_code == 200:
                    self._local.warmed = True
            except requests.RequestException:
                pass

    def fetch(self, url: str) -> M.FetchResult:
        session = self._session()
        self._warm_session(session)
        last_status: int | None = None
        last_error: str | None = None
        final_url = url

        for attempt in range(1, self.retries + 1):
            if not self._reserve():
                return M.FetchResult(final_url, None, None, "request budget exhausted")
            try:
                response = self._request(session, url)
                final_url = self._source_url(response, url)
                last_status = response.status_code
                content_type = response.headers.get("content-type", "")
                if response.status_code == 200 and "text/html" in content_type:
                    self._local.warmed = True
                    return M.FetchResult(final_url, response.status_code, response.text, None)
                if response.status_code == 403:
                    self._local.warmed = False
                    self._warm_session(session, force=True)
                if response.status_code not in M.RETRYABLE:
                    return M.FetchResult(final_url, response.status_code, None, None)
            except requests.RequestException as exc:
                last_error = str(exc)
            time.sleep(min(8.0, 1.0 * (2 ** (attempt - 1))))

        return M.FetchResult(final_url, last_status, None, last_error)


M.PoliteFetcher = ResilientPoliteFetcher


if __name__ == "__main__":
    M.main()
