---
name: ds-lite-iterate
description: "Use when resuming a cross-session research or engineering workspace, advancing exactly one bounded action, updating recoverable artifacts and Mission Board state, reflecting on the result, reporting to the user, and stopping."
---

# DS Lite Iterate

Run one visible research-worker iteration. This skill is for a Codex worker supervised by a user or OpenScience-style controller; it is not a daemon, scheduler, or permission to run indefinitely.

Before acting, read [the Responsible Exploration Covenant](../../references/responsible-exploration-covenant.md) and use the shared start / progress / end protocol. Send the mandatory Start report before registering the iteration, use Progress reports during long work, and finish with the mandatory End report after reflection; missing evidence becomes `blocked` or `not-verified`, never polished success prose.

## Workflow

1. Read `PROJECT.md`, `STATUS.md`, `RESEARCH_MAP.md`, `research/work-unit.json`, and `research/state/graph.json`. Give the covenant's start feedback before mutation.
2. Run `python <plugin>/scripts/ds_lite_state.py mission --root <project> --format json` and treat it as the current task board. Check `claim_readiness`, `evidence_detail`, `latest_iteration`, `hypothesis_pool`, compatibility warnings, and active-route waiting separately from off-route blocked debt.
3. Check `research/artifacts/external-tmux-plan-*.md` before `external-task-*.md`. If a gate state is not `verified`, it cannot authorize a slot. Codex must not create or expand tmux capacity. If any task is non-terminal (`prepared`, `running`, `suspect`, `interrupted`, or `recovering`), read [the external long-task protocol](../../references/external-long-task-protocol.md), choose only one status check, evidence backup, repair, recovery decision, `stop`, or `ask-human`, and keep the plan's single launch authority. A non-authority worker must not race another launcher.
4. Choose exactly one action kind from `scout`, `idea`, `collect-evidence`, `execute`, `debug`, `review`, `analysis`, `write`, `branch`, `rollback`, `stop`, `ask-human`, or `status-check`. Map legacy `exploit` explicitly to `execute`; reject any other unregistered action. State its prediction, falsification condition, resource limits, authorization, and stop condition.
5. Write `research/artifacts/frontier-decision-<slug>.md` with the current situation, hypothesis, latest evidence, chosen and rejected actions, metric tradeoff, budget, rollback or supersede target, and checkpoint. Prepare the action JSON required by the iteration helper without secrets or workstation roots.
6. Before the action, run `python <plugin>/scripts/ds_lite_iteration.py init --root <project> --iteration-id <id> --selected-skill <target-skill> --action-json <action-json> --input-ref <ref> --expected-revision <revision>`. Confirm the receipt is `running`; if registration fails, do not act.
7. Complete exactly one `plan -> act -> verify -> reflect -> report -> stop` cycle. Invoke at most one narrower skill or perform one status/stop action, update Graph only through `ds_lite_state.py` with expected revision, retain negative results, and run the smallest relevant validation. Do not begin a second action when the first is partial or blocked.
8. Build one terminal result with status `completed|partial|blocked|failed|ambiguous`, after revision, outputs, Graph changes, validations, stop reason, `reflection`, and `user_report`. Reflection records observable outcomes, hypothesis updates, expectation gap, negative results, authorization and obligations, learned boundaries, next candidates, and the minimal discriminating test. It never stores hidden reasoning or a full transcript.
9. Run `python <plugin>/scripts/ds_lite_iteration.py finalize --root <project> --path <iteration-ref> --result-json <terminal-result-json>`. An error, timeout, or ambiguous transport still needs a factual terminal receipt; do not retry an ambiguous or duplicate-risk action.
10. Run `python <plugin>/scripts/ds_lite_iteration.py verify --root <project> --path <iteration-ref>`. If verification fails, report the receipt as partial or blocked rather than completed.
11. Run `render-status` so `STATUS.md` projects the terminal `latest_iteration`, updated hypothesis pool, evidence gate, blocker, and string `next_action`.
12. Give the covenant's end feedback and stop. This minimal receipt is not an exactly-once transaction and does not claim full P1 execution semantics.

## Hard Rules

- One invocation equals one iteration. Do not loop.
- Do not start a reflection loop. Reflection is the mandatory tail of the one action.
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

## Handoff

End with a compact worker handoff: action taken, files changed, graph node or edge changed, status board path, remaining blocker, and the next single action.
