---
name: nature-academic-search
description: Use the complete nature-academic-search workflow, preserving its upstream routing and supporting materials. Multi-source literature search, citation verification, strict independent other-citation audits, article-level citation metric tables, influential citer profiling with citation-context extraction, MeSH search strategy, citation file management (.nbib/.ris/.bib conversion), and reference management (BibTeX, related articles, ID conversion) via MCP tools (PubMed, CrossRef, arXiv, Scopus, ScienceDirect).
---

# DS Lite Integration Boundary

This entry preserves the complete upstream nature-academic-search workflow at commit `91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b`.
Use the upstream manifest, static fragments, references, scripts, templates, and tests
that remain in this directory; this file is not a summary replacement.

Before using any MCP, external API, browser, downloader, LaTeX, Node, or Python
integration, first run `python <academic-plugin>/scripts/ds_lite_pack_doctor.py --core-root <core-plugin>`, then run
`python <academic-plugin>/scripts/ds_lite_nature_setup.py doctor --workspace .`.
Record only redacted status and relative evidence references. Missing dependencies are
`not-observed` or `blocked`, never silently treated as available.

Read [responsible-exploration-covenant.md](../../references/responsible-exploration-covenant.md) first.
Every invocation follows DS Lite `start / progress / end`: state the target, facts,
authorization, actual action, evidence, failure layer, unverified items, and one next
action. Do not save prompts, credentials, raw responses, hidden reasoning, or absolute
workstation paths.

## Preserved Upstream Workflow

# Academic Search — Router

This skill is split into two layers:

- A **static layer** under `static/` that holds versioned, reusable content fragments (the MCP tool inventory and shared modules, and source routing plus operational rules).
- A **dynamic layer** (this file plus `manifest.yaml`) that detects which workflow the user needs and loads that workflow, reaching for shared modules and scripts only when a step needs them.

Do not try to apply the search logic from memory or from this router. Always load fragments from disk as described below.

## Routing protocol

Follow these five steps every time the skill is invoked.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml). It declares the `workflow` axis, the allowed values, and the file paths each value maps to.

Also read every file listed under `always_load`:

- `static/core/tools.md` — the MCP tool inventory (core search, extended search, PubMed utilities) and the shared-module map.
- `static/core/routing-and-ops.md` — the T1→T2→T3 source routing quick guide, environment setup, error handling, and limitations.

### 2. Detect the workflow

Map the user's need to one or more `workflow` values:

- `multi-source-search` — find literature across sources.
- `citation-verification` — verify citations extracted from a document.
- `mesh-strategy` — build a MeSH/PubMed search strategy.
- `citation-file-mgmt` — convert/manage `.nbib`/`.ris`/`.bib` files.
- `reference-mgmt` — BibTeX, related-article discovery, ID conversion.
- `strict-other-citation-impact-audit` — determine strict independent other-citations, build article-level citation metric tables, identify high-profile citers (academy members, presidents/deans, talent-award holders, fellows, field leaders), and extract how they cited the target paper.

A combined request (for example search then export) may need more than one. State the detected workflow(s) in one short line before proceeding.

### 3. Load the matching workflow fragment(s)

Read the file mapped for each detected workflow (under `references/workflows/`). Do **not** read every workflow. Each workflow file links to the shared modules it needs.

### 4. Run the workflow using the loaded material

Apply the loaded material in this order:

1. Core tools and routing (`core/tools.md`, `core/routing-and-ops.md`) — which MCP tool for which need, and the T1→T2→T3 fallback chain that is the standard execution order across all workflows.
2. The workflow fragment — its specific steps.
3. Shared modules and scripts on demand (dedup, citation parser, search strategy, RIS/BibTeX format, format converter).

Report specific tool failures and continue with remaining tools; broaden terms when there are no results; fall back to manual generation from MCP-fetched metadata if a script fails twice.

### 5. Reach for references only when needed

The files under `references/` (and `scripts/`) are deep references, not defaults. Open them on demand per the `references.on_demand` table in the manifest — for example `references/source-tiers.md` for the full reliability classification, `references/dedup-engine.md` / `references/citation-parser.md` / `references/search-strategy.md` / `references/ris-bibtex-format.md` for the shared modules, and `scripts/academic_search.py` (no-MCP fallback discovery search) / `scripts/format-converter.py` / `scripts/preflight.py` for the tooling.

## Why this split

- The static layer is versioned and reviewable; the workflow files and shared modules were already factored this way.
- The dynamic layer keeps each invocation cheap: only the workflow the user needs enters context, instead of all six plus every module.
- The router itself is short on purpose. Update fragments and references, not this file, when adding scope.
- This structure mirrors the other nature-* skills (`nature-writing`, `nature-polishing`, `nature-reader`, `nature-paper2ppt`, `nature-figure`, `nature-citation`, `nature-response`, `nature-data`).
