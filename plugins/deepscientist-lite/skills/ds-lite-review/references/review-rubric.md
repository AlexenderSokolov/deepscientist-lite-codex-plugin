# DS Lite Review Rubric

## Status vocabulary

- `pass`: evidence is present and supports the lane's narrow claim.
- `fail`: evidence contradicts the contract or is missing/corrupted where required.
- `needs-human`: a qualified check cannot be completed safely or confidently in this run.
- `not-applicable`: the lane genuinely does not apply; explain why.

## Lanes

### Reproducibility and integrity

Require a deterministic Evidence Pack verification result, contract, stdout/stderr, metrics, and hashes for project-local files. A nonzero experiment exit code is not itself corruption. Hash mismatch, missing required logs, or an invalid manifest is `fail`.

### Specification and metric compliance

Compare the contract command, inputs, seeds, budget, expected outputs, metric names, thresholds, and failure interpretation with the recorded run. A threshold miss is `fail` for the promised success criterion, even when the run executed correctly.

### Citation authenticity

Check that claim-bearing citations resolve to matching primary sources and that title, authors, identifier, and supported claim agree. No citations may be `not-applicable`; unavailable source access is `needs-human`.

### Method-code-log alignment

Compare only material method claims with scripts, command, logs, metrics, and outputs. Do not claim line-by-line proof from an LLM review. Missing implementation evidence or a material contradiction is `fail`.

## Overall decision

- `fail` if any lane fails.
- `needs-human` if no lane fails and at least one lane needs human review.
- `pass` only when reproducibility and specification pass and every other lane is pass or not-applicable.

The review artifact must cite paths or sources for every lane. A narrative assertion without an evidence pointer cannot receive `pass`.
