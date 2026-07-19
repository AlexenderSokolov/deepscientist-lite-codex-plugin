# Changelog

## Unreleased

- Add the domain-neutral Scientific Factor Card protocol and `ds-lite.factor-card.v1` validator/template.
- Teach `$ds-lite-idea` to compare six evidence-linked factors and run `validate-factor-card` without creating a weighted total or promoting the card as evidence.
- Extend `$ds-lite-review` to reject unsupported novelty scores, reversed cost/risk semantics, and Factor Card claims that bypass typed evidence.

## 0.5.0-beta.2

- Re-import all 39 files from the three fixed humanizer commits as byte-verified, non-runtime audit snapshots and reduce the public adoption matrix to its fixed nine fields.
- Add `ds-lite.communication-audit.v1` with `init`, `record-check`, `record-claim`, `finalize`, `validate`, and `render`; claims, protected-content hashes, eight `honor-*` checks, self-audit phases, and handoff are deterministic gates.
- Close finalized communication receipts against later CLI writes and retain a second hash for the redacted command text so command evidence cannot be silently rewritten.
- Expand the seven skills with the three-phase self-audit contract and explicit reflection/reporting requirements without adding a skill or changing Graph, Evidence Pack, or Work Unit schemas.
- Add the optional four-event hook adapter and confirmation-only installer. Missing/invalid/closed audits, unsupported completion claims, direct Graph writes, destructive commands, and unprocessed iteration failures are blocked; `stop_hook_active` cannot convert a failure into success.
- Replace the twelve A/B labels with complete fixed inputs containing Chinese/English prose, numbers, citation keys, commands, JSON, expected protected strings, profiles, and semantic fields. The cases remain `runtime_loaded: false`.
- Bump the plugin and documentation release line to `0.5.0-beta.2`; source tests and isolated package tests are evidence, while fresh cache, new-thread, real-host hook registration, and human A/B remain manual gates.
- Record the 2026-07-19 cross-platform source validation and isolated installation. The real CLI canary timed out without a final event, so fresh-agent communication and matched A/B remain explicitly unverified.

## 0.5.0-beta.1

- Add an optional project-root `STYLE.md` contract with four built-in communication profiles and custom extension points.
- Add a progressively loaded communication core, Chinese/English humanization overlays, and conservative academic-writing rules without changing Graph, Evidence, Work Unit, or review schemas.
- Preserve code, commands, paths, structured data, logs, metrics, formulas, citations, and formal definitions; add the eight engineering principles as operational guidance.
- Add runtime MIT notices and source references for the three selectively adapted humanizer projects; no upstream workflow or dependency is bundled.
- Extend repository and isolated acceptance validation with fixed communication references, twelve A/B prompts, and an anonymous scoring worksheet.
- Keep the release gate manual: fresh cache, new-thread skill discovery, four-profile behavior, and human A/B results are not claimed until observed.

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
