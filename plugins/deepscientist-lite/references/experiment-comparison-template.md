# Experiment Comparison Template

Use this template when a DS Lite experiment compares methods, policies, prompts, models, or search strategies.

## Hypothesis

State the expected difference and why it should appear.

Record the parent line this experiment extends or challenges.

## Baselines

List the old method, random/control method, and strongest known comparator.

## Metrics

Record primary and secondary metrics. If budget matters, separate:

- early-budget metric
- final-budget metric
- aggregate metric such as normalized AUC

For every metric, write the direction (`max`, `min`, `target`, or `observe`) and the reason this direction matches the research question.

## Run Contract

Create a `ds-lite.experiment-contract.v1` JSON file before execution. Record commands, inputs, metrics and thresholds, seeds, early/final budget, budget cap, output paths, sanitized environment metadata, and failure interpretation.

## Evidence Pack

Link the finalized `research/evidence/<run-id>/manifest.json`, strict verification result, stdout/stderr, metrics, and output hashes.

## Results

Summarize metrics in prose and point to raw result files.

## Failure Interpretation

Say what it means if the experiment fails, partially succeeds, or only improves one metric surface.

If a metric direction or aggregate definition was wrong, mark the correction as protocol-breaking and state which old claims are blocked, superseded, or rolled back.

## Route Decision

Record promotion status, rollback target, supersede reason, and the next candidate. A useful comparison can say "v2 has better AUC but weaker final behavior" or "v3 has better final behavior but worse AUC" without forcing a premature winner.

## Next Action

Route the experiment through `$ds-lite-review`, then choose exactly one: analyze, revise, rollback, branch, run stronger validation, or stop.
