# Known Issues

## Codex Desktop plugin hot loading

Codex Desktop may not expose newly installed or upgraded skills until the app is restarted and a new thread is opened.

## Marketplace cache access denied

`codex plugin marketplace upgrade deepscientist-lite` can fail with an access-denied error while Codex Desktop is using the plugin cache. Close or restart Codex Desktop, then retry the upgrade.

## Local marketplace registration without plugin installation

`codex plugin marketplace add` registers a source. Installation is a separate action in the `/plugins` browser, and the exact surface can vary by Codex build. A new thread may continue loading an older cached plugin even when source registration succeeds. Verify the exact version, source, UI description, and six discovered skills in a fresh session; never treat a marketplace config entry as installation evidence. Preserve the old cache until the new source is confirmed.

## Windows non-ASCII command arguments

PowerShell or console encoding can corrupt Chinese arguments passed directly to Python. Prefer the available UTF-8 `--*-file` options for title, question, summary, and reason values.

## Graph v1 external paths

Automatic migration stops when a v1 graph contains an absolute path outside the project. Run `migrate --external-map alias=ROOT`; do not manually replace the JSON path because the migration also creates the v1 backup and Graph v2 revision.

## External aliases

`validate` warns when an `external://alias/path` cannot be resolved. Set `DS_LITE_EXTERNAL_<ALIAS>` in the local environment or the relevant `run_*.sh`. Do not commit workstation absolute roots to graph state.

## Evidence integrity is not scientific truth

Evidence Pack verification proves that declared files exist, required metrics are present, thresholds can be evaluated, and hashed files have not changed. It does not prove dataset validity, causal claims, statistical appropriateness, or citation truth. Those remain review and human-scientist responsibilities.

The contract and environment schemas reject sensitive field names, but the CLI cannot reliably detect secrets embedded inside free-form commands, logs, notes, or result files. Sanitize those files before finalizing a pack and never place credentials on a recorded command line.

## Strict validation scope

Default `validate --strict` audits warnings from the whole graph, so a deliberately preserved failed branch can keep it non-zero. `validate --strict --scope active-route` applies the warning gate only to the current progression route and reports other node warnings separately as `off_route_warnings`. Structural, path-integrity, and graph-semantic errors remain global in both modes.

## External evidence hashing

External files are not hashed by default because they may be large or sensitive. Use `finalize --hash-external` only after confirming the intended external resource and cost. The graph and manifest retain the symbolic `external://` path, never the workstation root.

## Review independence

`ds-lite-review` creates a separate workflow pass and artifact. Without separately authorized subagents or infrastructure it does not guarantee a different model, process, or isolated evaluator.

## Scope boundary

DeepScientist Lite has no daemon, MCP server, Web/TUI, connector, runner registry, or long-running scheduler. It is a lightweight file-led research protocol for Codex skills.
