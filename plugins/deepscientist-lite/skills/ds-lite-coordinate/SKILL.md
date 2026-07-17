---
name: ds-lite-coordinate
description: Use when a DeepScientist Lite work unit has two or three independent bounded subtasks that may be delegated after explicit user or OpenScience approval, with disjoint path ownership and parent-owned integration.
---

# DS Lite Coordinate

Plan and collect one bounded delegation without turning DeepScientist Lite into a scheduler. Use the host's child-agent capability only after approval; the parent worker remains the integration owner.

## Workflow

1. Read `PROJECT.md`, `STATUS.md`, `research/work-unit.json`, and the current Mission Board. Use a single worker or `$ds-lite-iterate` when there are fewer than two independent tasks, when write ownership overlaps, or when the parent cannot verify every result.
2. Read [the delegation protocol](../../references/delegation-protocol.md). Create `research/artifacts/delegation-<delegation-id>.json` from `assets/templates/research/delegation.json` with schema `ds-lite.delegation.v1`.
3. Declare a maximum of three tasks. For each task, record one objective, only the required input refs, disjoint allowed paths, expected output/result refs, validation commands, open resource limits, stop conditions, and initial status. Set `nested_delegation=false` and name exactly one integration owner that is not a child task.
4. Run `python <plugin>/scripts/ds_lite_protocol.py validate-delegation --path <delegation.json>`. Resolve every schema, path, ownership, or budget error before asking for approval.
5. While approval is `required`, present the plan and stop. Do not launch a child task until explicit user or OpenScience approval exists. Record only a minimal project-relative approval artifact, then set `approval.authority`, `approval.approval_ref`, and `approval.status=approved`; do not preserve hidden reasoning, credentials, or full conversation text.
6. After approval, invoke no more than the declared tasks through a host-provided child-agent facility. Use `parallel` only for truly independent path owners; otherwise follow `sequential`. Give each child only its declared objective, refs, paths, validation, resource limits, stop conditions, and result path. A child must not delegate again, expand scope, integrate siblings, or retry automatically.
7. Require every child to write or return its declared result ref. Update task status and `result_ref`, validate the sidecar again, and preserve `partial`, `blocked`, or `cancelled` outcomes instead of hiding them or launching replacements.
8. As the integration owner, inspect all returned artifacts and scoped diffs, reject ownership conflicts, run each declared validation command, then run the repository-wide validation required by `PROJECT.md`. The parent alone decides whether accepted changes enter the work unit and graph.
9. Mark the delegation terminal only when its task states and result refs agree. Report completed, partial, and blocked tasks separately, record the next bounded suggestion, and stop after this one coordination cycle.

## Hard Rules

- A delegation plan is not execution authority. Explicit user or OpenScience approval is mandatory.
- A plan has a maximum of three children and `nested_delegation=false`.
- Keep path ownership disjoint. Expected output refs are owned paths; only the integration owner may combine results.
- Do not create a daemon, queue, scheduler, background worker service, or automatic retry loop.
- Do not treat a child response as verified evidence. Check the declared artifact, diff, and validation result.
- Do not retry an ambiguous or duplicate-risk action. Preserve the result as partial or blocked and return control to the supervisor.
- Do not change `ds-lite-iterate`: one iterate invocation remains one action and one checkpoint.

## Handoff

End with the delegation path, approval authority/ref, task statuses and result refs, validations run, conflicts or blockers, integration decision, and the next single supervisor action. Stop after the handoff.
