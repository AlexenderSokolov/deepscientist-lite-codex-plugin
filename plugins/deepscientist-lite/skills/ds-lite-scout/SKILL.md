---
name: ds-lite-scout
description: Use when Codex should clarify a DS Lite research question, scout literature, datasets, benchmarks, baselines, metrics, risks, and feasibility, then record a scout artifact and Research Map node without running the full DeepScientist platform.
---

# DS Lite Scout

Scout narrows a vague research direction into a verifiable route. It should leave a compact artifact and a graph node that later idea and experiment work can trust.

## Workflow

1. Read `PROJECT.md`, `STATUS.md`, `RESEARCH_MAP.md`, and the active node from `research/state/graph.json`.
2. Clarify the task into: research question, target claim, expected evidence, available data/code, baseline, metric, and first failure mode.
3. Search or inspect only what is needed. For current papers, benchmarks, libraries, or datasets, verify with primary or official sources where possible.
4. Write `research/artifacts/scout-<slug>.md` with facts, citations or source paths, candidate baselines, metrics, feasibility, and unknowns.
5. Add a `scout` node from the active node:
   `python ../../scripts/ds_lite_state.py add-node --root <project> --kind scout --parent <active> --relation next --title "<title>" --summary "<summary>" --artifact-path research/artifacts/scout-<slug>.md --active --render`
6. Update `STATUS.md` with the selected next stage, usually `idea` or `experiment`.

## Quality Bar

- Separate confirmed facts from assumptions.
- Prefer one strong baseline path over a long undigested list.
- Record why a benchmark or metric is appropriate for the project goal.
- If evidence is insufficient, mark the node `blocked` and name the missing input.
