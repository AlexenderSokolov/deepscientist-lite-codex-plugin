# AIResearch Case Study: Tree Search vs Optimization Frontier

This case study shows how DeepScientist Lite can drive a real research loop without running the full DeepScientist daemon.

## Project Question

Compare two agentic research paradigms:

- tree-style exploration, represented by AI Scientist v2 style `Node` / `Journal` search;
- durable optimization-frontier management, represented by DeepScientist-style candidate and artifact tracking;
- hybrid Tree-BO policies that use structure-level search plus within-structure parameter optimization.

## DS Lite Role

DS Lite did not provide a model runner or a daemon. Its contribution was research-state discipline:

- `PROJECT.md` kept durable project memory;
- `STATUS.md` exposed the active node and next action;
- `research/state/graph.json` stored the adjacency-list route;
- `RESEARCH_MAP.md` rendered the human-readable route;
- `research/artifacts/*.md` preserved ideas, experiments, negative evidence, and claims.

## Route Summary

The active route reached:

1. intake of the existing AIResearch project;
2. source-code scout of AI Scientist v2 and DeepScientist mechanisms;
3. hybrid Tree-BO idea selection;
4. CPU/GPU proxy baseline audits;
5. fusion-policy v2 experiments;
6. mathematical regret decomposition;
7. hybrid Tree-BO v3 experiments.

## Main Evidence Pattern

The experiments found that a hybrid policy can improve some budget regimes, but the key problem is budget allocation rather than the word "hybrid" itself.

- v2 improved GPU-light normalized regret AUC and CPU old-hybrid AUC, but weakened CPU final convergence.
- v3 added a fixed late exploitation switch. It slightly repaired final convergence relative to v2, and reached zero final regret on GPU-light, but worsened AUC against v2.
- The next defensible idea is v4: confidence-gap or plateau-triggered switching rather than a fixed half-budget switch.

## Teaching Use

Use this case when explaining why automated research needs state management. A chat transcript can propose many ideas, but a research system needs a recoverable route: what was tried, which evidence supported it, which results were negative, and why the next branch is justified.

## Boundary

This is not full DeepScientist. It has no daemon, no Web/TUI, no MCP artifact service, no automatic runner registry, and no long-running scheduler. It is a lightweight Codex plugin that teaches the core protocol before introducing the full platform.
