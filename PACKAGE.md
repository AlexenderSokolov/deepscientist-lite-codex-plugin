# Package Layout

This repository is packaged as a Codex marketplace repository.

## Runtime plugin package

- `.agents/plugins/marketplace.json`: marketplace index for Codex.
- `plugins/deepscientist-lite/`: the installable plugin package.
- `plugins/deepscientist-lite/.codex-plugin/plugin.json`: plugin manifest.
- `plugins/deepscientist-lite/skills/`: five runtime skills.
- `plugins/deepscientist-lite/scripts/ds_lite_state.py`: no-dependency state graph helper.
- `plugins/deepscientist-lite/assets/templates/`: project file templates.
- `plugins/deepscientist-lite/references/`: protocol references used by skills.

## Non-runtime project material

- `docs/`: implementation and maintenance documentation.
- `teaching/`: standalone teaching material and sanitized case walkthroughs.
- `tools/validation/`: repository validation tools. These are not plugin runtime entrypoints.

## Release boundary

The plugin remains lightweight: no MCP server, daemon, hooks, Web/TUI, connector, or local model bundle is declared in the manifest.
