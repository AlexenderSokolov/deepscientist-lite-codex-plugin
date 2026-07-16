---
name: ds-lite-idea
description: Use when Codex should generate, compare, and select 2-3 lightweight research ideas or hypotheses from DS Lite scout evidence, then record candidate branches, a chosen route, and validation criteria in the Research Map.
---

# DS Lite Idea

Idea work turns scout evidence into a small decision, not a brainstorm dump. Keep each candidate testable and traceable.

## Workflow

1. Read the latest scout artifact, `PROJECT.md`, `STATUS.md`, `research/work-unit.json`, and the active graph node. Idea selection remains `planning`; an idea artifact or any non-empty path is not typed claim evidence.
2. Produce 2-3 candidate directions. For each, state: hypothesis, novelty lever, minimum experiment, expected signal, cost, and risk.
3. Select one route for immediate validation. Explain why the rejected candidates are deferred, not forgotten.
4. Write `research/artifacts/idea-<slug>.md` with the candidate table, selected route, parent line, promotion status, acceptance target, rollback target, and supersede reason if it replaces an older idea.
5. Read the current revision, add branch nodes for meaningful candidates, and use `set-active` or `set-status` to select and defer routes. Pass `--expected-revision` on each write and refresh it after success.
6. Run `render-status` so `STATUS.md` shows the next experiment command or implementation checkpoint.

## State Pattern

- Use `branch` edges for real alternatives.
- Use `supersedes` only when evidence invalidates an older idea.
- Use `rollback` when returning to a prior viable node after a failed experiment.
- Record whether each candidate is `proposed`, `promoted`, `deferred`, `superseded`, or `abandoned`; do not let a created idea line masquerade as experimental progress.
- Link the idea artifact to every candidate node it explains.
- Use `link-path --type artifact` and `update-node` for changes. Never edit `graph.json` directly; reload and reconcile on exit code 4.

## Output

End with the chosen idea, why it is the cheapest useful test, the artifact path, active node id, and the first experiment to run.
