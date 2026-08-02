---
name: ds-lite-analysis-write
description: Use when reviewed research or engineering evidence must become bounded claims, limitations, negative results, confidence notes, mathematical analysis, summaries, reports, paper sections, or a recoverable final handoff.
---

# DS Lite Analysis And Write

Communication boundary: 保护内容必须原样保留；不得改写用户约束或证据限定。

Analysis and writing translate artifacts into claims. Treat unsupported claims as blockers, not prose problems.

Before acting, read [the Responsible Exploration Covenant](../../references/responsible-exploration-covenant.md) and use the shared start / progress / end protocol. Send the mandatory Start report before analysis or writing, use Progress reports during long work, and finish with the mandatory End report; missing evidence becomes `blocked` or `not-verified`, never polished success prose.

## Writing And Polishing Router

Choose the route before editing prose:

- For a reviewed experiment, claim-bearing analysis, conclusion, paper section, or final handoff, use the evidence workflow below. Pure polishing requests do not bypass the typed review gate, and polishing never promotes evidence strength.
- For an existing manuscript paragraph or section whose facts and citation intent are already supplied, capability-discover `$nature-polishing` and load the Academic package workflow when it is installed. Detect paper type, section, language, and journal from its manifest; repair structural problems before sentence-level style, and preserve claims, numbers, uncertainty, terminology, and citation intent. If Academic is unavailable, use the Core evidence-preserving fallback and report that the Nature route was not observed.
- For drafting a new manuscript argument or initial-submission package rather than revising existing prose, capability-discover `$nature-writing`; post-decision correspondence belongs to `$nature-response`. Both are optional Academic routes and must not be treated as Core dependencies.

The polishing route must still emit the DS Lite start / progress / end reports. Its artifact records the original text, polished text, structural changes, unresolved evidence or logic problems, and a relative source/output reference. If the requested wording would conceal missing evidence or change a claim, stop and report the conflict instead of polishing it away.

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

## Communication and Learning Gate

Before a non-trivial action, read `../../references/communication/core.md` and `../../references/communication/self-audit.md`; read the project `STYLE.md` when present.
Complete Phase 1 before the first side effect. Preserve protected content, report observable evidence, and finish with a readable Handoff.
When this skill is selected, run the learning receipt check for its declared tutorial set before the first write, command, or network request. A stale or missing receipt is a blocker; the learning helper itself is the only exception.
