---
name: ds-lite-web
description: Acquire, normalize, and record public web sources for a bounded research task. Use for public web search, URL capture, public PDF or RSS acquisition, source provenance, backend capability checks, or comparisons among Playwright CLI, Firecrawl, Tapestry, and agent-browser. Version 2 forbids login state, cookies, form submission, unrestricted crawling, and claims that an unavailable backend was used.
---

# DS Lite Web

Use this pack only with the matching DeepScientist Lite Core version. Run `python <web-plugin>/scripts/ds_lite_extensions.py doctor --core-root <core-plugin>` first; a missing or incompatible core is `blocked`.

Before acquisition, write the allowed domains, maximum pages, maximum bytes, timeout, external-service authorization, and output root. Pass each domain as a repeated `--allowed-domain <host>` option. An empty allowlist is a structured `blocked` policy result. Initial URLs, redirects, and Firecrawl results are checked against the same scope. Version 1 is public-only: do not log in, reuse cookies, submit forms, upload files, or operate a user's existing Chrome profile.

Discover actual backend capabilities and record them as `ds-lite.capability.v1`. Prefer host-provided browser capabilities when available, use Playwright CLI as the reference interactive backend, treat Firecrawl and Tapestry as explicit opt-in external backends, use agent-browser as a measured alternative, and use OpenCLI only for manifest-verified public read-only adapters. Never use OpenCLI's browser, profile, auth, daemon, cookie, form, or upload surfaces. Browser-use, PinchTab, browser clusters, and OpenClaw are outside this pack's runtime boundary.

Use the package CLI entrypoints `doctor`, `fetch`, `search`, `render`, and `benchmark`. `fetch` uses bounded public HTTP and writes `ds-lite.source-record.v2`; v1 records remain readable. `search` and `render` can drive Firecrawl only when both `FIRECRAWL_API_KEY` and `--authorized-external-provider` are present; otherwise they stop before making a request. `benchmark` compares the bounded stdlib fetch with an explicitly authorized Firecrawl scrape and records unavailable backends. A captured or partial source must have content hash and relative artifact refs. A failed source may omit them but must record failure layer and reason. Every redirect is checked for public URI policy. Playwright and agent-browser remain capability-discovered and are not guessed or auto-installed.

Finish with DS Lite `start / progress / end`: report the actual source records, failures, cost or usage if observed, and one next action. Never promote a source record directly into reviewed knowledge.
