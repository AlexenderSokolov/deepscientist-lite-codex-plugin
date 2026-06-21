# Teaching Case: Tree Search vs Optimization Frontier

This case is a teaching example for DeepScientist Lite. It shows how the plugin records a research route with ideas, experiments, negative evidence, and follow-up questions. It is not a benchmark claim for the plugin itself.

## Question

The case compares three research-search patterns:

- tree-style exploration, where a project grows through parent-child attempts;
- optimization-frontier management, where candidate routes and evidence are kept as durable artifacts;
- hybrid Tree-BO policies, where a discrete structure line is chosen first and a parameter search happens inside that line.

## What DeepScientist Lite Demonstrates

DeepScientist Lite does not run the experiment and does not provide a model runner. Its role is to keep the process traceable:

- `PROJECT.md` stores durable project memory;
- `STATUS.md` keeps the active node and next action visible;
- `research/state/graph.json` stores the route as an adjacency-list graph;
- `RESEARCH_MAP.md` renders that route for humans;
- `research/artifacts/*.md` keeps ideas, experiments, analysis, and negative results.

## Example Route

A compact route for teaching can look like this:

1. intake an existing research project;
2. audit source mechanisms and baseline evidence;
3. choose a hybrid Tree-BO idea;
4. record CPU/GPU proxy results;
5. write a math note for regret decomposition;
6. preserve a partial success and a negative result;
7. explain the next branch without overwriting the old route.

## Main Lesson

The useful teaching point is not “hybrid wins.” The useful point is that research often produces mixed evidence: one variant may improve early-budget behavior while hurting final convergence. DeepScientist Lite keeps that nuance visible instead of flattening it into a single success/failure label.

## How To Use This Case

Use this case when explaining why automated research needs state management. A chat transcript can contain many ideas, but a research workflow needs recoverable files: what was tried, what evidence supported it, what failed, and why the next branch is justified.

## Boundary

This case is not part of the runtime plugin package. It lives in `teaching/` so users can study the workflow without confusing the case with plugin functionality.
