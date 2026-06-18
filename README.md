# DeepScientist Lite Codex Plugin

DeepScientist Lite is a teaching-first Codex plugin. It does not run the DeepScientist daemon, local models, Web/TUI, connectors, or MCP servers. Instead, it packages the teachable core of DeepScientist into Codex skills, templates, and a tiny adjacency-list state kernel.

It is meant for onboarding, demos, and lightweight research automation:

- intake a research project
- scout baselines and benchmarks
- branch and select ideas
- record experiments and failures
- analyze evidence and write handoffs
- keep all durable state in files

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
bash run_validate.sh
```

On Windows PowerShell:

```powershell
.\run_validate.ps1
```

or:

```bash
python scripts/validate_repo.py
```

## GitHub Marketplace Test

This repository is laid out as a Codex marketplace: `.agents/plugins/marketplace.json` points at `plugins/deepscientist-lite/`.

```bash
codex plugin marketplace add AlexenderSokolov/deepscientist-lite-codex-plugin
```

If a fresh thread can find the plugin under `.codex/.tmp/marketplaces/deepscientist-lite` but does not expose `$ds-lite-*` skills, confirm that `~/.codex/config.toml` contains:

```toml
[plugins."deepscientist-lite@deepscientist-lite"]
enabled = true
```

Then start a new Codex thread. Some Codex CLI builds expose marketplace commands but not a separate `codex plugin add` command, so this enabled plugin entry is the important part.

On Windows, non-ASCII command-line arguments may be corrupted by shell encoding. For Chinese titles or questions, write UTF-8 text files and call:

```powershell
python path\to\ds_lite_state.py init --root . --title-file title.txt --question-file question.txt
```
