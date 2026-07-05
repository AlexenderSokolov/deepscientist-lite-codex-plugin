# DeepScientist Lite Documentation

This folder explains how the plugin is built and maintained. Start with the root README if you only want to use the plugin.

## For Users And Teachers

- [中文用户指南](user-guide.zh.md): a beginner-facing explanation of the six skills, file roles, Graph revisions, Evidence Packs, review boundaries, path aliases, and session recovery.
- [设计、实现、现状与演进审视](implementation.zh.md): the primary Chinese design document, covering product intent, architecture, code composition, state protocol, verified status, technical debt, and the improvement roadmap.
- [Teaching materials](../teaching/README.zh.md): runnable 20/30/45/90-minute courses, guided and one-prompt modes, worksheets, rubric, and reference answers.

## For Maintainers

- [Known issues](maintainers/known-issues.md): installation and runtime caveats.
- [Graph v2 migration](maintainers/graph-v2-migration.md): safe v1 upgrade, backups, external aliases, and revision conflicts.
- [v0.2 Windows/WSL audit](maintainers/v0.2-audit.zh.md): local platform evidence, current limitations, self-reflection, and future directions.
- [v0.3 recommendation assessment](maintainers/v0.3-recommendation-assessment.zh.md): adopted, deferred, and rejected platform recommendations.
- [v0.3 evidence/review audit](maintainers/v0.3-audit.zh.md): local validation matrix, WSL evidence, known boundaries, and remaining manual gates.
- [v0.3 Codex acceptance audit](maintainers/v0.3-codex-acceptance.zh.md): real skill triggers, isolated teaching projects, cache-install findings, fixes, and remaining manual blockers.
- [Release checklist](maintainers/release-checklist.md): checks before beta or stable releases.
- [Release status](maintainers/release-status.zh.md): current positioning and long-term maintenance notes.
- [Writing guide](maintainers/writing-guide.zh.md): Chinese terminology, claim strength, examples, and version-fact maintenance rules.

## Runtime References

The installable plugin keeps only skill-facing protocol references under `plugins/deepscientist-lite/references/`. Teaching cases and maintainer notes live outside the runtime plugin package.
