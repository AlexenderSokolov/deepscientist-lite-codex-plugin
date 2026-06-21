# Known Issues

## Codex Desktop plugin hot loading

Codex Desktop may not expose newly installed or upgraded skills until the app is restarted and a new thread is opened.

## Marketplace cache access denied

`codex plugin marketplace upgrade deepscientist-lite` can fail with an access-denied error while Codex Desktop is using the plugin cache. Close or restart Codex Desktop, then retry the upgrade.

## Windows non-ASCII command arguments

PowerShell or console encoding can corrupt Chinese arguments passed directly to Python. For `ds_lite_state.py init`, prefer UTF-8 text files with `--title-file` and `--question-file`.

## Scope boundary

DeepScientist Lite has no daemon, MCP server, Web/TUI, connector, runner registry, or long-running scheduler. It is a lightweight file-led research protocol for Codex skills.
