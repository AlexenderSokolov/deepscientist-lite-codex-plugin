# DS Lite State Graph Protocol

`research/state/graph.json` is the machine-readable source of truth. `RESEARCH_MAP.md` is a rendered projection for humans.

## Graph Shape

```json
{
  "schema_version": "ds-lite.graph.v2",
  "revision": 0,
  "project": {"id": "", "title": ""},
  "root_node_id": "",
  "active_node_id": "",
  "nodes": {},
  "adjacency": {}
}
```

## Node

Required fields:

- `id`: stable node id
- `kind`: `intake`, `scout`, `idea`, `experiment`, `review`, `analysis`, `write`, `decision`, or `finalize`
- `status`: `proposed`, `active`, `blocked`, `done`, `superseded`, or `abandoned`
- `title`: short human title
- `summary`: public summary, not hidden reasoning
- `artifact_paths`: Markdown records or output files
- `memory_paths`: durable memory cards
- `evidence_paths`: code, data, log, figure, citation, or report paths
- `created_at`: UTC ISO timestamp
- `updated_at`: UTC ISO timestamp

## Edge

Each adjacency entry is keyed by source node id:

```json
{
  "to": "idea-cheap-baseline",
  "relation": "branch",
  "reason": "Candidate route after scout",
  "artifact_path": "research/artifacts/idea-cheap-baseline.md"
}
```

Allowed relations:

- `next`: normal stage progress
- `branch`: alternative route that may be revisited
- `supports`: evidence supports a claim or decision
- `blocks`: dependency or missing evidence blocks progress
- `supersedes`: newer node replaces an older route
- `rollback`: return to a previous viable node

## Rules

- Do not record hidden chain-of-thought.
- Record failed experiments as evidence.
- Preserve older nodes when decisions change; use edges to explain the change.
- Keep paths project-relative, or use `external://<alias>/<relative-path>` for resources outside the project. Resolve aliases with `DS_LITE_EXTERNAL_<ALIAS>`; never store workstation absolute paths.
- Render `RESEARCH_MAP.md` after graph edits.
- Use `ds_lite_state.py` for every mutation. Do not edit `graph.json` directly.
- Pass `--expected-revision` when coordinating multiple sessions. Reload and reconcile on exit code 4.
- New experiment nodes should link `research/evidence/<run-id>/manifest.json`; absence is a compatibility warning and fails strict validation.
- New analysis/write routes should have a direct progression parent of kind `review`.

## Work Unit v1

`research/work-unit.json` is a sidecar with schema `ds-lite.work-unit.v1`; it does not change Graph v2. It identifies one bounded research or engineering work unit through `work_unit_id`, `goal`, `execution_mode`, `profile_id`, `state`, prerequisites, required capabilities, evidence requirements and refs, open resource limits, subjects, and an optional active iteration ref.

- `execution_mode` is exactly `none`, `inline`, `external`, or `human`.
- A work unit with no claim requirement remains `planning`, even when ordinary artifacts, logs, `PROJECT.md`, or `STATUS.md` exist.
- A claim-bearing work unit is `needs-evidence` until its profile's typed validator passes the declared refs. P0 validates `experiment-run` through `ds-lite.evidence.v1`; other validators fail closed.
- Literature, mathematical exploration, software evaluation, and numerical simulation profile ids are reserved / not-validated. Their domain rules require future case evidence and are not current support claims.
- Unknown fields are rejected. Forward-compatible data may appear only under an `extensions` object.

Old Graph v2 projects without the sidecar remain readable. Mission derives a compatibility work unit from the active route and emits a compatibility warning; the graph itself is not migrated.

## Evidence Pack v1

- `contract.json` declares command, inputs, metrics, thresholds, seeds, budget, expected outputs, and failure interpretation before execution.
- `manifest.json` records execution status, logs, metrics, sanitized environment metadata, output paths, sizes, hashes, and verification results.
- Project-local files require SHA-256. External files are only hashed when explicitly requested.
- Verification failure blocks a done experiment; a failed process may still be valid evidence when its pack is intact.
- Review is a separate workflow and artifact, not a guarantee of separate-model or infrastructure isolation.

## Typed Review Result v1

A completed review links both a human-readable Markdown artifact and a `ds-lite.review-result.v1` JSON sidecar. The sidecar binds the review node, reviewed experiment node, work unit, profile, typed evidence refs, validator, evidence digest, review channels, limitations, and completion time.

- `verdict` is exactly `pass`, `fail`, or `needs-human` and controls the review gate.
- `claim_assessment` is independently `none`, `inconclusive`, `refuted`, or `supportable` and describes claim readiness.
- A review counts as `reviewed` only when the review node is done, the sidecar validates, all identities and refs match, and the evidence digest still matches.
- An active review, an empty artifact, or Markdown alone never upgrades evidence strength.
- Unknown fields are rejected outside `extensions`; sensitive keys, hidden reasoning, path escapes, and conflicting ids are rejected everywhere.

## Route Semantics

- Progression routes use only `next`, `branch`, and `supersedes`.
- `supports` and `blocks` express evidence or dependencies; `rollback` records a return but does not redefine the root-to-active progression route.
- `trace` defaults to progression mode. Use `trace --mode all` only when every relationship should be considered.
- Use `validate --strict --scope active-route` to gate the current route. Structural errors remain global, while warnings from preserved alternative branches are reported under `off_route_warnings`. Default `validate --strict` still gates every branch.

## Mission Board Projection

- `mission --format json|markdown` derives a user-visible task board from the current graph, linked evidence, validation results, branch queue, rollback targets, blockers, readiness rules, and metric surfaces.
- `render-status` writes the same projection to `STATUS.md`; it does not change the graph schema or revision.
- A user should be able to open `STATUS.md` and understand the active node, latest result, next action, evidence strength, whether user input is needed, and where rollback is possible.
- `claim_readiness` is `none`, `blocked`, `inconclusive`, `refuted`, or `supportable`. `evidence_detail` exposes the work unit/profile, validated and negative evidence counts, typed review count, latest refs, and blocking reasons.
- `waiting_for_user` is scoped to the active route, active-route blocker edges, a typed `needs-human` review, or a blocked work unit. Off-route blocked nodes and warnings stay visible without unconditionally stopping the current route.

## Migration And Writes

- Graph v1 remains readable. The first write migrates it to v2 and preserves `graph.v1.<timestamp>.json`.
- A v1 graph containing project-external absolute paths requires `migrate --external-map alias=ROOT` before mutation.
- Writes use a cross-platform lock, revision check, semantic validation, and atomic replacement. `RESEARCH_MAP.md` records the committed revision and can be rebuilt with `render-map`.
