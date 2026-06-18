---
name: ds-lite-intake
description: Use when Codex should start, attach, or audit a lightweight DeepScientist-style research project without deploying DeepScientist. Creates or reconciles PROJECT.md, RESEARCH_MAP.md, STATUS.md, research/state/graph.json, research/memory, research/artifacts, run_*.sh entries, goals, constraints, acceptance criteria, and the first intake node.
---

# DS Lite Intake

Start with files, not chat memory. Build a small project contract that future Codex sessions can read quickly.

## Workflow

1. Inspect existing project files first: README, notes, code, scripts, prior reports, `PROJECT.md`, `STATUS.md`, `RESEARCH_MAP.md`, and `research/state/graph.json` when present.
2. If this is a new project, initialize the DS Lite protocol with `ds_lite_state.py init --root <project> --title "<title>" --question "<question>"`. Resolve `ds_lite_state.py` from the installed plugin directory first; if non-ASCII command arguments become corrupted on Windows, write UTF-8 files and use `--title-file` or `--question-file`.
3. If this is an old project, do an intake audit: preserve existing conclusions, identify stale or unsupported claims, and create/update only the missing protocol files.
4. Fill `PROJECT.md` with durable background, hypotheses, goal, inputs, constraints, acceptance criteria, workflow, code layout, and run commands.
5. Update `STATUS.md` with current node, blockers, next action, and the date. Keep it short enough for a future session to read first.
6. Render `RESEARCH_MAP.md` from `research/state/graph.json`; treat the JSON graph as machine-readable state and the Markdown map as its human projection.

## State Rules

- Record public summaries, decisions, evidence paths, and artifacts. Do not write hidden chain-of-thought.
- Prefer the state script for graph edits. If unavailable, follow `../../references/state-graph-protocol.md` exactly.
- Never overwrite existing user conclusions silently. Mark uncertainty and source paths instead.
- Use `research/memory/*.md` for durable facts and `research/artifacts/*.md` for idea, baseline, experiment, analysis, and writing records.

## Handoff

End intake with: project title, active node id, acceptance target, first scout or experiment action, and files created or updated.
