#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE = "https://magireco.moe"
URLS = [
    f"{BASE}/wiki/Special:ListFiles?limit=500&ilsearch=.mp3",
    f"{BASE}/index.php?title=Special:ListFiles&limit=500&ilsearch=.mp3",
    f"{BASE}/wiki/Special:ListFiles?limit=500&mediatype=AUDIO",
    f"{BASE}/index.php?title=Special:ListFiles&limit=500&mediatype=AUDIO",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138 Safari/537.36 MagirecoPreservationAudioProbe/1.0",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
})

out = Path("audio-probe")
out.mkdir(exist_ok=True)
results = []

for index, url in enumerate(URLS, 1):
    try:
        response = session.get(url, timeout=30, allow_redirects=True)
        text = response.text
        soup = BeautifulSoup(text, "lxml")
        links = []
        for anchor in soup.select("a[href]"):
            href = urljoin(response.url, str(anchor.get("href") or ""))
            label = anchor.get_text(" ", strip=True)
            if re.search(r"\.mp3(?:$|[?#])", href, re.I) or re.search(r"\.mp3$", label, re.I):
                links.append({"label": label, "href": href})
        pagination = []
        for anchor in soup.select("a[href]"):
            href = urljoin(response.url, str(anchor.get("href") or ""))
            query = parse_qs(urlparse(href).query)
            if any(key in query for key in ("offset", "iloffset", "filefrom")):
                pagination.append({"label": anchor.get_text(" ", strip=True), "href": href})
        record = {
            "requested": url,
            "final": response.url,
            "status": response.status_code,
            "contentType": response.headers.get("content-type", ""),
            "bytes": len(response.content),
            "title": soup.title.get_text(" ", strip=True) if soup.title else "",
            "mp3Links": links[:1000],
            "mp3Count": len(links),
            "pagination": pagination[:100],
            "bodyPreview": re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:1200],
        }
        results.append(record)
        (out / f"response-{index}.html").write_text(text, encoding="utf-8")
    except Exception as exc:
        results.append({"requested": url, "error": repr(exc)})

(out / "probe.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
if not any(item.get("mp3Count", 0) for item in results):
    raise SystemExit("No MP3 listing links were discovered")
