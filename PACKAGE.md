# Package Layout

This repository is a Codex marketplace repository.

## Runtime Plugin Package

- `.agents/plugins/marketplace.json`: marketplace index for Codex.
- `plugins/deepscientist-lite/`: installable plugin package.
- `plugins/deepscientist-lite/.codex-plugin/plugin.json`: plugin manifest.
- `plugins/deepscientist-lite/skills/`: five runtime skills.
- `plugins/deepscientist-lite/scripts/ds_lite_state.py`: no-dependency state graph helper.
- `plugins/deepscientist-lite/assets/templates/`: project file templates.
- `plugins/deepscientist-lite/references/`: skill-facing protocol references only.

## Non-Runtime Material

- `docs/`: implementation and maintainer documentation.
- `teaching/`: standalone teaching material and sanitized case walkthroughs.
- `tools/validation/`: maintainer validation tools.

## Release Boundary

The plugin remains lightweight: no MCP server, daemon, hooks, Web/TUI, connector, or local model bundle is declared in the manifest.
