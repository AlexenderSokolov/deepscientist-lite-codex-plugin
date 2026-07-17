# Product Positioning And Long-Term Memory

## Primary Work

DeepScientist Lite is a Codex plugin project. Its primary goal is to make the core DeepScientist research protocol teachable and usable without deploying the full DeepScientist platform.

The plugin is the main product. Teaching cases and small experiments are validation material, not the product itself.

## What Counts As Plugin Progress

- Skills are discoverable, triggerable, and concise.
- The file protocol is easy to initialize in a new or existing research project.
- `ds_lite_state.py` keeps state traceable without hidden chain-of-thought.
- Users can recover from install/cache/encoding failures.
- A teacher can explain the core workflow in 20-30 minutes and run evidence/review labs in 45 or 90 minutes.
- A student can run a one-stop project loop and inspect the route afterward.

## What Experiments Are For

Experiments validate whether the plugin helps preserve research state, failures, and claims. They can be used as teaching demos, but they should not redefine the plugin as an algorithm benchmark repository.

The sanitized paradigm-comparison teaching case demonstrates how DS Lite records a real route: source audit, idea choice, experiment result, negative evidence, and next-step reasoning.

## Current Release Judgment

`v0.4.0-beta.2` is the worker-protocol source/package beta. It keeps Graph v2 and Evidence Pack v1, adds Mission Board projections, `mission` / `render-status`, a seventh `$ds-lite-iterate` skill, and OpenScience worker handoff guidance. Source/package validation is release evidence; fresh cache installation, all seven skills in a new thread, and one installed bounded iterate checkpoint remain explicitly unverified.

P0 source validation covers `ds-lite.work-unit.v1`, typed Evidence Pack promotion, `ds-lite.review-result.v1`, claim readiness, evidence detail, and route-scoped waiting. This remains source/package evidence only: the installed cache remains unverified and must not be inferred from the source tree. P1 action/receipt and P2 typed external-long profile are not part of this P0 claim.

The unreleased v0.5 source branch adds a domain-neutral `ds-lite.factor-card.v1` and an eighth `$ds-lite-coordinate` skill backed by `ds-lite.delegation.v1`. Their schemas, templates, CLI validation, negative fixtures, skill metadata, and repository anchors are source-testable. Fresh-agent Factor Card behavior, real child-task dispatch, host-enforced path scope, and new-thread eight-skill discovery remain not verified until separately authorized acceptance runs are recorded.

The manual tmux capacity handshake remains pending release evidence until a user-created fixed-socket surface survives a real disconnect/reconnect probe, a missing socket causes a clean stop without `new-session`, and a pane-scoped Codex CLI child worker records provider query/resume evidence separately from tmux and experiment recovery.

The previous `v0.3.0-beta.1` evidence-review teaching beta remains useful historical evidence: on 2026-07-05, 36 local tests, the repository smoke, Windows PowerShell, Git Bash, the plugin validator, and all six v0.3 skill validators passed. That evidence does not prove v0.4 cache installation or `$ds-lite-iterate` behavior. See the [hardening log](v0.3-hardening-log.zh.md) and [Codex acceptance audit](v0.3-codex-acceptance.zh.md). Remote CI for the new commits, explicit cache installation, completion of the main review/analysis/iterate recovery route, independent teaching reports, macOS verification, and repeatable cache-upgrade recovery remain release evidence.

## Long-Term Memory Rules

- Keep durable plugin decisions in this file, `known-issues.md`, `release-checklist.md`, README, and case studies.
- Keep algorithm experiment details inside the case study or the host research project.
- Do not add MCP, daemon, hooks, or Web/TUI unless the product goal explicitly changes.
- Treat teaching-case results as evidence for teaching value, not as a release blocker unless they expose a plugin workflow failure.
