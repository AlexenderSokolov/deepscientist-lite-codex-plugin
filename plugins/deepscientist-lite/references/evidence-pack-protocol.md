# DS Lite Evidence Pack v1

Evidence Pack v1 records what an experiment promised, what executed, and whether the recorded files still match. It does not decide whether a scientific claim is true.

## Schemas

- Contract: `ds-lite.experiment-contract.v1`
- Manifest: `ds-lite.evidence.v1`
- Sanitized environment description: `ds-lite.environment.v1`

Contracts require run/node ids, hypothesis, command, project-relative cwd, inputs, metric definitions, seeds, budget, expected outputs, and failure interpretation. Metric directions are `max`, `min`, `target`, or `observe`.

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
