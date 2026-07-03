# Product Positioning And Long-Term Memory

## Primary Work

DeepScientist Lite is a Codex plugin project. Its primary goal is to make the core DeepScientist research protocol teachable and usable without deploying the full DeepScientist platform.

The plugin is the main product. Teaching cases and small experiments are validation material, not the product itself.

## What Counts As Plugin Progress

- Skills are discoverable, triggerable, and concise.
- The file protocol is easy to initialize in a new or existing research project.
- `ds_lite_state.py` keeps state traceable without hidden chain-of-thought.
- Users can recover from install/cache/encoding failures.
- A teacher can explain the workflow in 20-30 minutes.
- A student can run a one-stop project loop and inspect the route afterward.

## What Experiments Are For

Experiments validate whether the plugin helps preserve research state, failures, and claims. They can be used as teaching demos, but they should not redefine the plugin as an algorithm benchmark repository.

The sanitized paradigm-comparison teaching case demonstrates how DS Lite records a real route: source audit, idea choice, experiment result, negative evidence, and next-step reasoning.

## Current Release Judgment

`v0.2.0-beta.1` is the reliability-focused teaching beta. Graph v2 adds revisions, locked atomic writes, migration backups, portable external paths, semantic validation, and progression-aware tracing. Local Windows PowerShell, Git Bash, WSL DrvFS, WSL ext4, and the remote Windows/Ubuntu CI matrix passed on 2026-07-02; see the [Windows/WSL audit](v0.2-audit.zh.md). Stable release still requires independent installation reports, macOS verification, and repeatable cache-upgrade recovery.

## Long-Term Memory Rules

- Keep durable plugin decisions in this file, `known-issues.md`, `release-checklist.md`, README, and case studies.
- Keep algorithm experiment details inside the case study or the host research project.
- Do not add MCP, daemon, hooks, or Web/TUI unless the product goal explicitly changes.
- Treat teaching-case results as evidence for teaching value, not as a release blocker unless they expose a plugin workflow failure.

