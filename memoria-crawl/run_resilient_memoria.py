#!/usr/bin/env python3
"""Run the memoria crawler with the proven Wiki session warm-up strategy.

The Wiki may return HTTP 403 to a fresh cloud session even though ordinary
rendered pages are public.  The existing 500-page preservation crawler handles
this by visiting the home page to establish cookies, warming again after a 403,
and then retrying with exponential backoff.  This runner applies the same
behaviour without duplicating the memoria parser.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import requests

import build_memoria_snapshot as M


M.USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/138.0 Safari/537.36 "
    "MagirecoChinesePreservationReader/3.0"
)


class ResilientPoliteFetcher(M.PoliteFetcher):
    """PoliteFetcher with per-thread cookie warm-up and 403 recovery."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._warm_lock = threading.Lock()

    def _warm_session(self, session: requests.Session, *, force: bool = False) -> None:
        if not force and getattr(self._local, "warmed", False):
            return
        # Serialise initial warm-ups so several workers do not hit the home page
        # simultaneously from one runner IP.
        with self._warm_lock:
            if not force and getattr(self._local, "warmed", False):
                return
            if not self._reserve():
                return
            try:
                response = session.get(
                    M.page_url("首页"),
                    timeout=self.timeout,
                    allow_redirects=True,
                    headers={"Referer": f"{M.BASE}/"},
                )
                if response.status_code == 200:
                    self._local.warmed = True
            except requests.RequestException:
                pass

    def fetch(self, url: str) -> M.FetchResult:
        session = self._session()
        self._warm_session(session)
        last_status: int | None = None
        last_error: str | None = None

        for attempt in range(1, self.retries + 1):
            if not self._reserve():
                return M.FetchResult(url, None, None, "request budget exhausted")
            try:
                response = session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True,
                    headers={"Referer": M.page_url("首页")},
                )
                last_status = response.status_code
                content_type = response.headers.get("content-type", "")
                if response.status_code == 200 and "text/html" in content_type:
                    self._local.warmed = True
                    return M.FetchResult(response.url, response.status_code, response.text, None)
                if response.status_code == 403:
                    self._local.warmed = False
                    self._warm_session(session, force=True)
                if response.status_code not in M.RETRYABLE:
                    return M.FetchResult(response.url, response.status_code, None, None)
            except requests.RequestException as exc:
                last_error = str(exc)
            time.sleep(min(8.0, 1.0 * (2 ** (attempt - 1))))

        return M.FetchResult(url, last_status, None, last_error)


M.PoliteFetcher = ResilientPoliteFetcher


if __name__ == "__main__":
    M.main()
