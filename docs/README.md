# DeepScientist Lite Documentation

This folder explains how the plugin is built and maintained. Start with the root README if you only want to use the plugin.

## For Users And Teachers

- [中文用户指南](user-guide.zh.md): a beginner-facing explanation of the nine Core skills, file roles, Mission Board, reflective iterations, Evidence Packs, review boundaries, bounded delegation, path aliases, and session recovery.
- [OpenScience worker handoff](openscience-worker-handoff.zh.md): how a supervisor system can call DS Lite as a lightweight Codex worker protocol without adding a daemon or MCP server.
- [设计、实现、现状与演进审视](implementation.zh.md): the primary Chinese design document, covering product intent, architecture, code composition, state protocol, verified status, technical debt, and the improvement roadmap.
- [Teaching materials](../teaching/README.zh.md): runnable 20/30/45/90-minute courses, guided and one-prompt modes, worksheets, rubric, and reference answers.

## For Maintainers


## Runtime References

Core keeps skill-facing protocol references under `plugins/deepscientist-lite-core/references/`; optional packs keep only their own domain references. Evaluation cases and maintainer notes live outside runtime packages.

- [external-long-task-protocol.md](../plugins/deepscientist-lite-core/references/external-long-task-protocol.md): ownership, manual tmux capacity handshakes, persistence probes, append-only task records, and recovery rules for work that may outlive a Codex worker or SSH connection.
- [responsible-exploration-covenant.md](../plugins/deepscientist-lite-core/references/responsible-exploration-covenant.md): the seven runtime actions and shared start/progress/end feedback protocol loaded by all nine Core skills.
- [Academic citation-check protocol](../plugins/deepscientist-lite-academic/references/citation-check-protocol.md): provider states, verification thresholds, reading scope, and cache policy.
- [Academic revision protocol](../plugins/deepscientist-lite-academic/references/revision-protocol.md): bounded revision constraints and adversarial-review isolation.
- [Empirical protocol](../plugins/deepscientist-lite-empirical/references/protocol.md): estimands, diagnostics, robustness, and Evidence Pack result handoff.
- [Engineering protocol](../plugins/deepscientist-lite-engineering/references/protocol.md): units, sampling, FFT, seeds, numerical checks, and figure axes.
