---
name: nature-data
description: Use the complete nature-data workflow, preserving its upstream routing and supporting materials. Prepare, audit, or revise Nature-ready Data Availability statements, data repository plans, dataset citations, and FAIR metadata checklists for manuscripts. Use when the user asks about Nature data availability, research data sharing, repository selection, accession numbers, restricted or sensitive data, source data, supplementary datasets, DataCite-style dataset references, FAIR metadata for academic publication, or Chinese-to-English data availability wording for Chinese-speaking authors preparing Nature-family submissions.
---

# DS Lite Integration Boundary

This entry preserves the complete upstream nature-data workflow at commit `91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b`.
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

# Nature Data Availability — Router

This skill is split into two layers:

- A **static layer** under `static/` that holds versioned, reusable content fragments (the default stance and source hierarchy, the Chinese-user operating mode, and the workflow with output format).
- A **dynamic layer** (this file plus `manifest.yaml`) that loads the core every time and reaches for the deeper policy/repository/FAIR references only when a step needs them.

Do not try to apply the data-availability logic from memory or from this router. Always load fragments from disk as described below.

## Routing protocol

Follow these four steps every time the skill is invoked.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml). Then read every file listed under `always_load`:

- `static/core/stance.md` — what the data-availability package is, the default stance, and the source hierarchy.
- `static/core/chinese-mode.md` — how to operate when the user writes in Chinese (accept Chinese, draft English, convert terms precisely).
- `static/core/workflow.md` — the eight-step workflow and the output format.

### 2. No content axis — confirm journal and language inline

Unlike nature-writing or nature-figure, nature-data has no fragment axis. Its variation is handled at runtime, not by loading different content bodies:

- **journal/article type** — if journal-specific instructions conflict with this skill, follow the journal.
- **access route** — each dataset is classified into one route (public repository, controlled access, within paper, reused public, third-party restricted, justified request, or not applicable).
- **user language** — if the user writes Chinese, follow `core/chinese-mode.md` and add the 中文核对 block.

### 3. Run the workflow

Follow the eight-step workflow in `core/workflow.md`: identify the journal, inventory every supporting dataset, classify each into one access route, choose repository and identifier strategy before drafting, draft the statement with explicit dataset-to-location mapping, add formal dataset citations, run the FAIR/metadata audit, and return ready-to-paste text plus unresolved fields.

Do not invent DOIs, accession numbers, repository names, licences, embargo dates, ethics approvals, access committees, or data-use conditions. Flag "available upon request" as weak unless there is a specific legal, ethical, commercial, or third-party restriction.

### 4. Reach for references only when needed

The files under `references/` are deep references, not defaults. Open them on demand per the `references.on_demand` table in the manifest — for example `references/policy-principles.md` for the governing rules and edge cases, `references/repository-and-identifiers.md` for repository/accession/DOI choices, `references/statement-patterns.md` for ready-to-adapt statements, `references/fair-metadata-checklist.md` for the FAIR audit, `references/chinese-author-alignment.md` for Chinese wording, and `references/source-basis.md` to justify a rule with its official source.

## Why this split

- The static layer is versioned and reviewable; the core stays small for a normal statement.
- The dynamic layer keeps each invocation cheap: the policy, repository, and FAIR depth load only when a step needs them.
- The router itself is short on purpose. Update fragments and references, not this file, when adding scope.
- This structure mirrors `nature-writing`, `nature-polishing`, `nature-reader`, `nature-paper2ppt`, `nature-figure`, `nature-citation`, and `nature-response`.
