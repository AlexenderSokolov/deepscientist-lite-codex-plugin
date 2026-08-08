# Maintainer Runners

These wrappers are repository-maintenance entry points for package validation,
phase evidence, release receipts, and controlled host probes. They are not
loaded by the marketplace packages. Runtime code belongs under `plugins/`;
generated evidence belongs under an ignored fresh run root.

PowerShell and Bash wrappers intentionally share names. They resolve the
repository root from this directory and never write receipts over an existing
run.

`run_accept_fresh_runtime_candidate.ps1` and
`run_accept_fresh_runtime_candidate.sh` run the candidate-bound App Server
acceptance. They require an explicit, redacted `ds-lite.provider-session.v1`
contract with `allowed_effects: ["read"]`; neither wrapper supplies provider
configuration, reads credentials, nor authorizes a release.
