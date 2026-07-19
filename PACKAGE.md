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
- `plugins/deepscientist-lite/assets/templates/STYLE.md`: optional project communication contract generated only for new projects.
- `plugins/deepscientist-lite/references/`: skill-facing protocol references only.
- `plugins/deepscientist-lite/references/communication/`: progressively loaded communication core, profiles, humanizer overlays, and academic-writing overlay.
- `plugins/deepscientist-lite/references/communication/self-audit.md`: three-phase observable self-check contract; `upstream/` and `upstream-adoption.json` are complete non-runtime source audit material.
- `plugins/deepscientist-lite/scripts/ds_lite_communication_audit.py`: standard-library `ds-lite.communication-audit.v1` receipt CLI.
- `plugins/deepscientist-lite/scripts/ds_lite_hook.py` and `hooks/hooks.json`: optional four-event deterministic adapter; disabled until the user confirms registration and the host format is verified.
- `plugins/deepscientist-lite/THIRD_PARTY_NOTICES.md`: MIT attribution and license text for selectively adapted communication guidance.

## Non-Runtime Material

- `docs/`: implementation and maintainer documentation.
- `teaching/`: standalone courses, the standard-library lab runner, cross-platform wrappers, worksheets, and sanitized fixtures; none are loaded as plugin runtime.
- `tools/validation/`: maintainer validation tools.
- `tests/`: standard-library Graph v2, Evidence Pack, and CLI regression tests.
- `.github/workflows/validate.yml`: Windows and Ubuntu validation matrix.

## Release Boundary

The `0.5.0-beta.2` plugin remains lightweight: no MCP server, daemon, Web/TUI, connector, or host `hooks` field is declared in the manifest, and runtime operation still uses only the Python standard library. The hook files are inert until explicitly registered; an unconfirmed host returns `host_supported: false` and is never guessed into `.codex/config.toml`.
