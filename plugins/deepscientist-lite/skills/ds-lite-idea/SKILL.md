---
name: ds-lite-idea
description: Use when Codex should generate, compare, and select 2-3 lightweight research ideas or hypotheses from DS Lite scout evidence, then record candidate branches, a chosen route, and validation criteria in the Research Map.
---

# DS Lite Idea

Idea work turns scout evidence into a small decision, not a brainstorm dump. Keep each candidate testable and traceable.

## Workflow

1. Read the latest scout artifact, `PROJECT.md`, `STATUS.md`, and the active graph node.
2. Produce 2-3 candidate directions. For each, state: hypothesis, novelty lever, minimum experiment, expected signal, cost, and risk.
3. Select one route for immediate validation. Explain why the rejected candidates are deferred, not forgotten.
4. Write `research/artifacts/idea-<slug>.md` with the candidate table, selected route, acceptance target, and rollback condition.
5. Add branch nodes for meaningful candidates when they may be revisited. Mark the selected node `active`; mark deferred nodes `proposed` or `superseded`.
6. Update `STATUS.md` with the next experiment command or implementation checkpoint.

## State Pattern

- Use `branch` edges for real alternatives.
- Use `supersedes` only when evidence invalidates an older idea.
- Use `rollback` when returning to a prior viable node after a failed experiment.
- Link the idea artifact to every candidate node it explains.

## Output

End with the chosen idea, why it is the cheapest useful test, the artifact path, active node id, and the first experiment to run.
