---
name: ds-lite-empirical
description: Specify, execute, diagnose, or review a bounded empirical research task. Use for estimands, samples, variables, causal identification, regression assumptions, missing data, clustered standard errors, difference-in-differences pretrends, robustness checks, null or negative results, and table or figure handoffs. Do not equate statistical significance with a research conclusion or assume R, Stata, StatsPAI, or Python is installed.
---

# DS Lite Empirical

Use this pack only with a DeepScientist Lite Core that satisfies this package's `compatibility.json`. Before acting, run `python <empirical-plugin>/scripts/ds_lite_empirical.py doctor --core-root <core-plugin>`. A missing or incompatible Core is `blocked`.

## Route

1. Read the Core work unit, Graph, authorization, and Evidence Pack boundary.
2. Write a `ds-lite.empirical-spec.v1` before analysis. Name the research question, estimand, population, sample rules, variables, identification strategy, assumptions, diagnostics, robustness plan, data references, and actually observed backend.
3. Inspect capabilities. Python is the reproducibility reference when observed; StatsPAI may be compared as a reference workflow. R and Stata remain `not-observed` until their commands are discovered. Never install a runtime or download data without approval.
4. Execute one bounded work unit. Preserve confounding warnings, failed parallel-trend tests, missingness, standard-error choices, robustness disagreement, and zero or negative results.
5. Write `ds-lite.empirical-result.v1`. It must cite a Core Evidence Pack and project-relative commands/artifacts; it does not create a second data store.
6. Stop at a checkpoint. Report what the evidence supports, what it does not support, and one next action.

Do not treat a p-value as proof of a theory, optimize specifications only for significance, hide failed diagnostics, or silently reinterpret the estimand after seeing results.

Load [protocol.md](../../references/protocol.md) when creating or validating the two envelopes.
