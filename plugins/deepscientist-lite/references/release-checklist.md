# Release Checklist

## Beta release

- Run `python scripts/validate_repo.py`.
- Confirm `.codex-plugin/plugin.json` version and repository URL.
- Confirm skill frontmatter contains only `name` and `description`.
- Install or upgrade from the GitHub marketplace source.
- Restart Codex Desktop and open a fresh thread.
- Verify the five `$ds-lite-*` skills are visible and triggerable.
- Run a blank-project intake smoke test.
- Run an old-project intake-audit smoke test.
- Record any installation or cache failure in `known-issues.md`.

## Stable public release

- Prepare CHANGELOG and release notes.
- Include a user-facing quickstart and an AIResearch case walkthrough.
- Collect at least one fresh-user installation report.
- Verify Windows PowerShell, Git Bash, and a Unix-like shell path.
- Keep the manifest free of MCP/apps/hooks unless a later version intentionally adds them.
