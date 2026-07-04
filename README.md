# DeepScientist Lite Codex Plugin

[中文说明](README.zh.md) · [Chinese user guide](docs/user-guide.zh.md) · [Documentation](docs/README.md) · [Teaching materials](teaching/README.zh.md) · [Plugin package](plugins/deepscientist-lite/)

DeepScientist Lite is a lightweight Codex plugin for learning and practicing a traceable, reviewable research workflow. It keeps project memory, research maps, artifacts, experiment contracts, Evidence Packs, review gates, and route tracing without asking users to deploy the full DeepScientist platform.

> **Independent project:** DeepScientist Lite is an unofficial third-party plugin. It is not sponsored, certified, or endorsed by ResearAI. “DeepScientist” is used descriptively to identify the workflow that inspired this project; see [NOTICE](NOTICE).

It is designed for onboarding, teaching demos, and small research projects where the first goal is to make the research process clear and recoverable.

The [Chinese user guide](docs/user-guide.zh.md) explains the six skills, Graph revisions, Evidence Packs, review boundaries, path aliases, and cross-session recovery with user-facing examples. The teaching area separates deterministic lab preparation from the judgments students or Codex must make.

## What It Does

- Starts or audits a research project with `PROJECT.md`, `STATUS.md`, and `RESEARCH_MAP.md`.
- Guides Codex through intake, scout, idea, experiment, review, and analysis/write stages.
- Records ideas, experiments, failures, and conclusions as files under `research/artifacts/`.
- Packages logs, metrics, and output hashes under `research/evidence/` before claim review.
- Maintains a small adjacency-list state graph in `research/state/graph.json`.
- Lets users trace the active research route without running a daemon.

## What It Does Not Do

DeepScientist Lite does not start a daemon, run a Web/TUI, install local models, expose MCP servers, connect chat channels, or replace the full DeepScientist platform. It is a teaching-first plugin and file protocol.

## Install From A Marketplace Repository

Requirements: Codex and Python 3.10 or newer. The runtime state helper uses only the Python standard library.

This repository follows the Codex marketplace layout: `.agents/plugins/marketplace.json` points to `plugins/deepscientist-lite/`.

```bash
codex plugin marketplace add AlexenderSokolov/deepscientist-lite-codex-plugin
```

After installing or upgrading, restart Codex Desktop and open a fresh thread if the `$ds-lite-*` skills do not appear immediately.

## Start Using It

In a project folder, ask Codex to use one of the DS Lite skills, for example:

```text
$ds-lite-intake start a DS Lite research project from this question: ...
$ds-lite-scout audit the baseline and benchmark route
$ds-lite-experiment record this experiment in the research map
$ds-lite-review review the Evidence Pack before analysis
$ds-lite-analysis-write summarize the evidence and limitations
```

For Chinese project titles or questions on Windows, prefer UTF-8 text files with `--title-file` and `--question-file` when calling `ds_lite_state.py` directly.

Graph v2 uses atomic writes, revision checks, and project-relative or symbolic external paths. Evidence Pack v1 adds a separate standard-library CLI for contracts, manifests, SHA-256 records, and strict verification. Existing Graph v1 projects are migrated on the first write; read the [migration guide](docs/maintainers/graph-v2-migration.md) before upgrading projects that contain absolute paths.

## Repository Map

- `plugins/deepscientist-lite/`: installable Codex plugin package.
- `docs/README.md`: implementation and maintainer documentation index.
- `teaching/README.zh.md`: teaching materials and demo scripts.
- `tools/validation/`: maintainer validation tools.
- `PACKAGE.md`: package layout and release boundary.

## Validate The Repository

For maintainers:

```bash
bash tools/validation/run_validate.sh
```
