# DS Lite State Graph Protocol

`research/state/graph.json` is the machine-readable source of truth. `RESEARCH_MAP.md` is a rendered projection for humans.

## Graph Shape

```json
{
  "schema_version": "ds-lite.graph.v1",
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
- `kind`: `intake`, `scout`, `idea`, `experiment`, `analysis`, `write`, `decision`, or `finalize`
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
- Keep paths project-relative.
- Render `RESEARCH_MAP.md` after graph edits.

