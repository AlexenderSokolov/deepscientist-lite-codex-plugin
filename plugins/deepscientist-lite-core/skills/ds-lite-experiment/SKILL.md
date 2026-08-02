---
name: ds-lite-experiment
description: Use when implementing, running, repairing, comparing, or documenting a bounded research or engineering experiment with explicit predictions, baselines, metrics, budgets, stop conditions, reproducible commands, and evidence.
---

# DS Lite Experiment

Communication boundary: 保护内容必须原样保留；不得改写用户约束或证据限定。

Experiments must be reproducible enough that another session can rerun or diagnose them from files.

Before acting, read [the Responsible Exploration Covenant](../../references/responsible-exploration-covenant.md) and use the shared start / progress / end protocol. Send the mandatory Start report before execution, use Progress reports during long work, and finish with the mandatory End report; missing evidence becomes `blocked` or `not-verified`, never polished success prose.

## Workflow

1. Read the active idea node, linked idea artifact, `PROJECT.md`, `STATUS.md`, `research/work-unit.json`, and current run scripts.
2. Define the smallest useful test: hypothesis, baseline, command, inputs, metric direction, early budget, final budget, aggregate/AUC metric when relevant, budget cap, expected signal, success threshold, and failure interpretation.
3. Read `../../references/evidence-pack-protocol.md`. For comparison experiments, also read `../../references/experiment-comparison-template.md` and use its headings unless the host project already has a stronger local template. If execution must outlive the current tool call, SSH connection, or Codex worker, also read [the external long-task protocol](../../references/external-long-task-protocol.md) and create `research/artifacts/external-task-<task-id>.md` before launch.
4. If tmux is the requested runtime surface, inventory all concurrent experiments and planned Codex CLI child workers. Compute `required_workload_panes = max_t(concurrent external processes at t)`: count each experiment, data job, resident coordinator, or Codex CLI child worker that must be alive at the same time, but not queued work that will reuse a slot after a recorded terminal state. Write `research/artifacts/external-tmux-plan-<plan-id>.md` with the minimum server/session/window/pane and resource capacity, a fixed socket, named slot mapping, exact User bootstrap command block, probe checkpoint, and forbidden Codex actions. Stop at `awaiting-user-bootstrap`, ask the user to run the block from an independent stable shell, and do not launch a claim-bearing task in this iteration.
5. After the user reports bootstrap completion, inspect the fixed socket read-only, record the complete server fingerprint, and require a real detach/disconnect/reconnect probe. Continue only when the plan is `verified`; otherwise mark it `stale` or `rejected`, preserve the evidence, and stop. Never create the tmux server or top-level session, expand capacity, or fall back to another socket.
6. Before claim-bearing execution, update `research/work-unit.json` to profile `experiment-run`, declare `evidence_requirements` with the applicable `ds-lite.evidence.v1` validator, and reserve the canonical manifest path in `evidence_refs`. Keep machine- or domain-specific details under `extensions`; reject unknown top-level fields. Run `mission --format json` and stop if the work unit is invalid.
7. Create `research/artifacts/experiment-contract-<slug>.json` from the plugin Evidence Pack contract template. The contract must declare metric direction, early/final/aggregate metric surfaces when they can disagree, final budget cap, and what each failure mode means. Do not include credentials, tokens, passwords, or a process environment dump.
8. Validate and initialize the pack before execution: `python <plugin>/scripts/ds_lite_evidence.py init --root <project> --run-id <run-id> --contract <contract-file>`.
9. Implement or repair code using the host project's conventions. Keep unrelated refactors out. Extend the initialized `run_experiment.sh` instead of replacing its portable resolver: preserve the project-root derivation and `tools/ds_lite_runtime.sh`, then add the complete replay command, log capture, metrics output, and finalize/verify arguments. Machine-specific CLI roots belong in `PYTHON_BIN`, `DS_LITE_EVIDENCE_CLI`, or `DS_LITE_PLUGIN_ROOT` at execution time, never in the saved script.
10. Run the experiment when practical. Save stdout, stderr, numeric `metrics.json`, a sanitized `ds-lite.environment.v1` JSON description, and declared outputs. GPU jobs, long runs, dependency installs, cluster jobs, and external data access require user or OpenScience supervisor approval unless the project budget policy already authorizes them. For a tmux-backed task, continue only if this worker is the plan's single launch authority; recheck the verified fingerprint, slot, capacity, command hash, budget, and duplicate guard, persist the slot claim/idempotency key in the external task attempt, then launch only in its assigned user-provisioned pane. A child worker must never claim another slot or launch another worker. For a Codex CLI child worker, also record pane/CLI PIDs with start times, provider surface/version, thread/task ID when exposed, query/resume commands, and observed resume support. Tmux persistence alone never proves conversation recovery. An `agent-ephemeral` or `unknown` launch context without a verified external plan may only produce a launch-ready handoff. If compute, data, ownership, capacity, cluster paths, or credentials block execution, keep the initialized pack, save the exact command, and mark the experiment node `blocked`.
11. Finalize and verify completed or failed runs with `ds_lite_evidence.py finalize` followed by `verify --strict`. A failed process is still valid evidence when its pack is intact.
12. Write `research/artifacts/experiment-<slug>.md` with the contract, command, environment, metrics, logs, outputs, failures, manifest path, and next interpretation.
13. Read the current revision, then add or update an `experiment` node with `add-node`/`update-node`; link the manifest through `link-path --type evidence`, attach artifacts, update status with `set-status`, and pass `--expected-revision` on every write. For a long task, attach the external task record and linked external tmux plan to the experiment node with `link-path --type artifact` before handing it to review.
14. Run `render-status` so `STATUS.md` shows what ran, what failed, what waits for review, and the next concrete action.

## Recording Rules

- Record failed experiments as first-class evidence.
- Separate smoke checks from claim-bearing runs; a smoke pass only proves the plumbing works.
- Report early-budget, final-budget, and aggregate/AUC metrics separately when budget matters.
- Treat a metric direction or aggregation bug as a protocol-breaking correction. Record the old interpretation, correction, affected claims, and `rollback` or `supersedes` relation; do not silently overwrite evidence.
- Record parent line, promotion status, rollback target, and supersede reason in experiment artifacts when a run branches from or replaces a prior line.
- Attach output files, logs, figures, and scripts through `artifact_paths` or `evidence_paths`.
- Use project-relative paths. Record `external://` outputs without hashing unless the user explicitly authorizes `--hash-external`.
- Do not begin analysis/write directly after experiment; hand the finalized run to `$ds-lite-review`.
- If an experiment invalidates an idea, add a `rollback` or `supersedes` edge instead of erasing the old route.
- Keep `STATUS.md` honest through `render-status`: active node, what ran, what failed, and the next concrete action.
- On resume, reconcile the external task record before launching anything. Preserve partial evidence and append a new attempt only after proving the prior process is absent, recovery is impossible, budget remains, and duplicate submission is ruled out. A new claim-bearing launch attempt must use a new run ID and Evidence Pack; never finalize over a prior attempt's pack. Reconnection to the same process stays in the same attempt.
- A user-created tmux surface is capacity, not progress. Do not claim a task or conversation is running until its actual PIDs, provider handle, logs, heartbeat, and attempt record are reconciled.
- Never edit `graph.json` directly. On revision conflict, reload the graph and reconcile both sessions' evidence before retrying.
- Keep generated shell scripts LF-encoded. On Windows, distinguish a launcher/preflight failure from a claim-bearing experiment attempt and record both honestly; do not spend a second declared run merely to hide an invocation error.

## Communication and Learning Gate

Before a non-trivial action, read `../../references/communication/core.md` and `../../references/communication/self-audit.md`; read the project `STYLE.md` when present.
Complete Phase 1 before the first side effect. Preserve protected content, report observable evidence, and finish with a readable Handoff.
When this skill is selected, run the learning receipt check for its declared tutorial set before the first write, command, or network request. A stale or missing receipt is a blocker; the learning helper itself is the only exception.
