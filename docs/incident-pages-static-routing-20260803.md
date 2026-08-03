# Cloudflare Pages static/RSC routing incident (2026-08-03)

The Pages wrapper was changed to send every request through the generated OpenNext worker. On Cloudflare Pages this also routed static public files such as `story_index.json` through OpenNext, leaving the homepage client waiting indefinitely at `数据加载中…`.

The corrected boundary is:

- direct Pages `ASSETS` delivery for the root document and explicit public/static paths;
- OpenNext for `/api/`, `/reader/`, `/review/`, non-GET methods, and all Next.js RSC/Flight requests;
- asset fallback to OpenNext only when the selected static path is absent.

This preserves the static catalogue required for initial loading while preventing Pages asset fallback from swallowing Next.js client-navigation responses.
