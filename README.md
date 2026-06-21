# DeepScientist Lite Codex Plugin

DeepScientist Lite is a teaching-first Codex plugin. It does not run the DeepScientist daemon, local models, Web/TUI, connectors, or MCP servers. Instead, it packages the teachable core of DeepScientist into Codex skills, templates, and a tiny adjacency-list state kernel.

It is meant for onboarding, demos, and lightweight research automation:

- intake a research project
- scout baselines and benchmarks
- branch and select ideas
- record experiments and failures
- analyze evidence and write handoffs
- keep all durable state in files


## Product Positioning

The plugin is the main product. Teaching cases and similar experiments are validation and teaching cases that demonstrate traceable research workflow; they are not release blockers unless they expose a plugin workflow failure. See `plugins/deepscientist-lite/references/product-positioning-and-memory.md`, `known-issues.md`, and `release-checklist.md`.

## What Is Included

- Plugin manifest at `plugins/deepscientist-lite/.codex-plugin/plugin.json`
- Five skills under `plugins/deepscientist-lite/skills/`
- State graph script at `plugins/deepscientist-lite/scripts/ds_lite_state.py`
- Templates under `plugins/deepscientist-lite/assets/templates/`
- Protocol and teaching references under `plugins/deepscientist-lite/references/`

## State Model

`research/state/graph.json` is the machine-readable source of truth. `RESEARCH_MAP.md` is a rendered human view.

The graph uses nodes plus adjacency lists to make research routes, branches, artifacts, and rollback paths inspectable without a daemon.

## Validate

```bash
python tools/validation/validate_repo.py
```

Optional wrappers live under `tools/validation/` and are intentionally kept out of the repository root.

## GitHub Marketplace Test

This repository is laid out as a Codex marketplace: `.agents/plugins/marketplace.json` points at `plugins/deepscientist-lite/`.

```bash
codex plugin marketplace add <owner>/deepscientist-lite-codex-plugin
```

If a fresh thread can find the plugin under `.codex/.tmp/marketplaces/deepscientist-lite` but does not expose `$ds-lite-*` skills, confirm that `~/.codex/config.toml` contains:

```toml
[plugins."deepscientist-lite@deepscientist-lite"]
enabled = true
```

Then start a new Codex thread. Some Codex CLI builds expose marketplace commands but not a separate `codex plugin add` command, so this enabled plugin entry is the important part.

In Codex Desktop, plugin configuration may not be hot-reloaded by already running app sessions. After adding the enabled plugin entry, restart Codex Desktop and then start a fresh thread.

On Windows, non-ASCII command-line arguments may be corrupted by shell encoding. For Chinese titles or questions, write UTF-8 text files and call:

```powershell
python path\to\ds_lite_state.py init --root . --title-file title.txt --question-file question.txt
```

## Current E2E Status

Verified:

- The GitHub marketplace can be pulled with `codex plugin marketplace add`.
- The marketplace cache contains `deepscientist-lite` 0.1.1.
- `ds_lite_state.py` passes init, add-node, add-edge, trace, trace-artifact, validate, and render-map checks.
- The one-stop file protocol creates project memory, status, research map, state graph, memory cards, artifacts, and run scripts.
- Iteration preserves the first insufficient experiment and records branch, rollback, and supersedes edges.
- `--title-file` and `--question-file` avoid Windows non-ASCII command-line corruption.

Remaining runtime boundary:

- Without restarting Codex Desktop, a newly written `[plugins."deepscientist-lite@deepscientist-lite"] enabled = true` entry may still not expose `$ds-lite-*` skills in new threads.
- GitHub pull and script/protocol behavior are validated; automatic skill exposure still needs a Codex Desktop restart followed by a fresh-thread check.

## Documentation Map

- `PACKAGE.md`: package layout and release boundary.
- `docs/implementation.zh.md`: implementation details.
- `teaching/`: standalone teaching material and sanitized cases.
- `tools/validation/`: repository validation tools.
