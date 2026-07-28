#!/usr/bin/env python3
"""Synchronize the production shell with a versioned Service Worker file.

Cloudflare Pages may retain fixed application assets at the edge even when a
query string changes. A browser could therefore load an old application body
from a nominally new URL and register the obsolete worker. This patch uses a
genuinely versioned worker filename, updates app.js registration, derives the
pre-cache URLs from the final index, writes compatibility and versioned worker
files, and emits no-cache rules for every application update entry point.
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
    parser.add_argument("--revision", default="5.5")
    args = parser.parse_args()

    root = args.root.resolve()
    index_path = root / "index.html"
    app_path = root / "app.js"
    compatibility_sw_path = root / "sw.js"
    versioned_sw_name = f"sw-v{args.revision}.js"
    versioned_sw_path = root / versioned_sw_name

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

    old_registration = "navigator.serviceWorker.register(`/sw.js?v=${UI_VERSION}`, { updateViaCache: 'none' })"
    new_registration = "navigator.serviceWorker.register(`/sw-v${UI_VERSION}.js`, { updateViaCache: 'none' })"
    if old_registration not in patched_app:
        raise RuntimeError("legacy Service Worker registration expression not found")
    patched_app = patched_app.replace(old_registration, new_registration, 1)
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
const FALLBACK_URL = new URL('/index.html', self.location.origin).href;

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

async function cachedShell(request) {{
  const cache = await caches.open(SHELL);
  return (await cache.match(request, {{ ignoreSearch: true }}))
    || (await cache.match(FALLBACK_URL, {{ ignoreSearch: true }}));
}}

async function networkFirst(request) {{
  const cache = await caches.open(SHELL);
  try {{
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  }} catch {{
    return (await cachedShell(request)) || new Response(
      '<!doctype html><meta charset="utf-8"><title>离线</title><p>资料库离线缓存尚未完成，请恢复网络后重新打开一次。</p>',
      {{ status: 503, headers: {{ 'content-type': 'text/html; charset=utf-8' }} }},
    );
  }}
}}

async function staleWhileRevalidate(request, cacheName) {{
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request, {{ ignoreSearch: true }});
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
    event.respondWith(networkFirst(request));
    return;
  }}
  if (url.pathname === '/health.json' || url.pathname === '/index.html') {{
    event.respondWith(networkFirst(request));
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
    compatibility_sw_path.write_text(source, encoding="utf-8")
    versioned_sw_path.write_text(source, encoding="utf-8")

    no_cache = "Cache-Control: no-cache, no-store, must-revalidate"
    update_paths = [
        "/",
        "/index.html",
        "/health.json",
        "/app.js",
        "/ui-v4-runtime.js",
        "/structured-ui.js",
        "/doppel-ui.js",
        "/styles.css",
        "/ui-v4-fixes.css",
        "/structured-ui.css",
        "/doppel-ui.css",
    ]
    blocks = [f"{path}\n  {no_cache}" for path in update_paths]
    blocks.extend(
        [
            f"/sw.js\n  {no_cache}\n  Service-Worker-Allowed: /",
            f"/{versioned_sw_name}\n  {no_cache}\n  Service-Worker-Allowed: /",
        ]
    )
    headers = "\n\n".join(blocks) + "\n"
    (root / "_headers").write_text(headers, encoding="utf-8")

    print(json.dumps({
        "revision": args.revision,
        "version": version,
        "worker": f"/{versioned_sw_name}",
        "noCachePaths": update_paths + ["/sw.js", f"/{versioned_sw_name}"],
        "core": core,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
