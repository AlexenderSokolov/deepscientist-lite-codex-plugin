---
name: ds-lite-experiment
description: Use when Codex should implement, run, repair, compare, or document a lightweight DS Lite experiment, including baselines, metrics, budgets, seeds, expected signals, failure interpretation, run_*.sh commands, artifacts, and Research Map updates.
---

# DS Lite Experiment

Experiments must be reproducible enough that another session can rerun or diagnose them from files.

## Workflow

1. Read the active idea node, linked idea artifact, `PROJECT.md`, `STATUS.md`, and current run scripts.
2. Define the smallest useful test: hypothesis, baseline, command, inputs, metric, budget/seed setting, expected signal, success threshold, and failure interpretation.
3. For comparison experiments, read `../../references/experiment-comparison-template.md` and use its headings unless the host project already has a stronger local template.
4. Implement or repair code using the host project's conventions. Keep unrelated refactors out.
5. Create or update the relevant `run_*.sh` entry so the experiment is replayable.
6. Run the experiment when practical. If compute, data, cluster paths, or credentials block execution, save the exact command and mark the experiment node `blocked`.
7. Write `research/artifacts/experiment-<slug>.md` with command, environment, metrics, logs, outputs, failures, and next interpretation.
8. Add or update an `experiment` node with artifact and evidence paths, then render the map.

## Recording Rules

- Record failed experiments as first-class evidence.
- Separate smoke checks from claim-bearing runs.
- Report early-budget and final-budget metrics separately when budget matters.
- Attach output files, logs, figures, and scripts through `artifact_paths` or `evidence_paths`.
- If an experiment invalidates an idea, add a `rollback` or `supersedes` edge instead of erasing the old route.
- Keep `STATUS.md` honest: active node, what ran, what failed, and the next concrete action.
