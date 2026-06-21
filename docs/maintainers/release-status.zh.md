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

`v0.1.4-beta` is suitable for private beta / teaching beta use. It is not yet a stable public release because fresh-thread skill exposure after Codex Desktop restart and cache-upgrade recovery still need external validation.

## Long-Term Memory Rules

- Keep durable plugin decisions in this file, `known-issues.md`, `release-checklist.md`, README, and case studies.
- Keep algorithm experiment details inside the case study or the host research project.
- Do not add MCP, daemon, hooks, or Web/TUI unless the product goal explicitly changes.
- Treat teaching-case results as evidence for teaching value, not as a release blocker unless they expose a plugin workflow failure.

