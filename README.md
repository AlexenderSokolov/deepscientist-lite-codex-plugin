# DeepScientist Lite Codex Plugin

[中文说明](README.zh.md) · [Chinese user guide](docs/user-guide.zh.md) · [Documentation](docs/README.md) · [Teaching materials](teaching/README.zh.md) · [Plugin package](plugins/deepscientist-lite/)

DeepScientist Lite is a lightweight Codex plugin for learning and practicing a traceable, reviewable research workflow. It keeps project memory, research maps, artifacts, experiment contracts, Evidence Packs, review gates, and route tracing without asking users to deploy the full DeepScientist platform.

> **Independent project:** DeepScientist Lite is an unofficial third-party plugin. It is not sponsored, certified, or endorsed by ResearAI. “DeepScientist” is used descriptively to identify the workflow that inspired this project; see [NOTICE](NOTICE).

It is designed for onboarding, teaching demos, and small research projects where the first goal is to make the research process clear and recoverable.

The [Chinese user guide](docs/user-guide.zh.md) explains the 26 runtime skills: nine DS Lite continuity/evidence skills and the complete 17-skill nature-skills academic workflow family. It also covers Graph revisions, Mission Board, reflective iterations, Evidence Packs, review boundaries, bounded delegation, path aliases, first-use MCP/API onboarding, and cross-session recovery. The teaching area separates deterministic lab preparation from the judgments students or Codex must make.

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

DeepScientist Lite does not start a daemon, run a Web/TUI, install local models, expose an MCP server, connect chat channels, or replace the full DeepScientist platform. Nature MCP/API integrations are opt-in workspace configuration and require explicit user authorization. It is a teaching-first plugin and file protocol.

## Install From A Marketplace Repository

Requirements: Codex and Python 3.10 or newer. The runtime state helper uses only the Python standard library.

This repository follows the Codex marketplace layout: `.agents/plugins/marketplace.json` points to `plugins/deepscientist-lite/`.

```bash
codex plugin marketplace add AlexenderSokolov/deepscientist-lite-codex-plugin
```

This command adds a plugin source; it does not by itself prove that the plugin is installed. Open `/plugins`, select this marketplace, and install `deepscientist-lite`. After installing or upgrading, restart Codex Desktop and use a fresh thread to verify the actual plugin version and skill count. The published `0.4.0-beta.2` has seven skills; the current source candidate `0.6.0-beta.1` has 26. Do not infer cache state from the source tree.

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
