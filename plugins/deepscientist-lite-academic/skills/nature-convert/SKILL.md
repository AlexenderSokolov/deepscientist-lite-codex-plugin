---
name: nature-convert
description: Convert scientific papers to other formats: paper to presentation slides, or paper to patent application. Routes to paper2ppt or paper-to-patent based on user intent.
---

# Nature Convert

This skill aggregates two upstream workflows into one routed entry point:

1. **paper2ppt** — Convert a paper into a presentation. Extract key points, figures, and tables; generate a structured slide deck.
2. **paper-to-patent** — Convert a scientific paper into a patent application. Extract novel claims, prior art, and technical descriptions; structure into patent application format.

## Routing

Before acting, run `python <academic-plugin>/scripts/ds_lite_pack_doctor.py --core-root <core-plugin>`, then run `python <academic-plugin>/scripts/ds_lite_nature_setup.py doctor --workspace .`.

Read [responsible-exploration-covenant.md](../../references/responsible-exploration-covenant.md) first.

### Route Selection

| User intent | Route | Original skill |
| --- | --- | --- |
| "论文转PPT"、"转演示文稿"、"paper to slides" | paper2ppt | nature-paper2ppt |
| "论文转专利"、"转专利申请"、"paper to patent" | paper-to-patent | nature-paper-to-patent |

### Workflow

1. Read `PROJECT.md`, `STATUS.md`, `RESEARCH_MAP.md`, `research/work-unit.json`, and the active node from `research/state/graph.json`.
2. Determine which sub-route the user's request maps to.
3. Execute the upstream workflow for that sub-route, preserving all original routing, static fragments, references, scripts, templates, and tests.
4. Record only redacted status and relative evidence references.
5. Send the mandatory Start report before work, use Progress reports during long work, and finish with the mandatory End report.

### Quality Bar

- Converted outputs must preserve the original paper's key claims and evidence.
- Patent applications must clearly distinguish novel claims from prior art.
- Presentation slides must accurately represent the paper's findings.
- If evidence is insufficient, mark the node `blocked` and name the missing input.

## State Rules

- Every graph mutation must use `ds_lite_state.py`; never edit `graph.json` directly.
- Pass `--expected-revision` on every write. On exit code 4, reload the graph, preserve both sessions' evidence, and retry from the new revision.

---

*This skill preserves the complete upstream workflows at commit `91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b`. The two original skills (nature-paper2ppt, nature-paper-to-patent) remain available as sub-routes within this aggregated entry point.*
