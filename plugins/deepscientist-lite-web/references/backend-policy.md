# Web backend policy

DS Lite Web v1 handles public acquisition only. Every run declares allowed
domains, maximum pages, maximum bytes, timeout, output root, and whether an
external service may receive URLs or content. Login, cookie reuse, form
submission, uploads, and an existing browser profile are outside v1.

The CLI expresses the domain boundary with one or more repeated
`--allowed-domain example.org` options. The option is deliberately optional at
the parser level so the command can return a machine-readable `blocked`
record; execution is fail-closed when the list is empty. Initial URLs, every
redirect, and every Firecrawl search result must match an exact domain or a
subdomain of one of the declared values. A result outside the scope is a
policy failure, not a result to silently discard.

## Backend roles

| Backend | Role | Default state |
| --- | --- | --- |
| Playwright CLI | Reference renderer and public-page interaction backend | capability-discovered |
| Firecrawl | Optional hosted search and extraction | blocked until API, cost, and data egress are authorized |
| Tapestry adapter | Experimental Chinese-platform capture handoff | alpha; proposal-only downstream |
| agent-browser | Challenger for matched measurements | optional |
| OpenCLI | Optional public read-only adapter challenger | available only when its manifest declares `access=read`, `strategy=PUBLIC`, `browser=false` |
| Codex Chrome | Host capability, not a plugin dependency | deferred to v2 |

Record observed capabilities with `ds-lite.capability.v1`. OpenCLI is never
invoked through its browser, profile, auth, daemon, cookie, form, or upload
surfaces. After a backend has
written a public artifact, use `record-source` in `ds_lite_extensions.py` to
hash it and create `ds-lite.source-record.v1`. Configuration is not execution
evidence, and a failed capture still needs a failure-layer record.

The Firecrawl `search` and `render` commands require both `FIRECRAWL_API_KEY`
and the per-invocation `--authorized-external-provider` flag. The key is never
written to a receipt. `benchmark` records bounded stdlib HTTP and explicitly
authorized Firecrawl outcomes separately; unavailable backends remain
`not-observed`. Example:

```text
python ds_lite_extensions.py fetch --url https://example.org/page \
  --allowed-domain example.org --project-root . \
  --output research/page.html --record-output research/page.json \
  --source-id page
```
