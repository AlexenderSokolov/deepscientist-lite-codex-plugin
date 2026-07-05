---
name: ds-lite-experiment
description: Use when Codex should implement, run, repair, compare, or document a lightweight DS Lite experiment, including baselines, metrics, budgets, seeds, expected signals, failure interpretation, run_*.sh commands, artifacts, and Research Map updates.
---

# DS Lite Experiment

Experiments must be reproducible enough that another session can rerun or diagnose them from files.

## Workflow

1. Read the active idea node, linked idea artifact, `PROJECT.md`, `STATUS.md`, and current run scripts.
2. Define the smallest useful test: hypothesis, baseline, command, inputs, metric, budget/seed setting, expected signal, success threshold, and failure interpretation.
3. Read `../../references/evidence-pack-protocol.md`. For comparison experiments, also read `../../references/experiment-comparison-template.md` and use its headings unless the host project already has a stronger local template.
4. Create `research/artifacts/experiment-contract-<slug>.json` from the plugin Evidence Pack contract template. Do not include credentials, tokens, passwords, or a process environment dump.
5. Validate and initialize the pack before execution: `python <plugin>/scripts/ds_lite_evidence.py init --root <project> --run-id <run-id> --contract <contract-file>`.
6. Implement or repair code using the host project's conventions. Keep unrelated refactors out. Extend the initialized `run_experiment.sh` instead of replacing its portable resolver: preserve the project-root derivation and `tools/ds_lite_runtime.sh`, then add the complete replay command, log capture, metrics output, and finalize/verify arguments. Machine-specific CLI roots belong in `PYTHON_BIN`, `DS_LITE_EVIDENCE_CLI`, or `DS_LITE_PLUGIN_ROOT` at execution time, never in the saved script.
7. Run the experiment when practical. Save stdout, stderr, numeric `metrics.json`, a sanitized `ds-lite.environment.v1` JSON description, and declared outputs. If compute, data, cluster paths, or credentials block execution, keep the initialized pack, save the exact command, and mark the experiment node `blocked`.
8. Finalize and verify completed or failed runs with `ds_lite_evidence.py finalize` followed by `verify --strict`. A failed process is still valid evidence when its pack is intact.
9. Write `research/artifacts/experiment-<slug>.md` with the contract, command, environment, metrics, logs, outputs, failures, manifest path, and next interpretation.
10. Read the current revision, then add or update an `experiment` node with `add-node`/`update-node`; link the manifest through `link-path --type evidence`, attach artifacts, update status with `set-status`, and pass `--expected-revision` on every write.

## Recording Rules

- Record failed experiments as first-class evidence.
- Separate smoke checks from claim-bearing runs.
- Report early-budget and final-budget metrics separately when budget matters.
- Attach output files, logs, figures, and scripts through `artifact_paths` or `evidence_paths`.
- Use project-relative paths. Record `external://` outputs without hashing unless the user explicitly authorizes `--hash-external`.
- Do not begin analysis/write directly after experiment; hand the finalized run to `$ds-lite-review`.
- If an experiment invalidates an idea, add a `rollback` or `supersedes` edge instead of erasing the old route.
- Keep `STATUS.md` honest: active node, what ran, what failed, and the next concrete action.
- Never edit `graph.json` directly. On revision conflict, reload the graph and reconcile both sessions' evidence before retrying.
- Keep generated shell scripts LF-encoded. On Windows, distinguish a launcher/preflight failure from a claim-bearing experiment attempt and record both honestly; do not spend a second declared run merely to hide an invocation error.
