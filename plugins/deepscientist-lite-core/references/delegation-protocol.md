# Bounded Delegation Protocol

DeepScientist Lite may describe one supervised fan-out with
`ds-lite.delegation.v1`. This is a project-visible coordination record, not a
runtime service. It provides no daemon, no queue, no scheduler, no background
worker ownership, and no automatic retry.

## When Delegation Is Appropriate

Use delegation only when one active research or engineering work unit contains
two or three bounded tasks that can be understood independently. The parent
must be able to give each task a complete local contract and verify the returned
artifact. Use one normal worker when the tasks share write ownership, depend on
unrecorded context, require more than the declared budget, or form a single
inseparable action.

The protocol permits a maximum of three child tasks. Every plan sets
`nested_delegation=false`: children cannot create children. A host may execute
approved tasks in parallel or sequentially, but DS Lite does not retain or
schedule workers after the current coordination cycle.

## Authority Gate

Create and validate the plan before execution. Its initial approval is:

```json
{
  "status": "required",
  "authority": "none",
  "approval_ref": "",
  "extensions": {}
}
```

The coordinator must show the bounded plan and stop for explicit approval. Only
explicit user or OpenScience approval may change the authority to `user` or
`openscience` and status to `approved`. Store a short project-relative approval
artifact that identifies the delegation, approved task IDs, scope, and time;
do not copy a full conversation, hidden reasoning, credentials, or environment.
Denied approval closes the plan. Missing or ambiguous approval never launches a
child.

## Machine Contract

The root object has exactly these fields; future additions belong only in
`extensions`:

| Field | Contract |
| --- | --- |
| `schema_version` | Always `ds-lite.delegation.v1`. |
| `delegation_id` | Stable ID distinct from the parent work unit and task IDs. |
| `parent_work_unit_id` | Active bounded work unit. |
| `strategy` | `parallel` or `sequential`. |
| `status` | `planned`, `authorized`, `running`, `collecting`, `completed`, `partial`, `blocked`, or `cancelled`. |
| `approval` | Explicit authority state and project-relative evidence ref. |
| `integration_owner` | The single parent-side integration owner; never a child task ID. |
| `max_children` | Integer from 1 to 3; the task list cannot exceed it. |
| `nested_delegation` | Always `false`. |
| `tasks` | One to three bounded task contracts. |
| `created_at`, `updated_at` | UTC protocol timestamps. |
| `extensions` | Only forward-compatible namespace. |

Each task declares exactly:

- `task_id` and a non-empty `objective`;
- `input_refs` containing only the authority and evidence needed for that task;
- `allowed_paths` and `expected_output_refs`, both treated as exclusive path
  ownership for the task;
- one or more `validation_commands`;
- open `resource_limits` entries using dimension, unit, and positive value;
- one or more observable `stop_conditions`;
- `status`, `result_ref`, and `extensions`.

Paths must be project-relative and must not escape the project. No two task
ownership paths may be equal or contain one another. Project-external inputs may
use an authorized `external://alias/path` ref, but write/output ownership cannot.

## Lifecycle And Results

`planned` means the plan is validated but not authorized. `authorized`,
`running`, and `collecting` require approved authority. Children return through
their independent declared artifact/result ref; they do not merge sibling work
or mutate the parent graph. A terminal task (`completed`, `partial`, `blocked`,
or `cancelled`) must retain a non-empty result ref describing what happened,
including a bounded failure or blocker. A terminal delegation requires every
task to be terminal; `completed` additionally requires every task to be
`completed`. Task IDs must remain distinct from the delegation and parent work
unit IDs.

The integration owner checks path ownership, returned artifacts, scoped diffs,
and declared validation commands. It then runs the parent repository validation
and decides what, if anything, enters the work unit and Graph. Child completion
is not evidence validation and does not upgrade claim readiness by itself.

If a task is partial or blocked, keep its result and end the coordination cycle.
If execution or transport is ambiguous, do not resubmit it: record the duplicate
risk and request a supervisor decision. A later attempt requires a new audited
action, not an automatic retry.

## Validation

Run:

```text
python <plugin>/scripts/ds_lite_protocol.py validate-delegation --path <delegation.json>
```

Validation rejects missing fields, unsupported enums, more than three tasks,
`nested_delegation=true`, ID conflicts, path overlap or escape, sensitive or
hidden-reasoning fields, unknown keys outside `extensions`, active states without
approval, and terminal tasks without result refs. The forward-compatible
`extensions` object also cannot introduce daemon, queue, scheduler, background
worker, automatic retry, or retry-policy fields because those capabilities are
outside the Lite product boundary.
