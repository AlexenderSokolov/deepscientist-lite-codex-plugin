---
name: ds-lite-control-plane
description: Use when an approved project explicitly needs durable multi-gate orchestration, DBOS recovery, or control-plane receipts.
---

# DS Lite Control Plane

This is an optional extension. It owns durable controller and DBOS bridge behavior; Core remains usable without it.

Require an existing `PROJECT.md`, a valid work-unit, explicit project authorization, and a finite budget. Missing DBOS, credentials, publication authority, or an irreversible boundary returns `blocked` or `awaiting-user-action`.

Every run must emit a write-once receipt and state whether evidence is source, offline, host, or formal. This skill does not grant release permission.
