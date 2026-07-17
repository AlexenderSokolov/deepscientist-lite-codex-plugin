# Scientific Factor Card Protocol

Use `ds-lite.factor-card.v1` to compare a small set of research or engineering ideas before spending a larger evidence budget. A card records an assessment and the evidence used to make it; the card does not become evidence merely because it is complete or highly scored.

## Boundary

- The card is a decision artifact, not a claim validator, paper review, experiment result, or automatic truth score.
- Keep the six factors fixed: `novelty`, `feasibility`, `evidence_strength`, `cost`, `risk`, and `alignment`.
- Record every factor exactly once. Use `score=null` and `confidence=unknown` when the factor has not been checked.
- Use scores from 0 to 4. Higher novelty, feasibility, evidence strength, and alignment are favorable. Higher cost and risk mean a larger burden. There is no weighted total and no automatic winner.
- Every non-null score needs at least one project-relative or `external://` evidence ref. A Factor Card cannot cite itself as support.
- Do not store hidden reasoning, complete environments, credentials, tokens, secrets, or workstation absolute roots.
- Put forward-compatible data only under `extensions`; unknown fields elsewhere fail validation.

## Six Assessments

### Novelty

Check whether the mechanism, combination, target, or evidence claim differs from the closest known work. Primary sources, official repositories, or a bounded source dossier are required. Without a source comparison, set novelty to unknown rather than guessing from phrasing.

### Feasibility

Check whether the smallest implementation or derivation can run with the declared data, tools, permissions, and resource limits. A plausible description is weaker than a passed smoke check.

### Evidence Strength

Check what typed, reproducible, or independently inspectable evidence already exists. The Factor Card itself never upgrades Mission Board `evidence_strength` or `claim_readiness`.

### Cost

Estimate the open resource burden: time, compute, external calls, data preparation, human review, and opportunity cost. Score 0 for negligible cost and 4 for the highest bounded cost under consideration.

### Risk

Record technical, scientific, duplication, authorization, safety, and interpretation risks. Score 0 for low observed risk and 4 for high unresolved risk. A high risk score is not favorable.

### Alignment

Check whether the idea directly advances the active work unit, acceptance criteria, and current route. Interesting off-route work may be parked without being rejected.

## Decision

Choose exactly one:

- `explore`: the idea is ready for a bounded exploratory check.
- `verify-first`: a missing prerequisite or decisive uncertainty should be tested first.
- `park`: preserve the idea without spending the current budget.
- `reject`: recorded evidence makes the current formulation unsuitable.
- `needs-human`: authorization, domain judgment, or source access is required.

Do not derive the decision by summing scores. Explain tradeoffs in the idea artifact and record one `minimal_test` that could change the assessment. The test must include a question, method, expected evidence, open resource limits, and a stop condition.

## File And Validation

Create one `research/artifacts/factor-card-<slug>.json` per assessed candidate from `assets/templates/research/artifacts/factor-card.json`. Bind it to the current work unit, profile, and idea artifact, then validate it:

```bash
python <plugin>/scripts/ds_lite_protocol.py validate-factor-card \
  --path research/artifacts/factor-card-<slug>.json
```

Link a valid card to its idea node as an artifact. Do not link it as claim-bearing evidence. A reviewer may check the card, its sources, and its minimal test, but only an applicable typed evidence validator can promote evidence strength.

## Provenance

The process framing was independently adapted from high-level workflow ideas audited in the DeepScientist v0.1.5 `wq-alpha-research` material: start from a mechanism hypothesis, distinguish ideation from validation status, diagnose failure modes, preserve uncertainty, and choose the next bounded test. This plugin does not redistribute that skill's source text, financial fields, formulas, datasets, credentials, or domain thresholds. Finance remains a pressure-case fixture rather than a default DS Lite domain.
