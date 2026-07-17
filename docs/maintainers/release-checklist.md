# Release Checklist

## Beta release

- Run `bash tools/validation/run_validate.sh` or `tools/validation/run_validate.ps1`.
- Confirm the Windows/Ubuntu Python 3.10 and 3.x CI matrix is green.
- Confirm `.codex-plugin/plugin.json` version and repository URL.
- Confirm `CHANGELOG.md`, `LICENSE`, `NOTICE`, and the Graph v2 migration guide match the release.
- Confirm skill frontmatter contains only `name` and `description`.
- Run the official plugin validator from the installed `plugin-creator` skill.
- Install or upgrade from the GitHub marketplace source.
- Restart Codex Desktop and open a fresh thread.
- Verify the release-specific `$ds-lite-*` skill count is visible and triggerable. `0.4.0-beta.2` has seven; a v0.5 candidate must expose eight, including `$ds-lite-review`, `$ds-lite-iterate`, and `$ds-lite-coordinate`.
- Verify `mission --format json`, `mission --format markdown`, and `render-status` expose a readable Mission Board after a branch, rollback, and blocked review.
- Verify a blank project creates `ds-lite.work-unit.v1` with planning/none, and ordinary artifacts or logs cannot promote evidence strength.
- Verify a claim-bearing work unit stays needs-evidence until its profile validator passes, including missing/damaged Evidence Pack fixtures.
- Verify only a done review with a matching `ds-lite.review-result.v1` sidecar becomes reviewed; exercise verdict/claim-assessment independence and malformed/path/sensitive/id/unknown-field fixtures.
- Verify off-route blocked debt remains visible without forcing `waiting_for_user`, and all reserved / not-validated profiles fail closed.
- Run one `$ds-lite-iterate` checkpoint and confirm it stops after a single frontier decision rather than looping.
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

## Stable public release

- Prepare CHANGELOG and release notes.
- Include a user-facing quickstart and a sanitized paradigm-comparison case walkthrough.
- Collect at least one fresh-user installation report.
- Verify Windows PowerShell, Git Bash, and a Unix-like shell path.
- Add macOS verification before removing the beta label.
- Keep the manifest free of MCP/apps/hooks unless a later version intentionally adds them.
- Do not claim the tmux handshake as verified release evidence until the user bootstrap, disconnect probe, missing-socket stop, and provider-resume checks above are recorded on a real host.
