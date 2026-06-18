---
name: ds-lite-experiment
description: Use when Codex should implement, run, repair, or document a lightweight DS Lite experiment, update run_*.sh commands, capture metrics and failures, and attach experiment artifacts to the Research Map.
---

# DS Lite Experiment

Experiments must be reproducible enough that another session can rerun or diagnose them from files.

## Workflow

1. Read the active idea node, linked idea artifact, `PROJECT.md`, and current run scripts.
2. Define the smallest useful test: command, inputs, expected output, metric, success threshold, and failure interpretation.
3. Implement or repair code using the host project's conventions. Keep unrelated refactors out.
4. Create or update the relevant `run_*.sh` entry so the experiment is replayable.
5. Run the experiment when practical. If compute, data, cluster paths, or credentials block execution, save the exact command and mark the experiment node `blocked`.
6. Write `research/artifacts/experiment-<slug>.md` with command, environment, git branch or worktree note, metrics, logs, failures, and next interpretation.
7. Add or update an `experiment` node with the artifact path, then render the map.

## Recording Rules

- Record failed experiments as first-class evidence.
- Attach output files, logs, figures, and scripts through `artifact_paths` or `evidence_paths`.
- If an experiment invalidates an idea, add a `rollback` or `supersedes` edge instead of erasing the old route.
- Keep `STATUS.md` honest: active node, what ran, what failed, and the next concrete action.
