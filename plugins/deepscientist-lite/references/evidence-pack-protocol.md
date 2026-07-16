# DS Lite Evidence Pack v1

Evidence Pack v1 records what an experiment promised, what executed, and whether the recorded files still match. It does not decide whether a scientific claim is true.

## Schemas

- Contract: `ds-lite.experiment-contract.v1`
- Manifest: `ds-lite.evidence.v1`
- Sanitized environment description: `ds-lite.environment.v1`

Contracts require run/node ids, hypothesis, command, project-relative cwd, inputs, metric definitions, seeds, budget, expected outputs, and failure interpretation. Metric directions are `max`, `min`, `target`, or `observe`; a missing or wrong direction is a protocol failure, not a harmless display bug.

When a comparison depends on budget, the contract and experiment artifact must distinguish smoke checks, early-budget metrics, final-budget metrics, and aggregate metrics such as AUC. The budget field is the declared cap for the current run; GPU jobs, long runs, dependency installs, cluster jobs, and external data access require user or supervisor approval unless the project has an explicit budget policy.

Environment JSON accepts only: `schema_version`, `python`, `platform`, `packages`, `container`, `hardware`, and `notes`. Never add tokens, passwords, credentials, API keys, or a full process environment.

## Commands

```bash
python <plugin>/scripts/ds_lite_evidence.py init \
  --root <project> --run-id <run-id> --contract <contract.json>

python <plugin>/scripts/ds_lite_evidence.py finalize \
  --root <project> --run-id <run-id> --exit-code 0 \
  --stdout <stdout.log> --stderr <stderr.log> --metrics <metrics.json> \
  --environment <environment.json> --output <project-relative-path>

python <plugin>/scripts/ds_lite_evidence.py verify \
  --root <project> --run-id <run-id> --strict
```

`init` is idempotent only when the existing canonical contract is identical. `finalize` preserves a stable execution record on identical retries. `verify` updates the manifest verification section and exits 1 for errors, or for warnings under `--strict`.

## Paths And Hashes

- Use normalized POSIX project-relative paths without `..`.
- Represent outside resources as `external://alias/path`; resolve with `DS_LITE_EXTERNAL_<ALIAS>`.
- Project-local contract inputs and evidence files always require SHA-256.
- External outputs are recorded without hashes unless `finalize --hash-external` is explicitly authorized.
- Evidence files reached through symlinks must still resolve inside the declared project or external root.
- Schema validation rejects sensitive field names, but free-form commands and logs still require manual secret sanitization before finalize.

## Review Boundary

An intact pack can describe a failed process. Threshold misses appear as verification warnings and fail strict verification. `$ds-lite-review` uses the pack plus source checks to decide `pass`, `fail`, or `needs-human`; it must not rewrite evidence to manufacture a passing result.

Mission only promotes a manifest to `has-evidence` when the active `ds-lite.work-unit.v1` declares that exact ref and the `experiment-run` profile's `ds-lite.evidence.v1` validator passes. Ordinary artifacts, logs, project files, and arbitrary non-empty `evidence_paths` do not satisfy a claim requirement.

Review writes a separate `ds-lite.review-result.v1` sidecar. `verdict` controls the review gate; `claim_assessment` independently records `none`, `inconclusive`, `refuted`, or `supportable`. The result counts only when its work unit, profile, review/experiment nodes, evidence refs, validator, and digest match. Markdown alone never promotes a route to `reviewed`.

If a metric direction, aggregation, or threshold interpretation is corrected after a run, record a protocol-breaking correction artifact and preserve the old node through `rollback` or `supersedes`. Do not mutate old evidence to make later claims look consistent.
