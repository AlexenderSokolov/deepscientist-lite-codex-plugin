---
name: ds-lite-analysis-write
description: Use when Codex should analyze DS Lite experiment evidence, compare early and final metrics, consolidate claims, limitations, confidence, missing checks, mathematical notes, summaries, paper sections, or final handoffs without inventing unsupported results.
---

# DS Lite Analysis And Write

Analysis and writing translate artifacts into claims. Treat unsupported claims as blockers, not prose problems.

## Workflow

1. Read linked experiment artifacts, latest `RESEARCH_MAP.md`, `STATUS.md`, and result files.
2. Build a claim table: claim, supporting artifact, metric or observation, limitation, confidence, and missing check.
3. Separate early-budget behavior, final-budget behavior, and aggregate metrics such as AUC when they can disagree.
4. For theoretical or mathematical exploration, read `../../references/math-exploration-template.md` and keep assumptions explicit.
5. If evidence is sufficient, write `research/artifacts/analysis-<slug>.md`, `math-<slug>.md`, or `paper-<slug>.md`.
6. Read the current revision, add an `analysis`, `write`, or `finalize` node from the active node, and link every supporting path with `link-path`. Pass `--expected-revision` on each state write.
7. Update `PROJECT.md` only with durable conclusions, adopted workflow changes, or important rejected assumptions.
8. Update `STATUS.md` with remaining checks or mark the project ready for handoff.

## Writing Rules

- Do not upgrade weak evidence into strong claims.
- Preserve negative results and partial successes.
- Keep final summaries source-grounded: every major claim should point to an artifact, run command, figure, or data path.
- When metrics conflict, state the tradeoff instead of forcing a winner.
- Use `../../references/teaching-guide.zh.md` when preparing a teaching explanation for a senior student or lab demo.
- Use `update-node` and `set-status` for revisions; never edit `graph.json` directly. On exit code 4, reload and reconcile before retrying.

## Handoff

End with the final claim status, artifact paths, active/final node id, known limitations, and the next defensible action.
