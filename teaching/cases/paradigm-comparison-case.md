# Teaching Case: Tree Search vs Optimization Frontier

This case study shows how a durable research-frontier system Lite can drive a real research loop without running the full a durable research-frontier system daemon.

## Project Question

Compare two agentic research paradigms:

- tree-style exploration, represented by a tree-search research agent style `Node` / `Journal` search;
- durable optimization-frontier management, represented by a durable research-frontier system-style candidate and artifact tracking;
- hybrid Tree-BO policies that use structure-level search plus within-structure parameter optimization.

## DeepScientist Lite Role

DeepScientist Lite did not provide a model runner or a daemon. Its contribution was research-state discipline:

- `PROJECT.md` kept durable project memory;
- `STATUS.md` exposed the active node and next action;
- `research/state/graph.json` stored the adjacency-list route;
- `RESEARCH_MAP.md` rendered the human-readable route;
- `research/artifacts/*.md` preserved ideas, experiments, negative evidence, and claims.

## Route Summary

The active route reached:

1. intake of the existing the paradigm-comparison teaching project project;
2. source-code scout of a tree-search research agent and a durable research-frontier system mechanisms;
3. hybrid Tree-BO idea selection;
4. CPU/GPU proxy baseline audits;
5. fusion-policy v2 experiments;
6. mathematical regret decomposition;
7. hybrid Tree-BO v3 experiments.

## Main Evidence Pattern

The experiments are used here as a teaching case. They show that DeepScientist Lite can preserve a nuanced research route: a hybrid policy can improve some budget regimes, but the key scientific issue is budget allocation rather than the word "hybrid" itself.

- v2 improved GPU-light normalized regret AUC and CPU old-hybrid AUC, but weakened CPU final convergence.
- v3 added a fixed late exploitation switch. It slightly repaired final convergence relative to v2, and reached zero final regret on GPU-light, but worsened AUC against v2.
- A possible next teaching branch is v4: confidence-gap or plateau-triggered switching rather than a fixed half-budget switch. This is a case-study continuation, not a plugin release requirement.

## Teaching Use

Use this case when explaining why automated research needs state management. The goal is to teach traceable research workflow, not to claim that the plugin itself is an optimization algorithm. A chat transcript can propose many ideas, but a research system needs a recoverable route: what was tried, which evidence supported it, which results were negative, and why the next branch is justified.

## Boundary

This is not full a durable research-frontier system. It has no daemon, no Web/TUI, no MCP artifact service, no automatic runner registry, and no long-running scheduler. It is a lightweight Codex plugin that teaches the core protocol before introducing the full platform.
