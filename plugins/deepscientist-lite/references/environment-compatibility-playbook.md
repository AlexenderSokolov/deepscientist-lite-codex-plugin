# Environment Compatibility Playbook

This reference is a troubleshooting record for the Lite execution boundary. It does not add a runtime, provider router, scheduler, or credential manager. It tells a skill how to diagnose an environment problem without mistaking it for a research result.

## First classify the failure

Record one category before changing anything:

- `configuration`: the isolated home does not contain the required non-secret provider route or model catalog.
- `authentication`: the process has no usable authentication path. Never copy or print credentials into project artifacts.
- `provider`: the route is configured, but the provider returned a rate limit, unavailable, or transport error.
- `cli`: the executable version or feature surface differs from the tested version.
- `path`: a Windows drive path, WSL mount, relative reference, or case-sensitive path is wrong.
- `encoding`: PowerShell, cmd, Bash, or Python disagree about UTF-8 or a non-ASCII argument.
- `format`: TOML, JSON, YAML, Markdown, or line endings changed the meaning of a contract.
- `resource`: timeout, disk, memory, TTY, or process-tree limits stopped the call.

Do not collapse these categories into “the plugin failed”. Preserve the command result and stop reason.

## Minimal provider check

The isolated pilot may copy only these non-secret values from the formal home:

```toml
model_provider = "custom"
model = "gpt-5.6-sol"
model_reasoning_effort = "low"
model_catalog_json = "model-catalogs/<relative-file>.json"

[model_providers.custom]
name = "custom"
base_url = "https://<provider>/v1"
wire_api = "responses"
requires_openai_auth = true
request_max_retries = 0
stream_max_retries = 0
```

The catalog reference must be project-relative to the isolated home. Reject absolute paths, `..`, Windows backslashes, tokens, passwords, headers, and environment dumps. `auth.json` is not part of the cloned route. An inherited environment authentication category can be recorded as `environment-api-key` without recording its value.

Check in this order:

1. Resolve the exact CLI binary and print only its version.
2. Parse the isolated config and verify the provider route and catalog file exist.
3. Run the host's model/debug command without a model request.
4. Run one read-only canary with a new pilot id.
5. Require `thread.started`, `turn.completed`, non-zero usage, final feedback, and unchanged workspace.

Model discovery proves only configuration. A canary proves actual request reachability for that attempt. A `rate-limit` or ambiguous transport result freezes the attempt; do not replay it under the same id.

## Redacted transport diagnostics

Future receipts use `ds-lite.transport-diagnostic.v1`. Keep the legacy coarse category, stderr line count, and stderr SHA-256 for compatibility, then add only normalized observations:

- `failure_class`: `auth`, `rate-limit`, `network`, `protocol`, `timeout`, `child-process`, `ambiguous`, `unknown`, or `none`.
- HTTP status category and an allow-listed provider error code; unknown vendor codes become `unrecognized`.
- Connection and response-header state only when stderr provides direct evidence. A thread id is not connection evidence.
- Subprocess exit cause, child-process state, and stdout/stderr pipe states observed by the runner.

Raw stderr remains in memory only long enough to update the reducer. Never save it, a prompt, tool arguments, credentials, full environment state, or workstation roots. A local fake-provider/fake-Codex result validates only this reducer and one-attempt behavior; it is not provider reachability or real Codex protocol evidence.

If a fresh authenticated Responses probe records `connection_state=established`, `response_header_state=received`, `http_status_category=4xx`, no terminal event, and zero usage, classify the layer as provider protocol acceptance for that route. Do not treat it as DNS/TCP/TLS failure, do not infer Codex CLI wire compatibility, and do not retry the same diagnostic identity.

## Windows, Bash, and WSL boundaries

- Keep machine roots in the runner or environment, never in Graph, STATUS, receipts, or prompts.
- Store protocol paths as POSIX-relative refs such as `research/artifacts/result.json`.
- For WSL computation, record the distribution and proof artifact. This proves the computation ran in WSL, not that Codex Linux installation is verified.
- Use `--title-file`, `--question-file`, or UTF-8 files for Chinese arguments instead of passing long non-ASCII strings through legacy PowerShell quoting.
- Use `PYTHON_BIN`, `DS_LITE_PLUGIN_ROOT`, and `DS_LITE_STATE_CLI` in `run_*.sh`; do not hard-code a workstation root.
- If `tempfile` cannot create a file, classify the test as an environment write-permission failure and set `TEMP`/`TMP` to an authorized writable test root. Do not treat it as a plugin or provider failure.
- `.cmd` launchers can leave child processes and pipes behind. On timeout, terminate the process tree and keep the receipt terminal; never finalize a live request as completed.

## Format and contract conflicts

Before editing a protocol file, validate its declared schema and compare the current revision. JSON unknown fields belong under `extensions`; TOML provider settings must be explicitly allow-listed; Markdown is a human projection, not typed evidence. Normalize line endings only in files owned by the current change. A successful parser or exit code is not evidence that the scientific claim is valid.

## Reporting template

Every environment incident should report:

```text
category -> observed command/result -> preserved evidence ref -> blocked or passed gate -> next diagnostic
```

This keeps “the plugin was not loaded”, “the provider was unavailable”, and “the task itself failed” as three different conclusions.
