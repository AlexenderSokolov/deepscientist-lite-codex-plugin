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

`v0.3.0-beta.1` is the evidence-review teaching beta. It keeps Graph v2 and Evidence Pack v1, and adds beginner-facing Chinese documentation plus six runnable teaching labs with separate student/reference modes. The post-acceptance hardening pass added isolated acceptance tooling, portable generated scripts, active-route strict validation, and machine-checkable teaching handoffs. On 2026-07-05, 36 local tests, the repository smoke, Windows PowerShell, Git Bash, the plugin validator, and all six skill validators passed. The current host has no registered WSL distribution, so the earlier 2026-07-04 DrvFS/ext4 evidence has not yet been repeated after these fixes. The local acceptance package is structurally valid, but `codex-cli 0.128.0` cannot list the marketplace and therefore does not prove cachebuster installation. See the [hardening log](v0.3-hardening-log.zh.md) and [Codex acceptance audit](v0.3-codex-acceptance.zh.md). Remote CI for the new commits, explicit cache installation, completion of the main review/analysis recovery route, independent teaching reports, macOS verification, and repeatable cache-upgrade recovery remain release evidence.

## Long-Term Memory Rules

- Keep durable plugin decisions in this file, `known-issues.md`, `release-checklist.md`, README, and case studies.
- Keep algorithm experiment details inside the case study or the host research project.
- Do not add MCP, daemon, hooks, or Web/TUI unless the product goal explicitly changes.
- Treat teaching-case results as evidence for teaching value, not as a release blocker unless they expose a plugin workflow failure.
