# Package Layout

This repository is a Codex marketplace repository.

## Runtime Plugin Package

- `.agents/plugins/marketplace.json`: marketplace index for Codex.
- `plugins/deepscientist-lite/`: installable plugin package.
- `plugins/deepscientist-lite/.codex-plugin/plugin.json`: plugin manifest.
- `plugins/deepscientist-lite/skills/`: 26 runtime skills: nine DS Lite continuity/evidence skills and the complete 17-skill nature-skills academic workflow family.
- `plugins/deepscientist-lite/vendor/`: fixed, provenance-preserving snapshots of `nature-skills` (Apache-2.0) and the authorized `codex-autoresearch` package (MIT declaration). Vendor files are source evidence, not silently executed entrypoints.
- `plugins/deepscientist-lite/scripts/ds_lite_state.py`: no-dependency state graph helper.
- `plugins/deepscientist-lite/scripts/ds_lite_evidence.py`: no-dependency Evidence Pack contract, finalize, and verification helper.
- `plugins/deepscientist-lite/scripts/ds_lite_protocol.py`: strict work-unit, review-result, Factor Card, and bounded-delegation validator.
- `plugins/deepscientist-lite/scripts/ds_lite_iteration.py`: strict init/finalize/verify helper for one reflective iteration; not an exactly-once transaction.
- `plugins/deepscientist-lite/scripts/ds_lite_hook.py` and `hooks/hooks.json`: optional, stateless, redacted Hook helper and candidate host configuration; fresh-host loading is not verified.
- `plugins/deepscientist-lite/scripts/ds_lite_state_v1_legacy.py`: preserved v1 implementation for audit only; it is not the runtime entry point.
- `plugins/deepscientist-lite/scripts/ds_lite_nature_setup.py`: workspace-local first-use inventory, doctor, onboarding, apply, and verify CLI for MCP/API/tool dependencies.
- `plugins/deepscientist-lite/scripts/codex_autoresearch_adapter.py`: bounded, redacted compatibility adapter; external execution remains policy-blocked until its child-output contract is verified.
- `plugins/deepscientist-lite/assets/templates/`: project file templates.
- `plugins/deepscientist-lite/references/`: skill-facing protocol references only.

## Non-Runtime Material

- `docs/`: implementation and maintainer documentation.
- `teaching/`: standalone courses, the standard-library lab runner, cross-platform wrappers, worksheets, and sanitized fixtures; none are loaded as plugin runtime.
- `tools/validation/`: maintainer validation tools.
- `tools/validation/upstream_manager.py`: read-only upstream inventory, provenance check, diff observation, and update-plan generator.
- `tests/`: standard-library Graph v2, Evidence Pack, and CLI regression tests.
- `.github/workflows/validate.yml`: Windows and Ubuntu validation matrix.

## Release Boundary

The plugin remains lightweight: no MCP server, daemon, Web/TUI, connector, or local model bundle is declared in the manifest. MCP and external APIs are opt-in workspace templates, not silent global registration. The plugin-local Hook helper does not own a queue, scheduler, background worker, or approval state.
