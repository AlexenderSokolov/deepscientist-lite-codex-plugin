---
name: nature-reviewer
description: Use the complete nature-reviewer workflow, preserving its upstream routing and supporting materials. Simulate a Nature-style reviewer assessment from the referee perspective rather than an author rebuttal. Use when the user wants a pre-submission review, reviewer report, peer-review style critique, novelty/significance/technical soundness assessment, reviewer-style manuscript evaluation, 审稿人视角评估, 预审稿意见, or Nature reviewer report. Return 3 reviewer reports plus a cross-review synthesis, grounded only in the local Nature reviewer source basis. Also trigger on general pre-submission review requests during academic writing even without the word "Nature", such as getting a mock peer review for any journal, critiquing a draft as a reviewer would, assessing novelty/rigor before submission, and Chi
---

# DS Lite Integration Boundary

This entry preserves the complete upstream nature-reviewer workflow at commit `91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b`.
Use the upstream manifest, static fragments, references, scripts, templates, and tests
that remain in this directory; this file is not a summary replacement.

Before using any MCP, external API, browser, downloader, LaTeX, Node, or Python
integration, first run `python <academic-plugin>/scripts/ds_lite_pack_doctor.py --core-root <core-plugin>`, then run
`python <academic-plugin>/scripts/ds_lite_nature_setup.py doctor --workspace .`.
Record only redacted status and relative evidence references. Missing dependencies are
`not-observed` or `blocked`, never silently treated as available.

Read [responsible-exploration-covenant.md](../../references/responsible-exploration-covenant.md) first.
Every invocation follows DS Lite `start / progress / end`: state the target, facts,
authorization, actual action, evidence, failure layer, unverified items, and one next
action. Do not save prompts, credentials, raw responses, hidden reasoning, or absolute
workstation paths.

## Academic beta.2 adversarial mode

For adversarial review, load [revision-protocol.md](../../references/revision-protocol.md). Ask one fresh reviewer for the single strongest rejection argument, then use a distinct fresh adjudicator to decompose it into atomic P0-P3 concerns and verdicts. Mark isolation `observed` only when two distinct fresh-context receipts exist; otherwise write `not-observed`. This mode reviews evidence and constraints but never launches an unattended edit or experiment loop.

## Preserved Upstream Workflow

# Nature Reviewer Assessment Skill

Use this skill to simulate a `Nature`-style reviewer assessment package from the referee
side.

This skill is for reviewer-style manuscript evaluation, not for drafting the authors'
response. If the user wants rebuttal writing, route to `nature-response`.

## Default stance

- Ground the review only in the local source basis plus manuscript facts supplied by the user.
- Evaluate the manuscript against source-grounded axes: `originality`, `scientific importance`, `interdisciplinary readership`, `technical soundness`, and `readability for nonspecialists`.
- Use the 12-axis technical concern taxonomy only as an internal coverage checklist; it supplements but never replaces the five source-grounded axes.
- Return exactly `3 reviewer reports + 1 cross-review synthesis` unless the user explicitly asks for another structure.
- The three reviewers may differ only in `emphasis`; do not invent reviewer identities, specialties, institutions, or biographies.
- Identify who would be interested in the results and why.
- Identify technical failings that must be addressed before the authors' case is established.
- Give every substantive concern a stable ID, a faithful `claim_pointer`, and a verifiable `evidence_pointer`; mark missing locations instead of inventing them.
- Distinguish clearly between what is supported, what is weak, and what is not assessable from the provided material.
- When the manuscript has a clear technical domain, use claim-dependent domain gates as supporting checks, but keep the output inside the same 3-reviewer `nature-reviewer` structure.
- Do not claim the editor's final decision or certainty about fit to `Nature`.

## Accepted inputs

The skill may receive:

- full manuscript draft
- abstract, summary paragraph, or cover-summary style text
- introduction, results, discussion, or methods excerpts
- figure legends, selected figures, or result notes
- author notes in Chinese or English describing the claimed contribution
- pre-submission positioning notes

If the provided material is partial, perform a bounded review and mark the assessment boundary explicitly.

## Workflow

1. Identify the input scope and whether the job is a reviewer-style assessment rather than rebuttal drafting.
2. Extract a shared manuscript fact base: main claim, visible evidence, claimed significance, likely readership, and visible limitations.
3. Check readiness and label missing evidence or missing sections instead of inventing them.
4. Assess the manuscript using the source-grounded axes.
5. Build an internal concern ledger using `references/technical-concern-taxonomy.md`; record applicability, claim/evidence pointers, severity, and the resolution test for each supported concern.
6. If the manuscript clearly falls into a technical domain covered by `references/domain-specific-review-gates.md`, load only the relevant domain section and use it to sharpen the technical-soundness critique.
7. Generate `Reviewer 1`, `Reviewer 2`, and `Reviewer 3` using shared facts but different emphasis. Reuse ledger issue keys internally so repeated concerns can be measured and cross-referenced.
8. Generate a `Cross-review synthesis` that captures consensus and weighting differences. Label an issue as consensus only when at least two reviewer reports raise the same underlying concern.
9. Run QA for evidence anchoring, overlap, groundedness, coverage, role boundaries, and non-invention.

## Output format

Unless the user asks for another format, return:

```text
Review setup
- Input scope:
- Assessment boundary:
- Shared manuscript claim summary:
- Visible evidence base:
- Missing materials affecting confidence:

Reviewer 1
- Overall assessment:
- Who would be interested in the results, and why:
- Major strengths:
- Major concerns:
- Technical failings that need to be addressed before the case is established:
- Assessment against Nature-style criteria:
- Recommendation posture:

For each substantive concern:
- Concern ID: R1-M1
- Axis:
- Claim pointer:
- Evidence pointer:
- Concern and resolution test:

Reviewer 2
[Same structure]

Reviewer 3
[Same structure]

Cross-review synthesis
- Consensus strengths:
- Consensus technical risks:
- Where emphasis differs across reviewers:
- Broad-interest / significance readout:
- Most important issues to resolve before a strong Nature-style case is established:

Risk / unsupported claims
- [specific unsupported or not-assessable items]
```

## Red lines

- Do not invent reviewer identities, specialty roles, or selection history.
- Do not invent experiments, validations, controls, citations, figure details, line numbers, or prior-work distinctions not present in the input.
- Do not silently turn reviewer assessment into author rebuttal drafting.
- Do not present the review as an editorial decision letter.
- Do not state that the manuscript belongs in `Nature` as a settled fact.
- Do not omit technical failings when the provided evidence does not establish the authors' case.

## Related files

| File | Open when |
|---|---|
| [references/source-basis.md](references/source-basis.md) | You need source provenance, local rule summaries, or source-vs-implementation boundaries |
| [references/reviewer-workflow.md](references/reviewer-workflow.md) | You need the invocation order, fact-base extraction flow, or synthesis rules |
| [references/review-axes.md](references/review-axes.md) | You need the evaluation axes or reviewer weighting logic |
| [references/technical-concern-taxonomy.md](references/technical-concern-taxonomy.md) | You need the internal 12-axis coverage check, concern ledger, or claim/evidence-pointer rules |
| [references/domain-specific-review-gates.md](references/domain-specific-review-gates.md) | The manuscript has clear chemistry, engineering, materials, atmospheric, climate-ecology, hydrology, or remote-sensing evidence chains |
| [references/report-structure.md](references/report-structure.md) | You need the default output contract or section anatomy |
| [references/role-boundaries.md](references/role-boundaries.md) | You need constraints on reviewer differences and editor-versus-reviewer boundaries |
| [references/qa-checklist.md](references/qa-checklist.md) | You are finalizing an output and need groundedness / non-invention checks |
| [references/editorial criteria and processes.md](references/editorial criteria and processes.md) | You need the primary local Nature source text |

## Source hierarchy

Use sources in this order:

1. `references/editorial criteria and processes.md`
2. manuscript facts supplied by the user
3. conservative local implementation rules documented in `references/source-basis.md`
4. domain-specific supporting gates in `references/domain-specific-review-gates.md`

If a user asks for policy-level certainty beyond this local source, state the limit instead of improvising broader journal policy.
