# ADR v7: 0.10 Beta Package and Autonomy Boundary

**Date:** 2026-08-07  
**Status:** Accepted for implementation; publication remains gated

## Context

The v6 record treated Core and the durable control-plane implementation as one
runtime boundary and counted six packages. The 0.10 beta audit showed that this
couples an optional DBOS dependency to Core validation and makes release
authorization ambiguous for ordinary research work.

## Decision

1. `plugins/deepscientist-lite-core` is the sole Core runtime source.
2. `plugins/deepscientist-lite-control-plane` is the seventh optional package and
   owns the canonical controller implementation plus the installation/validation
   boundary for DBOS and controller workflows.
3. `ds-lite.autonomy-contract.v2` is the generic bounded foreground protocol.
   Its terminal policy defaults to `report` or `handoff`; `release` requires a
   separate formal release gate.
4. The old v1 contract and the Core controller path remain as one-beta compatibility
   projections. They are not silently deleted or treated as fresh release evidence.

This supersedes the v6 decisions “six packages” and “DBOS ships with Core” while
retaining v6 as historical rationale.

## Consequences

Core can be validated without DBOS. Control-plane receipts remain separately
classified, and a candidate cannot become a public beta until fresh host and
continuation gates are observed.
