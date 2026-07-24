# Context Handoff Protocol

Use `ds-lite.handoff.v1` when a conversation is long, a task changes owner, or
a bounded child task returns to its parent. The handoff is a projection, not a
transcript. It carries only the goal, observed facts, hypotheses, authorization
boundary, non-secret configuration, relative evidence refs, failure layer,
unverified items, and one next action.

Create and validate it with `teaching/handoff_protocol.py`. A handoff must have
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
