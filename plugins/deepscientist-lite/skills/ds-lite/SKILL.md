---
name: ds-lite
description: Use when taking over or resuming a research or engineering project, maintaining continuity across sessions, comparing experiments, reviewing evidence, managing hypotheses, recovering context, or supervising one task-oriented action.
---

# DS Lite

## Overview

Use this gateway when the user needs the plugin but has not named a narrower action skill. Identify the workspace, explain why DS Lite is relevant, and route exactly one bounded action; do not run a multi-stage workflow or loop.

Before acting, read [the Responsible Exploration Covenant](../../references/responsible-exploration-covenant.md) and use its shared start / progress / end protocol. Do not start the action until the mandatory Start report is sent with its exact labels. Do not finish with a bare success sentence: the mandatory End report must contain the evidence, failure layer, unverified items, next action, and user decision.

For a long conversation, resumed task, or ownership change, create and validate a `ds-lite.handoff.v1` projection using [the handoff protocol](../../references/handoff-protocol.md) before acting. For Windows, `cmd`, Git Bash, WSL, or external execution, apply [the CLI boundary compatibility protocol](../../references/cli-boundary-compatibility.md). These projections carry redacted facts and configuration, never a transcript or hidden reasoning.

## Workflow

1. Inspect the current folder for `PROJECT.md`, `STATUS.md`, `RESEARCH_MAP.md`, `research/work-unit.json`, and `research/state/graph.json`. Do not infer a DS Lite workspace from unrelated notes or ordinary task lists.
2. If the project is new, state that DS Lite is intervening to create recoverable research or engineering context, then route exactly one action to `$ds-lite-intake`.
3. If the workspace exists, run `python <plugin>/scripts/ds_lite_state.py mission --root <project> --format json`. Read the Mission Board active route, evidence gate, latest iteration, hypothesis pool, blockers, and string `next_action`.
4. Tell the user why the plugin is relevant in one sentence: continuity, evidence review, hypothesis management, bounded iteration, or approved task coordination. Do not claim the plugin is required when the task is unrelated.
5. Select exactly one action skill from the table below, follow that skill, give the mandatory start/progress/end reports, and stop at its checkpoint. If the host, provider, shell, or tool fails, report the failure layer and observed diagnostic before proposing a next action.
6. When handing work to another conversation or child, send only the validated handoff projection and declared scope. Require receiver acknowledgement of authorization and configuration; a missing acknowledgement is `blocked`.

## Routing

| Situation | Route |
| --- | --- |
| New, incomplete, or inconsistent project contract | `$ds-lite-intake` |
| Facts, literature, baselines, metrics, feasibility, or risk are unclear | `$ds-lite-scout` |
| Two or three hypotheses or candidate mechanisms need comparison | `$ds-lite-idea` |
| One bounded implementation, experiment, repair, or evidence collection action is ready | `$ds-lite-experiment` |
| Evidence or a claim must pass an independent gate | `$ds-lite-review` |
| Passing or negative reviewed evidence must become a bounded analysis or handoff | `$ds-lite-analysis-write` |
| An existing workspace should advance through one complete plan-execute-verify-reflect-report cycle | `$ds-lite-iterate` |
| Two or three independent subtasks have disjoint paths and explicit delegation approval | `$ds-lite-coordinate` |

## Feedback

At the start, use the covenant's exact `Start report` labels. During long work, use `Progress report` at least every 60 seconds. At the end, use the exact `End report` labels. A missing report field is a blocked communication contract, not permission to fill the gap with polished prose.

## Hard Rules

- One gateway invocation routes exactly one skill. Never call the full sequence automatically.
- Do not create a daemon, queue, scheduler, background loop, MCP service, database, model router, or tmux capacity.
- Do not edit `graph.json` directly. Use the state CLI and expected revision.
- Do not treat Factor Card, Markdown, ordinary artifacts, or a hypothesis label as typed evidence.
- Do not delegate without explicit user or OpenScience approval.
- Do not use this gateway for general office tasks, personal todo management, translation, or unrelated content generation.
