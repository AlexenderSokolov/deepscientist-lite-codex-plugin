# DeepScientist Lite Documentation

This folder explains how the plugin is built and maintained. Start with the root README if you only want to use the plugin.

## For Users And Teachers

- [中文用户指南](user-guide.zh.md): a beginner-facing explanation of the nine Core skills, file roles, Mission Board, reflective iterations, Evidence Packs, review boundaries, bounded delegation, path aliases, and session recovery.
- [OpenScience worker handoff](openscience-worker-handoff.zh.md): how a supervisor system can call DS Lite as a lightweight Codex worker protocol without adding a daemon or MCP server.
- [设计、实现、现状与演进审视](implementation.zh.md): the primary Chinese design document, covering product intent, architecture, code composition, state protocol, verified status, technical debt, and the improvement roadmap.
- [Teaching materials](../teaching/README.zh.md): runnable 20/30/45/90-minute courses, guided and one-prompt modes, worksheets, rubric, and reference answers.

## For Maintainers

- [Known issues](maintainers/known-issues.md): installation and runtime caveats.
- [Skills trigger matrix](maintainers/skill-trigger-matrix-20260804.zh.md): full trigger conditions, Mermaid dependency graph, boundary declarations, and overlap analysis for all 30 skills.
- [Skills audit and aggregation](maintainers/skills-audit-and-aggregation-20260804.zh.md): functional overlap audit and aggregation refactoring plan for all skills.
- [External projects annotation](maintainers/external-projects-annotation-20260804.zh.md): external MCP tools, plugins, and referenced projects used in conversation `019fcaa5`.
- [Next phase development memo](maintainers/next-phase-development-memo-20260804.zh.md): next phase plan covering skills integration, plugin simplification, and innovation exploration.
- [Public/private file boundary audit](maintainers/public-private-file-boundary-audit-20260804.zh.md): audit of which files should be public vs private.
- [Action, reflection, and responsibility architecture](maintainers/action-reflection-philosophy.zh.md): how the philosophy is translated into one bounded action, public reflection, Hook limits, feedback, and OpenScience supervision.
- [Graph v2 migration](maintainers/graph-v2-migration.md): safe v1 upgrade, backups, external aliases, and revision conflicts.
- [v0.2 Windows/WSL audit](maintainers/v0.2-audit.zh.md): local platform evidence, current limitations, self-reflection, and future directions.
- [v0.3 recommendation assessment](maintainers/v0.3-recommendation-assessment.zh.md): adopted, deferred, and rejected platform recommendations.
- [v0.3 evidence/review audit](maintainers/v0.3-audit.zh.md): local validation matrix, WSL evidence, known boundaries, and remaining manual gates.
- [v0.3 Codex acceptance audit](maintainers/v0.3-codex-acceptance.zh.md): real skill triggers, isolated teaching projects, cache-install findings, fixes, and remaining manual blockers.
- [v0.3 hardening log](maintainers/v0.3-hardening-log.zh.md): staged fixes after manual acceptance, with design decisions, tests, and open risks.
- [Release checklist](maintainers/release-checklist.md): checks before beta or stable releases.
- [Release status](maintainers/release-status.zh.md): current positioning and long-term maintenance notes.
- [Roadmap and deferred gates](maintainers/roadmap.zh.md): active short-term work and the P1-P3 interfaces that remain explicitly deferred.
- [Writing guide](maintainers/writing-guide.zh.md): Chinese terminology, claim strength, examples, and version-fact maintenance rules.
- [Cross-disciplinary adoption audit](maintainers/cross-disciplinary-adoption.zh.md): design-atom, license, clean-room, companion, and deferred decisions for the new Academic, Empirical, and Engineering packs.
- [上游设计原子吸收审计表](maintainers/upstream-design-atom-audit-20260726.zh.md):逐项核对推荐项目的精华落点、协议、测试、吸收深度和明确排除项。
- [0.8 真实验收审计表](maintainers/real-acceptance-audit-20260726.zh.md):本轮新身份的实际证据、状态、阻塞和用户动作。
- [0.8 续验审计表](maintainers/real-acceptance-audit-20260727.zh.md):完整回归、包矩阵、真实宿主门和下一条用户动作。
- [Learning and quality protocol](maintainers/learning-quality-protocol.zh.md): short on-demand tutorials, learning receipts, industrial quality plans, and public-only Web/Knowledge boundaries.

## Runtime References

Core keeps skill-facing protocol references under `plugins/deepscientist-lite-core/references/`; optional packs keep only their own domain references. Evaluation cases and maintainer notes live outside runtime packages.

- [external-long-task-protocol.md](../plugins/deepscientist-lite-core/references/external-long-task-protocol.md): ownership, manual tmux capacity handshakes, persistence probes, append-only task records, and recovery rules for work that may outlive a Codex worker or SSH connection.
- [responsible-exploration-covenant.md](../plugins/deepscientist-lite-core/references/responsible-exploration-covenant.md): the seven runtime actions and shared start/progress/end feedback protocol loaded by all nine Core skills.
- [Academic citation-check protocol](../plugins/deepscientist-lite-academic/references/citation-check-protocol.md): provider states, verification thresholds, reading scope, and cache policy.
- [Academic revision protocol](../plugins/deepscientist-lite-academic/references/revision-protocol.md): bounded revision constraints and adversarial-review isolation.
- [Empirical protocol](../plugins/deepscientist-lite-empirical/references/protocol.md): estimands, diagnostics, robustness, and Evidence Pack result handoff.
- [Engineering protocol](../plugins/deepscientist-lite-engineering/references/protocol.md): units, sampling, FFT, seeds, numerical checks, and figure axes.
