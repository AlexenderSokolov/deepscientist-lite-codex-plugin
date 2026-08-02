# Web package notices

This package contains no browser runtime, daemon, extension, credentials, or
third-party source snapshot. Optional backends are discovered at runtime and
must produce a public-only `ds-lite.source-record.v2`.

| Upstream | Fixed/observed version | License | Use | Excluded |
| --- | --- | --- | --- | --- |
| Playwright CLI | capability-discovered | Apache-2.0 | Reference renderer, only in an isolated validation environment | No automatic global install or login profiles |
| Firecrawl | capability-discovered | hosted service | Explicitly authorized search/extraction challenger | No API key storage, external calls without authorization |
| agent-browser | capability-discovered | upstream terms | Matched benchmark challenger | Not a runtime dependency |
| Tapestry | external adapter | upstream license | Chinese-platform proposal capture | No embedded data store or formal knowledge writes |
| `@jackwener/opencli` | 1.8.6 | Apache-2.0 | Optional public read-only adapter challenger | No daemon, Chrome Bridge, login, Cookie, form, upload, or browser commands |

OpenCLI source: https://github.com/jackwener/opencli
and npm package: https://www.npmjs.com/package/@jackwener/opencli.
