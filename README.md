# DeepScientist Lite Codex Plugin

[中文说明](README.zh.md) · [Chinese user guide](docs/user-guide.zh.md) · [Documentation](docs/README.md) · [Evaluation](evaluation/README.md) · [Core package](plugins/deepscientist-lite-core/) · [Acknowledgments](ACKNOWLEDGMENTS.md)

DeepScientist Lite is a lightweight Codex plugin for learning and practicing a traceable, reviewable research workflow. It keeps project memory, research maps, artifacts, experiment contracts, Evidence Packs, review gates, and route tracing without asking users to deploy the full DeepScientist platform.

> **Independent project:** DeepScientist Lite is an unofficial third-party plugin. It is not sponsored, certified, or endorsed by ResearAI. “DeepScientist” is used descriptively to identify the workflow that inspired this project; see [NOTICE](NOTICE).

It is designed for onboarding, teaching demos, and small research projects where the first goal is to make the research process clear and recoverable.

The [Chinese user guide](docs/user-guide.zh.md) explains the nine Core skills and five optional packs. Academic contains the 17 Nature workflows plus citation/revision gates; Web records public-source provenance; Knowledge emits review-gated proposals; Empirical and Engineering each expose one domain router. It also covers Graph revisions, Mission Board, reflective iterations, Evidence Packs, review boundaries, bounded delegation, path aliases, first-use onboarding, and cross-session recovery.

## What It Does

- Starts or audits a research project with `PROJECT.md`, `STATUS.md`, and `RESEARCH_MAP.md`.
- Guides Codex through intake, scout, idea, experiment, review, analysis/write, one bounded iterate step, and an optional explicitly approved coordination step.
- Renders a user-visible Mission Board with `mission` and `render-status` so `STATUS.md` shows what happened, what is next, and where rollback is possible.
- Records one bounded action, verification, reflection, user report, and stop reason in `ds-lite.iteration.v1`, then stops.
- Records ideas, experiments, failures, and conclusions as files under `research/artifacts/`.
- Packages logs, metrics, and output hashes under `research/evidence/` before claim review.
- Maintains a small adjacency-list state graph in `research/state/graph.json`.
- Records up to three independent delegated tasks with disjoint path ownership, result refs, and one parent integration owner.
- Lets users trace the active research route without running a daemon, queue, or scheduler.

## What It Does Not Do

Core does not start a daemon, run a Web/TUI, install local models, expose an MCP server, connect chat channels, or replace the full DeepScientist platform. Academic MCP/API integrations and hosted Web backends are opt-in workspace configuration and require explicit user authorization.

The Web package is public-only and fail-closed: every `fetch`, `search`, `render`, or `benchmark` run must pass one or more `--allowed-domain` values. Initial URLs, redirects, and Firecrawl results are checked against that scope. Login, cookies, form submission, uploads, and automatic browser/provider installation are not supported.

## Install From A Marketplace Repository

Requirements: Codex and Python 3.10 or newer. The runtime state helper uses only the Python standard library.

This repository follows the Codex marketplace layout: `.agents/plugins/marketplace.json` exposes six independent packages under `plugins/deepscientist-lite-*`.

```bash
codex plugin marketplace add AlexenderSokolov/deepscientist-lite-codex-plugin
```

This command adds a plugin source; it does not by itself prove that a plugin is installed. Open `/plugins`, select this marketplace, and install `deepscientist-lite` Core by default. Install Academic, Web, Knowledge, Empirical, or Engineering separately when needed. After installing or upgrading, restart Codex Desktop and use a fresh task to verify actual versions and skill counts. The split candidates expect 9 Core skills, 17 Academic skills, and one skill in each other pack. Do not infer cache state from the source tree.

## Start Using It

In a project folder, ask Codex to use one of the DS Lite skills, for example:

```text
$ds-lite inspect this research or engineering workspace, explain why the plugin applies, and route to one next action
$ds-lite-intake start a DS Lite research project from this question: ...
$ds-lite-scout audit the baseline and benchmark route
$ds-lite-experiment record this experiment in the research map
$ds-lite-review review the Evidence Pack before analysis
$ds-lite-analysis-write summarize the evidence and limitations
$ds-lite-iterate register one action, verify it, reflect, report, update STATUS, and stop
$ds-lite-coordinate plan two independent tasks, stop for approval, then collect and verify their results
```

For Chinese project titles or questions on Windows, prefer UTF-8 text files with `--title-file` and `--question-file` when calling `ds_lite_state.py` directly.

Graph v2 uses atomic writes, revision checks, and project-relative or symbolic external paths. Evidence Pack v1 adds a separate standard-library CLI for contracts, manifests, SHA-256 records, and strict verification. Existing Graph v1 projects are migrated on the first write; read the [migration guide](docs/maintainers/graph-v2-migration.md) before upgrading projects that contain absolute paths.

## Repository Map

- `plugins/deepscientist-lite-core/`: default Core package with nine skills and Hooks.
- `plugins/deepscientist-lite-academic/`: optional 17-skill academic package.
- `plugins/deepscientist-lite-web/` and `plugins/deepscientist-lite-knowledge/`: experimental public-web and review-proposal packages.
- `plugins/deepscientist-lite-empirical/`: `0.2.0-alpha.1` method-neutral empirical specification and result handoff.
- `plugins/deepscientist-lite-engineering/`: `0.2.0-alpha.1` numerical, FFT, sampling, and figure-audit protocol.
- `plugins/deepscientist-lite/`: frozen `0.6.0-beta.1` monolith retained for evidence identity, not a marketplace target.
- `docs/README.md`: implementation and maintainer documentation index.
- `teaching/README.zh.md`: teaching materials and demo scripts.
- `tools/validation/`: maintainer validation tools.
- `PACKAGE.md`: package layout and release boundary.

## Validate The Repository

For maintainers:

```bash
bash tools/validation/run_validate.sh
```
