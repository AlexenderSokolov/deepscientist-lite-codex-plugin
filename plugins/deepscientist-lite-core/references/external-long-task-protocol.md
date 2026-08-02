# External Long-Task Stewardship Protocol

This protocol applies when an experiment, data job, training run, evaluation, or
other command must survive the current tool call, SSH connection, or Codex worker
lifetime. DeepScientist Lite does not own, supervise, or restart the process. A
user, OpenScience-style controller, scheduler, container platform, or other
durable external system remains the runtime owner. DS Lite records enough
project-visible state for another bounded Codex iteration to inspect, preserve,
repair, or resume the task without guessing.

## Lifecycle Model

Treat these lifetimes as independent:

1. The conversation may remain recoverable after a connection closes.
2. The Codex worker or command-execution shell may be temporary.
3. A tmux server may detach from a terminal but still belong to the same cgroup,
   container, host, or allocation as the shell that created it.
4. The experiment process may exit while its tmux session or controller remains.
5. Project artifacts may survive even when every process has stopped.

Automatic creation is not the deciding factor. The deciding factor is whether a
durable owner outside the disposable launch context has been identified and
tested. `nohup`, `disown`, `setsid`, a background ampersand, or an automatically
created tmux session is not persistence evidence by itself.

## Launch Contexts

Record one launch context before execution:

- `stable-user-shell`: a user-controlled login environment whose disconnect
  behavior has been probed on the same host.
- `scheduler`: a recorded Slurm, PBS, or equivalent submission with a queryable
  scheduler job ID.
- `external-supervisor`: another authorized controller owns the process and
  exposes a query and recovery path.
- `agent-ephemeral`: the command is launched by a disposable agent/tool shell.
- `unknown`: ownership or cleanup behavior has not been established.

An `agent-ephemeral` or `unknown` context may prepare a launch-ready handoff, but
must not claim that it created a persistent run. If the task needs to outlive that
context, stop before the claim-bearing launch and hand the exact command to an
authorized durable owner.

## Tmux Capacity And Manual Bootstrap

When tmux is selected as the external runtime surface, Codex must plan capacity
before asking for any session. In this protocol, one planned "tmux terminal" is
one workload pane. A typical plan uses one tmux server + anchor session and one
named workload window/pane per concurrent long-running process. Increase the
count only for a documented isolation or concurrency need; tmux does not enforce
CPU, memory, GPU, disk, or API budgets.

Calculate `required_workload_panes = max_t(concurrent external processes at t)`.
Count every experiment, data job, and resident Codex CLI child worker that must
be alive at the same time; do not count queued work that will reuse a slot after
the prior task reaches a recorded terminal state. If the coordinator itself must
remain resident in tmux, count it as a separate child-worker slot. For example,
three simultaneous experiments plus two resident CLI workers require five
workload panes under one server and anchor session. The plan must show this
calculation, not merely request a convenient round number.

Create `research/artifacts/external-tmux-plan-<plan-id>.md` when one verified tmux
server will carry one or more external tasks. The plan is a capacity and
authorization baseline, not a second runtime state store. Each linked
`external-task-<task-id>.md` remains authoritative for process state and attempt
history.

Use this template:

```markdown
# External Tmux Plan <plan-id>

## Identity
- Plan id:
- Linked task ids:
- Gate state:
- Planned at:

## Capacity Request
- Why tmux is required:
- Required concurrent workloads:
- Server count:
- Anchor session count:
- Workload session / window / pane count:
- Slot mapping: slot id / task id / role / requested name:
- Per-slot CPU / RAM / GPU / disk / walltime / API budget:
- Reserved capacity and enforcement owner:

## Manual Bootstrap Contract
- Launch context expected from the user:
- Fixed socket path:
- Anchor session name:
- Top-level session / window / pane names:
- Allowed Codex child-worker slots:
- Allowed name prefix and capacity ceiling:
- Single launch authority / controller task ID:
- Slot claim key format and authority handoff rule:
- User bootstrap command block:
- User bootstrap command block SHA-256:
- Detach / disconnect / reconnect checkpoint:
- Commands Codex is forbidden to execute:

## Observed Server Fingerprint
- Host / user / UID / boot ID:
- tmux version:
- Socket path / owner / mode / inode:
- Server PID / process start time / parent PID:
- cgroup / container / PID namespace / allocation:
- Anchor and workload coordinates observed:

## Persistence Probe
- Probe command / PID / log / exit path:
- Before-disconnect observation:
- After-reconnect observation:
- Fingerprint comparison:
- Proven scope and remaining uncertainty:

## Attach Authorization
- Verified at / by:
- Exact read-only query and attach commands:
- Authorized slots and expiry:
- Supersedes plan:
- Conclusion and next action:
```

The plan gate states are:

`draft / awaiting-user-bootstrap / observed / probe-pending / verified / stale / rejected / superseded`

Only `verified` plans authorize slots. `draft`, `awaiting-user-bootstrap`,
`observed`, `probe-pending`, and `stale` require another bounded handshake or
human decision. `rejected` and `superseded` are closed and can never allocate a
slot; a linked task that still needs tmux requires a new plan.

The bootstrap handshake is mandatory:

1. Codex inventories every planned long-running experiment and Codex CLI child
   worker, calculates the minimum session/window/pane and concurrency capacity,
   writes the plan, and emits an exact User bootstrap command block.
2. Codex stops at `awaiting-user-bootstrap`. The user runs that block from an
   independent stable shell. Codex must not execute it on the user's behalf.
3. After the user reports completion, Codex uses the fixed socket path only for
   read-only identity checks. It records host, UID, boot ID, socket identity,
   server PID plus start time, parent, cgroup/container/namespace, and all planned
   coordinates. A socket path or PID alone is insufficient.
4. The user and Codex complete the same-boundary detach/disconnect/reconnect
   probe. The plan becomes `verified` only when the server fingerprint and probe
   evidence remain consistent. Otherwise mark it `stale` or `rejected` and stop.
5. Before each launch, Codex rechecks the fingerprint, assigned slot, capacity,
   command hash, budget, launch authority, and duplicate guard. Only the plan's
   recorded single launch authority may start a workload. Before sending the
   command, it persists a slot claim in the external task attempt using
   `plan_id + slot_id + task_id + attempt + command_hash` as the idempotency key.
   Child workers may not claim slots or launch other workers. Authority transfer
   requires an explicit handoff record; if multiple launchers are possible and
   no host-provided atomic claim exists, stop instead of racing. Codex must not
   create the tmux server or top-level session, expand capacity, silently select
   another socket, or fall back to `tmux new-session` when the verified server is
   absent.
6. Capacity changes require a new or superseding plan and another user bootstrap
   handshake. Codex may not infer extra authorization from an idle pane.

### Codex CLI Child Workers

A tmux session has no parent-child hierarchy, and this protocol does not define a
tmux "subsession" object. When a user asks for a child conversation, interpret it
as a pane-scoped Codex CLI child worker process launched in a user-provisioned,
verified workload pane. Codex may start such a worker only in a slot named and
authorized by the verified plan. This is a single supervised launch action, not
DS Lite subagent orchestration or a background scheduler.

For every Codex CLI child worker, record its parent task, pane coordinate, pane
root PID/start time/PGID, CLI PID/start time, provider surface and exact version,
provider thread/task ID when exposed, the ID acquisition evidence, read-only
query command, exact resume command, and a tested or unverified resume result.
If the provider exposes no stable handle, record `unavailable` rather than
claiming recoverability.

The tmux server, CLI process, provider conversation, experiment process, and
artifacts remain independent states. **tmux persistence does not prove Codex
conversation recovery**. A surviving CLI process must still be queried; a
recoverable provider thread does not prove the experiment is alive; and a live
experiment must not be restarted merely because its parent conversation cannot
be resumed.

## External Task Record

Create `research/artifacts/external-task-<task-id>.md` before a claim-bearing long
task starts. Keep the task identity stable and append a new attempt section for
each claim-bearing launch or process restart. A reconnection or observation of
the same process stays in its current attempt. Never rewrite an earlier failed
or interrupted attempt.

Use these headings and fields:

```markdown
# External Task <task-id>

## Identity
- Task id:
- Experiment or graph node:
- Evidence Pack index:
- Current state:

## Attempt <number>
- Evidence Pack / run ID:
- Launch context:
- Runtime owner:
- Host / user / node:
- Container or cgroup identity:
- Working directory:
- Exact command:
- Command SHA-256:
- PID and process start time:
- tmux socket / session / window / pane:
- Tmux plan / slot and server fingerprint:
- Slot claim idempotency key / launch authority:
- Pane root PID / start time / PGID:
- Codex CLI PID / start time:
- Provider surface / exact version / thread or task ID:
- Tmux query / attach command:
- Provider query / resume command and observed result:
- Experiment checkpoint resume command:
- Scheduler and scheduler job ID:
- Stdout / stderr / exit-code paths:
- Checkpoint paths:
- Heartbeat path and last observed time:
- Declared budget and consumed budget:
- Query command:
- Recovery command:
- Duplicate submission guard or idempotency key:
- Observation evidence:
- Conclusion and next action:
```

The only task states are:

`prepared / running / suspect / interrupted / recovering / completed / failed / abandoned`

Terminal states: `completed / failed / abandoned`.

Non-terminal states: `prepared / running / suspect / interrupted / recovering`.

An attempt process failure is not automatically a terminal task failure. Record
the attempt's exit evidence, but keep the task `interrupted` or `recovering`
while an authorized resume or retry remains possible. Set the task to `failed`
only when the unsuccessful task is closed and no further attempt is planned.

Each new claim-bearing launch attempt must use a new run ID and Evidence Pack,
and the attempt must retain that manifest path permanently. Repeated observation
or reconnection to the same process remains in the same attempt and may keep the
same pack. Never finalize a later attempt over an earlier attempt's pack or move
the stable identity pointer in a way that hides the complete attempt-to-pack
index.

`suspect` means current evidence cannot distinguish a live process from stale
state. Missing tmux state alone is not proof of failure, and a surviving
conversation or pane alone is not proof that the experiment is running.

Do not record secrets, authorization headers, tokens, cookies, complete process
environments, or credential-bearing URLs. Exact runtime identity paths such as a
tmux socket, cgroup, or scheduler allocation may be recorded in external task
artifacts because recovery depends on them, but they must not be copied into
portable Graph fields or generated run scripts. Use project-relative paths or
declared `external://` aliases for data and result roots.

## Persistence Probe

Before the first expensive run on a launch surface:

1. Record host, user, node, parent process, cgroup/container/allocation identity,
   tmux socket when applicable, and the proposed query command.
2. Run a short disposable probe through the same ownership boundary.
3. Detach or disconnect in the same way expected during the real task.
4. Reconnect to the same host and user, then query the external owner, process,
   log, and exit evidence.
5. Record what the probe proves and what remains unverified.

A probe on one login node, container, Codex execution surface, or scheduler does
not establish persistence on another.

## Recovery Algorithm

Use the rule **recover first, resubmit last**:

1. Read `PROJECT.md`, the Mission Board, the external task record, its Evidence
   Pack index, every recorded attempt pack, and any linked external tmux plan
   before issuing process commands.
2. Confirm host, user, node, namespace, container/cgroup/allocation, and tmux
   socket identities.
3. Query the durable owner, scheduler job, tmux server fingerprint, assigned
   slot, pane/CLI/experiment PIDs with start times, and provider thread handle. A
   missing pane or surviving tmux server is only one observation.
4. Inspect the exit-code file, sanitized log tail, heartbeat, checkpoint,
   consumed budget, expected outputs, and recorded hashes.
5. Classify the task as `running`, `suspect`, `interrupted`, `completed`, or
   `failed`; do not convert uncertainty or a retryable attempt failure into a
   terminal task failure.
6. Before repair, preserve partial logs, configuration, checkpoint files, output
   inventory, and the previous attempt conclusion. Hash project-local evidence
   through the Evidence Pack where applicable.
7. Repair, resume, or start a new attempt only from a non-terminal task after the
   failure boundary is identified. A new attempt is allowed only when the
   original process is proven absent, in-place recovery is not possible, the
   budget permits another attempt, and the duplicate submission guard is clear;
   set the task to `recovering` before recording that attempt.
8. Append the new observation to the task record, update the experiment artifact
   and Graph/STATUS through normal DS Lite commands, and stop the bounded worker
   iteration.

## Backup And Repair Discipline

- Treat partial outputs and failed attempts as evidence, not cleanup targets.
- Preserve the exact command, configuration, logs, exit evidence, checkpoints,
  and output inventory before changing code or resuming.
- Write a new attempt or correction artifact instead of replacing prior evidence.
- Keep large or sensitive external checkpoints behind explicit aliases; do not
  copy them into the project merely to call the copy a backup.
- Never restart only because a controller, conversation, pane, or heartbeat is
  missing. Reconcile all available ownership and artifact evidence first.
- Never hide a duplicate launch, consumed budget, or partially produced valid/test
  output by relabeling the later attempt as the original run.

## Product Boundary

DS Lite provides this file protocol, Evidence Packs, bounded iteration, and
review gates. It does not provide a daemon, queue, process supervisor, launcher,
tmux manager, scheduler adapter, or automatic retry service. A future full
DeepScientist runtime may implement those capabilities, but it must keep runtime
ownership, experiment state, conversation state, and artifact state separate and
must expose the same recovery evidence rather than inferring success from UI or
session state.
