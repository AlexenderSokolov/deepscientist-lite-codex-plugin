# Experiment Comparison Template

Use this template when a DS Lite experiment compares methods, policies, prompts, models, or search strategies.

## Hypothesis

State the expected difference and why it should appear.

## Baselines

List the old method, random/control method, and strongest known comparator.

## Metrics

Record primary and secondary metrics. If budget matters, separate:

- early-budget metric
- final-budget metric
- aggregate metric such as normalized AUC

## Run Contract

Create a `ds-lite.experiment-contract.v1` JSON file before execution. Record commands, inputs, metrics and thresholds, seeds, budgets, output paths, sanitized environment metadata, and failure interpretation.

## Evidence Pack

Link the finalized `research/evidence/<run-id>/manifest.json`, strict verification result, stdout/stderr, metrics, and output hashes.

## Results

Summarize metrics in prose and point to raw result files.

## Failure Interpretation

Say what it means if the experiment fails, partially succeeds, or only improves one metric surface.

## Next Action

Route the experiment through `$ds-lite-review`, then choose exactly one: analyze, revise, rollback, branch, run stronger validation, or stop.
