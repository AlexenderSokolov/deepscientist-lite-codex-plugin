---
name: nature-literature
description: Complete literature workflow: multi-source search, citation verification, strict independent other-citation audits, article-level citation metric tables, influential citer profiling, citation file management, reference management, and reference verification. Routes to search, citation, or ref-verifier based on user intent.
---

# Nature Literature

This skill aggregates three upstream workflows into one routed entry point:

1. **search** — Multi-source literature search via PubMed, CrossRef, arXiv, Scopus, ScienceDirect. Includes MeSH search, citation metric tables, influential citer profiling, and citation file management (.nbib/.ris/.bib conversion).
2. **citation** — Add strict Nature/CNS citations to manuscript text. Splits long passages into citable segments, searches accepted flagship and subjournal titles, exports reference-manager-ready output.
3. **ref-verifier** — Verify references against multiple sources. Checks author, title, year, volume, page; flags DOI year conflicts, author order anomalies, page number deviations. Supports Zotero sync.

## Routing

Before acting, run `python <academic-plugin>/scripts/ds_lite_pack_doctor.py --core-root <core-plugin>`, then run `python <academic-plugin>/scripts/ds_lite_nature_setup.py doctor --workspace .`.

Read [responsible-exploration-covenant.md](../../references/responsible-exploration-covenant.md) first.

### Route Selection

| User intent | Route | Original skill |
| --- | --- | --- |
| "找文献"、"搜论文"、"检索" | search | nature-academic-search |
| "添加引用"、"分段引用"、"找引用" | citation | nature-citation |
| "验证参考文献"、"检查引用"、"交叉验证" | ref-verifier | nature-ref-verifier |

### Workflow

1. Read `PROJECT.md`, `STATUS.md`, `RESEARCH_MAP.md`, `research/work-unit.json`, and the active node from `research/state/graph.json`.
2. Determine which sub-route the user's request maps to.
3. Execute the upstream workflow for that sub-route, preserving all original routing, static fragments, references, scripts, templates, and tests.
4. Record only redacted status and relative evidence references. Missing dependencies are `not-observed` or `blocked`, never silently treated as available.
5. Send the mandatory Start report before work, use Progress reports during long work, and finish with the mandatory End report.

### Quality Bar

- Separate confirmed facts from assumptions.
- Prefer primary or official sources over secondary citations.
- Record citation chains and verification results as structured artifacts.
- If evidence is insufficient, mark the node `blocked` and name the missing input.

## State Rules

- Every graph mutation must use `ds_lite_state.py`; never edit `graph.json` directly.
- Pass `--expected-revision` on every write. On exit code 4, reload the graph, preserve both sessions' evidence, and retry from the new revision.

---

*This skill preserves the complete upstream workflows at commit `91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b`. The three original skills (nature-academic-search, nature-citation, nature-ref-verifier) remain available as sub-routes within this aggregated entry point.*
