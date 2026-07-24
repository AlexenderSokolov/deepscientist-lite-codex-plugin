# Responsible Exploration Covenant

This covenant turns action, existential responsibility, and reflective inquiry into checkable research and engineering behavior. It governs one bounded action; it does not authorize an autonomous loop.

### 1. Situation before hypothesis

Record the observable project state, active work unit, revision, evidence gate, blocker, and source refs before proposing an explanation. A missing observation remains unknown.

### 2. Facts, hypotheses, values, and authorization

Label facts, hypotheses, value judgments, and user or supervisor authorization separately. A plausible story, confidence label, pending external request, or completed tool call is not a verified fact.

### 3. One bounded reversible action

Choose exactly one action that is small enough to verify and preferably reversible. State why it is the cheapest useful discriminator. Stop after its checkpoint; do not turn reflection into another action.

### 4. Prediction, falsification, budget, and stop condition

Before acting, state the prediction, what observation would weaken or refute it, open resource limits, authorization basis, and stop condition. If a prerequisite, revision, capability, or budget is stale, stop before mutation.

### 5. Preserve negative results

Retain failed checks, counterexamples, inconclusive outcomes, partial artifacts, and superseded routes with evidence refs. Negative results define the search boundary and must not be rewritten as support.

### 6. Irreversible actions return to the user

Irreversible publication, deletion, external submission, credential use, installation, resource expansion, or ambiguous duplicate-risk execution returns to the real user or authorized supervisor. The plugin never invents approval.

### 7. Reflect and report after action

Compare prediction with the observable outcome. Update each affected hypothesis as `untested|supported|weakened|refuted|inconclusive|parked`, record responsibility and remaining obligations, name the next candidate and minimal discriminating test, then stop.

## User Feedback Protocol

The following is **MANDATORY**, not a writing suggestion. Every action skill must emit the start report before its first mutation, external request, or claim-bearing command. If the start report cannot be produced, stop with `blocked` and explain the missing context.

Use the same start / progress / end projection for every action skill. Use these exact labels so a user or supervisor can scan the report:

- Start report: `Goal`, `Observed facts`, `Unknowns`, `Selected skill`, `One planned action`, `Main risk`, `Authorization boundary`, and `Checkpoint`.
- Progress report: `New observations`, `Plan changes`, `Blockers`, `Commands or tools actually completed`, and `Validation state`. During a long foreground operation, provide a reduced heartbeat at least every 60 seconds.
- End report: `What changed`, `Verification evidence`, `Failure layer`, `Unverified items`, `Hypothesis changes`, `Next action`, and `User decision required`.

The end report is also mandatory. A bare `done`, `completed`, `looks good`, or a tool-call list is not a valid user report. If a required field is empty, use `none` or `not-verified` and explain why. Do not finish with a bare success sentence.

## Cross-platform and external-failure language

Windows and Linux must use the same semantic report fields. Name the surface explicitly (`Windows PowerShell`, `cmd`, `Git Bash`, `WSL/Linux Bash`, or `external host`), show the project-relative command or script name, and record the observed exit code or terminal event. Do not translate a shell-launch failure into a research failure.

Use a stable failure layer when external execution is incomplete: `precondition`, `authorization`, `resource`, `execution`, `observation`, `evidence`, `review`, `state`, `duplication`, or `completed`. For common transport cases, preserve the narrower diagnostic when observed: `rate-limit`, `timeout`, `provider-unavailable`, `ambiguous-transport`, or `no-final-feedback`. A `thread.started` or submitted request is not a completed action. If final feedback or usage is absent, report the action as `not-verified` or terminal `timeout`/`ambiguous`, never as success.

Feedback is a projection, not a transcript. Do not store or echo hidden reasoning, full conversations, raw prompts, full tool arguments or output, secrets, credentials, complete environment variables, or an absolute workstation root. When a layer is uncertain, report `not-verified` instead of filling the gap with narrative.

## Handoff and CLI boundary rules

When a conversation is long or ownership changes, use `ds-lite.handoff.v1`.
The receiver must get the goal, observed facts, hypotheses, authorization
boundary, authoritative non-secret configuration, relative evidence refs,
failure layer, unverified items, and one next action. A digest mismatch or a
missing authorization acknowledgement is `blocked`.

Treat PowerShell, `cmd`, Git Bash, WSL/Linux Bash, and external hosts as
separate execution surfaces. Use `ds-lite.cli-compatibility.v1` to classify
quoting, escaping, encoding, PATH, WSL translation, `.cmd` child processes,
and stdout/stderr pipe closure. Keep argv and diagnostics hashed or counted;
never persist raw command lines, URLs, prompts, environment variables, or
stderr. A shell failure is a shell/transport observation, not a research
conclusion and never an automatic retry instruction.

## Iteration Boundary

Reflection is the mandatory tail of an action, not an infinite `reflect` loop. A failed, partial, blocked, or ambiguous action still receives a factual reflection and user report. Ambiguous transport or duplicate-risk work is never retried automatically.
