# Cloudflare Pages static/RSC routing incident (2026-08-03)

The Pages wrapper previously tried `ASSETS` before OpenNext for every GET/HEAD
request.  In Chromium, Next.js client navigation to a dynamic `/reader/...`
route could therefore receive an ordinary asset/HTML response rather than the
expected RSC response.  The page flashed and returned to the catalogue.

The corrected boundary is:

- direct Pages `ASSETS` delivery for the root document and explicit public or
  static paths;
- OpenNext for `/api/`, `/reader/`, `/review/`, non-GET methods, and every
  Next.js RSC/Flight request;
- asset fallback to OpenNext only when the selected static path is absent.

This keeps `story_index.json`, data, audio, fonts and Next static assets fast,
while preserving the headers and dynamic routing required by the reader.
