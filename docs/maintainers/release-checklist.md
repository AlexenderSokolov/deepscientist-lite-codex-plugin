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
- Verify the five `$ds-lite-*` skills are visible and triggerable.
- Run a blank-project intake smoke test.
- Run an old-project intake-audit smoke test.
- Migrate a Graph v1 fixture, confirm the read-only backup exists, and test a stale revision conflict.
- Confirm no project-external absolute paths appear in the migrated graph.
- Record any installation or cache failure in `known-issues.md`.

## Stable public release

- Prepare CHANGELOG and release notes.
- Include a user-facing quickstart and a sanitized paradigm-comparison case walkthrough.
- Collect at least one fresh-user installation report.
- Verify Windows PowerShell, Git Bash, and a Unix-like shell path.
- Add macOS verification before removing the beta label.
- Keep the manifest free of MCP/apps/hooks unless a later version intentionally adds them.

