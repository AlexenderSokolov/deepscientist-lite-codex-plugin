---
name: nature-review
description: Complete review workflow: simulate Nature-style reviewer assessment from referee perspective, and draft/audit/revise Nature-style revision correspondence packages. Routes to reviewer or response based on user intent.
---

# Nature Review

This skill aggregates two upstream workflows into one routed entry point:

1. **reviewer** — Simulate a Nature-style reviewer assessment from the referee perspective. Return 3 reviewer reports plus a cross-review synthesis, grounded only in the local Nature reviewer source basis.
2. **response** — Draft, audit, or revise Nature-style revision correspondence packages. Point-by-point reviewer response letters, rebuttal letters, revision cover letters, LaTeX cover/response templates, and red-marked revised-manuscript excerpts.

## Routing

Before acting, run `python <academic-plugin>/scripts/ds_lite_pack_doctor.py --core-root <core-plugin>`, then run `python <academic-plugin>/scripts/ds_lite_nature_setup.py doctor --workspace .`.

Read [responsible-exploration-covenant.md](../../references/responsible-exploration-covenant.md) first.

### Route Selection

| User intent | Route | Original skill |
| --- | --- | --- |
| "审稿模拟"、"预审稿"、"reviewer report" | reviewer | nature-reviewer |
| "修回信"、"回复审稿人"、"rebuttal" | response | nature-response |

### Workflow

1. Read `PROJECT.md`, `STATUS.md`, `RESEARCH_MAP.md`, `research/work-unit.json`, and the active node from `research/state/graph.json`.
2. Determine which sub-route the user's request maps to.
3. Execute the upstream workflow for that sub-route, preserving all original routing, static fragments, references, scripts, templates, and tests.
4. Record only redacted status and relative evidence references.
5. Send the mandatory Start report before work, use Progress reports during long work, and finish with the mandatory End report.

### Quality Bar

- Reviewer reports must be grounded in the manuscript text, not fabricated.
- Response letters must address each reviewer comment point-by-point.
- Red-marked revisions must preserve the original meaning while incorporating changes.
- If evidence is insufficient, mark the node `blocked` and name the missing input.

## State Rules

- Every graph mutation must use `ds_lite_state.py`; never edit `graph.json` directly.
- Pass `--expected-revision` on every write. On exit code 4, reload the graph, preserve both sessions' evidence, and retry from the new revision.

---

*This skill preserves the complete upstream workflows at commit `91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b`. The two original skills (nature-reviewer, nature-response) remain available as sub-routes within this aggregated entry point.*
