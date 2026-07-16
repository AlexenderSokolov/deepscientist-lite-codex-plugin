---
name: ds-lite-analysis-write
description: Use when Codex should analyze DS Lite experiment evidence, compare early and final metrics, consolidate claims, limitations, confidence, missing checks, mathematical notes, summaries, paper sections, or final handoffs without inventing unsupported results.
---

# DS Lite Analysis And Write

Analysis and writing translate artifacts into claims. Treat unsupported claims as blockers, not prose problems.

## Workflow

1. Read the latest direct `review` predecessor, its Markdown artifact, typed review result, linked Evidence Pack, latest `RESEARCH_MAP.md`, `STATUS.md`, and result files.
2. If no valid typed review result exists, route the experiment to `$ds-lite-review`. If `verdict` is `fail` or `needs-human`, do not promote the claim or create an active analysis/write node; record only the limitation and required follow-up. A passing gate permits evidence analysis, but only `claim_assessment=supportable` permits a supporting claim; `inconclusive` and `refuted` remain valid negative analyses.
3. For a passing review, build a claim table: claim, supporting artifact, metric or observation, review lane, limitation, confidence, and missing check.
4. Separate early-budget behavior, final-budget behavior, and aggregate metrics such as AUC when they can disagree.
5. Write the main analysis narrative in this order: hypothesis -> change -> result -> tradeoff -> next candidate -> claim status.
6. For theoretical or mathematical exploration, read `../../references/math-exploration-template.md` and keep assumptions explicit.
7. If reviewed evidence is sufficient, write `research/artifacts/analysis-<slug>.md`, `math-<slug>.md`, or `paper-<slug>.md`.
8. Read the current revision, add an `analysis`, `write`, or `finalize` node directly from the passing review node, and link every supporting artifact, manifest, and review path. Pass `--expected-revision` on each state write.
9. Update `PROJECT.md` only with durable conclusions, adopted workflow changes, or important rejected assumptions.
10. Run `render-status` so `STATUS.md` shows remaining checks or marks the project ready for handoff.
11. Before handoff, run state `validate --strict --scope active-route`. Report `off_route_warnings` as preserved branch debt; do not delete failed branches to make the gate green.

## Writing Rules

- Do not upgrade weak evidence into strong claims.
- Treat review failure or unresolved human checks as workflow blockers, not prose caveats.
- Preserve negative results and partial successes.
- Include parent line, promotion status, rollback target, and supersede reason when explaining why one branch replaces or defers another.
- Keep final summaries source-grounded: every major claim should point to an artifact, run command, figure, or data path.
- When metrics conflict, state the tradeoff instead of forcing a winner.
- Use `../../references/teaching-guide.zh.md` when preparing a teaching explanation for a senior student or lab demo.
- Use `update-node` and `set-status` for revisions; never edit `graph.json` directly. On exit code 4, reload and reconcile before retrying.

## Handoff

End with the final claim status, artifact paths, active/final node id, known limitations, and the next defensible action.
