---
name: ds-lite
description: Use when taking over or resuming a research or engineering project, maintaining continuity across sessions, comparing experiments, reviewing evidence, managing hypotheses, recovering context, or supervising one task-oriented action.
---

# DS Lite

Communication boundary: 保护内容必须原样保留；不得改写用户约束或证据限定。

## Overview

Use this gateway when the user needs the plugin but has not named a narrower action skill. The default project-setting is **automatic project advancement**: inspect the workspace, derive or load an approved `ds-lite.autonomy-contract.v1`, and keep the foreground controller moving every independent ready gate until all gates are terminal. A user who explicitly asks for one bounded action, planning only, or no side effects retains that narrower boundary.

Before acting, read [the Responsible Exploration Covenant](../../references/responsible-exploration-covenant.md) and use its shared start / progress / end protocol. Do not start the action until the mandatory Start report is sent with its exact labels. Do not finish with a bare success sentence: the mandatory End report must contain the evidence, failure layer, unverified items, next action, and user decision.

For a long conversation, resumed task, or ownership change, create and validate a `ds-lite.handoff.v1` projection using [the handoff protocol](../../references/handoff-protocol.md) before acting. For Windows, `cmd`, Git Bash, WSL, or external execution, apply [the CLI boundary compatibility protocol](../../references/cli-boundary-compatibility.md). These projections carry redacted facts and configuration, never a transcript or hidden reasoning.

## Workflow

1. Inspect the current folder for `PROJECT.md`, `STATUS.md`, `RESEARCH_MAP.md`, `research/work-unit.json`, and `research/state/graph.json`. Do not infer a DS Lite workspace from unrelated notes or ordinary task lists.
2. If the project is new, state that DS Lite is intervening to create recoverable research or engineering context, then route exactly one action to `$ds-lite-intake`.
3. If the workspace exists, run `python <plugin>/scripts/ds_lite_state.py mission --root <project> --format json`. Read the Mission Board active route, evidence gate, latest iteration, hypothesis pool, blockers, and string `next_action`.
4. Tell the user why the plugin is relevant in one sentence: continuity, evidence review, hypothesis management, bounded iteration, or approved task coordination. Do not claim the plugin is required when the task is unrelated.
5. For a normal project-setting request, create or load an approved autonomy contract and invoke `ds_lite_autonomy.py`. A failed gate freezes only that identity, while every independent ready gate continues automatically. Use `--resume` after a terminal interruption so completed or frozen gates are not replayed. Only select exactly one narrower skill when the user explicitly chose a bounded action.
6. During controller execution, perform the contract's silent receipt polls and transient retry schedule without conversationally stopping between polls. Every terminal gate must still write a progress receipt that explains why it ran, what happened, evidence, failure layer, and the next automatic action.
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
| An approved bounded multi-gate acceptance or release experiment must continue without manual prompting | `ds_lite_autonomy.py` with `ds-lite.autonomy-contract.v1` |
| The user asks to continue, automatically advance, or not stop until terminal evidence exists | Create/load `ds-lite.autonomy-contract.v1`, run `ds_lite_autonomy.py`, then `--resume` after interruption |

## Feedback

At the start, use the covenant's exact `Start report` labels. During long work, use `Progress report` at least every 60 seconds. At the end, use the exact `End report` labels. A missing report field is a blocked communication contract, not permission to fill the gap with polished prose.

This applies to every terminal state, including `completed`, `failed`, `blocked`,
and `ambiguous`. Do not replace the exact End report labels with an informal
summary. A completed action must still name verification evidence, remaining
unverified items, and one concrete next action; use `none` only when the field
is genuinely empty and explain why.

Use repository-relative artifact refs in every report. Never quote raw stderr or absolute private paths;
summarize such diagnostics with a normalized failure class and, when traceability is needed,
a digest stored in private evidence.

## Hard Rules

- Automatic project advancement is the default for a project-setting request. It is foreground, bounded, receipt-producing, and must continue independent ready gates after a blocked gate. Do not silently fall back to one-action-and-stop merely because one gate is blocked.
- Do not create a daemon, queue, scheduler, background loop, MCP service, database, model router, or tmux capacity.
- Do not edit `graph.json` directly. Use the state CLI and expected revision.
- Do not treat Factor Card, Markdown, ordinary artifacts, or a hypothesis label as typed evidence.
- Do not delegate without explicit user or OpenScience approval.
- Do not use this gateway for general office tasks, personal todo management, translation, or unrelated content generation.

## Communication and Learning Gate

Before a non-trivial action, read `../../references/communication/core.md` and `../../references/communication/self-audit.md`; read the project `STYLE.md` when present.
Complete Phase 1 before the first side effect. Preserve protected content, report observable evidence, and finish with a readable Handoff.
When this skill is selected, run the learning receipt check for its declared tutorial set before the first write, command, or network request. A stale or missing receipt is a blocker; the learning helper itself is the only exception.
