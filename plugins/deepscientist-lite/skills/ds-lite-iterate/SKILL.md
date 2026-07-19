---
name: ds-lite-iterate
description: "Use when Codex should advance a DeepScientist Lite project by exactly one bounded worker iteration: read the mission board, choose one action, record a frontier decision, update artifacts, graph, STATUS, and stop at a checkpoint."
---

# DS Lite Iterate

Run one visible research-worker iteration. This skill is for a Codex worker supervised by a user or OpenScience-style controller; it is not a daemon, scheduler, or permission to run indefinitely.

## Workflow

1. Read `PROJECT.md`, `STATUS.md`, `RESEARCH_MAP.md`, `research/work-unit.json`, and `research/state/graph.json`.
2. Run `python <plugin>/scripts/ds_lite_state.py mission --root <project> --format json` and treat it as the current task board. Check `claim_readiness`, `evidence_detail`, compatibility warnings, and active-route waiting separately from off-route blocked debt before choosing an action.
3. Check `research/artifacts/external-tmux-plan-*.md` before `external-task-*.md`. If an active or linked plan's gate state is not `verified`, it cannot authorize a slot. For `draft`, `awaiting-user-bootstrap`, `observed`, `probe-pending`, or `stale`, perform exactly one evidence-preserving status check or `ask-human`, then stop; `rejected` and `superseded` remain unavailable and require a new plan if tmux is still needed. Codex must not create or expand tmux capacity. If any task is non-terminal (`prepared`, `running`, `suspect`, `interrupted`, or `recovering`), read [the external long-task protocol](../../references/external-long-task-protocol.md), perform exactly one bounded status check, evidence backup, repair, recovery decision, `stop`, or `ask-human` action, update the handoff, and end this iteration without starting new work.
4. Choose exactly one action: `exploit`, `branch`, `debug`, `review`, `analysis`, `stop`, or `ask-human`.
5. Write `research/artifacts/frontier-decision-<slug>.md` with: current hypothesis, parent line, latest evidence, chosen action, rejected actions, promotion status, metric tradeoff, budget check, rollback target, supersede reason, and stop condition.
6. If the action is `review`, use `$ds-lite-review`; if `analysis`, use `$ds-lite-analysis-write`; if `exploit`, `branch`, or `debug`, create or update only the minimum idea/experiment/checkpoint needed for the next bounded step.
7. Update graph only through `ds_lite_state.py`, attach the frontier decision artifact, and preserve branch/rollback/supersedes relationships.
8. Run `render-status` so `STATUS.md` becomes the visible Mission Board.
9. Stop after this one iteration. Report the chosen action, artifact path, active node, next action, and whether user/OpenScience approval is needed.

## Hard Rules

- One invocation equals one iteration. Do not loop.
- Artifact is not progress; API or graph readiness is not completion.
- An idea line is not an experiment. Without smoke/default/review/analysis evidence, the next action remains experiment preparation.
- Do not choose `analysis` unless a direct passing review and Evidence Pack exist. If evidence is absent, choose `debug`, `review`, `ask-human`, or `stop`.
- Metric direction errors are protocol failures. Record a protocol-breaking correction and do not silently overwrite old evidence.
- GPU runs, long runs, dependency installs, cluster jobs, and external data access require user or supervisor approval unless a project budget policy already authorizes them.
- Every claim-bearing experiment must have an Evidence Pack and review before analysis/write.
- Preserve negative results. Use `rollback`, `branch`, or `supersedes`; do not delete old nodes to make the route look clean.
- A missing pane, stale heartbeat, or surviving conversation is not enough to classify a long task. Query its recorded owner and process evidence, preserve partial outputs, and never submit a replacement run until duplicate execution and budget reuse have been ruled out.
- A verified tmux server is not a live-worker signal. Query the assigned pane root, Codex CLI or experiment process, provider handle, and attempt evidence separately; never allocate an unplanned pane or restart a live experiment because a conversation cannot be resumed.
- Only the plan's single launch authority may persist a slot claim and start a pane workload. A child worker or non-authority iteration must stop and hand the request to that authority; it must not race another launcher.

## Frontier Decision Template

Use these headings in `frontier-decision-<slug>.md`:

- Current mission
- Latest evidence
- Candidate actions considered
- Chosen action
- Metric and budget check
- Rollback or branch target
- User or supervisor decision needed
- Next visible checkpoint

## Communication Layer

Before iterating, read `../../references/communication/core.md`, `../../references/communication/self-audit.md`, and the project-root `STYLE.md` when present. Follow Phase 1 before action, Phase 2 after each material action, and Phase 3 before handoff. Use the selected profile only for the user-facing decision and handoff; it does not change the one-iteration boundary, graph authority, evidence gate, or execution permission. Protect commands, paths, JSON/YAML, logs, metrics, formulas, citations, and formal definitions（保护内容不因改写而改变）, and state exactly what was verified.

## Handoff

End with a compact worker handoff: action taken, files changed, graph node or edge changed, status board path, remaining blocker, and the next single action.
