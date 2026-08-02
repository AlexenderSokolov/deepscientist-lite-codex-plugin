---
name: ds-lite-knowledge
description: Convert captured web or paper-library evidence into reviewable knowledge proposals without creating a second library or writing formal knowledge directly. Use for Tapestry capture handoffs, ScholarAIO paper evidence, ResearchKB review queues, source deduplication, proposal withdrawal, provenance updates, and review-gated promotion of notes or claims.
---

# DS Lite Knowledge

Use this pack only with the matching DeepScientist Lite Core version. Run `python <knowledge-plugin>/scripts/ds_lite_pack_doctor.py --core-root <core-plugin>` first; a missing or incompatible core is `blocked`.

Treat Tapestry and ScholarAIO as companion systems. Tapestry may produce capture/feed/note artifacts in a user-selected project or external root; ScholarAIO owns paper import, parsing, retrieval, workspaces, and its library. Do not store either system's data in an installed plugin directory.

Read validated `ds-lite.source-record.v1` or v2 inputs and create a `ds-lite.knowledge-proposal.v1`. Use `doctor` to observe companion CLIs; `pull-tapestry` and `pull-scholaraio` only report passed for an explicit external export, otherwise they remain `blocked/not-observed`. `propose`, `withdraw`, and `supersede` write fresh immutable proposal records. Every claim must cite one or more source records and state uncertainty. Write proposals to the target's review queue or a project-local pending directory. Do not publish, merge, or mark a proposal accepted without a non-empty target-native review reference.

Preserve duplicate, superseded, withdrawn, rejected, and conflicting proposals. Finish with DS Lite `start / progress / end`, including the target, proposal refs, review state, unresolved provenance, and one next action.
