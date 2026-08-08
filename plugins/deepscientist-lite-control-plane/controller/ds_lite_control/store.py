from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .errors import FenceRejected, IntegrityIncident, LeaseBusy
from .failure_policy import FailureDecision
from .migrations import SCHEMA_VERSION, open_database


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


class ControlStore:
    """DS Lite domain truth. DBOS runtime state is deliberately separate."""

    def __init__(self, path: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.path = path.resolve()
        self.connection = open_database(self.path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self._clock()
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @staticmethod
    def _stamp(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_stamp(value: str | None) -> datetime | None:
        if not value:
            return None
        normalized = value.replace(" ", "T").replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)

    @property
    def schema_version(self) -> int:
        return int(self.connection.execute("PRAGMA user_version").fetchone()[0])

    def close(self) -> None:
        self.connection.close()

    def integrity_check(self) -> str:
        return str(self.connection.execute("PRAGMA integrity_check").fetchone()[0])

    def _lease_for_action(self, action_id: str) -> str:
        row = self.connection.execute(
            "SELECT a.work_item_id FROM attempts a JOIN actions x ON x.attempt_id=a.attempt_id "
            "WHERE x.action_id=?", (action_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown action")
        return str(row[0])

    def _lease_for_attempt(self, attempt_id: str) -> str:
        row = self.connection.execute(
            "SELECT work_item_id FROM attempts WHERE attempt_id=?", (attempt_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown attempt")
        return str(row[0])

    def _check_fence(self, resource_id: str, owner_id: str, fence_epoch: int) -> None:
        row = self.connection.execute(
            "SELECT expires_at FROM leases WHERE resource_id=? AND owner_id=? AND fence_epoch=?",
            (resource_id, owner_id, fence_epoch),
        ).fetchone()
        expires_at = self._parse_stamp(str(row[0])) if row is not None and row[0] else None
        if row is None or (expires_at is not None and expires_at <= self._now()):
            raise FenceRejected("stale lease epoch")

    def acquire_lease(
        self,
        work_item_id: str,
        owner: str,
        *,
        ttl_seconds: int = 60,
        allow_unexpired_takeover: bool = False,
    ) -> int:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                "SELECT owner_id, fence_epoch, expires_at FROM leases WHERE resource_id=?", (work_item_id,)
            ).fetchone()
            if row is not None and row[0] != owner:
                expires_at = self._parse_stamp(str(row[2])) if row[2] else None
                if not allow_unexpired_takeover and (expires_at is None or expires_at > self._now()):
                    raise LeaseBusy("lease is held by a live owner")
            epoch = int(row[1]) if row is not None and row[0] == owner else (int(row[1]) + 1 if row else 1)
            now = self._now()
            expires = now + timedelta(seconds=ttl_seconds)
            self.connection.execute(
                "INSERT INTO leases(resource_id,owner_id,fence_epoch,expires_at,heartbeat_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(resource_id) DO UPDATE SET "
                "owner_id=excluded.owner_id,fence_epoch=excluded.fence_epoch,"
                "expires_at=excluded.expires_at,heartbeat_at=excluded.heartbeat_at",
                (work_item_id, owner, epoch, self._stamp(expires), self._stamp(now)),
            )
            self.connection.commit()
            return epoch
        except Exception:
            self.connection.rollback()
            raise

    def heartbeat_lease(
        self, work_item_id: str, owner_id: str, fence_epoch: int, *, ttl_seconds: int = 60
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self._check_fence(work_item_id, owner_id, fence_epoch)
            now = self._now()
            cursor = self.connection.execute(
                "UPDATE leases SET heartbeat_at=?,expires_at=? WHERE resource_id=? AND owner_id=? AND fence_epoch=?",
                (self._stamp(now), self._stamp(now + timedelta(seconds=ttl_seconds)),
                 work_item_id, owner_id, fence_epoch),
            )
            if cursor.rowcount != 1:
                raise FenceRejected("stale lease epoch")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def create_job_work_item(
        self, job_id: str, work_item_id: str, owner_id: str, *, lease_ttl_seconds: int = 60
    ) -> int:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                "INSERT OR IGNORE INTO jobs(job_id,goal_hash,state) VALUES(?,?,'running')",
                (job_id, _canonical_hash({"job_id": job_id})),
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO work_items(work_item_id,job_id,type,state) VALUES(?,?,'control','running')",
                (work_item_id, job_id),
            )
            row = self.connection.execute(
                "SELECT owner_id,fence_epoch,expires_at FROM leases WHERE resource_id=?", (work_item_id,)
            ).fetchone()
            if row is not None and row[0] != owner_id:
                expires_at = self._parse_stamp(str(row[2])) if row[2] else None
                if expires_at is None or expires_at > self._now():
                    raise LeaseBusy("lease is held by a live owner")
            epoch = int(row[1]) if row is not None and row[0] == owner_id else (int(row[1]) + 1 if row else 1)
            now = self._now()
            self.connection.execute(
                "INSERT INTO leases(resource_id,owner_id,fence_epoch,expires_at,heartbeat_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(resource_id) DO UPDATE SET owner_id=excluded.owner_id,"
                "fence_epoch=excluded.fence_epoch,expires_at=excluded.expires_at,heartbeat_at=excluded.heartbeat_at",
                (work_item_id, owner_id, epoch,
                 self._stamp(now + timedelta(seconds=lease_ttl_seconds)), self._stamp(now)),
            )
            self.connection.commit()
            return epoch
        except Exception:
            self.connection.rollback()
            raise

    def register_job_graph(
        self,
        job_id: str,
        gates: list[dict[str, Any]],
        dependencies: list[dict[str, str]],
    ) -> None:
        if not job_id or not gates:
            raise ValueError("job_id and gates are required")
        gate_ids = [str(gate["id"]) for gate in gates]
        if len(set(gate_ids)) != len(gate_ids):
            raise IntegrityIncident("duplicate gate identity")
        known = set(gate_ids)
        if any(
            dep.get("predecessor_id") not in known or dep.get("successor_id") not in known
            for dep in dependencies
        ):
            raise ValueError("dependency references an unknown gate")
        adjacency = {gate_id: [] for gate_id in gate_ids}
        indegree = {gate_id: 0 for gate_id in gate_ids}
        for dependency in dependencies:
            predecessor = str(dependency["predecessor_id"])
            successor = str(dependency["successor_id"])
            adjacency[predecessor].append(successor)
            indegree[successor] += 1
        ready = [gate_id for gate_id, degree in indegree.items() if degree == 0]
        visited = 0
        while ready:
            current = ready.pop()
            visited += 1
            for successor in adjacency[current]:
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    ready.append(successor)
        if visited != len(gate_ids):
            raise ValueError("dependency graph contains a cycle")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                "INSERT OR IGNORE INTO jobs(job_id,goal_hash,state) VALUES(?,?,'running')",
                (job_id, _canonical_hash({"job_id": job_id, "gates": gate_ids})),
            )
            for gate in gates:
                gate_id = str(gate["id"])
                existing = self.connection.execute(
                    "SELECT job_id,type,priority FROM work_items WHERE work_item_id=?", (gate_id,)
                ).fetchone()
                expected = (job_id, str(gate["type"]), int(gate.get("priority", 0)))
                if existing is not None and tuple(existing) != expected:
                    raise IntegrityIncident("gate identity reused with conflicting content")
                self.connection.execute(
                    "INSERT OR IGNORE INTO work_items(work_item_id,job_id,type,state,priority,max_attempts,"
                    "failure_policy,evidence_class) VALUES(?,?,?,'pending',?,?,?,?)",
                    (gate_id, job_id, expected[1], expected[2], int(gate.get("max_attempts", 3)),
                     str(gate.get("failure_policy", "standard")),
                     str(gate.get("evidence_class", "offline"))),
                )
            for dependency in dependencies:
                self.connection.execute(
                    "INSERT OR IGNORE INTO dependencies(predecessor_id,successor_id,required_outcome) "
                    "VALUES(?,?,?)",
                    (dependency["predecessor_id"], dependency["successor_id"],
                     dependency.get("required_outcome", "completed")),
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def claim_ready_items(
        self,
        job_id: str,
        owner_id: str,
        *,
        max_concurrency: int,
        retry_concurrency: int,
        lease_ttl_seconds: int = 60,
    ) -> list[dict[str, Any]]:
        if max_concurrency <= 0 or retry_concurrency < 0:
            raise ValueError("invalid concurrency budget")
        now = self._now()
        now_text = self._stamp(now)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            running = int(self.connection.execute(
                "SELECT COUNT(*) FROM work_items WHERE job_id=? AND state='running'", (job_id,)
            ).fetchone()[0])
            running_retries = int(self.connection.execute(
                "SELECT COUNT(*) FROM work_items WHERE job_id=? AND state='running' AND attempt_count>1",
                (job_id,),
            ).fetchone()[0])
            available = max(0, max_concurrency - running)
            if available == 0:
                self.connection.commit()
                return []
            rows = self.connection.execute(
                "SELECT w.work_item_id,w.attempt_count,w.priority FROM work_items w "
                "WHERE w.job_id=? AND w.state='pending' "
                "AND (w.next_eligible_at IS NULL OR w.next_eligible_at<=?) "
                "AND NOT EXISTS ("
                " SELECT 1 FROM dependencies d JOIN work_items p ON p.work_item_id=d.predecessor_id "
                " WHERE d.successor_id=w.work_item_id AND (p.state!='terminal' OR "
                " (d.required_outcome!='terminal' AND COALESCE(p.result_class,'')!=d.required_outcome))"
                ") ORDER BY w.priority DESC,w.work_item_id",
                (job_id, now_text),
            ).fetchall()
            claims: list[dict[str, Any]] = []
            for row in rows:
                if len(claims) >= available:
                    break
                is_retry = int(row[1]) > 0
                if is_retry and running_retries >= retry_concurrency:
                    continue
                lease = self.connection.execute(
                    "SELECT owner_id,fence_epoch,expires_at FROM leases WHERE resource_id=?",
                    (row[0],),
                ).fetchone()
                if lease is not None and lease[0] != owner_id:
                    expires = self._parse_stamp(str(lease[2])) if lease[2] else None
                    if expires is None or expires > now:
                        continue
                epoch = (
                    int(lease[1]) if lease is not None and lease[0] == owner_id
                    else int(lease[1]) + 1 if lease is not None else 1
                )
                expires_text = self._stamp(now + timedelta(seconds=lease_ttl_seconds))
                self.connection.execute(
                    "INSERT INTO leases(resource_id,owner_id,fence_epoch,expires_at,heartbeat_at) "
                    "VALUES(?,?,?,?,?) ON CONFLICT(resource_id) DO UPDATE SET "
                    "owner_id=excluded.owner_id,fence_epoch=excluded.fence_epoch,"
                    "expires_at=excluded.expires_at,heartbeat_at=excluded.heartbeat_at",
                    (row[0], owner_id, epoch, expires_text, now_text),
                )
                attempt_number = int(row[1]) + 1
                attempt_id = f"{row[0]}:attempt:{attempt_number}"
                action_id = f"{row[0]}:action:{attempt_number}"
                payload_hash = _canonical_hash({
                    "job_id": job_id, "work_item_id": str(row[0]),
                    "attempt_number": attempt_number,
                })
                self.connection.execute(
                    "INSERT INTO attempts(attempt_id,work_item_id,ordinal,state,input_hash,config_hash) "
                    "VALUES(?,?,?,'running',?,?)",
                    (attempt_id, row[0], attempt_number, payload_hash,
                     _canonical_hash({"workflow": "run_gate_v1"})),
                )
                self.connection.execute(
                    "INSERT INTO actions(action_id,attempt_id,type,state,idempotency_marker,payload_hash,"
                    "owner_id,fence_epoch) VALUES(?,?,'gate-action','planned',?,?,?,?)",
                    (action_id, attempt_id, action_id, payload_hash, owner_id, epoch),
                )
                self.connection.execute(
                    "INSERT INTO outbox(outbox_id,action_id,state,owner_id,fence_epoch) "
                    "VALUES(?,?,'queued',?,?)",
                    (action_id, action_id, owner_id, epoch),
                )
                self.connection.execute(
                    "UPDATE work_items SET state='running',attempt_count=?,updated_at=CURRENT_TIMESTAMP "
                    "WHERE work_item_id=?",
                    (attempt_number, row[0]),
                )
                claims.append({
                    "job_id": job_id, "work_item_id": str(row[0]), "owner_id": owner_id,
                    "fence_epoch": epoch, "attempt_number": attempt_number,
                    "attempt_id": attempt_id, "action_id": action_id,
                })
                if is_retry:
                    running_retries += 1
            self.connection.commit()
            return claims
        except Exception:
            self.connection.rollback()
            raise

    def recover_expired_running_items(
        self, job_id: str, owner_id: str, *, lease_ttl_seconds: int = 60,
    ) -> list[dict[str, Any]]:
        if lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds must be positive")
        now = self._now()
        now_text = self._stamp(now)
        expires_text = self._stamp(now + timedelta(seconds=lease_ttl_seconds))
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            rows = self.connection.execute(
                "SELECT w.work_item_id,w.attempt_count,l.fence_epoch,a.attempt_id,x.action_id "
                "FROM work_items w JOIN leases l ON l.resource_id=w.work_item_id "
                "JOIN attempts a ON a.work_item_id=w.work_item_id AND a.ordinal=w.attempt_count "
                "JOIN actions x ON x.attempt_id=a.attempt_id "
                "WHERE w.job_id=? AND w.state='running' AND l.expires_at IS NOT NULL "
                "AND l.expires_at<=? ORDER BY w.priority DESC,w.work_item_id",
                (job_id, now_text),
            ).fetchall()
            recovered: list[dict[str, Any]] = []
            for row in rows:
                epoch = int(row[2]) + 1
                self.connection.execute(
                    "UPDATE leases SET owner_id=?,fence_epoch=?,expires_at=?,heartbeat_at=? "
                    "WHERE resource_id=? AND expires_at<=?",
                    (owner_id, epoch, expires_text, now_text, row[0], now_text),
                )
                self.connection.execute(
                    "UPDATE actions SET owner_id=?,fence_epoch=? WHERE action_id=?",
                    (owner_id, epoch, row[4]),
                )
                self.connection.execute(
                    "UPDATE outbox SET owner_id=?,fence_epoch=? WHERE action_id=?",
                    (owner_id, epoch, row[4]),
                )
                self.connection.execute(
                    "UPDATE workflow_bindings SET owner_id=?,fence_epoch=? WHERE action_id=?",
                    (owner_id, epoch, row[4]),
                )
                self.connection.execute(
                    "UPDATE thread_bindings SET owner_id=?,fence_epoch=? WHERE attempt_id=?",
                    (owner_id, epoch, row[3]),
                )
                self.connection.execute(
                    "UPDATE rpc_requests SET owner_id=?,fence_epoch=? WHERE action_id=? "
                    "AND state!='terminal'",
                    (owner_id, epoch, row[4]),
                )
                recovered.append({
                    "job_id": job_id, "work_item_id": str(row[0]),
                    "owner_id": owner_id, "fence_epoch": epoch,
                    "attempt_number": int(row[1]), "attempt_id": str(row[3]),
                    "action_id": str(row[4]),
                })
            self.connection.commit()
            return recovered
        except Exception:
            self.connection.rollback()
            raise

    def apply_failure(
        self,
        work_item_id: str,
        owner_id: str,
        fence_epoch: int,
        attempt_number: int,
        decision: FailureDecision,
        evidence_hash: str,
    ) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self._check_fence(work_item_id, owner_id, fence_epoch)
            row = self.connection.execute(
                "SELECT last_failure_signature,failure_streak FROM work_items WHERE work_item_id=?",
                (work_item_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown work item")
            streak = int(row[1]) + 1 if row[0] == decision.signature else 1
            state = {
                "cooldown": "cooldown",
                "awaiting_user_action": "awaiting_user_action",
                "reconciling": "reconciling",
                "valid_negative": "terminal",
            }.get(decision.disposition, "failed")
            circuit_state = "open" if decision.disposition == "cooldown" and streak >= 5 else "closed"
            next_eligible = decision.next_eligible_at
            if circuit_state == "open":
                next_eligible = self._stamp(self._now() + timedelta(minutes=15))
            failure_id = f"failure-{work_item_id}-{attempt_number}"
            self.connection.execute(
                "INSERT INTO failures(failure_id,layer,class,disposition,signature,retry_after,"
                "work_item_id,impact_scope,next_action,evidence_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (failure_id, decision.layer, decision.failure_class, decision.disposition,
                 decision.signature, decision.next_eligible_at, work_item_id,
                 decision.impact_scope, decision.next_action, evidence_hash, self._stamp(self._now())),
            )
            self.connection.execute(
                "UPDATE work_items SET state=?,next_eligible_at=?,circuit_state=?,failure_streak=?,"
                "last_failure_signature=?,result_class=CASE WHEN ?='valid_negative' THEN 'valid_negative' "
                "ELSE result_class END,updated_at=CURRENT_TIMESTAMP WHERE work_item_id=?",
                (state, next_eligible, circuit_state, streak, decision.signature,
                 decision.disposition, work_item_id),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def requeue_due(self, job_id: str) -> int:
        now = self._stamp(self._now())
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = self.connection.execute(
                "UPDATE work_items SET state='pending',circuit_state='closed',updated_at=CURRENT_TIMESTAMP "
                "WHERE job_id=? AND state='cooldown' AND next_eligible_at<=?",
                (job_id, now),
            )
            self.connection.commit()
            return int(cursor.rowcount)
        except Exception:
            self.connection.rollback()
            raise

    def mark_gate_ready_if_due(
        self, work_item_id: str, owner_id: str, fence_epoch: int
    ) -> str:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self._check_fence(work_item_id, owner_id, fence_epoch)
            row = self.connection.execute(
                "SELECT state,next_eligible_at FROM work_items WHERE work_item_id=?",
                (work_item_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown work item")
            state = str(row[0])
            due = self._parse_stamp(str(row[1])) if row[1] else None
            if state == "cooldown" and due is not None and due <= self._now():
                self.connection.execute(
                    "UPDATE work_items SET state='pending',circuit_state='closed',"
                    "updated_at=CURRENT_TIMESTAMP WHERE work_item_id=?",
                    (work_item_id,),
                )
                state = "pending"
            self.connection.commit()
            return state
        except Exception:
            self.connection.rollback()
            raise

    def complete_work_item(
        self,
        work_item_id: str,
        owner_id: str,
        fence_epoch: int,
        *,
        outcome: str,
        evidence_hash: str,
    ) -> str | None:
        if outcome not in {"completed", "failed", "ambiguous", "valid_negative", "release_blocked"}:
            raise ValueError("unsupported gate outcome")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self._check_fence(work_item_id, owner_id, fence_epoch)
            existing = self.connection.execute(
                "SELECT outcome,evidence_hash FROM gate_results WHERE result_id=?",
                (f"result-{work_item_id}",),
            ).fetchone()
            if existing is not None and tuple(existing) != (outcome, evidence_hash):
                raise IntegrityIncident("gate result identity conflict")
            self.connection.execute(
                "INSERT OR IGNORE INTO gate_results(result_id,work_item_id,outcome,evidence_hash,"
                "owner_id,fence_epoch,created_at) VALUES(?,?,?,?,?,?,?)",
                (f"result-{work_item_id}", work_item_id, outcome, evidence_hash,
                 owner_id, fence_epoch, self._stamp(self._now())),
            )
            self.connection.execute(
                "UPDATE work_items SET state='terminal',result_class=?,updated_at=CURRENT_TIMESTAMP "
                "WHERE work_item_id=?",
                (outcome, work_item_id),
            )
            self.connection.execute(
                "UPDATE actions SET state='terminal' WHERE attempt_id IN ("
                "SELECT attempt_id FROM attempts WHERE work_item_id=?)",
                (work_item_id,),
            )
            self.connection.execute(
                "UPDATE outbox SET state='terminal' WHERE action_id IN ("
                "SELECT x.action_id FROM actions x JOIN attempts a ON a.attempt_id=x.attempt_id "
                "WHERE a.work_item_id=?)",
                (work_item_id,),
            )
            successor: str | None = None
            if outcome == "valid_negative":
                row = self.connection.execute(
                    "SELECT job_id,type,priority FROM work_items WHERE work_item_id=?", (work_item_id,)
                ).fetchone()
                successor = f"{work_item_id}:iteration:2"
                self.connection.execute(
                    "INSERT OR IGNORE INTO work_items(work_item_id,job_id,type,state,priority) "
                    "VALUES(?,?,?,'pending',?)",
                    (successor, row[0], "iteration", int(row[2])),
                )
                self.connection.execute(
                    "INSERT OR IGNORE INTO dependencies(predecessor_id,successor_id,required_outcome) "
                    "VALUES(?,?,'valid_negative')",
                    (work_item_id, successor),
                )
            job_id = self.connection.execute(
                "SELECT job_id FROM work_items WHERE work_item_id=?", (work_item_id,)
            ).fetchone()[0]
            self.connection.execute(
                "UPDATE jobs SET state=CASE WHEN NOT EXISTS ("
                "SELECT 1 FROM work_items WHERE job_id=? AND state!='terminal'"
                ") THEN 'terminal' ELSE 'running' END WHERE job_id=?",
                (job_id, job_id),
            )
            self.connection.commit()
            return successor
        except Exception:
            self.connection.rollback()
            raise

    def work_item(self, work_item_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM work_items WHERE work_item_id=?", (work_item_id,)
        ).fetchone()
        if row is None:
            raise ValueError("unknown work item")
        return dict(row)

    def dependency(self, successor_id: str) -> dict[str, str] | None:
        row = self.connection.execute(
            "SELECT predecessor_id,required_outcome FROM dependencies WHERE successor_id=?",
            (successor_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def create_context_handoff(
        self,
        predecessor_attempt_id: str,
        owner_id: str,
        fence_epoch: int,
        *,
        state_pack_hash: str,
        evidence_hash: str,
    ) -> str:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                "SELECT work_item_id,ordinal,input_hash,config_hash FROM attempts WHERE attempt_id=?",
                (predecessor_attempt_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown predecessor attempt")
            self._check_fence(str(row[0]), owner_id, fence_epoch)
            successor = f"{row[0]}:attempt:{int(row[1]) + 1}"
            handoff_id = f"handoff-{predecessor_attempt_id}"
            existing = self.connection.execute(
                "SELECT successor_attempt_id,state_pack_hash,evidence_hash FROM handoffs "
                "WHERE handoff_id=?",
                (handoff_id,),
            ).fetchone()
            expected = (successor, state_pack_hash, evidence_hash)
            if existing is not None and tuple(existing) != expected:
                raise IntegrityIncident("handoff identity reused with conflicting content")
            self.connection.execute(
                "UPDATE attempts SET state='frozen' WHERE attempt_id=? AND state!='terminal'",
                (predecessor_attempt_id,),
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO attempts(attempt_id,work_item_id,ordinal,state,input_hash,config_hash) "
                "VALUES(?,?,?,'queued',?,?)",
                (successor, row[0], int(row[1]) + 1, row[2], row[3]),
            )
            thread = self.connection.execute(
                "SELECT thread_id FROM thread_bindings WHERE attempt_id=?",
                (predecessor_attempt_id,),
            ).fetchone()
            self.connection.execute(
                "INSERT OR IGNORE INTO handoffs(handoff_id,predecessor_attempt_id,successor_attempt_id,"
                "state_pack_hash,evidence_hash,predecessor_thread_id,owner_id,fence_epoch,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (handoff_id, predecessor_attempt_id, successor, state_pack_hash, evidence_hash,
                 str(thread[0]) if thread is not None and thread[0] else None,
                 owner_id, fence_epoch, self._stamp(self._now())),
            )
            self.connection.commit()
            return successor
        except Exception:
            self.connection.rollback()
            raise

    def record_supervisor_heartbeat(
        self,
        supervisor_id: str,
        owner_id: str,
        *,
        controller_pid: int | None,
        witness_hash: str,
        ttl_seconds: int = 60,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        now = self._now()
        expires = now + timedelta(seconds=ttl_seconds)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self.connection.execute(
                "SELECT owner_id FROM supervisor_heartbeats WHERE supervisor_id=?",
                (supervisor_id,),
            ).fetchone()
            if existing is not None and existing[0] != owner_id:
                raise IntegrityIncident("supervisor identity changed owner")
            self.connection.execute(
                "INSERT INTO supervisor_heartbeats(supervisor_id,owner_id,controller_pid,witness_hash,"
                "state,observed_at,expires_at) VALUES(?,?,?,?, 'active',?,?) "
                "ON CONFLICT(supervisor_id) DO UPDATE SET controller_pid=excluded.controller_pid,"
                "witness_hash=excluded.witness_hash,state='active',observed_at=excluded.observed_at,"
                "expires_at=excluded.expires_at",
                (supervisor_id, owner_id, controller_pid, witness_hash,
                 self._stamp(now), self._stamp(expires)),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def stop_supervisor(self, supervisor_id: str, owner_id: str) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = self.connection.execute(
                "UPDATE supervisor_heartbeats SET state='stopped',expires_at=?,observed_at=? "
                "WHERE supervisor_id=? AND owner_id=?",
                (self._stamp(self._now()), self._stamp(self._now()), supervisor_id, owner_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("unknown supervisor")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def project_job_status(
        self, job_id: str, *, supervisor_id: str | None = None
    ) -> dict[str, Any]:
        job = self.connection.execute(
            "SELECT job_id,state FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if job is None:
            raise ValueError("unknown job")
        now = self._now()
        supervisor = None
        if supervisor_id is not None:
            supervisor = self.connection.execute(
                "SELECT supervisor_id,owner_id,controller_pid,witness_hash,state,observed_at,expires_at "
                "FROM supervisor_heartbeats WHERE supervisor_id=?",
                (supervisor_id,),
            ).fetchone()
        supervisor_stale = True
        supervisor_live = False
        if supervisor is not None:
            observed = self._parse_stamp(str(supervisor[5]))
            expires = self._parse_stamp(str(supervisor[6]))
            supervisor_stale = observed is None or (now - observed).total_seconds() >= 120
            supervisor_live = (
                supervisor[4] == "active" and expires is not None and expires > now
                and not supervisor_stale
            )

        gates: list[dict[str, Any]] = []
        rows = self.connection.execute(
            "SELECT * FROM work_items WHERE job_id=? ORDER BY priority DESC,work_item_id",
            (job_id,),
        ).fetchall()
        for item in rows:
            item_value = dict(item)
            attempt = self.connection.execute(
                "SELECT attempt_id,ordinal,state FROM attempts WHERE work_item_id=? "
                "ORDER BY ordinal DESC LIMIT 1",
                (item["work_item_id"],),
            ).fetchone()
            action = None
            outbox = None
            thread = None
            if attempt is not None:
                action = self.connection.execute(
                    "SELECT action_id,state FROM actions WHERE attempt_id=? ORDER BY action_id DESC LIMIT 1",
                    (attempt[0],),
                ).fetchone()
                thread = self.connection.execute(
                    "SELECT thread_id,last_turn_id,lifecycle_state,pending_archive FROM thread_bindings "
                    "WHERE attempt_id=?",
                    (attempt[0],),
                ).fetchone()
            if action is not None:
                outbox = self.connection.execute(
                    "SELECT state,not_before FROM outbox WHERE action_id=?", (action[0],)
                ).fetchone()
            lease = self.connection.execute(
                "SELECT owner_id,fence_epoch,heartbeat_at,expires_at FROM leases WHERE resource_id=?",
                (item["work_item_id"],),
            ).fetchone()
            lease_expires = self._parse_stamp(str(lease[3])) if lease is not None and lease[3] else None
            lease_valid = lease is not None and lease_expires is not None and lease_expires > now
            outbox_durable = outbox is not None and outbox[0] not in {"terminal", "cancelled"}
            confirmed = bool(supervisor_live and lease_valid and outbox_durable)
            state = str(item["state"])
            if state == "cooldown":
                next_action = f"wait-until:{item['next_eligible_at']}"
            elif state == "reconciling":
                next_action = f"reconcile:{action[0] if action is not None else item['work_item_id']}"
            elif state == "awaiting_user_action":
                next_action = "await-user-action"
            elif outbox_durable:
                next_action = f"dispatch:{action[0]}"
            else:
                next_action = "none" if state == "terminal" else "schedule"
            evidence = self.connection.execute(
                "SELECT evidence_set_id,manifest_hash FROM evidence_sets WHERE work_item_id=? "
                "ORDER BY created_at DESC LIMIT 1", (item["work_item_id"],)
            ).fetchone()
            verifier = self.connection.execute(
                "SELECT verifier_id,status,receipt_id FROM verifier_runs WHERE work_item_id=? "
                "ORDER BY created_at DESC LIMIT 1", (item["work_item_id"],)
            ).fetchone()
            review = self.connection.execute(
                "SELECT q.review_id,r.verdict,r.sidecar_receipt_id FROM review_requests q "
                "LEFT JOIN review_results r ON r.review_id=q.review_id WHERE q.work_item_id=? "
                "ORDER BY q.created_at DESC LIMIT 1", (item["work_item_id"],)
            ).fetchone()
            gate_decision = self.connection.execute(
                "SELECT decision_id,status,receipt_id FROM gate_decisions WHERE work_item_id=? "
                "ORDER BY created_at DESC LIMIT 1", (item["work_item_id"],)
            ).fetchone()
            sources = [{"kind": "domain-work-item", "id": str(item["work_item_id"])}]
            if evidence is not None:
                sources.append({"kind": "evidence-set", "id": str(evidence[0]), "hash": str(evidence[1])})
            if verifier is not None:
                sources.append({"kind": "verifier-receipt", "id": str(verifier[2])})
            if review is not None and review[2] is not None:
                sources.append({"kind": "review-receipt", "id": str(review[2])})
            if gate_decision is not None:
                sources.append({"kind": "gate-decision", "id": str(gate_decision[2])})
            gates.append({
                "work_item_id": str(item["work_item_id"]), "type": str(item["type"]),
                "state": state, "result_class": item["result_class"],
                "attempt_id": str(attempt[0]) if attempt is not None else None,
                "action_id": str(action[0]) if action is not None else None,
                "outbox_state": str(outbox[0]) if outbox is not None else None,
                "owner_id": str(lease[0]) if lease is not None else None,
                "fence_epoch": int(lease[1]) if lease is not None else None,
                "lease_valid": bool(lease_valid),
                "canonical_thread_id": str(thread[0]) if thread is not None and thread[0] else None,
                "canonical_turn_id": str(thread[1]) if thread is not None and thread[1] else None,
                "next_eligible_at": item["next_eligible_at"],
                "next_durable_action": next_action,
                "continuation_confirmed": confirmed,
                "evidence_class": str(item_value["evidence_class"]),
                "evidence_set_id": str(evidence[0]) if evidence is not None else None,
                "verifier_status": str(verifier[1]) if verifier is not None else None,
                "review_verdict": str(review[1]) if review is not None and review[1] is not None else None,
                "gate_decision": str(gate_decision[1]) if gate_decision is not None else None,
                "sources": sources,
            })
        release = self.connection.execute(
            "SELECT decision_id,profile_id,status,release_allowed,receipt_id FROM release_decisions "
            "WHERE job_id=? ORDER BY created_at DESC LIMIT 1", (job_id,)
        ).fetchone()
        release_receipt: dict[str, Any] | None = None
        release_source: dict[str, Any] | None = None
        if release is not None:
            indexed = self.connection.execute(
                "SELECT path,content_hash FROM receipt_index WHERE receipt_id=?", (release[4],)
            ).fetchone()
            if indexed is not None:
                receipt_path = self.path.parent / "receipts" / str(indexed[0])
                try:
                    raw = receipt_path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() == indexed[1]:
                        parsed = json.loads(raw.decode("utf-8"))
                        if isinstance(parsed, dict) and parsed.get("decision_id") == release[0]:
                            release_receipt = parsed
                            release_source = {
                                "kind": "release-decision",
                                "id": str(release[4]),
                                "hash": str(indexed[1]),
                            }
                except (OSError, UnicodeError, json.JSONDecodeError):
                    release_receipt = None
        release_valid = release_receipt is not None
        release_allowed = bool(release[3]) if release is not None and release_valid else False
        release_blockers = []
        if release_receipt is not None:
            release_blockers = [
                *[f"missing:{item}" for item in release_receipt.get("missing_gates", [])],
                *[f"nonpassing:{item}" for item in release_receipt.get("nonpassing_gates", [])],
            ]
            if release_receipt.get("unresolved_integrity_incidents", 0):
                release_blockers.append("unresolved-integrity-incidents")
        elif release is not None:
            release_blockers = ["release-receipt-unreadable"]
        unresolved = int(self.connection.execute(
            "SELECT COUNT(*) FROM integrity_incidents WHERE resolved_at IS NULL"
        ).fetchone()[0])
        return {
            "schema_version": "ds-lite.project-status.v3",
            "job_id": job_id,
            "job_state": str(job[1]),
            "gates": gates,
            "supervisor_id": supervisor_id,
            "supervisor_stale": bool(supervisor_stale),
            "continuation_confirmed": any(gate["continuation_confirmed"] for gate in gates),
            "release": {
                "decision_id": str(release[0]) if release is not None else None,
                "profile_id": str(release[1]) if release is not None else None,
                "status": str(release[2]) if release is not None and release_valid else "blocked",
                "release_allowed": release_allowed,
                "blockers": release_blockers,
                "source_receipt": str(release[4]) if release is not None else None,
                "sources": [release_source] if release_source is not None else [],
            },
            "integrity": {
                "unresolved_incidents": unresolved,
                "dispatch_paused": unresolved > 0,
            },
            "release_allowed": release_allowed,
        }

    def record_integrity_incident(
        self, incident_id: str, *, scope: str, entity_id: str,
        reason_code: str, evidence_hash: str,
    ) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self.connection.execute(
                "SELECT scope,entity_id,reason_code,evidence_hash FROM integrity_incidents "
                "WHERE incident_id=?", (incident_id,)
            ).fetchone()
            expected = (scope, entity_id, reason_code, evidence_hash)
            if existing is not None and tuple(existing) != expected:
                raise IntegrityIncident("integrity incident identity conflict")
            self.connection.execute(
                "INSERT OR IGNORE INTO integrity_incidents(incident_id,scope,entity_id,reason_code,"
                "evidence_hash,created_at) VALUES(?,?,?,?,?,?)",
                (incident_id, scope, entity_id, reason_code, evidence_hash,
                 self._stamp(self._now())),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def assert_dispatch_allowed(self) -> None:
        unresolved = int(self.connection.execute(
            "SELECT COUNT(*) FROM integrity_incidents WHERE resolved_at IS NULL"
        ).fetchone()[0])
        if unresolved:
            raise IntegrityIncident("dispatch paused by unresolved integrity incident")

    def plan_attempt_action(self, *, job_id: str, work_item_id: str, attempt_id: str,
                            action_id: str, kind: str, payload_hash: str,
                            owner_id: str, fence_epoch: int) -> dict[str, str]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self._check_fence(work_item_id, owner_id, fence_epoch)
            existing = self.connection.execute(
                "SELECT type,payload_hash,attempt_id FROM actions WHERE action_id=?", (action_id,)
            ).fetchone()
            if existing is not None:
                if (existing[0], existing[1], existing[2]) != (kind, payload_hash, attempt_id):
                    raise IntegrityIncident("action identity reused with conflicting content")
                self.connection.commit()
                return {"action_id": action_id, "outbox_id": action_id}
            item = self.connection.execute(
                "SELECT job_id FROM work_items WHERE work_item_id=?", (work_item_id,)
            ).fetchone()
            if item is None or item[0] != job_id:
                raise ValueError("unknown job/work item")
            self.connection.execute(
                "INSERT INTO attempts(attempt_id,work_item_id,ordinal,state,input_hash,config_hash) "
                "VALUES(?,?,1,'queued',?,?)",
                (attempt_id, work_item_id, payload_hash, _canonical_hash({"kind": kind})),
            )
            self.connection.execute(
                "INSERT INTO actions(action_id,attempt_id,type,state,idempotency_marker,payload_hash,owner_id,fence_epoch) "
                "VALUES(?,?,?,'planned',?,?,?,?)",
                (action_id, attempt_id, kind, action_id, payload_hash, owner_id, fence_epoch),
            )
            self.connection.execute(
                "INSERT INTO outbox(outbox_id,action_id,state,owner_id,fence_epoch) VALUES(?,?,'queued',?,?)",
                (action_id, action_id, owner_id, fence_epoch),
            )
            self.connection.commit()
            return {"action_id": action_id, "outbox_id": action_id}
        except Exception:
            self.connection.rollback()
            raise

    def transition_outbox(self, action_id: str, state: str, owner_id: str, fence_epoch: int) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            resource = self._lease_for_action(action_id)
            self._check_fence(resource, owner_id, fence_epoch)
            current = self.connection.execute(
                "SELECT state FROM outbox WHERE action_id=?", (action_id,)
            ).fetchone()
            if current is None:
                raise ValueError("missing outbox")
            if current[0] == "terminal" and state != "terminal":
                raise IntegrityIncident("terminal outbox cannot be reopened")
            cursor = self.connection.execute(
                "UPDATE outbox SET state=?,owner_id=?,fence_epoch=?,dispatch_count=dispatch_count+1 "
                "WHERE action_id=?", (state, owner_id, fence_epoch, action_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("missing outbox")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def action_state(self, action_id: str) -> str:
        row = self.connection.execute("SELECT state FROM actions WHERE action_id=?", (action_id,)).fetchone()
        if row is None:
            raise ValueError("unknown action")
        return str(row[0])

    def bind_canonical_thread(self, attempt_id: str, adapter: str, thread_id: str,
                              schema_digest: str, owner_id: str,
                              fence_epoch: int) -> dict[str, Any]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            resource = self._lease_for_attempt(attempt_id)
            self._check_fence(resource, owner_id, fence_epoch)
            existing = self.connection.execute(
                "SELECT adapter,thread_id,schema_digest FROM thread_bindings WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            expected = (adapter, thread_id, schema_digest)
            if existing is not None and tuple(existing) != expected:
                raise IntegrityIncident("canonical thread binding conflict")
            self.connection.execute(
                "INSERT OR IGNORE INTO thread_bindings(attempt_id,adapter,thread_id,schema_digest,"
                "lifecycle_state,pending_archive,owner_id,fence_epoch) VALUES(?,?,?,?,'active',0,?,?)",
                (attempt_id, adapter, thread_id, schema_digest, owner_id, fence_epoch),
            )
            self.connection.execute(
                "UPDATE thread_bindings SET lifecycle_state='active',owner_id=?,fence_epoch=?,"
                "last_reconciled_at=CURRENT_TIMESTAMP WHERE attempt_id=?",
                (owner_id, fence_epoch, attempt_id),
            )
            self.connection.commit()
            return self.thread_binding(attempt_id)
        except Exception:
            self.connection.rollback()
            raise

    def thread_binding(self, attempt_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT attempt_id,adapter,thread_id,last_turn_id,schema_digest,lifecycle_state,"
            "pending_archive,last_reconciled_at,owner_id,fence_epoch FROM thread_bindings "
            "WHERE attempt_id=?", (attempt_id,),
        ).fetchone()
        if row is None:
            raise ValueError("canonical thread is not bound")
        return dict(row)

    def set_thread_archive_pending(self, attempt_id: str, pending: bool, owner_id: str,
                                   fence_epoch: int) -> dict[str, Any]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            resource = self._lease_for_attempt(attempt_id)
            self._check_fence(resource, owner_id, fence_epoch)
            cursor = self.connection.execute(
                "UPDATE thread_bindings SET pending_archive=?,lifecycle_state=?,owner_id=?,"
                "fence_epoch=?,last_reconciled_at=CURRENT_TIMESTAMP WHERE attempt_id=?",
                (int(pending), "archive_pending" if pending else "active", owner_id,
                 fence_epoch, attempt_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("canonical thread is not bound")
            self.connection.commit()
            return self.thread_binding(attempt_id)
        except Exception:
            self.connection.rollback()
            raise

    def complete_thread_archive(self, attempt_id: str, owner_id: str,
                                fence_epoch: int) -> dict[str, Any]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            resource = self._lease_for_attempt(attempt_id)
            self._check_fence(resource, owner_id, fence_epoch)
            cursor = self.connection.execute(
                "UPDATE thread_bindings SET pending_archive=0,lifecycle_state='archived',"
                "owner_id=?,fence_epoch=?,last_reconciled_at=CURRENT_TIMESTAMP WHERE attempt_id=?",
                (owner_id, fence_epoch, attempt_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("canonical thread is not bound")
            self.connection.commit()
            return self.thread_binding(attempt_id)
        except Exception:
            self.connection.rollback()
            raise

    def plan_rpc_request(self, *, request_id: str, action_id: str, method: str,
                         params_hash: str, pre_dispatch_turn_id: str | None,
                         owner_id: str, fence_epoch: int) -> dict[str, Any]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            resource = self._lease_for_action(action_id)
            self._check_fence(resource, owner_id, fence_epoch)
            existing = self.connection.execute(
                "SELECT action_id,method,params_hash,pre_dispatch_turn_id FROM rpc_requests "
                "WHERE request_id=?", (request_id,),
            ).fetchone()
            expected = (action_id, method, params_hash, pre_dispatch_turn_id)
            if existing is not None and tuple(existing) != expected:
                raise IntegrityIncident("rpc request identity conflict")
            self.connection.execute(
                "INSERT OR IGNORE INTO rpc_requests(request_id,action_id,method,params_hash,state,"
                "pre_dispatch_turn_id,owner_id,fence_epoch) VALUES(?,?,?,?,'planned',?,?,?)",
                (request_id, action_id, method, params_hash, pre_dispatch_turn_id,
                 owner_id, fence_epoch),
            )
            self.connection.commit()
            return self.rpc_request(request_id)
        except Exception:
            self.connection.rollback()
            raise

    def rpc_request(self, request_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT request_id,action_id,method,params_hash,state,wire_request_id,thread_id,turn_id,"
            "pre_dispatch_turn_id,response_hash,error_class,owner_id,fence_epoch FROM rpc_requests "
            "WHERE request_id=?", (request_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown rpc request")
        return dict(row)

    def transition_rpc_request(self, request_id: str, state: str, owner_id: str,
                               fence_epoch: int, *, wire_request_id: int | None = None,
                               thread_id: str | None = None, turn_id: str | None = None,
                               response_hash: str | None = None,
                               error_class: str | None = None) -> dict[str, Any]:
        allowed = {
            "planned": {"planned", "written", "ambiguous"},
            "written": {"written", "acknowledged", "terminal", "ambiguous"},
            "acknowledged": {"acknowledged", "terminal", "ambiguous"},
            "ambiguous": {"ambiguous", "acknowledged", "terminal"},
            "terminal": {"terminal"},
        }
        if state not in allowed:
            raise ValueError("unsupported rpc request state")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                "SELECT action_id,state,wire_request_id,thread_id,turn_id,response_hash,error_class "
                "FROM rpc_requests WHERE request_id=?", (request_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown rpc request")
            resource = self._lease_for_action(str(row[0]))
            self._check_fence(resource, owner_id, fence_epoch)
            if state not in allowed[str(row[1])]:
                raise IntegrityIncident("rpc request state regression")
            supplied = (wire_request_id, thread_id, turn_id, response_hash, error_class)
            current = tuple(row[index] for index in range(2, 7))
            for old, new in zip(current, supplied):
                if old is not None and new is not None and old != new:
                    raise IntegrityIncident("rpc request observation conflict")
            merged = tuple(new if new is not None else old for old, new in zip(current, supplied))
            self.connection.execute(
                "UPDATE rpc_requests SET state=?,wire_request_id=?,thread_id=?,turn_id=?,response_hash=?,"
                "error_class=?,owner_id=?,fence_epoch=?,updated_at=CURRENT_TIMESTAMP WHERE request_id=?",
                (state, *merged, owner_id, fence_epoch, request_id),
            )
            self.connection.commit()
            return self.rpc_request(request_id)
        except Exception:
            self.connection.rollback()
            raise

    def append_protocol_event(self, *, journal_id: str, request_id: str | None,
                              direction: str, message_kind: str, method: str | None,
                              wire_id: int | None, thread_id: str | None,
                              turn_id: str | None, payload_hash: str, observed_at: str,
                              owner_id: str, fence_epoch: int) -> dict[str, Any]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            if request_id is None:
                raise ValueError("request_id is required for fenced protocol events")
            request = self.connection.execute(
                "SELECT action_id FROM rpc_requests WHERE request_id=?", (request_id,),
            ).fetchone()
            if request is None:
                raise ValueError("unknown rpc request")
            resource = self._lease_for_action(str(request[0]))
            self._check_fence(resource, owner_id, fence_epoch)
            fields = (request_id, direction, message_kind, method, wire_id, thread_id,
                      turn_id, payload_hash, observed_at)
            existing = self.connection.execute(
                "SELECT request_id,direction,message_kind,method,wire_id,thread_id,turn_id,"
                "payload_hash,observed_at FROM protocol_journal WHERE journal_id=?", (journal_id,),
            ).fetchone()
            if existing is not None and tuple(existing) != fields:
                raise IntegrityIncident("protocol journal identity conflict")
            self.connection.execute(
                "INSERT OR IGNORE INTO protocol_journal(journal_id,request_id,direction,message_kind,"
                "method,wire_id,thread_id,turn_id,payload_hash,observed_at,owner_id,fence_epoch) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (journal_id, *fields, owner_id, fence_epoch),
            )
            self.connection.commit()
            row = self.connection.execute(
                "SELECT journal_id,request_id,direction,message_kind,method,wire_id,thread_id,turn_id,"
                "payload_hash,observed_at FROM protocol_journal WHERE journal_id=?", (journal_id,),
            ).fetchone()
            return dict(row)
        except Exception:
            self.connection.rollback()
            raise

    def attach_workflow(self, action_id: str, workflow_kind: str, owner_id: str,
                        fence_epoch: int, runtime_state: str = "attached") -> dict[str, str]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            resource = self._lease_for_action(action_id)
            self._check_fence(resource, owner_id, fence_epoch)
            existing = self.connection.execute(
                "SELECT workflow_id,workflow_kind FROM workflow_bindings WHERE action_id=?", (action_id,)
            ).fetchone()
            if existing is not None and (existing[0] != action_id or existing[1] != workflow_kind):
                raise IntegrityIncident("workflow binding conflict")
            self.connection.execute(
                "INSERT OR IGNORE INTO workflow_bindings(action_id,backend,workflow_id,workflow_kind,"
                "code_version,runtime_state,owner_id,fence_epoch) VALUES(?,'dbos',?,?,'v1',?,?,?)",
                (action_id, action_id, workflow_kind, runtime_state, owner_id, fence_epoch),
            )
            self.connection.execute(
                "UPDATE workflow_bindings SET runtime_state=?,last_reconciled_at=CURRENT_TIMESTAMP,"
                "owner_id=?,fence_epoch=? WHERE action_id=? AND workflow_id=? AND workflow_kind=?",
                (runtime_state, owner_id, fence_epoch, action_id, action_id, workflow_kind),
            )
            self.connection.execute(
                "UPDATE outbox SET state=CASE WHEN state='terminal' THEN state ELSE 'workflow_attached' END,"
                "owner_id=?,fence_epoch=? WHERE action_id=?",
                (owner_id, fence_epoch, action_id),
            )
            self.connection.commit()
            return {"action_id": action_id, "workflow_id": action_id, "workflow_kind": workflow_kind}
        except Exception:
            self.connection.rollback()
            raise

    def record_host_event(self, *, event_id: str, action_id: str, event_type: str,
                          observed_at: str, payload_hash: str, owner_id: str,
                          fence_epoch: int) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            resource = self._lease_for_action(action_id)
            self._check_fence(resource, owner_id, fence_epoch)
            existing = self.connection.execute(
                "SELECT event_type,observed_at,witness_hash FROM host_events WHERE event_id=?", (event_id,)
            ).fetchone()
            if existing is not None and tuple(existing) != (event_type, observed_at, payload_hash):
                raise IntegrityIncident("host event identity conflict")
            sequence = int(self.connection.execute(
                "SELECT COALESCE(MAX(host_sequence),0)+1 FROM host_events WHERE action_id=?", (action_id,)
            ).fetchone()[0])
            self.connection.execute(
                "INSERT OR IGNORE INTO host_events(event_id,action_id,host_sequence,event_type,observed_at,"
                "witness_hash,owner_id,fence_epoch) VALUES(?,?,?,?,?,?,?,?)",
                (event_id, action_id, sequence, event_type, observed_at, payload_hash, owner_id, fence_epoch),
            )
            if event_type == "terminal":
                self.connection.execute("UPDATE actions SET state='terminal' WHERE action_id=?", (action_id,))
                self.connection.execute("UPDATE outbox SET state='terminal' WHERE action_id=?", (action_id,))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def terminal_event(self, action_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT event_id,event_type,observed_at,witness_hash FROM host_events "
            "WHERE action_id=? AND event_type='terminal' ORDER BY host_sequence LIMIT 1", (action_id,),
        ).fetchone()
        if row is None:
            raise ValueError("terminal event not observed")
        return dict(row)

    def action_context(self, action_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT j.job_id,w.work_item_id,a.attempt_id,x.action_id,x.type,x.payload_hash,"
            "b.workflow_id,b.workflow_kind FROM actions x JOIN attempts a ON a.attempt_id=x.attempt_id "
            "JOIN work_items w ON w.work_item_id=a.work_item_id JOIN jobs j ON j.job_id=w.job_id "
            "LEFT JOIN workflow_bindings b ON b.action_id=x.action_id WHERE x.action_id=?", (action_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown action")
        return dict(row)

    def index_receipt(self, *, receipt_id: str, entity_id: str, path: str, content_hash: str,
                      previous_hash: str | None, owner_id: str, fence_epoch: int) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            resource = self._lease_for_action(entity_id)
            self._check_fence(resource, owner_id, fence_epoch)
            existing = self.connection.execute(
                "SELECT path,content_hash,previous_hash FROM receipt_index WHERE receipt_id=?", (receipt_id,)
            ).fetchone()
            expected = (path, content_hash, previous_hash)
            if existing is not None and tuple(existing) != expected:
                raise IntegrityIncident("receipt index conflict")
            self.connection.execute(
                "INSERT OR IGNORE INTO receipt_index(receipt_id,entity_id,path,content_hash,previous_hash,"
                "owner_id,fence_epoch) VALUES(?,?,?,?,?,?,?)",
                (receipt_id, entity_id, path, content_hash, previous_hash, owner_id, fence_epoch),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def receipt_index(self, receipt_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT receipt_id,entity_id,path,content_hash,previous_hash FROM receipt_index WHERE receipt_id=?",
            (receipt_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def latest_receipt_hash(self) -> str | None:
        row = self.connection.execute(
            "SELECT content_hash FROM receipt_index ORDER BY indexed_at DESC, receipt_id DESC LIMIT 1"
        ).fetchone()
        return str(row[0]) if row else None

    def project_status(self, job_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT j.job_id,l.owner_id,l.heartbeat_at,l.fence_epoch,b.workflow_id,b.runtime_state,o.state,"
            "tb.thread_id AS canonical_thread_id,tb.last_turn_id AS canonical_turn_id,"
            "tb.lifecycle_state AS thread_lifecycle_state,tb.pending_archive,"
            "r.request_id AS rpc_request_id,r.state AS rpc_state,r.thread_id AS rpc_thread_id,"
            "r.turn_id AS rpc_turn_id "
            "FROM jobs j JOIN work_items w ON w.job_id=j.job_id LEFT JOIN leases l ON l.resource_id=w.work_item_id "
            "LEFT JOIN attempts a ON a.work_item_id=w.work_item_id LEFT JOIN actions x ON x.attempt_id=a.attempt_id "
            "LEFT JOIN workflow_bindings b ON b.action_id=x.action_id LEFT JOIN outbox o ON o.action_id=x.action_id "
            "LEFT JOIN thread_bindings tb ON tb.attempt_id=a.attempt_id "
            "LEFT JOIN rpc_requests r ON r.action_id=x.action_id "
            "WHERE j.job_id=? ORDER BY a.ordinal DESC LIMIT 1", (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown job")
        result = dict(row)
        result["evidence_class"] = "fake-host"
        if result.get("rpc_state") == "ambiguous":
            result["next_durable_action"] = f"reconcile:{result.get('rpc_request_id')}"
        elif result.get("rpc_state") == "planned":
            result["next_durable_action"] = f"dispatch:{result.get('rpc_request_id')}"
        else:
            result["next_durable_action"] = "none" if result.get("state") == "terminal" else result.get("state", "reconcile")
        result["schema_version"] = "ds-lite.project-status.v1"
        return result

    # Phase 0.5 compatibility surface used only by the frozen spike harness.
    def plan_action(self, action_id: str, kind: str) -> dict[str, str]:
        if not action_id:
            raise ValueError("action_id is required")
        work_item_id = action_id.replace("action", "work", 1)
        epoch = self.create_job_work_item("phase05-spike", work_item_id, "phase05-owner")
        self.plan_attempt_action(
            job_id="phase05-spike", work_item_id=work_item_id, attempt_id=f"attempt-{action_id}",
            action_id=action_id, kind=kind, payload_hash=_canonical_hash({"kind": kind}),
            owner_id="phase05-owner", fence_epoch=epoch,
        )
        self.attach_workflow(action_id, "phase05_spike_v1", "phase05-owner", epoch)
        return {"action_id": action_id, "workflow_id": action_id}

    def workflow_binding_count(self, action_id: str) -> int:
        return int(self.connection.execute(
            "SELECT COUNT(*) FROM workflow_bindings WHERE action_id=?", (action_id,)
        ).fetchone()[0])

    def enqueue(self, action_id: str, fence_epoch: int, owner: str) -> None:
        resource = self._lease_for_action(action_id)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self._check_fence(resource, owner, fence_epoch)
            self.connection.execute(
                "UPDATE outbox SET state='queued',owner_id=?,fence_epoch=? WHERE action_id=?",
                (owner, fence_epoch, action_id),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def outbox_fence(self, action_id: str) -> tuple[str, int] | None:
        row = self.connection.execute(
            "SELECT owner_id,fence_epoch FROM outbox WHERE action_id=?", (action_id,)
        ).fetchone()
        return (str(row[0]), int(row[1])) if row else None
