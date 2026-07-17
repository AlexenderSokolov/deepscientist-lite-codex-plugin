# Package Layout

This repository is a Codex marketplace repository.

## Runtime Plugin Package

- `.agents/plugins/marketplace.json`: marketplace index for Codex.
- `plugins/deepscientist-lite/`: installable plugin package.
- `plugins/deepscientist-lite/.codex-plugin/plugin.json`: plugin manifest.
- `plugins/deepscientist-lite/skills/`: seven runtime skills, including independent review and one-iteration worker handoff workflows.
- `plugins/deepscientist-lite/scripts/ds_lite_state.py`: no-dependency state graph helper.
- `plugins/deepscientist-lite/scripts/ds_lite_evidence.py`: no-dependency Evidence Pack contract, finalize, and verification helper.
- `plugins/deepscientist-lite/scripts/ds_lite_state_v1_legacy.py`: preserved v1 implementation for audit only; it is not the runtime entry point.
- `plugins/deepscientist-lite/assets/templates/`: project file templates.
- `plugins/deepscientist-lite/references/`: skill-facing protocol references only.

## Non-Runtime Material

- `docs/`: implementation and maintainer documentation.
- `teaching/`: standalone courses, the standard-library lab runner, cross-platform wrappers, worksheets, and sanitized fixtures; none are loaded as plugin runtime.
- `tools/validation/`: maintainer validation tools.
- `tests/`: standard-library Graph v2, Evidence Pack, and CLI regression tests.
- `.github/workflows/validate.yml`: Windows and Ubuntu validation matrix.

## Release Boundary

The plugin remains lightweight: no MCP server, daemon, hooks, Web/TUI, connector, or local model bundle is declared in the manifest.
