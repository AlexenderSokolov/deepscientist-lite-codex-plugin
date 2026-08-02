# Maintainer Runners

These wrappers are repository-maintenance entry points for package validation,
phase evidence, release receipts, and controlled host probes. They are not
loaded by the marketplace packages. Runtime code belongs under `plugins/`;
generated evidence belongs under an ignored fresh run root.

PowerShell and Bash wrappers intentionally share names. They resolve the
repository root from this directory and never write receipts over an existing
run.
