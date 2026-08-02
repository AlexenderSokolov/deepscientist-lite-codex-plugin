# Known Issues

## Candidate 0.6.0-beta.1 upstream integration (2026-07-24)

The source candidate contains 26 discoverable skills: nine DS Lite core skills
and all 17 `nature-skills` workflows at commit
`91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b`. The fixed Nature snapshot is kept
under `vendor/`; `nature-shared` is an internal layer and must not be counted as
a user skill. `ds_lite_nature_setup.py` checks local tool and environment-key
presence and writes only workspace-local configuration. It does not enable MCP,
external APIs, credentials, or downloads by itself.

The authorized `codex-autoresearch` snapshot is recorded at commit
`f2389bffbb4cd7789deb6796bc4ba35bf31f2a90` / npm `0.1.5-beta.0`. Its adapter is
bounded and fail-closed, with zero automatic retry; it inspects provenance but
does not execute the upstream runner until sanitized child output is verified.

`tools/validation/check_text_compatibility.py` treats binary assets as binary
and marks immutable vendor files `provenance-only`; it enforces ASCII/LF rules
only on owned executable wrappers and parses owned UTF-8 text. The cross-system
JSON report configures UTF-8 output so PowerShell 5.1 code pages cannot hide the
actual finding. PowerShell 7, WSL/Bash, and shellcheck remain `not-observed` when
the tool is unavailable.

This integration does not unlock real provider wire, Hook host, Desktop,
child-agent delegation, matched effect, formal cache, or release gates.

The 2026-07-24 unified Windows run completed `304/304` tests and produced a
fresh cross-system report with 1465 files scanned and zero compatibility
failures. Bash, PowerShell 7, and shellcheck were unavailable on this host and
remain `not-observed`; this is an execution-surface limitation, not a product
failure or success claim. Evidence:
`.validation-tmp/validation-20260724T0120359466120-21292/cross-system-validation-20260724T0120359466120-21292.json`.

## Cross-system execution surface

- Executable scripts must be ASCII and LF where required. The unified validator
  reports corrupted wrappers and mixed line endings as blocking findings.
- PowerShell profile/language-mode restrictions are recorded as `not-observed`,
  not as syntax success.

## Codex Desktop plugin hot loading

Codex Desktop may not expose newly installed or upgraded skills until the app is restarted and a new thread is opened.

## Source release is not cache acceptance

`v0.4.0-beta.2` may be validated, tagged, and published from a clean source package without changing the installed Codex cache. That proves the source/package surface only. Do not report the installed version, skill discovery, or fresh-thread behavior as verified until a separately authorized cache installation and new-thread probe records the exact loaded version.

## Marketplace cache access denied

`codex plugin marketplace upgrade deepscientist-lite` can fail with an access-denied error while Codex Desktop is using the plugin cache. Close or restart Codex Desktop, then retry the upgrade.

## Local marketplace registration without plugin installation

`codex plugin marketplace add` registers a source. Installation is a separate action in the `/plugins` browser, and the exact surface can vary by Codex build. A new thread may continue loading an older cached plugin even when source registration succeeds. Verify the exact version, source, UI description, and release-specific skill count in a fresh session: `0.4.0-beta.2` has seven skills, while the unreleased v0.5 source has nine, adding `$ds-lite-coordinate` and the `$ds-lite` gateway. Never treat a marketplace config entry as installation evidence. Preserve the old cache until the new source is confirmed.

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

## Bounded delegation is not host execution proof

`ds-lite.delegation.v1`, `validate-delegation`, and `$ds-lite-coordinate` can prove that a plan is structurally bounded, approved, path-disjoint, and result-linked. They do not prove that the Codex host discovered the new skill, enforced a child's filesystem scope, or executed children independently. A fresh-agent forward test requires separate authorization. Until then, report the protocol as source-validated and host behavior as not verified.

The coordinator must stop before execution when approval is missing. It must also preserve partial/blocked results and stop on ambiguous transport or duplicate risk; the protocol provides no background queue or automatic retry.

## Plugin-local Hook is not host enforcement proof

The Core source includes `hooks/hooks.json` and a tested standard-library helper for redacted Mission context, deterministic pre-tool blocks, post-tool consistency summaries, and one guarded Stop continuation. Codex stable `0.146.0` has actually auto-discovered that directory without relying on a `hooks` manifest field. Source retains the explicit pointer; the deterministic release-package projection removes only that redundant field because the pinned official validator rejects it, while preserving the Hook config. A file on disk or one discovery event still does not prove the full Hook sequence.

Report only the sequence present in the cited fresh-host receipt. The Phase 5 stable receipt observes one CLI turn with `Stop:block`, same-turn repair, and `Stop:allow`; it does not make Hook a cross-process controller or prove every future host build. If a pinned host stops auto-discovering the directory, fail closed and fall back to the shared skill covenant, `ds_lite_iteration.py verify`, and repository validation. Do not claim that Hook can enforce approvals, prevent every indirect Graph edit, or make multiple files transactional.

## Minimal iteration is not exactly-once execution

`ds-lite.iteration.v1` records one running or terminal action with revisions, refs, validations, reflection, stop reason, and user report. It does not yet provide an action envelope, canonical idempotency key, same-key receipt replay, input-conflict detection, or automatic cross-file partial-write repair. An `ambiguous` receipt means stop and ask; it is not permission to retry.

## Matched pilot preparation is not effectiveness evidence

`teaching/lab_runner.py --lab matched-pilot` prepares four cases across plain, scratchpad, and DS Lite arms. Repository tests verify layout, equal input digests, runnable standard-library fixtures, pending result state, and absence of prefilled answers. They do not execute 12 Codex tasks or show that one arm performs better.

Before a real comparison, record the exact model, prompt budget, tools, material digest, timer rule, and cost unit, then obtain explicit authorization for model calls. Use a host sandbox or a separate execution copy for each arm; changing the current directory alone does not prevent access to siblings or instructor files. Report a first pilot descriptively; do not claim statistical significance or promote reserved profiles from one teaching run.

## First authorized matched pilot is blocked

`matched-pilot-20260717-01` used a frozen eight-skill source snapshot, Codex CLI `0.144.5`, `gpt-5.6-sol/low`, separate control/DS Lite homes, and an 18-call serial plan. The first plain engineering process exited 1 after about 767 seconds with a session id but zero tokens, no final message, and no confirmed workspace change. Runtime stopped at `0/18`; WSL numerical arms never ran.

The saved structured events do not identify authentication, model, rate-limit, network, or timeout as the cause, so do not assign a narrower root cause. The pilot remains blocked and must not be resumed or retried. A temporary round-1 session remains in the isolated home because the authorized deletion point was after round 2; do not read, publish, or delete it without separate user direction.

Post-freeze runtime code now hashes and categorizes stderr without storing its text. This improves future diagnosis but cannot repair or reinterpret the blocked run. A future comparison requires a new pilot id, new output roots, a separately verified CLI dependency surface, and renewed execution authorization.

## Isolated skill home is not plugin cache acceptance

The pilot `install` action copies the frozen source snapshot into two isolated `CODEX_HOME` trees: a zero-skill control and a nine-skill DS Lite home. This is a controlled CLI experiment surface only. It does not use `/plugins`, modify the formal Codex cache, or prove that a fresh Desktop task discovers the plugin bundle.

Run `preflight` before any real model call. It must confirm the pinned CLI version, usable authentication category, feature enumeration, zero/nine skill separation, WSL availability, and source digest. A passed preflight permits only one separately authorized canary. The canary receipt is immutable: timeout, failure, ambiguous transport, zero usage, missing feedback, missing tool observation, or missing implicit skill evidence freezes that attempt and must not be retried under the same pilot id.

### Provider route cloning correction (2026-07-20)

The first isolated-home implementation copied only the model name and skill bundle. It did not copy the formal home's non-secret `model_provider`, `model_catalog_json`, or `[model_providers.custom]` route, so model discovery could succeed while a real request used no equivalent provider route. `install_homes` now copies only those validated, non-secret route fields and the referenced relative catalog into each isolated home; it always forces the pilot reasoning effort to `low` and never copies `auth.json`, tokens, headers, or global configuration. The home manifest records only `copied|not-found|invalid` and whether the catalog/route was copied.

This fixes the isolation setup defect; it does not reinterpret the frozen canary `communication-beta2-20260720-gated-01`, whose provider-side `rate-limit` result remains terminal and non-retryable. Any new real request requires a new pilot id and new output roots after an independent provider preflight.

The follow-up pilot `communication-beta2-20260720-gated-02` copied both route and catalog (`status=copied`) and passed preflight with the same pinned CLI and environment authentication category. Its single canary established a thread but ended after 11 seconds with `process-failed` / `transport`, zero usage, zero tools, no terminal turn, and no final feedback. This separates the old configuration defect from a still-unresolved provider/transport availability problem. The receipt is frozen; it is not evidence about Agent wording and must not be retried.

The 2026-07-20 slim isolated-home canary passed this narrower gate: control and DS Lite homes both completed read-only ephemeral model calls with terminal events, final output, usage, and no workspace writes. DS Lite exposed nine current-source skills and added clearer applicability/state/boundary reporting, but this remains an isolated-home result. Do not promote it to formal cache, fresh-host, Hook, full campaign, or release evidence.

## Explainability is a separate acceptance claim

The teaching scorer now separates applicability accuracy, false activation, rationale evidence, verification traceability, user-decision clarity, unsupported completion, and artifact recovery. A skill name in a response is not proof that the plugin was applicable or loaded. The current deterministic tests pass; the planned four-task matched comparison and real host delegation probe remain unverified.

The corrected 2026-07-20 isolated preflight for `cross-task-explainability-20260720-02` passed with Codex `0.144.5`, provider/auth, stable `hooks`/`multi_agent`/`plugins` features, WSL, zero-skill control, and nine-skill DS Lite prompt discovery. Its one implicit canary then established a thread but froze at 180 seconds with redacted `rate-limit`, zero usage, zero tools, no terminal turn, no final feedback, and no workspace change. The receipt is frozen; the 12-case campaign and real delegation probe were not started and must not be inferred from preflight.

The communication contract is now mandatory in the gateway and all narrow skills: every action must expose a start report, progress observations when work is non-trivial, and an end report containing changes, verification evidence, failure layer, unverified items, reflection, and one next action. The deterministic source tests do not prove that a model will follow the contract under provider pressure. A transport-level rate limit can terminate a canary before the first model response, so it provides no evidence about wording quality, implicit skill selection, or artifact behavior. The correct next step is a new pilot id after provider availability is independently confirmed; do not replay the frozen request.

The unified acceptance gate is now attached to pilot receipts under `extensions.acceptance_gate`. It is terminal and fail-closed: `blocked`, `not-verified`, and `ambiguous` cannot unlock the next gate. `communication-beta2-20260720-gated-02` passed source, environment, authorization, and isolated-package gates, then froze its only real canary at the `transport` boundary. Hook host loading, real delegation, and matched comparison were therefore not started. Earlier named pilots that recorded `rate-limit` retain that separate historical classification.

The 2026-07-20 Windows and Bash validation entries completed 169 tests with zero failures; the WSL check compiled the communication/runtime modules and ran the 10 trigger-contract tests. One WSL warning (`Failed to translate 'E:\\PyCharm 2025.2\\bin'`) is host environment noise and is not plugin evidence. These results establish source and cross-shell compatibility only, not fresh-host Hook loading, formal cache installation, or real-agent expression quality.

An isolated home may intentionally omit `auth.json` while the parent process supplies `OPENAI_API_KEY`. In that case `login status` alone can report not logged in even though the CLI has an environment authentication path. Preflight records only `environment-api-key` presence, never the value; the real canary remains the proof of whether the path actually works.

## Windows cmd timeout must terminate the child tree

On Windows, a `.cmd` Codex launcher can create a wrapper process above Node/Codex. Terminating only the wrapper or waiting on its PID can orphan children that retain stdout/stderr pipes, leaving the execution receipt at `running`. The runtime now uses a tree termination on timeout and has a deterministic `.cmd → worker → child` regression test. This improves future cleanup but cannot retroactively terminalize a previously frozen receipt.

The 2026-07-18 E1 canary hit this boundary after establishing a thread but producing no terminal turn, tool event, token usage, or final feedback. The redacted stderr classifier reported `rate-limit`; the exact provider message was intentionally not retained. Do not infer that the process-tree bug caused the provider failure. The original runner finalized a terminal timeout only after its child pipes were closed; the pilot is frozen, not retried, and E2 remains unverified.

## Offline transport evidence is not real-host evidence

`ds-lite.transport-diagnostic.v1` records only normalized classes, HTTP status categories, allow-listed provider codes, connection/header observations, subprocess and pipe states, stderr line count, and stderr SHA-256. Missing observations stay `unknown` or `not-observed`; `thread.started` alone never proves a provider connection. Isolated pilot homes force `request_max_retries=0` rather than inheriting a formal-home retry count.

The standard-library offline harness uses a loopback fake provider and a fake Codex subprocess. It proves deterministic reduction, one-attempt behavior, raw-stderr exclusion, fake Hook behavior, delegation plan/result rules, and matched preparation/failure freezing. It does not prove real Codex/provider wire compatibility, real Hook loading, real child-agent dispatch, matched effect, cache installation, or expression quality. Its receipt always keeps `real_gates_unlocked=false`.

### Fresh wire and CLI gate (2026-07-24)

`communication-beta2-20260724-wire-01` passed the one-request provider Responses
gate: terminal event, nonzero usage (4412), output observed, request count one,
and no automatic retry. `communication-beta2-20260724-gated-cli-02` then passed
the pinned 0.144.5 CLI canary with 26 discovered skills, terminal completion,
final feedback, 16 tool events, usage 77706, and no workspace mutation.

The first new Hook identity was blocked by the host trust policy before process
start because the configured provider destination is not yet approved for
workspace-context export. No workaround or retry was attempted. Real Hook
loading, child-agent delegation, matched effect, formal cache, fresh Desktop,
and release remain frozen until a user explicitly trusts that destination.

### Real wire diagnostic freeze (2026-07-21)

`communication-beta2-20260720-wire-diagnostic-01` and `communication-beta2-20260720-wire-diagnostic-02` used fresh F/G roots and did not read, replay, or modify `communication-beta2-20260720-gated-02`. Both identities passed prepare, route/catalog preflight, pinned Codex `0.144.5` SHA verification, environment authentication category, and DNS/TCP/TLS reachability. The authenticated minimal Responses SSE gate then made exactly one provider request and froze with `http_status_category=4xx`, `connection_state=established`, `response_header_state=received`, no terminal event, zero usage, no output, no automatic retry, and no persisted raw response, endpoint, prompt, or credential. After the reducer correction, the supported failure layer is `protocol`.

This rules out local DNS/TCP/TLS failure for that attempt and rules out the earlier isolated-route omission as the current blocker. It does not prove Codex CLI wire compatibility, Hook host loading, real child-agent dispatch, matched effect, formal cache loading, or Agent expression improvement. The next authorized investigation should focus on provider/model/parameter acceptance for the configured Responses route, using a new diagnostic identity and one request per hypothesis.

### Wire and fresh-host follow-up (2026-07-21)

`communication-beta2-20260720-wire-diagnostic-03` passed the fresh Responses probe with HTTP 200, a terminal `response.completed` event, nonzero usage, and one provider request. The first CLI canary `communication-beta2-20260720-gated-03` still froze at an authenticated 4xx; the isolated route had no `env_key`. The route fix now injects the non-secret `env_key=OPENAI_API_KEY` while keeping `requires_openai_auth=true` and both retry limits at zero. A new one-shot canary `communication-beta2-20260720-gated-04` passed with Codex `0.144.5`, `turn.completed`, final feedback, 14 tool events, and nonzero usage. Its process diagnostic still contains classified stderr noise despite success; this is diagnostic residue, not a gate failure.

The fresh host package `communication-beta2-20260720-host-01` was registered in an isolated `CODEX_HOME` and installed through the real `codex plugin marketplace` / `plugin add` commands. The candidate version, local source, nine-skill cache, and `hooks/hooks.json` were observed. A subsequent fresh CLI task produced no JSONL events and was frozen without retry; the failure layer is `fresh-cli-host / process-start-or-auth`, not a proof of Hook behavior. Real Hook loading, fresh Desktop loading, child-agent dispatch, matched effect, and release readiness therefore remain unverified. Its redacted receipt is `host-01/results/host-cli.json` within the fresh evidence root.

### Context handoff and CLI boundary management (2026-07-22)

The plugin now has machine-checkable `ds-lite.handoff.v1` and `ds-lite.cli-compatibility.v1` projections. They make long-context authority, non-secret configuration, evidence refs, shell surface, quoting/encoding/path failures, `.cmd` child state, and pipe closure explicit without storing transcripts, raw commands, prompts, credentials, or hidden reasoning. This improves management of common CLI failures; it does not prove a particular fresh host or Desktop task will succeed.

### Fresh host probe freeze (2026-07-22)

The new `communication-beta2-20260720-host-02` identity installed the candidate through an isolated marketplace and ran exactly one `fresh_host_probe` request. The process started and exited, both pipes closed, no timeout occurred, and zero JSONL events or terminal events were observed. The redacted diagnostic classified the shell boundary as `unknown`; the raw output was not retained and the identity is frozen. This is stronger process evidence than host-01, but it still does not identify the provider/CLI message or prove Hook loading. A new host identity and a narrower model-free/process hypothesis are required before another external request.

The fresh `communication-beta2-20260720-host-03` identity is limited to model-free CLI-start checks. `--version`, `features list`, and `plugin list --json` each started once, returned an observable exit, and closed both pipes; the receipt records no external model request and no raw output. This does not prove that a candidate plugin was installed or loaded, nor does it unlock Hook, Desktop, delegation, matched effect, formal cache, or release gates. Receipt: `.validation-tmp/communication-beta2-20260720-host-03/model-free.json`.

The fresh `communication-beta2-20260720-host-04` identity repeated the model-free checks with pinned Codex `0.144.5` (SHA-256 `EFDB3540EF74B9909408C8D38DA79483454797B36F471E3E004FC2BF2B70E22A`). Version, features, and plugin-list processes all started once, exited observably, and closed both pipes. The receipt proves pinned CLI-start only; it does not prove candidate plugin installation or Hook loading. Receipt: `.validation-tmp/communication-beta2-20260720-host-04/model-free.json`.

The fresh `communication-beta2-20260720-host-05` identity installed `0.5.0-beta.1` through the isolated marketplace and observed nine skills plus the Hook manifest. One pinned CLI task then exited with code 2 before any `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, or `Stop` receipt was produced. Raw output was not retained, no retry was attempted, and the identity is frozen. Receipt: `.validation-tmp/communication-beta2-20260720-host-05/hook-host.json`.

Static `codex exec --help` inspection then showed that `0.144.5` does not support `--ask-for-approval`; the probe also lacked `--skip-git-repo-check`. The wrapper was corrected without replaying host-05. Fresh host-06 installed the same candidate, and one real task produced a `UserPromptSubmit` receipt before timing out. No PreToolUse, PostToolUse, or Stop receipt was observed. This proves partial Hook loader invocation but not the complete event sequence. Receipt: `.validation-tmp/communication-beta2-20260720-host-06/hook-host.json`.

Host-07 additionally verified that provider route TOML must be composed before marketplace/plugin tables; appending root keys after a table changes their TOML scope. Its corrected model-free checks passed with pinned `0.144.5`, candidate `0.5.0-beta.1`, nine skills, and the Hook manifest. A real provider task was blocked by the execution policy because it would send workspace context to an untrusted external destination. This policy block is not evidence for or against Hook loading.

The fresh offline acceptance `offline-acceptance-20260722-host-boundary` passed all fake transport scenarios and the fake Hook/delegation/matched-preparation protocols. Its scope is explicitly fake-provider/fake-Codex only; it does not unlock any real host, Desktop, child-agent, effect, cache, or release gate.

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

`$ds-lite-iterate` is a one-round worker checkpoint, not autonomous background research. It must stop after one action, verification, reflection, user report, terminal receipt verification, and Mission Board update.
# Cross-system execution surface

- PowerShell 5.1 can misread non-ASCII no-BOM scripts. Executable entrypoints
  must remain ASCII and delegate to Python CLIs via argv.
- The managed validation environment may deny child creation under
  `.validation-tmp`; affected tests must be recorded as `not-observed` or
  `skip`, never upgraded to a pass.
- Existing mixed-line-ending files and legacy wrapper bytes are surfaced by
  `check_text_compatibility.py` and require explicit maintenance cleanup.

## Current Responses wire freeze (2026-07-23)

The fresh identities `communication-beta2-20260723-loop-wire-02`, `communication-beta2-20260723-loop-wire-03`, and `communication-beta2-20260723-loop-wire-04` were independent one-request diagnostics. The baseline request received HTTP 400/4xx; adding only the Codex Responses Lite header kept HTTP 400/4xx; changing only `input` to the Codex `message[]` shape changed the response to HTTP 502/5xx. All three had an established connection, received response headers, no terminal event, zero usage, one provider request, and no automatic retry.

The 502 is evidence that the request reached a different provider execution layer, not evidence of success. The wire gate remains blocked at `protocol`. Codex `rust-v0.144.5` source was read only to compare request construction: `use_responses_lite` adds a dedicated header, uses a `ResponseItem` array, and sends `store=false` for non-Azure routes. CLI canary, real Hook loading, Desktop, child-agent dispatch, matched effect, formal cache, and release gate remain unverified.

The local regression suite now runs `289/289` tests. An offline-only `codex-lite-minimal` profile is available for the next fresh diagnostic; it has not been sent to the real provider. Validation shell and runtime templates no longer embed Python source through `python -c`; they parse `python --version` in shell before invoking formal Python CLIs.

## Real Hook host partial evidence (2026-07-23)

The fresh pinned 0.144.5 host in `trusted-hook-05` emitted real UserPromptSubmit, PreToolUse, and PostToolUse receipts, while the task ended at `turn.failed` before the required PreToolUse block and Stop block/allow sequence. This is partial loader evidence only. Do not describe it as complete Hook acceptance or unlock real delegation, matched effect, formal cache, Desktop, or release. See `docs/maintainers/real-hook-acceptance-20260723.zh.md`.

The older note saying that no CLI canary was created is historical for the earlier wire-blocked stage. The later fresh `communication-beta2-20260723-loop-wire-05` Responses probe and `communication-beta2-20260723-gated-cli-01` canary passed their respective gates; this does not rewrite any older receipt or unlock the blocked Hook and downstream gates.
