# Release Checklist

## Beta release

- Run `bash tools/validation/run_validate.sh` or `tools/validation/run_validate.ps1`.
- Run all six package wrappers and retain the `ds-lite.package-validation.v1` receipt. Check core-only, core+academic, core+empirical, core+engineering, core+web, core+knowledge, core+web+knowledge, and all-six matrices independently.
- Confirm the Windows/Ubuntu Python 3.10 and 3.x CI matrix is green.
- Confirm `.codex-plugin/plugin.json` version and repository URL.
- Confirm `CHANGELOG.md`, `LICENSE`, `NOTICE`, and the Graph v2 migration guide match the release.
- Confirm skill frontmatter contains only `name` and `description`.
- Run the official plugin validator from the installed `plugin-creator` skill.
- Install or upgrade from the GitHub marketplace source.
- Restart Codex Desktop and open a fresh thread.
- Verify the release-specific skill count is visible and triggerable. The split candidate expects 9 Core skills, 17 Academic skills, and one skill in each other pack. Do not treat source counts as cache or fresh-task evidence.
- For Academic, run `run_accept_academic_providers.*` only with explicit external-provider authorization and retain its independent receipt. A pending/unavailable provider blocks Academic live acceptance; it never becomes a fabricated not-found result.
- For Web/Knowledge, run the public-only CLI cases with explicit `--allowed-domain` scopes and retain source-record v2, Tapestry, ScholarAIO, and review-queue receipts. Exercise redirects, out-of-scope URLs, provider 429/timeout/invalid responses, and missing authorization. Missing stable external interfaces remain `not-observed`.
- For Empirical, exercise confounding OLS, failed DiD pretrend, clustered standard errors, missing data, robustness disagreement, and null-result fixtures.
- For Engineering, exercise mixed-frequency FFT, leakage, aliasing, bad sampling rate, unit conflict, missing seed, and wrong-axis fixtures.
- Verify `mission --format json`, `mission --format markdown`, and `render-status` expose a readable Mission Board after a branch, rollback, and blocked review.
- Verify a blank project creates `ds-lite.work-unit.v1` with planning/none, and ordinary artifacts or logs cannot promote evidence strength.
- Verify a claim-bearing work unit stays needs-evidence until its profile validator passes, including missing/damaged Evidence Pack fixtures.
- Verify only a done review with a matching `ds-lite.review-result.v1` sidecar becomes reviewed; exercise verdict/claim-assessment independence and malformed/path/sensitive/id/unknown-field fixtures.
- Verify off-route blocked debt remains visible without forcing `waiting_for_user`, and all reserved / not-validated profiles fail closed.
- Run one `$ds-lite-iterate` checkpoint and confirm it stops after a single frontier decision rather than looping.
- Exercise first-use learning receipts, stale tutorial/package invalidation, quality-plan PreToolUse blocking, and Stop enforcement for missing quality results.
- Validate a planned `ds-lite.delegation.v1` with two disjoint tasks, confirm `$ds-lite-coordinate` stops before execution without explicit approval, then use a separately authorized fresh-agent run to check at most three children, `nested_delegation=false`, result refs, parent-only integration, and no automatic retry.
- For the manual tmux capacity handshake, have the user execute the generated fixed-socket bootstrap block from an independent stable shell, then complete a real detach/disconnect/reconnect probe and confirm the server fingerprint is unchanged.
- Use an isolated disposable plan whose fixed socket is deliberately absent, and confirm Codex stops without calling `tmux new-session`, selecting another socket, or expanding capacity.
- Launch one pane-scoped Codex CLI child worker and verify its process identity, provider thread/task handle, query command, and resume result independently from tmux attach and experiment checkpoint recovery.
- Run a blank-project intake smoke test.
- Run an old-project intake-audit smoke test.
- Run `bash teaching/run_evidence_lab.sh` and inspect the retained experiment→review→analysis project.
- Tamper with one packed output and confirm `verify --strict` fails.
- Confirm a failed or `needs-human` review cannot advance a new analysis/write route.
- Migrate a Graph v1 fixture, confirm the read-only backup exists, and test a stale revision conflict.
- Confirm no project-external absolute paths appear in the migrated graph.
- Record any installation or cache failure in `known-issues.md`.
- Confirm contract/environment JSON contains no credentials, process environment dump, or workstation absolute root.
- If publishing source/package-only, state that cache installation and new-thread discovery are not verified; do not silently perform those external state changes.
- Feed independent `passed` receipts for source, offline, CLI, provider, Hook, delegation, matched effect, formal cache, fresh Desktop, OpenScience, and docs into `tools/validation/runners/run_accept_formal_host.*` using `ds-lite.formal-release-gate.v2`. A missing or non-passing receipt must keep release blocked; adjacent evidence cannot substitute.

## Stable public release

- Prepare CHANGELOG and release notes.
- Include a user-facing quickstart and a sanitized paradigm-comparison case walkthrough.
- Collect at least one fresh-user installation report.
- Verify Windows PowerShell, Git Bash, and a Unix-like shell path.
- Add macOS verification before removing the beta label.
- Keep the manifest free of MCP/apps/hooks unless a later version intentionally adds them.
- Do not claim the tmux handshake as verified release evidence until the user bootstrap, disconnect probe, missing-socket stop, and provider-resume checks above are recorded on a real host.
