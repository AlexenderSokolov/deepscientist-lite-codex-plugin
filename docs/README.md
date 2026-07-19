# DeepScientist Lite Documentation

This folder explains how the plugin is built and maintained. Start with the root README if you only want to use the plugin.

## For Users And Teachers

- [中文用户指南](user-guide.zh.md): a beginner-facing explanation of the seven skills, file roles, Mission Board, Graph revisions, Evidence Packs, review boundaries, path aliases, and session recovery.
- [OpenScience worker handoff](openscience-worker-handoff.zh.md): how a supervisor system can call DS Lite as a lightweight Codex worker protocol without adding a daemon or MCP server.
- [设计、实现、现状与演进审视](implementation.zh.md): the primary Chinese design document, covering product intent, architecture, code composition, state protocol, verified status, technical debt, and the improvement roadmap.
- [Teaching materials](../teaching/README.zh.md): runnable 20/30/45/90-minute courses, guided and one-prompt modes, worksheets, rubric, and reference answers.

## For Maintainers

- [Known issues](maintainers/known-issues.md): installation and runtime caveats.
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
- [v0.5.0-beta.2 acceptance record](maintainers/acceptance-beta2-20260719.zh.md): source/package, isolated install, canary timeout, and the remaining fresh-agent/A/B gates.
- [Pre-existing dirty-worktree audit](maintainers/preexisting-dirty-worktree-audit.zh.md): path-level classification of the isolated original worktree and the narrowly reimplemented hook/iteration semantics.
- The beta.2 communication layer lives in `plugins/deepscientist-lite/references/communication/`; its optional `STYLE.md`, four profiles, six progressive references, protected-content rules, complete non-runtime upstream snapshots, `ds-lite.communication-audit.v1`, hook boundary, and 12-case A/B fixture are documented in the Chinese user guide and implementation notes.

## Runtime References

The installable plugin keeps only skill-facing protocol references under `plugins/deepscientist-lite/references/`. Teaching cases and maintainer notes live outside the runtime plugin package.

- [external-long-task-protocol.md](../plugins/deepscientist-lite/references/external-long-task-protocol.md): ownership, manual tmux capacity handshakes, persistence probes, append-only task records, and recovery rules for work that may outlive a Codex worker or SSH connection.
