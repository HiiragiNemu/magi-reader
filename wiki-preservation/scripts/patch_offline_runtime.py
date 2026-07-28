#!/usr/bin/env python3
"""Synchronize the application shell and Service Worker with one revision.

The reader evolved from UI v4 to structured v5 without updating the old
Service Worker cache namespace or its pre-cached URLs.  That allowed installed
browsers to retain a v4 offline shell which did not include the character,
voice, or Doppel runtimes.  This build-time patch derives the exact same-origin
asset URLs from the final index.html, updates app.js registration revision, and
writes a new Service Worker which deletes all older reader caches on activate.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


ASSET_RE = re.compile(
    r"<(?:script\b[^>]*?\bsrc|link\b[^>]*?\bhref)=[\"']([^\"']+)[\"']",
    re.I,
)


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--revision", default="5.4")
    args = parser.parse_args()

    root = args.root.resolve()
    index_path = root / "index.html"
    app_path = root / "app.js"
    sw_path = root / "sw.js"

    index = index_path.read_text(encoding="utf-8")
    app = app_path.read_text(encoding="utf-8")

    patched_app, replacements = re.subn(
        r"const UI_VERSION\s*=\s*(?:\d+|'[^']+'|\"[^\"]+\");",
        f"const UI_VERSION = '{args.revision}';",
        app,
        count=1,
    )
    if replacements != 1:
        raise RuntimeError("app.js UI_VERSION declaration not found exactly once")
    app_path.write_text(patched_app, encoding="utf-8")

    assets: list[str] = []
    for raw in ASSET_RE.findall(index):
        parsed = urlsplit(raw)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
            continue
        if parsed.path.endswith((".js", ".css", ".webmanifest", ".svg", ".png", ".ico")):
            assets.append(raw)

    core = unique(
        [
            "/",
            "/index.html",
            *assets,
            "/health.json",
            "/data/runtime-manifest.json",
            "/data/structured/manifest.json",
            "/data/structured/characters.json",
            "/data/structured/voice-index.json",
            "/data/structured/doppel.json",
        ]
    )

    required = ("/app.js", "/structured-ui.js", "/doppel-ui.js")
    for path in required:
        if not any(urlsplit(value).path == path for value in core):
            raise RuntimeError(f"final index does not reference required asset: {path}")

    version = f"magireco-cn-reader-v{args.revision}-offline"
    source = f"""/* Generated from the final production index by patch_offline_runtime.py. */
const VERSION = {json.dumps(version)};
const SHELL = `${{VERSION}}-shell`;
const DATA = `${{VERSION}}-data`;
const STATIC = `${{VERSION}}-static`;
const CORE = {json.dumps(core, ensure_ascii=False, indent=2)};

self.addEventListener('install', (event) => {{
  event.waitUntil(
    caches.open(SHELL)
      .then((cache) => cache.addAll(CORE))
      .then(() => self.skipWaiting()),
  );
}});

self.addEventListener('activate', (event) => {{
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key.startsWith('magireco-cn-reader-') && ![SHELL, DATA, STATIC].includes(key))
          .map((key) => caches.delete(key)),
      ))
      .then(() => self.clients.claim()),
  );
}});

async function networkFirst(request, fallback = null) {{
  const cache = await caches.open(SHELL);
  try {{
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  }} catch {{
    return (await cache.match(request))
      || (fallback ? await cache.match(fallback) : null)
      || Response.error();
  }}
}}

async function staleWhileRevalidate(request, cacheName) {{
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const refresh = fetch(request)
    .then(async (response) => {{
      if (response.ok) await cache.put(request, response.clone());
      return response;
    }})
    .catch(() => null);
  return cached || (await refresh) || Response.error();
}}

self.addEventListener('fetch', (event) => {{
  const request = event.request;
  if (request.method !== 'GET' || request.headers.has('range')) return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {{
    event.respondWith(networkFirst(request, '/index.html'));
    return;
  }}
  if (url.pathname === '/health.json' || url.pathname === '/index.html') {{
    event.respondWith(networkFirst(request, '/index.html'));
    return;
  }}
  if (url.pathname.startsWith('/data/') && (url.pathname.endsWith('.json') || url.pathname.endsWith('.gz'))) {{
    event.respondWith(staleWhileRevalidate(request, DATA));
    return;
  }}
  if (/\.(?:js|css|woff2?|png|jpe?g|gif|svg|webp|ico|webmanifest)$/i.test(url.pathname)) {{
    event.respondWith(staleWhileRevalidate(request, STATIC));
  }}
}});

self.addEventListener('message', (event) => {{
  if (event.data === 'SKIP_WAITING') self.skipWaiting();
  if (event.data === 'CLEAR_READER_CACHE') {{
    event.waitUntil(Promise.all([SHELL, DATA, STATIC].map((name) => caches.delete(name))));
  }}
}});
"""
    sw_path.write_text(source, encoding="utf-8")
    print(json.dumps({"revision": args.revision, "version": version, "core": core}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
