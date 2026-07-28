#!/usr/bin/env python3
"""Make Reader UI updates visible on the first online reload.

Older workers used stale-while-revalidate for JavaScript and CSS.  A navigation
could therefore receive the new HTML while the controlling worker returned an
old app.js from Cache Storage.  This patch runs after the normal offline worker
is generated.  It makes update entry points network-first and injects a small,
version-scoped cache migration into the HTML shell.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


NETWORK_FIRST_PATHS = (
    "/index.html",
    "/health.json",
    "/ui-version.json",
    "/app.js",
    "/ui-v4-runtime.js",
    "/structured-ui.js",
    "/doppel-ui.js",
    "/memoria-ui.js",
    "/styles.css",
    "/ui-v4-fixes.css",
    "/structured-ui.css",
    "/doppel-ui.css",
    "/memoria-ui.css",
    "/dense-reader.css",
    "/dense-reader-compact.css",
)

BOOTSTRAP_MARKER = "reader-version-cache-bootstrap"


def patch_worker(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    declaration = (
        f"const NETWORK_FIRST_PATHS = new Set({json.dumps(NETWORK_FIRST_PATHS, ensure_ascii=False)});\n"
    )
    fetch_marker = "self.addEventListener('fetch', (event) => {"
    if declaration not in text:
        if text.count(fetch_marker) != 1:
            raise RuntimeError(f"fetch listener marker missing in {path}")
        text = text.replace(fetch_marker, declaration + "\n" + fetch_marker, 1)

    old = "if (url.pathname === '/health.json' || url.pathname === '/index.html') {"
    new = "if (NETWORK_FIRST_PATHS.has(url.pathname)) {"
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise RuntimeError(f"network-first update condition missing in {path}")

    for value in NETWORK_FIRST_PATHS:
        if value not in text:
            raise RuntimeError(f"critical update path missing from {path}: {value}")
    path.write_text(text, encoding="utf-8")


def patch_index(path: Path, revision: str) -> None:
    text = path.read_text(encoding="utf-8")
    if BOOTSTRAP_MARKER in text:
        return
    marker = "</head>"
    if text.count(marker) != 1:
        raise RuntimeError("index head terminator missing")
    revision_json = json.dumps(revision)
    script = f"""  <script data-reader-bootstrap=\"{BOOTSTRAP_MARKER}\">
    (() => {{
      const revision = {revision_json};
      const sessionKey = `magireco-reader-cache-reset:${{revision}}`;
      if (sessionStorage.getItem(sessionKey)) return;
      sessionStorage.setItem(sessionKey, '1');
      if (!('caches' in window)) return;
      Promise.all([
        caches.keys().then((keys) => {{
          const keep = `magireco-cn-reader-v${{revision}}-`;
          const obsolete = keys.filter((name) =>
            name.startsWith('magireco-cn-reader-') && !name.startsWith(keep)
          );
          return Promise.all(obsolete.map((name) => caches.delete(name)))
            .then(() => obsolete.length);
        }}),
        navigator.serviceWorker
          ? navigator.serviceWorker.getRegistrations().then((registrations) =>
              Promise.all(registrations.map((registration) =>
                registration.update().catch(() => undefined)
              ))
            )
          : Promise.resolve([]),
      ]).then(([removed]) => {{
        if (!removed) return;
        const url = new URL(location.href);
        url.searchParams.set('reader-ui', revision);
        location.replace(url.href);
      }}).catch(() => undefined);
    }})();
  </script>
"""
    text = text.replace(marker, script + marker, 1)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    for name in ("sw.js", f"sw-v{args.revision}.js"):
        patch_worker(root / name)
    patch_index(root / "index.html", args.revision)
    print(json.dumps({
        "revision": args.revision,
        "networkFirst": NETWORK_FIRST_PATHS,
        "bootstrap": BOOTSTRAP_MARKER,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
