# Known Issues

## Codex Desktop plugin hot loading

Codex Desktop may not expose newly installed or upgraded skills until the app is restarted and a new thread is opened.

## Marketplace cache access denied

`codex plugin marketplace upgrade deepscientist-lite` can fail with an access-denied error while Codex Desktop is using the plugin cache. Close or restart Codex Desktop, then retry the upgrade.

## Windows non-ASCII command arguments

PowerShell or console encoding can corrupt Chinese arguments passed directly to Python. Prefer the available UTF-8 `--*-file` options for title, question, summary, and reason values.

## Graph v1 external paths

Automatic migration stops when a v1 graph contains an absolute path outside the project. Run `migrate --external-map alias=ROOT`; do not manually replace the JSON path because the migration also creates the v1 backup and Graph v2 revision.

## External aliases

`validate` warns when an `external://alias/path` cannot be resolved. Set `DS_LITE_EXTERNAL_<ALIAS>` in the local environment or the relevant `run_*.sh`. Do not commit workstation absolute roots to graph state.

## Scope boundary

DeepScientist Lite has no daemon, MCP server, Web/TUI, connector, runner registry, or long-running scheduler. It is a lightweight file-led research protocol for Codex skills.
