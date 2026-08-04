# Causal Router Protocol

## Purpose

This protocol implements a Router that distinguishes four causal tasks,
each with independent evidence gates and output artifacts. It prevents
the common mistake of treating "causal chain analysis" as a universal
tool for finding research mechanisms, proving causal effects, locating
software bugs, and summarizing automation failures.

## Schema: ds-lite.causal-router.v1

### Four Causal Task Modes

1. **Mechanism Chain**: Known problem phenomenon and approximate mechanism.
   How to decompose conditions and find more intervention points.
   - Method: Budgeted causal-chain/TRIZ-style AND/OR condition decomposition
   - Output: Causal Model Artifact, edges default to hypothesis
   - Does NOT claim to prove real causal relationships

2. **Causal Inference**: What is the effect of treatment/exposure X on
   outcome Y? Are identification assumptions met?
   - Method: DAG + estimand + identification + estimation + refutation
   - Output: Empirical Evidence Pack + assumption table
   - Does NOT use language chains as a substitute for confounding

3. **Causal Discovery**: What structures in the data are worth forming
   subsequent hypotheses?
   - Method: causal-learn algorithms + background knowledge + stability
   - Output: Exploratory artifact
   - Does NOT promote observed directed edges to facts

4. **Incident/System Analysis**: Why does an engineering/automation failure
   recur? How did system conditions jointly produce the result?
   - Method: Experience Ledger, fault tree, CAST/STPA-style multi-factor
   - Output: Incident + root-cause candidate + verified repair
   - Does NOT force a single "root cause"

### Routing Logic

```
因果问题
  |
  +-- Need to estimate numerical effect? --> Causal Inference
  |
  +-- Mechanism roughly known? --> Mechanism Chain
  |
  +-- Has data and accepts exploratory structure? --> Causal Discovery
  |
  +-- Failure/incident复盘? --> Incident/System Analysis
```

### Causal Model Artifact (Minimum Contract)

```json
{
  "schema": "ds-lite.causal-model.v1",
  "mode": "mechanism-chain|causal-inference|causal-discovery|incident-analysis",
  "question": "...",
  "scope_conditions": [],
  "nodes": [
    {"id": "n1", "statement": "...", "status": "observed|hypothesis|validated|contested"}
  ],
  "edges": [
    {
      "from": "n1",
      "to": "n2",
      "relation": "causes|enables|blocks|mediates|moderates|confounds|precedes",
      "logic": "AND|OR|UNKNOWN",
      "status": "hypothesis|supported|contested|refuted",
      "evidence_refs": [],
      "alternative_explanations": [],
      "falsifiers": []
    }
  ],
  "interventions": [],
  "unresolved_assumptions": [],
  "review_ref": null
}
```

### Validation Anti-Patterns

The validator checks for these common causal analysis anti-patterns:

- `correlation_as_causation`: Correlation written as causation
- `common_cause_omitted`: Common cause not included
- `temporal_order_reversed`: Time order reversed
- `selection_bias`: Selection bias not addressed
- `feedback_loop`: Feedback loop not addressed
- `multiple_sufficient_causes`: Multiple sufficient causes not considered
- `non_manipulable_variable`: Non-manipulable variable treated as intervention
- `causal_discovery_unstable`: Causal discovery output unstable
- `single_root_cause_oversimplification`: Single incident reduced to one root cause
- `model_generated_chain_as_long_term_fact`: Model-generated chain promoted to fact

### Tool Selection

- **DoWhy**: Explicit modeling and testing of causal hypotheses
- **EconML**: ML-driven heterogeneous treatment effect estimation
- **causal-learn**: Causal discovery research and exploration
- **Engineering incidents**: Should return to observable receipt, system boundary,
  fault injection, timeline, and verified repair

### Acceptance Gate

Causal capability must pass at least these counter-examples:
- Correlation being wrongly written as causation
- Common cause being omitted
- Temporal order being reversed
- Selection bias
- Feedback loop
- Multiple sufficient causes
- Non-manipulable variable
- Unstable causal discovery
- Single incident being hard-summarized as the only root cause
- Model-generated chain being wrongly promoted to long-term fact