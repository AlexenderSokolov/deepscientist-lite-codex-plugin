# Context Handoff Protocol

Use `ds-lite.handoff.v1` when a conversation is long, a task changes owner, or
a bounded child task returns to its parent. The handoff is a projection, not a
transcript. It carries only the goal, observed facts, hypotheses, authorization
boundary, non-secret configuration, relative evidence refs, failure layer,
unverified items, and one next action.

Create the projection in the project and validate it with
`python <core-plugin>/scripts/ds_lite_handoff.py validate --path <handoff.json>`. A handoff must have
a digest over its redacted goal/facts/configuration projection. A receiver must
reject a missing or mismatched digest, stale authorization, absolute path,
prompt, raw JSONL, credential, token, or hidden reasoning field.

The sender must explicitly state what the receiver may do, what remains outside
scope, which configuration is authoritative, and which previous attempts are
frozen. The receiver must acknowledge the same boundary before mutation or an
external request. A child receives only its declared objective, refs, allowed
paths, validation commands, budget, stop conditions, and result ref.

Handoff status is `prepared`, `ready`, `blocked`, `completed`, or `cancelled`.
It never authorizes retry, release, cache mutation, nested delegation, or a
second action. A blocked or ambiguous handoff stays terminal until a supervisor
creates a new audited action.

When OpenScience, Codex tasks, or tmux panes need cross-system correlation,
place only opaque IDs in `extensions.host_mapping` using
`ds-lite.host-mapping.v1`: one `coordinator_host_id` and a non-empty
`worker_host_ids` task-to-host map. IDs must be unique and must not contain
commands, socket paths, prompts, credentials, or lifecycle authority. The
mapping identifies hosts; it does not let DS Lite create, kill, or own them.
