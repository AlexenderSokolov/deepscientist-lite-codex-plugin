# DeepScientist Lite Codex Plugin

[中文说明](README.zh.md) · [Chinese user guide](docs/user-guide.zh.md) · [Documentation](docs/README.md) · [Teaching materials](teaching/README.zh.md) · [Plugin package](plugins/deepscientist-lite/)

DeepScientist Lite is a lightweight Codex plugin for learning and practicing a research workflow that can be traced and reviewed. It keeps project memory, research maps, artifacts, experiment contracts, Evidence Packs, review gates, and route tracing without asking users to deploy the full DeepScientist platform.

> **Independent project:** DeepScientist Lite is an unofficial third-party plugin. It is not sponsored, certified, or endorsed by ResearAI. “DeepScientist” is used descriptively to identify the workflow that inspired this project; see [NOTICE](NOTICE).

It is for onboarding, teaching demos, and small research projects where the first job is to make the work understandable and recoverable.

The [Chinese user guide](docs/user-guide.zh.md) explains the seven skills, Graph revisions, Mission Board, Evidence Packs, review boundaries, path aliases, and cross-session recovery with user-facing examples. The teaching area separates deterministic lab preparation from the judgments students or Codex must make.

## What It Does

- Starts or audits a research project with `PROJECT.md`, `STATUS.md`, and `RESEARCH_MAP.md`.
- Guides Codex through intake, scout, idea, experiment, review, analysis/write, and one bounded iterate step.
- Renders a user-visible Mission Board with `mission` and `render-status` so `STATUS.md` shows what happened, what is next, and where rollback is possible.
- Records ideas, experiments, failures, and conclusions as files under `research/artifacts/`.
- Packages logs, metrics, and output hashes under `research/evidence/` before claim review.
- Maintains a small adjacency-list state graph in `research/state/graph.json`.
- Lets users trace the active research route without running a daemon.

## What It Does Not Do

DeepScientist Lite does not start a daemon, run a Web/TUI, install local models, expose MCP servers, connect chat channels, or replace the full DeepScientist platform. It is a teaching-first plugin and file protocol. The optional hook adapter is disabled by default and is not declared in `plugin.json`. When the host configuration format is unconfirmed, it reports `host_supported: false` instead of guessing.

## Install From A Marketplace Repository

Requirements: Codex and Python 3.10 or newer. The runtime state helper uses only the Python standard library.

This repository follows the Codex marketplace layout: `.agents/plugins/marketplace.json` points to `plugins/deepscientist-lite/`.

```bash
codex plugin marketplace add AlexenderSokolov/deepscientist-lite-codex-plugin
```

This command adds a plugin source; it does not by itself prove that the plugin is installed. Open `/plugins`, select this marketplace, and install `deepscientist-lite`. After installing or upgrading, restart Codex Desktop and use a fresh thread to verify the plugin version and all seven `$ds-lite-*` skills.

## Start Using It

In a project folder, ask Codex to use one of the DS Lite skills, for example:

```text
$ds-lite-intake start a DS Lite research project from this question: ...
$ds-lite-scout audit the baseline and benchmark route
$ds-lite-experiment record this experiment in the research map
$ds-lite-review review the Evidence Pack before analysis
$ds-lite-analysis-write summarize the evidence and limitations
$ds-lite-iterate advance exactly one visible research iteration and stop
```

For Chinese project titles or questions on Windows, prefer UTF-8 text files with `--title-file` and `--question-file` when calling `ds_lite_state.py` directly.

Graph v2 uses atomic writes, revision checks, and project-relative or symbolic external paths. Evidence Pack v1 adds a separate standard-library CLI for contracts, manifests, SHA-256 records, and strict verification. Existing Graph v1 projects are migrated on the first write; read the [migration guide](docs/maintainers/graph-v2-migration.md) before upgrading projects that contain absolute paths.

## Communication Style

New projects also receive an optional `STYLE.md` contract. It defaults to the `research-peer` profile, automatic language, adaptive detail, and the automatic academic writing overlay. Users can choose `teaching-explainer`, `compact-operator`, `reflective-researcher`, or write an original `custom` profile. The contract changes conversational and narrative Markdown wording only; it cannot change evidence status, execution authority, code, commands, paths, structured data, metrics, formulas, or citations. Old projects are not silently modified: intake explains the fallback and asks before creating the file.

Every DS Lite task can leave a project-relative `ds-lite.communication-audit.v1` receipt under `research/artifacts/communication-audit-<id>.json`. The receipt records the eight engineering checks, observable file hashes or command results, protected-content comparison, self-audit phases, limitations, reflection, and handoff. Once finalized, it is read-only; later work starts a new receipt.

`ds_lite_hook.py` can inject the profile/detail/audit checklist at prompt time, gate state writes, record post-tool outcomes, and stop unsupported completion claims. It cannot prove that a scientific conclusion is true, and it never records hidden reasoning or raw command text. The complete snapshots of `ai-zixun/humanizer-zh`, `blader/humanizer`, and `AIScientists-Dev/academic-humanizer` are audit material with `runtime_loaded: false`; named-author imitation and external Agent workflows are rejected.

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
