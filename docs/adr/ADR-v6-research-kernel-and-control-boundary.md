# ADR: v6 Research Kernel and Control Boundary

**Date**: 2026-08-04
**Status**: Approved
**Supersedes**: None

## Context

DeepScientist Lite (DS Lite) is a lightweight, auditable, recoverable research
execution unit for Codex. It is not a second OpenScience platform. The v6
design document (9134 lines, five parts) defines 35 fixed design decisions
that form the architectural baseline. This ADR records those decisions and
the current implementation status.

## Decision

### 1. Fixed Design Decisions (V6-2)

The following 35 decisions are approved and cannot be silently changed.
Changing any one requires a change request approved by the project lead.

1. DS Lite is a lightweight, auditable, recoverable execution unit for
   small-to-medium research tasks, not a second OpenScience.
2. OpenScience holds user relationships, cross-project priorities, global
   budget, final synthesis and delivery; DS Lite holds bounded Mission
   local execution and return.
3. Files, frozen contracts, Graph, Evidence, Ledger and Review are research
   authority; Catalog, Frontier, code graph and query databases are
   deletable projections.
4. research/state/graph.json only holds routes, active nodes, blockers
   and terminal states; it does not absorb all files, code, signals, claims
   and memory.
5. Core defaults to no daemon, no MCP service, no Web/TUI, no background
   observer, no vector database, no listening port, no global research
   database.
6. Core - Domain Profile - Project Overlay three layers are maintained;
   finance, Qlib, journal, lab resources and private corpora only enter
   Profile/Overlay.
7. Six package boundaries and nine Core Skill entries are preserved; new
   mechanisms enter shared protocols, validators, templates and scripts,
   not a new innovation master Skill or seventh runtime package.
8. Hook only determines whether the current turn has a safe stop checkpoint;
   Hook does not hold tasks, schedule future actions, or perform long
   retries.
9. External/foreground controller holds action/workflow identity, owner,
   lease, fence, outbox, cooldown, resume and reconcile; it does not hold
   scientific truth.
10. DBOS hybrid scheme is an explicit, optional foreground capability within
    the plugin; its code and tests may ship with Core, but DBOS dependency
    does not enter default Core, and runtime must exit when done.
11. Controller DB, DBOS runtime DB, Catalog cache, Graph, Memory and Evidence
    are physically and semantically isolated.
12. Mission Order/Return uses versioned files or stdin/stdout JSON;
    OpenScience and DS Lite do not share databases, do not require A2A
    network services.
13. Handoff is offer, accept, execute, return, integrate, close - six stages
    of responsibility transfer; returned does not equal integrated.
14. Sub-agents or tools only complete one minimal, path-isolated,
    independently verifiable action; parent is the sole integrator, child
    may not modify parent Graph or continue nested delegation.
15. Quality control is divided into five channels: requirements/spec,
    security/privacy, license supply chain, engineering quality, scientific
    method; none can substitute for another.
16. Seven quality gates G0-G6 and risk levels Q0-Q4 coexist; required gate
    unknown or not-run cannot aggregate into pass.
17. Implementer self-check, deterministic validator, independent reviewer,
    domain expert and human approval are different evidence; model verdict
    cannot cover deterministic failure.
18. Factor Card is retained and upgraded to v2; v1 is read-only compatible.
19. Research Signal Ledger is append-only; signals are observations with
    source, scope, dependencies and expiry, not final facts.
20. Discovery Frontier is a deterministic projection without execution
    authority; manually editing Frontier cannot activate Graph routes.
21. Candidate selection uses hard gates, comparability, partial ordering and
    diversity cells; no research total score is defined.
22. Task Assessment/Answerability is embedded in Mission/Experiment Contract
    v2, not a separate task contract.
23. Profile defines fidelity ladder, evaluator, comparison domain and claim
    permission; Core verifies identity, structure, promotion and
    over-level claims.
24. Claim Ledger binds selector, digest, transformation, dependence group,
    executed code and verifier at claim production time, not after paper
    writing.
25. Novelty can only be stated as no equivalent collision found within
    declared search scope; search degradation, unsearched scope and recent
    work must be visible.
26. generator, auditor, selector, executor, verifier roles are separated;
    may be executed sequentially by the same host, but each stage consumes
    frozen input and produces independent receipt.
27. Confirmatory results are protected; viewing-then-adjusting must create a
    new revision, not reuse the original confirmatory claim.
28. Experience only forms Incident, Lesson, Guard or Skill change proposal;
    may not auto-rewrite authoritative Skill.
29. Human Feynman notes and learning output belong to protected area; AI may
    not ghost-write, overwrite or auto-promote to project facts.
30. Financial factor mode only provides method metaphor of signalization,
    lineage, de-redundancy, diversity, low-cost screening, out-of-sample/graded
    validation, failure governance; IC, PnL, universe, formula and private
    records do not enter Core.
31. All failure, blocked, missing, ambiguous, negative, superseded,
    retracted, resource-stop must enter the report denominator.
32. External projects are only absorbed by mechanism-level decisions of
    adopt/adapt/reference/reject; license, version, source, rejected items
    and acknowledgments must be registered.
33. Operator O0-O7 grading: public read-only, authenticated read-only,
    reversible write, irreversible action are separately authorized;
    API/CLI first, accessibility second, visual click last.
34. Any non-repeatable or unverifiable effect external action enters
    ambiguous and stops after response loss; cannot blindly resend.
35. Release must be per-capability release/shadow/revise/reject; one
    capability passing cannot unlock another higher-permission or
    higher-claim capability.

### 2. Current Phase 3 Status

Phase 3 (real Provider multi-gate verification) has NOT passed. The
controller modules exist (25 modules in controller/ds_lite_control/),
but real terminal smoke, response drop, controller kill, TTL takeover,
single reversible matched effect, stale fence late write, ambiguous effect,
and fresh-process recovery have not been verified with a real Provider.

### 3. Controller Scientific Boundary

The controller does not answer whether a hypothesis is novel, whether an
experiment is scientifically valid, whether metrics support a claim, which
route should become a paper contribution, which Memory/Lesson should take
long-term effect, or what OpenScience next cross-project task is.

### 4. v1 Compatibility

All new schemas have canonical digest, negative examples and v1
compatibility decision.

### 5. No Daemon/MCP

Core defaults to no daemon, no MCP service, no Web/TUI, no background
observer, no vector database, no listening port, no global research database.

### 6. Graph Authority

research/state/graph.json is the authority for routes, active nodes,
blockers and terminal states. It does NOT absorb all files, code, signals,
claims and memory.

### 7. Frontier Non-Authority

Discovery Frontier is a deterministic projection. It does NOT hold execution
authority. Manually editing Frontier CANNOT activate Graph routes.

### 8. Task Assessment Embedded in Contract

Task Assessment/Answerability Gate is embedded in Mission/Experiment Contract
v2, NOT a separate task contract.

## Consequences

- All future development must respect these 35 fixed decisions
- Phase 3 must pass before release claims about controller reliability
- New schemas must include canonical digest, negative examples and v1
  compatibility
- No new runtime dependencies without explicit approval
- No new seventh runtime package