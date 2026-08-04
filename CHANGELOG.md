# Changelog

## 2026-08-04: v6 mechanisms, compatibility fixes, and teaching area restructure

- Implemented five missing v6 mechanisms:
  - M04 Memory Layers (ds_lite_memory_layers.py): Five-layer M0-M4 with per-layer write permissions
  - M05 Memory Card v2 (ds_lite_memory_card_v2.py): Reviewed project-level memory cards
  - M09 Task Router (ds_lite_task_router.py): Routes task kinds to minimal sufficient Skill combinations
  - M13 Operator Levels (ds_lite_operator_levels.py): O0-O7 grading with per-level authorization
  - M22 Method Fidelity Manifest (ds_lite_method_fidelity.py): Records original method, adaptations, and code identity
- Fixed cross-platform compatibility: dynamic Python interpreter resolution via DS_LITE_PYTHON env var
- Fixed BOM test to properly prune temp artifact directories
- Created teaching area AGENT restructure: AGENT_GUIDE.md, agent_recovery_scenarios/
- Created test_flexibility.py (15 tests), test_encoding.py (8 tests), test_hook_triggers.py (13 tests)
- Bumped versions: Core/Academic 0.9.0-beta.1 -> 0.9.0-beta.1, Web/Knowledge/Empirical/Engineering 0.3.0-alpha.1 -> 0.3.0-alpha.1
- Updated compatibility.json to use semver ranges (>=) instead of exact pins
- All 28 v6 mechanism tests pass, all 17 compatibility tests pass



## 2026-08-04: Skills aggregation, public/private boundary, and documentation polish

- Added three aggregated Academic skills: `nature-literature` (search + citation + ref-verifier),
  `nature-review` (reviewer + response), and `nature-convert` (paper2ppt + paper-to-patent).
  Original skills remain as sub-routes; functionality is preserved.
- Audited public/private file boundaries. Marked `docs/maintainers/`, `PROJECT.md`,
  and `evaluation/` as private in `.gitignore`.
- Updated README.md, README.zh.md, NOTICE, ACKNOWLEDGMENTS.md, PACKAGE.md, and
  docs/README.md to reflect official DeepScientist plugin positioning.
- Added Skills trigger matrix and dependency graph documentation.
- Added Skills functional overlap audit and aggregation refactoring plan.
- Added External projects annotation for conversation `019fcaa5`.
- Added Public/private file boundary audit.

## Unreleased: 0.9.0-beta.1 foreground autonomy controller

- Added `ds-lite.autonomy-contract.v1`, progress receipts, a dependency-aware
  foreground gate controller, and bounded three-attempt transient retry.
- Added `ds-lite.loop-contract.v2` autonomy controls while retaining v1 callers.
- Enabled the fixed `codex-autoresearch` compatibility adapter to use DS Lite's
  pinned Codex session/resume contract without persisting upstream raw logs.
- Extended Hook context and Stop checks so active autonomy contracts cannot end
  without a terminal summary and current progress receipt.

- Added `ds-lite.autonomy-contract.v1`, progress receipts, a dependency-aware
  foreground gate controller, and bounded three-attempt transient retry.
- Added `ds-lite.loop-contract.v2` autonomy controls while retaining v1 callers.
- Enabled the fixed `codex-autoresearch` compatibility adapter to use DS Lite's
  pinned Codex session/resume contract without persisting upstream raw logs.
- Extended Hook context and Stop checks so active autonomy contracts cannot end
  without a terminal summary and current progress receipt.

## Unreleased: 0.8.0-beta.1 core/academic and 0.3.0-alpha.1 optional packs

- Split the marketplace into six packages while keeping the `deepscientist-lite`
  Core ID and freezing the historical monolith at `0.6.0-beta.1`.
- Advanced Core and Academic to `0.8.0-beta.1` without adding a Core discoverable skill. Added
  citation check and batch envelopes, Crossref/OpenAlex/Semantic Scholar/arXiv
  adapters, terminal-status cache policy, bounded revision constraints, and
  fresh-context adversarial-review receipts.
- Added `deepscientist-lite-empirical` and
  `deepscientist-lite-engineering` `0.3.0-alpha.1` packages. Each has one
  router, exact Core compatibility, a standard-library validator, and no
  vendored runtime.
- Added eight deterministic installation matrices, domain validation wrappers,
  explicit Academic live-provider authorization entrypoints, upstream commit /
  license / hash adoption records, and user/maintainer protocol documentation.
- Web CLI now requires an explicit repeated `--allowed-domain` scope for every
  fetch/search/render/benchmark run, checks redirects and provider results,
  writes v2 source records, and classifies provider authorization, policy,
  network, and render failures without storing credentials.
- Offline and source validation pass for the new work. Real provider, Hook,
  delegation, matched effect, formal cache, fresh Desktop, and release gates
  remain `not-verified`; the full historical unittest run was not used to
  infer these host gates.

## Unreleased: 0.6.0-beta.1 candidate

- Added the complete 17-skill `nature-skills` snapshot at commit
  `91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b`, bringing the candidate to 26
  discoverable skills while keeping `nature-shared` internal.
- Added workspace-only Nature onboarding for MCP, external APIs, browser,
  downloader, LaTeX, Node, and Python dependencies. It reports missing
  configuration without reading or persisting secret values.
- Added the authorized `codex-autoresearch` fixed snapshot and a bounded,
  redacted adapter. The adapter does not execute the upstream runner until a
  compatible child-output contract is verified.
- Added `upstream_manager.py`, the upstream registry, provenance audits, and a
  weekly read-only GitHub Actions check. It produces update plans but never
  overwrites vendor sources or publishes changes.
- Fixed cross-system validation so binary assets and immutable vendor snapshots
  are not misclassified as text, and JSON diagnostics remain printable under
  legacy Windows code pages.
- Offline nature, adapter, loop, cross-system, and repository checks remain
  source-level evidence. Real provider, Hook, Desktop, delegation, matched
  effect, formal cache, and release gates remain locked.
- Verified the current candidate with the unified Windows entry: `304/304`
  unittest cases passed, the repository validator and `py_compile` passed, and
  cross-system compatibility scanned 1465 files with zero failures. Bash,
  PowerShell 7, and shellcheck were recorded as `not-observed` where absent.

## Cross-system reliability

- Added a fresh DS Lite Hook-host fixture and argv-only PowerShell/Bash launchers. The real `trusted-hook-05` run records partial loader evidence and remains fail-closed because the required block and Stop continuation were not observed.
- Recorded the current real gate state in `docs/maintainers/real-hook-acceptance-20260723.zh.md`; fake and offline results do not unlock delegation, matched effect, formal cache, Desktop, or release.

- Added the unified `ds-lite.cross-system-validation.v1` validator and clean
  trusted-hook wrapper entrypoints.
- Removed embedded `python -c` version probes from validation shell and runtime templates; version checks now use `--version` with shell-side numeric parsing.
- Added explicit Responses probe variants for the Codex Lite header and message-array input, with one-attempt and redaction regression coverage.
- Added an offline-only `codex-lite-minimal` request profile that records the Codex Lite header, `ResponseItem[]`, reasoning, include, text, and tool-control fields without enabling a real provider call.

## Unreleased

- Add `ds-lite.handoff.v1` for redacted long-conversation, resume, and child-task handoffs. Receivers must verify the digest, authorization boundary, authoritative configuration, relative evidence refs, failure layer, and one next action before acting.
- Add `ds-lite.cli-compatibility.v1` for PowerShell/cmd/Git Bash/WSL boundary diagnostics covering quoting, escaping, encoding, PATH, WSL translation, `.cmd` child processes, and stdout/stderr pipes without persisting raw commands or output.
- Add a one-shot fresh-host probe that terminalizes zero-event, timeout, pipe, and nonzero-exit processes into a redacted receipt and refuses retry or overwrite.
- Record fresh host-02 as a frozen zero-event CLI probe with closed pipes and no timeout; do not infer a provider message or Hook loading from the redacted `unknown` class.
- Add fixed in-memory CLI boundary reduction for auth, path, quoting, encoding, wrapper, protocol, timeout, and unknown failures; record fresh host-03 as CLI-start passed only.
- Record fresh host-04 as pinned Codex 0.144.5 model-free CLI-start passed; no later host or release gate is unlocked.
- Record fresh host-05 marketplace installation and frozen zero-event Hook host task; do not infer Hook loading from manifest or cache presence.
- Correct the pinned 0.144.5 exec wrapper flags and record host-06 partial Hook loader evidence (`UserPromptSubmit` only) followed by timeout; complete Hook acceptance remains frozen.
- Record host-07 root-level TOML and model-free checks; real provider Hook execution remained policy-blocked and did not unlock any release gate.
- Add trusted-host continuation scripts with pinned SHA verification and redacted Hook event summaries for execution in an explicitly trusted tenant surface.
- Add a parameter-light Windows launcher that prepares a fresh trusted Hook host without touching formal Codex state.
- Add a selective Superpowers adaptation reference for skill checks, short plans, TDD, bounded actions, verification, and explicit handoffs. It intentionally excludes daemon, MCP, hidden state, unbounded loops, and automatic retry.

- Add Responses wire diagnostics with exact status/category, redacted error shape, terminal/usage observations, request-id hashes, and a static Codex wire-shape comparison without retaining raw responses.
- Preserve `requires_openai_auth`, force `env_key=OPENAI_API_KEY` for the authenticated isolated route, and keep request/stream retries at zero. Record `wire-diagnostic-03` as provider-compatible and `gated-04` as a successful CLI canary after `gated-03` froze at an authenticated 4xx.
- Record the isolated real marketplace installation for `communication-beta2-20260720-host-01`; its candidate cache and Hook manifest were observed, but a fresh CLI task emitted no JSONL events and froze. Do not treat this as Hook loading, Desktop host, delegation, matched-effect, or release evidence.

- Add a ninth `$ds-lite` gateway that recognizes new or existing research/engineering workspaces, explains why the plugin is intervening, and routes to exactly one action skill.
- Add a shared seven-rule responsible-exploration covenant and `start / progress / end` feedback protocol across all nine skills.
- Add the minimal `ds-lite.iteration.v1` init/finalize/verify lifecycle with one bounded action, revision checks, terminal reflection, user report, and fail-closed ambiguous status; this is not an exactly-once transaction.
- Project `latest_iteration` and a derived hypothesis pool into the Mission Board without replacing Graph v2 or allowing Factor Cards to promote evidence.
- Add source-tested plugin-local Hook helpers for redacted Mission attachment, deterministic pre-tool blocks, post-tool checks, and one guarded Stop continuation; fresh-host Hook loading remains not verified and the manifest does not declare hooks.
- Add redacted pilot progress heartbeats and fake success, silence, timeout, failure, and ambiguous canaries without retaining prompts, raw event streams, stderr, or tool arguments.
- Add `ds-lite.transport-diagnostic.v1` with allow-listed HTTP/provider classification, connection/header observations, subprocess exit causes, child/pipe states, and fixed redacted summaries while retaining the legacy stderr category/count/SHA-256 fields.
- Correct real Responses `4xx` reduction so provider-side protocol failures are no longer reported as child-process failures when a response header is observed but no terminal event or usage is produced.
- Force isolated pilot provider routes to `request_max_retries=0`; add a fresh-only loopback fake-provider/fake-Codex acceptance suite for success, auth, rate-limit, network, malformed response, child early exit, and ambiguous transport.
- Add offline Hook, delegation, and matched prepare/freeze acceptance claims that remain explicitly fake/protocol-only and can never unlock real host, provider, cache, comparison, or release gates.
- Add explicit `preflight` and one-shot implicit `canary` gates, require fresh pilot ids and authorization refs, pin Codex CLI `0.144.5`, verify zero-skill control versus nine-skill isolated homes, and refuse the frozen 2026-07-17 pilot id.
- Rename the pilot `install` evidence to `isolated-skill-home`; it does not verify plugin cache installation. Acceptance records now keep only relative refs, source digests, dirty-snapshot state, and redacted host probe summaries.
- Classify inherited `OPENAI_API_KEY` presence without persisting its value, and terminate Windows `.cmd` child process trees before finalizing timeout receipts.
- Record the 2026-07-18 E1 preflight as passed but its single implicit canary as a frozen timeout: thread established, redacted `rate-limit` diagnostic, zero tokens/tools, no terminal turn or feedback, and no workspace change. Do not claim implicit triggering or proceed to E2.
- Record the 2026-07-20 slim isolated-home plugin-effect canary: zero-skill control and nine-skill current-source DS Lite homes both completed read-only ephemeral calls with terminal events, final output, usage, and no workspace writes; DS Lite added clearer applicability/state/boundary reporting at higher token/time cost, while formal cache, fresh host, Hook loading, full campaign, matched A/B, delegation, and release gates remain unverified.
- Add the teaching-layer explainability scorer and regression coverage for applicability accuracy, false activation, rationale evidence, verification traceability, user-decision clarity, unsupported completion, artifact recovery, delegation approval, path ownership, and result refs. Real four-task matched comparison and host subagent dispatch remain separate acceptance gates.
- Record the corrected 2026-07-20 isolated preflight as passed and its one implicit canary as frozen at 180 seconds with redacted `rate-limit`, zero usage/tools, no terminal turn/final feedback, and unchanged workspace; do not retry or start the matched campaign/delegation probe from this receipt.
- Add the action-and-reflection student/instructor lab, shared worksheet fields, OpenScience supervisor example, and maintainer philosophy/architecture guidance.
- Pin DeepScientist V2 `v2.1.8` provenance and record an AGPL-isolated, case-to-core transfer audit without copying upstream code, schema, or skill text.
- Add a strict `ds-lite.matched-pilot-execution.v1` record, frozen-source preparation, isolated control/DS Lite homes, fixed 18-call ordering, online JSON event reduction, and fail-closed resume behavior.
- Add cross-platform `run_pilot.ps1` / `run_pilot.sh` entry points and an artifact-only scorer that marks automatic results as awaiting blind review or incomplete.
- Record the first authorized real pilot as blocked at `0/18` after the initial Codex process failed with zero tokens and no result; do not claim an arm comparison or `0.5.0-beta.1` readiness.
- Preserve only a sanitized stderr category, line count, and SHA-256 in future failed receipts; raw stderr, event JSONL, hidden reasoning, secrets, and workstation roots remain excluded.
- Add the domain-neutral Scientific Factor Card protocol and `ds-lite.factor-card.v1` validator/template.
- Teach `$ds-lite-idea` to compare six evidence-linked factors and run `validate-factor-card` without creating a weighted total or promoting the card as evidence.
- Extend `$ds-lite-review` to reject unsupported novelty scores, reversed cost/risk semantics, and Factor Card claims that bypass typed evidence.
- Add the explicitly approved `$ds-lite-coordinate` skill for one bounded delegation of at most three independent tasks.
- Add `ds-lite.delegation.v1`, its strict standard-library validator, template, runtime protocol, ownership/approval/result rules, and negative fixtures.
- Keep coordination file-led and parent-integrated: no daemon, queue, scheduler, nested delegation, background worker ownership, or automatic retry.
- Mark fresh-agent coordination behavior as pending a separately authorized forward test; static schema and repository validation do not prove host-side delegation behavior.
- Add a deterministic matched-control teaching builder for four engineering/research cases across plain, single-scratchpad, and DS Lite arms.
- Add staged continuity prompts, runnable standard-library math/numerical fixtures, equal-input digests, pending result refs, a unified rubric, and separate student/instructor guidance.
- Keep real 12-arm Codex execution and scoring behind explicit authorization; preparation smoke does not claim effectiveness, statistical significance, or reserved-profile support.
- Keep node update timestamps monotonic across transient WSL/virtualized wall-clock regressions without weakening Graph validation.

## 0.4.0-beta.2

- Add `mission` and `render-status` state CLI commands that project Graph v2 into a user-visible Mission Board.
- Display Evidence Pack metric direction, thresholds, budgets, and early/final/aggregate metric surfaces in the Mission Board.
- Add the `ds-lite-iterate` skill for exactly one bounded worker iteration with a required frontier decision artifact.
- Add OpenScience worker handoff documentation for supervisor-driven Codex worker tasks.
- Update `STATUS.md` to show active route, next action, candidate queue, rollback targets, validation state, and readiness rules.
- Record AIResearch-derived readiness rules: artifact is not progress, ready is not done, idea is not experiment, metric errors are protocol failures, and invisible loops are not agent experience.
- Extend repository smoke coverage to verify mission JSON/Markdown, render-status, rollback, blocked branch visibility, and off-route warnings.
- Add an `external long-task stewardship` protocol for append-only runtime handoffs, recovery evidence, and duplicate-submission checks; this is a Codex behavior constraint, not background scheduling capability.
- Add a `manual tmux capacity handshake`: Codex plans named slots and exact bootstrap commands, the user creates the top-level tmux surface, and Codex verifies it before launching pane-scoped CLI workers.
- Add `ds-lite.work-unit.v1` planning and claim-bearing sidecars without changing Graph v2.
- Require typed Evidence Pack validation before `has-evidence`; ordinary artifacts, logs, and non-empty paths no longer promote evidence strength.
- Add the domain-neutral `ds-lite.review-result.v1` typed review result with separate review `verdict` and `claim_assessment`, plus Mission Board claim readiness and evidence detail.
- Scope `waiting_for_user` to the active route while preserving off-route blocked warnings and debt.
- Keep the Lite boundary unchanged: no daemon, MCP, Web/TUI, hooks, or long-running scheduler.
- Publish this version as a source/package prerelease; fresh Codex cache installation remains a separate, unverified acceptance surface.

## 0.3.0-beta.1

- Add standard-library Evidence Pack v1 contracts, manifests, hashing, and strict verification.
- Add the `ds-lite-review` skill and `review` Graph v2 node kind between experiment and analysis.
- Gate new analysis/write work on a passing review without breaking existing Graph v2 files.
- Add 45/90-minute evidence-chain and scored-branch teaching labs, worksheets, rubric, and answer key.
- Replace outline-only teaching material with a cross-platform six-lab runner, student/reference modes, guided prompts, observable failures, and beginner-facing course notes.
- Rewrite the Chinese quick start and add a user guide plus writing rules that explain mechanisms without overstating what Graph, Evidence Packs, or review can prove.
- Document which platform recommendations were adopted, deferred, or rejected to preserve the Lite boundary.
- Keep generated teaching `STATUS.md` synchronized with the final Graph active node and revision.
- Require portable review/experiment shell scripts that resolve plugin tooling through environment variables instead of persisting workstation or Codex cache paths.
- Record real Codex skill-trigger acceptance evidence and the remaining local-marketplace cache blocker.
- Add fresh-output-only Codex acceptance preparation and audit tools that separate marketplace registration, installation, and skill discovery evidence.
- Generate portable project shell entry points from a shared runtime resolver instead of placeholder scripts or saved cache paths.
- Add `validate --strict --scope active-route`, keeping structural errors global while reporting preserved branch warnings separately.
- Add `ds-lite.teaching-handoff.v1` so Graph, STATUS, active route, revision, and blocked follow-ups can be checked together.

## 0.2.0-beta.1

- Upgrade the research state protocol to `ds-lite.graph.v2` with revisions.
- Add cross-platform locking, atomic writes, stale-map detection, and v1 migration backups.
- Add `update-node`, `set-status`, `link-path`, and progression-aware trace modes.
- Enforce project-relative or symbolic external paths and expand semantic validation.
- Make `assets/templates/` the initialization source of truth.
- Add standard-library unit tests and Windows/Ubuntu CI.
- Make CLI and validation subprocess output independent of the Windows system code page.
- Add project memory, licensing, migration, attribution, and independent-project notices.

## 0.1.4

- Package the five-skill teaching beta and repository validation flow.
- Add Unicode-safe intake inputs, teaching material, and release-maintainer documentation.
- Add a redacted, fail-closed acceptance gate helper and attach its terminal decision to pilot receipts under `extensions.acceptance_gate`; a blocked real canary cannot unlock Hook, delegation, or matched-comparison gates.
- Record `communication-beta2-20260720-gated-02`: source/environment/preflight and isolated cachebuster package passed; the single real implicit canary froze before final feedback with a redacted `transport` category, so host Hook loading, real delegation, and matched comparison remain unverified. Earlier named `rate-limit` pilots retain their original classification.
# 2026-07-23

- Added argv-only trusted-host preparation and Hook runner CLIs.
- Added text encoding, line-ending, NUL, replacement-character, JSON/TOML and
  shell-boundary checks; real provider and release gates remain fail-closed.

