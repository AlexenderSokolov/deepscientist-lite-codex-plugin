# DeepScientist Lite Documentation

This folder explains how the plugin is built and maintained. Start with the root README if you only want to use the plugin.

## For Users And Teachers

- [设计、实现、现状与演进审视](implementation.zh.md): the primary Chinese design document, covering product intent, architecture, code composition, state protocol, verified status, technical debt, and the improvement roadmap.
- [Teaching materials](../teaching/README.zh.md): 20–30, 45, and 90-minute lesson paths, runnable evidence lab, worksheets, rubric, and cases.

## For Maintainers

- [Known issues](maintainers/known-issues.md): installation and runtime caveats.
- [Graph v2 migration](maintainers/graph-v2-migration.md): safe v1 upgrade, backups, external aliases, and revision conflicts.
- [v0.2 Windows/WSL audit](maintainers/v0.2-audit.zh.md): local platform evidence, current limitations, self-reflection, and future directions.
- [v0.3 recommendation assessment](maintainers/v0.3-recommendation-assessment.zh.md): adopted, deferred, and rejected platform recommendations.
- [v0.3 evidence/review audit](maintainers/v0.3-audit.zh.md): local validation matrix, WSL evidence, known boundaries, and remaining manual gates.
- [Release checklist](maintainers/release-checklist.md): checks before beta or stable releases.
- [Release status](maintainers/release-status.zh.md): current positioning and long-term maintenance notes.

## Runtime References

The installable plugin keeps only skill-facing protocol references under `plugins/deepscientist-lite/references/`. Teaching cases and maintainer notes live outside the runtime plugin package.
