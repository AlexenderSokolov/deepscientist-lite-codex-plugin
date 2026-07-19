---
name: ds-lite-intake
description: Use when Codex should start, attach, or audit a lightweight DeepScientist-style research project without deploying DeepScientist. Creates or reconciles PROJECT.md, RESEARCH_MAP.md, STATUS.md, research/state/graph.json, research/memory, research/artifacts, run_*.sh entries, goals, constraints, acceptance criteria, and the first intake node.
---

# DS Lite Intake

Start with files, not chat memory. Build a small project contract that future Codex sessions can read quickly.

## Workflow

1. Inspect existing project files first: README, notes, code, scripts, prior reports, `PROJECT.md`, `STATUS.md`, `RESEARCH_MAP.md`, and `research/state/graph.json` when present. If external long-task artifacts exist, read [the external long-task protocol](../../references/external-long-task-protocol.md), inventory `research/artifacts/external-tmux-plan-*.md` before `external-task-*.md`, record every plan gate and allocated slot, then inventory every non-terminal task and identify its runtime owner and recovery entry before planning new execution.
2. If this is a new project, initialize the DS Lite protocol with `ds_lite_state.py init --root <project> --title "<title>" --question "<question>"`. Resolve `ds_lite_state.py` from the installed plugin directory first; for non-ASCII values on Windows, prefer UTF-8 files with `--title-file` or `--question-file`. Initialization creates `research/work-unit.json` as a `ds-lite.work-unit.v1` planning unit with no claim requirement.
3. If this is an old project, do an intake audit: preserve existing conclusions, identify stale or unsupported claims, and create/update only the missing protocol files.
4. Fill `PROJECT.md` with durable background, hypotheses, goal, inputs, constraints, acceptance criteria, workflow, code layout, and run commands.
5. Validate `research/work-unit.json` through `mission --format json`. Keep planning/scout/idea work free of claim requirements; before claim-bearing work, replace it with the smallest profile-specific requirement and refs. Unknown fields belong only under `extensions`.
6. Run `render-status` so `STATUS.md` is the current Mission Board with active node, blockers, next action, and date. Keep it short enough for a future session to read first.
7. Render `RESEARCH_MAP.md` from `research/state/graph.json`; treat the JSON graph as machine-readable state and the Markdown map as its human projection.

## State Rules

- Record public summaries, decisions, evidence paths, and artifacts. Do not write hidden chain-of-thought.
- Use the state script for every graph mutation. If it is unavailable, continue only with ordinary project files, report graph synchronization as blocked, and do not edit `graph.json` directly.
- Read the current revision with `status`; on exit code 4, reload state and reconcile instead of overwriting a concurrent change.
- Represent project-external resources as `external://<alias>/<relative-path>` and resolve aliases through `DS_LITE_EXTERNAL_<ALIAS>` in the environment or run scripts.
- Never overwrite existing user conclusions silently. Mark uncertainty and source paths instead.
- Use `research/memory/*.md` for durable facts and `research/artifacts/*.md` for idea, baseline, experiment, analysis, and writing records.
- A recovered conversation or project does not prove that an external process is alive. Preserve `prepared`, `running`, `suspect`, `interrupted`, and `recovering` task records in the intake handoff until their owner, process, logs, checkpoints, and Evidence Pack have been reconciled.
- A `verified` tmux capacity plan proves only the recorded server fingerprint and probe scope. It does not prove that a workload, Codex CLI child worker, or provider conversation is still alive or resumable.

## Communication Layer

Before intake, read `../../references/communication/core.md`, `../../references/communication/self-audit.md`, and the project-root `STYLE.md` when present. Follow Phase 1 before action, Phase 2 after each material action, and Phase 3 before handoff. If an old project lacks `STYLE.md`, explain the default `research-peer` behavior and ask before creating it. Load profiles or language overlays only when requested or needed for teaching/polishing. Protect code, commands, paths, JSON/YAML, logs, metrics, formulas, citations, and formal definitions;保护内容不因润色而改变。Keep assumptions, inspected files, decisions, and verification visible.

## Handoff

End intake with: project title, active node id, acceptance target, first scout or experiment action, files created or updated, every tmux plan awaiting user bootstrap or marked stale, verified unused slots, and any non-terminal external task with its query or recovery entry.
