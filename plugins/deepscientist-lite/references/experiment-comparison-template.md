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

Record commands, seeds, budgets, output directory, environment, and expected files.

## Results

Summarize metrics in prose and point to raw result files.

## Failure Interpretation

Say what it means if the experiment fails, partially succeeds, or only improves one metric surface.

## Next Action

Choose exactly one: exploit, revise, rollback, branch, run stronger validation, or stop.
