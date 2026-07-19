# Known Issues

## Codex Desktop plugin hot loading

Codex Desktop may not expose newly installed or upgraded skills until the app is restarted and a new thread is opened.

## Source release is not cache acceptance

`v0.5.0-beta.2` may be validated from a clean source package without changing the installed Codex cache. That proves the source/package surface only. Do not report the installed version, skill discovery, four-profile behavior, real-host hook registration/blocking, human A/B result, or fresh-thread behavior as verified until separately authorized evidence records them.

The 2026-07-19 isolated install was successful, but the first real `codex exec --ephemeral --json` canary produced no event, final message, or usage before the 180-second budget and was terminated with timeout code `124`. This is an external model/host acceptance blocker, not evidence that the communication layer worked or failed. Do not launch the seven-skill campaign or matched A/B until a canary returns a verifiable final result.

## Host hook format is unconfirmed

The plugin-local `hooks/hooks.json` is a proposed four-event adapter, not a manifest registration. `ds_lite_hook.py install --show` displays it; `--apply` returns `host_supported: false` and writes no `.codex/config.toml` until official host documentation or a real host acceptance run confirms the format. This is an intentional fail-closed boundary, not evidence that the host lacks hooks.

## Marketplace cache access denied

`codex plugin marketplace upgrade deepscientist-lite` can fail with an access-denied error while Codex Desktop is using the plugin cache. Close or restart Codex Desktop, then retry the upgrade.

## Local marketplace registration without plugin installation

`codex plugin marketplace add` registers a source. Installation is a separate action in the `/plugins` browser, and the exact surface can vary by Codex build. A new thread may continue loading an older cached plugin even when source registration succeeds. Verify the exact version, source, UI description, and seven discovered skills in a fresh session; never treat a marketplace config entry as installation evidence. Preserve the old cache until the new source is confirmed.

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

## Markdown-only review compatibility

A Markdown-only review remains readable but cannot produce `evidence_strength=reviewed`. The review node must be done and link a valid `ds-lite.review-result.v1` sidecar whose work unit, profile, node ids, Evidence Pack refs, and digest match. Old projects receive a compatibility warning until the typed result is added; do not silence it by treating prose as typed evidence.

## Reserved profiles

`literature-evidence`, `mathematical-exploration`, `software-evaluation`, and `numerical-simulation` are `reserved / not-validated`. They intentionally fail closed when claim-bearing evidence is requested. Registration is not evidence of domain support.

## Ephemeral launch ownership

An `agent-ephemeral` or `unknown` launch context is not a durable runtime owner. A tmux server created inside a temporary Codex shell may remain tied to that shell's cgroup, container, host, or scheduler allocation, so detaching the pane does not prove persistence. `nohup`, `disown`, `setsid`, backgrounding, and automatic tmux creation are likewise insufficient evidence by themselves.

For work that must cross a tool call, SSH connection, or worker lifetime, run a persistence probe through the same ownership boundary and record the external owner, PID/job identity, logs, exit path, heartbeat, checkpoint, budget, and recovery command in `research/artifacts/external-task-<task-id>.md`. Preserve old attempts and reconcile the original process before resubmitting.

## Manual tmux capacity

A tmux session has no parent-child hierarchy. This protocol defines no Codex or tmux "child session"; the supported unit is a pane-scoped Codex CLI child worker. The user must create the server and top-level capacity from a separately owned stable shell after Codex writes an `external-tmux-plan-*`. Manual creation is still not persistence evidence until the recorded server fingerprint survives the planned disconnect/reconnect probe.

Do not infer provider conversation recovery from a surviving server, pane, or CLI PID. Record and test the provider thread/task handle and resume command separately. If the verified socket disappears, Codex must stop instead of using `new-session`, which could silently create an unverified replacement server.

## Scope boundary

DeepScientist Lite has no daemon, MCP server, Web/TUI, connector, runner registry, or long-running scheduler. It is a lightweight file-led research protocol for Codex skills.

`$ds-lite-iterate` is a one-round worker checkpoint, not autonomous background research. It must stop after writing the frontier decision, graph update, and Mission Board status.
