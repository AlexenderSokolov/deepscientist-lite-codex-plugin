---
name: ds-lite-idea
description: Use when Codex should generate, compare, and select 2-3 lightweight research ideas or hypotheses from DS Lite scout evidence, then record candidate branches, a chosen route, and validation criteria in the Research Map.
---

# DS Lite Idea

Idea work turns scout evidence into a small decision, not a brainstorm dump. Keep each candidate testable and traceable.

## Workflow

1. Read the latest scout artifact, `PROJECT.md`, `STATUS.md`, `research/work-unit.json`, and the active graph node. Idea selection remains `planning`; an idea artifact or any non-empty path is not typed claim evidence.
2. Produce 2-3 candidate directions. For each, state: mechanism hypothesis, closest known alternative, minimum experiment, expected signal, cost, risk, and the evidence needed to change the decision.
3. Read [the Scientific Factor Card protocol](../../references/scientific-factor-card-protocol.md). Create `research/artifacts/factor-card-<slug>.json` for each candidate that enters the comparison. Assess `novelty`, `feasibility`, `evidence_strength`, `cost`, `risk`, and `alignment`; use unknown rather than invented scores, and use no weighted total. Cost and risk scores record burden, not desirability.
4. Validate every card with `ds_lite_protocol.py validate-factor-card --path <card>`. Novelty without source refs remains unknown. A Factor Card is a decision artifact, not typed claim evidence, and must never upgrade Mission Board evidence strength.
5. Select one route for immediate validation. Use `explore`, `verify-first`, `park`, `reject`, or `needs-human`; explain why other candidates are preserved and name the smallest test that could change the selection.
6. Write `research/artifacts/idea-<slug>.md` with the candidate table, Factor Card refs, selected route, parent line, promotion status, acceptance target, rollback target, and supersede reason if it replaces an older idea.
7. Read the current revision, add branch nodes for meaningful candidates, link each valid Factor Card as an artifact, and use `set-active` or `set-status` to select and defer routes. Pass `--expected-revision` on each write and refresh it after success.
8. Run `render-status` so `STATUS.md` shows the next experiment command or implementation checkpoint.

## State Pattern

- Use `branch` edges for real alternatives.
- Use `supersedes` only when evidence invalidates an older idea.
- Use `rollback` when returning to a prior viable node after a failed experiment.
- Record whether each candidate is `proposed`, `promoted`, `deferred`, `superseded`, or `abandoned`; do not let a created idea line masquerade as experimental progress.
- Link the idea artifact to every candidate node it explains.
- Use `link-path --type artifact` and `update-node` for changes. Never edit `graph.json` directly; reload and reconcile on exit code 4.

## Output

End with the chosen idea, its Factor Card decision and uncertainty, why it is the cheapest useful test, the artifact/card paths, active node id, and the first experiment to run.
