from __future__ import annotations

import sqlite3
from pathlib import Path

from .errors import MigrationRejected


SCHEMA_VERSION = 4

SCHEMA_V1 = """
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY, goal_hash TEXT NOT NULL, state TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE work_items (
    work_item_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id),
    type TEXT NOT NULL, state TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 0,
    next_eligible_at TEXT, dependency_digest TEXT
);
CREATE TABLE dependencies (
    predecessor_id TEXT NOT NULL, successor_id TEXT NOT NULL,
    required_outcome TEXT NOT NULL,
    PRIMARY KEY(predecessor_id, successor_id)
);
CREATE TABLE attempts (
    attempt_id TEXT PRIMARY KEY,
    work_item_id TEXT NOT NULL REFERENCES work_items(work_item_id),
    ordinal INTEGER NOT NULL, state TEXT NOT NULL,
    input_hash TEXT NOT NULL, config_hash TEXT NOT NULL, failure_id TEXT
);
CREATE TABLE actions (
    action_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
    type TEXT NOT NULL, state TEXT NOT NULL,
    idempotency_marker TEXT NOT NULL, payload_hash TEXT NOT NULL,
    owner_id TEXT NOT NULL, fence_epoch INTEGER NOT NULL
);
CREATE TABLE outbox (
    outbox_id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL UNIQUE REFERENCES actions(action_id),
    state TEXT NOT NULL, not_before TEXT,
    dispatch_count INTEGER NOT NULL DEFAULT 0, last_error_id TEXT,
    owner_id TEXT NOT NULL, fence_epoch INTEGER NOT NULL
);
CREATE TABLE workflow_bindings (
    action_id TEXT PRIMARY KEY REFERENCES actions(action_id),
    backend TEXT NOT NULL, workflow_id TEXT NOT NULL UNIQUE,
    workflow_kind TEXT NOT NULL, code_version TEXT NOT NULL,
    runtime_state TEXT NOT NULL, last_reconciled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    owner_id TEXT NOT NULL, fence_epoch INTEGER NOT NULL
);
CREATE TABLE thread_bindings (
    attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id), adapter TEXT NOT NULL,
    thread_id TEXT, session_id TEXT, last_turn_id TEXT, schema_digest TEXT
);
CREATE TABLE host_events (
    event_id TEXT PRIMARY KEY, action_id TEXT NOT NULL REFERENCES actions(action_id),
    host_sequence INTEGER NOT NULL, event_type TEXT NOT NULL,
    observed_at TEXT NOT NULL, witness_hash TEXT NOT NULL,
    owner_id TEXT NOT NULL, fence_epoch INTEGER NOT NULL,
    UNIQUE(action_id, host_sequence)
);
CREATE TABLE failures (
    failure_id TEXT PRIMARY KEY, layer TEXT NOT NULL, class TEXT NOT NULL,
    disposition TEXT NOT NULL, signature TEXT NOT NULL, retry_after TEXT
);
CREATE TABLE leases (
    resource_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
    fence_epoch INTEGER NOT NULL, expires_at TEXT, heartbeat_at TEXT NOT NULL
);
CREATE TABLE receipt_index (
    receipt_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL, previous_hash TEXT,
    owner_id TEXT NOT NULL, fence_epoch INTEGER NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE status_projection (
    job_id TEXT PRIMARY KEY REFERENCES jobs(job_id), revision INTEGER NOT NULL,
    rendered_hash TEXT NOT NULL, rendered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
PRAGMA user_version=1;
INSERT INTO schema_migrations(version) VALUES (1);
"""

SCHEMA_V2 = """
ALTER TABLE thread_bindings ADD COLUMN lifecycle_state TEXT NOT NULL DEFAULT 'unbound';
ALTER TABLE thread_bindings ADD COLUMN pending_archive INTEGER NOT NULL DEFAULT 0;
ALTER TABLE thread_bindings ADD COLUMN last_reconciled_at TEXT;
ALTER TABLE thread_bindings ADD COLUMN owner_id TEXT;
ALTER TABLE thread_bindings ADD COLUMN fence_epoch INTEGER;
CREATE TABLE rpc_requests (
    request_id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL REFERENCES actions(action_id),
    method TEXT NOT NULL, params_hash TEXT NOT NULL,
    state TEXT NOT NULL, wire_request_id INTEGER,
    thread_id TEXT, turn_id TEXT, pre_dispatch_turn_id TEXT,
    response_hash TEXT, error_class TEXT,
    owner_id TEXT NOT NULL, fence_epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(action_id, method)
);
CREATE TABLE protocol_journal (
    journal_id TEXT PRIMARY KEY,
    request_id TEXT REFERENCES rpc_requests(request_id),
    direction TEXT NOT NULL, message_kind TEXT NOT NULL,
    method TEXT, wire_id INTEGER, thread_id TEXT, turn_id TEXT,
    payload_hash TEXT NOT NULL, observed_at TEXT NOT NULL,
    owner_id TEXT NOT NULL, fence_epoch INTEGER NOT NULL
);
CREATE INDEX protocol_journal_request_idx ON protocol_journal(request_id, observed_at);
PRAGMA user_version=2;
INSERT INTO schema_migrations(version) VALUES (2);
"""

SCHEMA_V3 = """
ALTER TABLE work_items ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3;
ALTER TABLE work_items ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE work_items ADD COLUMN failure_policy TEXT NOT NULL DEFAULT 'standard';
ALTER TABLE work_items ADD COLUMN circuit_state TEXT NOT NULL DEFAULT 'closed';
ALTER TABLE work_items ADD COLUMN failure_streak INTEGER NOT NULL DEFAULT 0;
ALTER TABLE work_items ADD COLUMN last_failure_signature TEXT;
ALTER TABLE work_items ADD COLUMN result_class TEXT;
ALTER TABLE work_items ADD COLUMN evidence_class TEXT NOT NULL DEFAULT 'offline';
ALTER TABLE work_items ADD COLUMN updated_at TEXT;
UPDATE work_items SET updated_at=CURRENT_TIMESTAMP WHERE updated_at IS NULL;
ALTER TABLE failures ADD COLUMN work_item_id TEXT REFERENCES work_items(work_item_id);
ALTER TABLE failures ADD COLUMN attempt_id TEXT REFERENCES attempts(attempt_id);
ALTER TABLE failures ADD COLUMN impact_scope TEXT NOT NULL DEFAULT 'gate';
ALTER TABLE failures ADD COLUMN next_action TEXT;
ALTER TABLE failures ADD COLUMN evidence_hash TEXT;
ALTER TABLE failures ADD COLUMN created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP;
CREATE TABLE scheduler_runs (
    run_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id),
    owner_id TEXT NOT NULL, fence_epoch INTEGER NOT NULL,
    state TEXT NOT NULL, ready_digest TEXT NOT NULL,
    claimed_digest TEXT NOT NULL,
    started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE gate_results (
    result_id TEXT PRIMARY KEY,
    work_item_id TEXT NOT NULL REFERENCES work_items(work_item_id),
    attempt_id TEXT REFERENCES attempts(attempt_id),
    outcome TEXT NOT NULL, evidence_hash TEXT NOT NULL,
    owner_id TEXT NOT NULL, fence_epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE handoffs (
    handoff_id TEXT PRIMARY KEY,
    predecessor_attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(attempt_id),
    successor_attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(attempt_id),
    state_pack_hash TEXT NOT NULL, evidence_hash TEXT NOT NULL,
    predecessor_thread_id TEXT, successor_thread_id TEXT,
    owner_id TEXT NOT NULL, fence_epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE supervisor_heartbeats (
    supervisor_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
    controller_pid INTEGER, witness_hash TEXT NOT NULL,
    state TEXT NOT NULL, observed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX work_items_ready_idx ON work_items(job_id,state,next_eligible_at,priority);
CREATE INDEX failures_work_item_idx ON failures(work_item_id,created_at);
PRAGMA user_version=3;
INSERT INTO schema_migrations(version) VALUES (3);
"""

SCHEMA_V4 = """
ALTER TABLE receipt_index ADD COLUMN entity_kind TEXT NOT NULL DEFAULT 'action';
ALTER TABLE receipt_index ADD COLUMN work_item_id TEXT REFERENCES work_items(work_item_id);
ALTER TABLE status_projection ADD COLUMN payload_json TEXT;
ALTER TABLE status_projection ADD COLUMN source_digest TEXT;
CREATE TABLE evidence_sets (
    evidence_set_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    work_item_id TEXT NOT NULL REFERENCES work_items(work_item_id),
    artifact_root TEXT NOT NULL,
    manifest_path TEXT NOT NULL UNIQUE,
    manifest_hash TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    evidence_class TEXT NOT NULL,
    state TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    fence_epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE evidence_members (
    evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
    relative_path TEXT NOT NULL,
    media_type TEXT NOT NULL,
    schema_version TEXT,
    size_bytes INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    PRIMARY KEY(evidence_set_id,relative_path)
);
CREATE TABLE verifier_runs (
    verifier_id TEXT PRIMARY KEY,
    work_item_id TEXT NOT NULL REFERENCES work_items(work_item_id),
    evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
    policy_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    checks_hash TEXT NOT NULL,
    receipt_id TEXT,
    owner_id TEXT NOT NULL,
    fence_epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE review_requests (
    review_id TEXT PRIMARY KEY,
    work_item_id TEXT NOT NULL REFERENCES work_items(work_item_id),
    evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
    verifier_id TEXT NOT NULL REFERENCES verifier_runs(verifier_id),
    state TEXT NOT NULL,
    reviewer_thread_id TEXT,
    reviewer_turn_id TEXT,
    schema_digest TEXT NOT NULL,
    model TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    pre_manifest_hash TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    fence_epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE review_results (
    review_id TEXT PRIMARY KEY REFERENCES review_requests(review_id),
    verdict TEXT NOT NULL,
    findings_hash TEXT NOT NULL,
    sidecar_receipt_id TEXT NOT NULL,
    post_manifest_hash TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    fence_epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE gate_decisions (
    decision_id TEXT PRIMARY KEY,
    work_item_id TEXT NOT NULL REFERENCES work_items(work_item_id),
    evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
    verifier_id TEXT NOT NULL REFERENCES verifier_runs(verifier_id),
    review_id TEXT NOT NULL REFERENCES review_results(review_id),
    status TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    receipt_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    fence_epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(work_item_id,evidence_set_id)
);
CREATE TABLE release_profiles (
    profile_id TEXT PRIMARY KEY,
    profile_hash TEXT NOT NULL,
    required_gates_digest TEXT NOT NULL,
    fixture_only INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE release_decisions (
    decision_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    profile_id TEXT NOT NULL REFERENCES release_profiles(profile_id),
    status TEXT NOT NULL,
    release_allowed INTEGER NOT NULL,
    input_digest TEXT NOT NULL,
    blockers_digest TEXT NOT NULL,
    receipt_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE private_witness_index (
    witness_id TEXT PRIMARY KEY,
    work_item_id TEXT NOT NULL REFERENCES work_items(work_item_id),
    event_class TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    spool_name TEXT NOT NULL UNIQUE,
    redaction_policy TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    fence_epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE integrity_incidents (
    incident_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    resolved_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX evidence_sets_work_item_idx ON evidence_sets(work_item_id,created_at);
CREATE INDEX verifier_runs_evidence_idx ON verifier_runs(evidence_set_id,created_at);
CREATE INDEX review_requests_evidence_idx ON review_requests(evidence_set_id,created_at);
CREATE INDEX release_decisions_job_idx ON release_decisions(job_id,created_at);
PRAGMA user_version=4;
INSERT INTO schema_migrations(version) VALUES (4);
"""


def _existing_state(path: Path) -> tuple[int, set[str]]:
    if not path.exists() or path.stat().st_size == 0:
        return 0, set()
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        tables = {str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        return version, tables
    finally:
        connection.close()


def open_database(path: Path) -> sqlite3.Connection:
    version, tables = _existing_state(path)
    if version == 0 and tables:
        raise MigrationRejected("unversioned database contains tables")
    if version > SCHEMA_VERSION:
        raise MigrationRejected(f"database schema {version} is newer than supported {SCHEMA_VERSION}")
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    if version == 0:
        connection.executescript(SCHEMA_V1)
        connection.commit()
        version = 1
    if version == 1:
        connection.executescript(SCHEMA_V2)
        connection.commit()
        version = 2
    if version == 2:
        connection.executescript(SCHEMA_V3)
        connection.commit()
        version = 3
    if version == 3:
        connection.executescript(SCHEMA_V4)
        connection.commit()
    return connection
