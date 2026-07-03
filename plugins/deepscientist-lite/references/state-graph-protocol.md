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

## Evidence Pack v1

- `contract.json` declares command, inputs, metrics, thresholds, seeds, budget, expected outputs, and failure interpretation before execution.
- `manifest.json` records execution status, logs, metrics, sanitized environment metadata, output paths, sizes, hashes, and verification results.
- Project-local files require SHA-256. External files are only hashed when explicitly requested.
- Verification failure blocks a done experiment; a failed process may still be valid evidence when its pack is intact.
- Review is a separate workflow and artifact, not a guarantee of separate-model or infrastructure isolation.

## Route Semantics

- Progression routes use only `next`, `branch`, and `supersedes`.
- `supports` and `blocks` express evidence or dependencies; `rollback` records a return but does not redefine the root-to-active progression route.
- `trace` defaults to progression mode. Use `trace --mode all` only when every relationship should be considered.

## Migration And Writes

- Graph v1 remains readable. The first write migrates it to v2 and preserves `graph.v1.<timestamp>.json`.
- A v1 graph containing project-external absolute paths requires `migrate --external-map alias=ROOT` before mutation.
- Writes use a cross-platform lock, revision check, semantic validation, and atomic replacement. `RESEARCH_MAP.md` records the committed revision and can be rebuilt with `render-map`.
