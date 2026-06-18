---
name: ds-lite-analysis-write
description: Use when Codex should analyze DS Lite experiment evidence, consolidate claims and limitations, write summaries or paper sections, finalize the research map, and produce a clear handoff without inventing unsupported results.
---

# DS Lite Analysis And Write

Analysis and writing translate artifacts into claims. Treat unsupported claims as blockers, not prose problems.

## Workflow

1. Read linked experiment artifacts, latest `RESEARCH_MAP.md`, `STATUS.md`, and any result files.
2. Build a claim table: claim, supporting artifact, metric or observation, limitation, confidence, and missing check.
3. If evidence is sufficient, write `research/artifacts/analysis-<slug>.md` or `research/artifacts/paper-<slug>.md`.
4. Add an `analysis`, `write`, or `finalize` node from the active node. Link every artifact that supports the claim.
5. Update `PROJECT.md` only with durable conclusions, adopted workflow changes, or important rejected assumptions.
6. Update `STATUS.md` with remaining checks or mark the project ready for handoff.

## Writing Rules

- Do not upgrade weak evidence into strong claims.
- Preserve negative results and limitations.
- Keep final summaries source-grounded: every major claim should point to an artifact, run command, figure, or data path.
- Use `../../references/teaching-guide.zh.md` when preparing a teaching explanation for a senior student or lab demo.

## Handoff

End with the final claim status, artifact paths, active/final node id, known limitations, and the next defensible action.
