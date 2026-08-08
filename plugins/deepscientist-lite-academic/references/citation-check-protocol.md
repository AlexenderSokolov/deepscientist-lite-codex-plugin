# Citation check protocol

Academic `0.10.0-beta.3` defines `ds-lite.citation-check.v1` and `ds-lite.citation-check-batch.v1`. The four first-class providers are Crossref, OpenAlex, Semantic Scholar, and arXiv. Each produces exactly one of `matched`, `not-found`, `unavailable`, `not-applicable`, or `conflict`.

The aggregate status is `verified`, `conflict`, `not-found`, or `pending`. An exact DOI/arXiv identifier match verifies a record; without one, verification needs two independent providers agreeing on title, authors, and year. HTTP 429, timeout, authentication, network, or malformed response is `unavailable`, so the aggregate remains `pending` unless stronger evidence resolves it. Submission mode allows only `verified`.

Checks record `metadata-only`, `abstract`, or `full-text` reading scope and optional claim page/section locations. The sanitized project cache retains `verified` for 30 days and `conflict` or `not-found` for 7 days. `pending` is never reusable final evidence. No key or raw provider response is stored.

Use `ds_lite_citation_check.py validate` for offline envelopes. A real request requires explicit external-provider authorization and the `run_accept_academic_providers.*` gate; configuration or an offline fixture is not live-provider evidence.
