from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evidence import EvidenceManager, canonical_hash, file_hash, write_once
from .errors import IntegrityIncident
from .store import ControlStore


class ReviewError(ValueError):
    pass


class ReviewSidecar:
    FIELDS = {"schema_version", "verdict", "finding_codes", "evidence_refs"}

    @classmethod
    def validate(cls, payload: dict[str, Any], *, allowed_refs: set[str]) -> dict[str, Any]:
        if not isinstance(payload, dict) or set(payload) != cls.FIELDS:
            raise ReviewError("review sidecar fields are invalid")
        if payload.get("schema_version") != "ds-lite.review-sidecar.v1":
            raise ReviewError("unsupported review sidecar schema")
        if payload.get("verdict") not in {"accept", "reject", "inconclusive"}:
            raise ReviewError("review verdict is invalid")
        findings = payload.get("finding_codes")
        refs = payload.get("evidence_refs")
        if not isinstance(findings, list) or not all(isinstance(item, str) and item for item in findings):
            raise ReviewError("finding codes must be strings")
        if not isinstance(refs, list) or not all(isinstance(item, str) and item in allowed_refs for item in refs):
            raise ReviewError("review evidence reference is not in the frozen evidence set")
        return payload


class ReviewCoordinator:
    def __init__(self, store: ControlStore, receipt_root: Path) -> None:
        self.store = store
        self.receipt_root = receipt_root.resolve()

    def prepare(
        self, work_item_id: str, evidence_set_id: str, verifier_id: str, *,
        schema_digest: str, model: str, owner_id: str, fence_epoch: int,
    ) -> dict[str, Any]:
        row = self.store.connection.execute(
            "SELECT v.status,e.manifest_hash FROM verifier_runs v JOIN evidence_sets e "
            "ON e.evidence_set_id=v.evidence_set_id WHERE v.verifier_id=? AND "
            "v.evidence_set_id=? AND v.work_item_id=?",
            (verifier_id, evidence_set_id, work_item_id),
        ).fetchone()
        if row is None or row[0] != "passed":
            raise ReviewError("terminal verifier pass is required")
        review_id = f"review-{canonical_hash([work_item_id, evidence_set_id, verifier_id])[:32]}"
        request_hash = canonical_hash({
            "work_item_id": work_item_id, "evidence_set_id": evidence_set_id,
            "verifier_id": verifier_id, "schema_digest": schema_digest, "model": model,
        })
        self.store.connection.execute("BEGIN IMMEDIATE")
        try:
            self.store._check_fence(work_item_id, owner_id, fence_epoch)
            existing = self.store.connection.execute(
                "SELECT evidence_set_id,verifier_id,schema_digest,model,request_hash,pre_manifest_hash "
                "FROM review_requests WHERE review_id=?", (review_id,)
            ).fetchone()
            expected = (evidence_set_id, verifier_id, schema_digest, model, request_hash, str(row[1]))
            if existing is not None and tuple(existing) != expected:
                raise IntegrityIncident("review request identity conflict")
            self.store.connection.execute(
                "INSERT OR IGNORE INTO review_requests(review_id,work_item_id,evidence_set_id,verifier_id,"
                "state,schema_digest,model,request_hash,pre_manifest_hash,owner_id,fence_epoch,created_at) "
                "VALUES(?,?,?,?,'planned',?,?,?,?,?,?,?)",
                (review_id, work_item_id, evidence_set_id, verifier_id, schema_digest, model,
                 request_hash, str(row[1]), owner_id, fence_epoch,
                 self.store._stamp(self.store._now())),
            )
            self.store.connection.commit()
        except Exception:
            self.store.connection.rollback()
            raise
        return {
            "review_id": review_id, "evidence_set_id": evidence_set_id,
            "verifier_id": verifier_id, "request_hash": request_hash,
            "pre_manifest_hash": str(row[1]), "state": "planned",
        }

    def bind_thread(
        self, review_id: str, thread_id: str, *, worker_thread_ids: set[str],
        owner_id: str, fence_epoch: int,
    ) -> None:
        if not thread_id or thread_id in worker_thread_ids:
            raise ReviewError("reviewer thread must be independent")
        self.store.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.store.connection.execute(
                "SELECT work_item_id,reviewer_thread_id FROM review_requests WHERE review_id=?",
                (review_id,),
            ).fetchone()
            if row is None:
                raise ReviewError("unknown review request")
            self.store._check_fence(str(row[0]), owner_id, fence_epoch)
            if row[1] is not None and row[1] != thread_id:
                raise ReviewError("second reviewer thread is forbidden")
            self.store.connection.execute(
                "UPDATE review_requests SET reviewer_thread_id=?,state='thread-bound',owner_id=?,fence_epoch=? "
                "WHERE review_id=?", (thread_id, owner_id, fence_epoch, review_id)
            )
            self.store.connection.commit()
        except Exception:
            self.store.connection.rollback()
            raise

    def record_result(
        self, review_id: str, payload: dict[str, Any], *, post_manifest_hash: str,
        reviewer_turn_id: str, owner_id: str, fence_epoch: int,
    ) -> dict[str, Any]:
        row = self.store.connection.execute(
            "SELECT r.work_item_id,r.evidence_set_id,r.verifier_id,r.reviewer_thread_id,"
            "r.pre_manifest_hash,r.schema_digest,r.model,e.manifest_hash FROM review_requests r "
            "JOIN evidence_sets e ON e.evidence_set_id=r.evidence_set_id WHERE r.review_id=?",
            (review_id,),
        ).fetchone()
        if row is None or row[3] is None:
            raise ReviewError("reviewer thread is not bound")
        allowed_refs = {
            str(item[0]) for item in self.store.connection.execute(
                "SELECT relative_path FROM evidence_members WHERE evidence_set_id=?", (row[1],)
            ).fetchall()
        }
        ReviewSidecar.validate(payload, allowed_refs=allowed_refs)
        if post_manifest_hash != row[4] or post_manifest_hash != row[7]:
            self.store.record_integrity_incident(
                f"incident-{canonical_hash([review_id, post_manifest_hash])[:32]}",
                scope="review", entity_id=review_id, reason_code="artifact-drift",
                evidence_hash=post_manifest_hash,
            )
            raise ReviewError("artifact manifest changed during review")
        receipt_id = f"sidecar-{review_id}"
        findings_hash = canonical_hash(payload)
        existing = self.store.connection.execute(
            "SELECT verdict,findings_hash,post_manifest_hash,evidence_hash FROM review_results "
            "WHERE review_id=?", (review_id,)
        ).fetchone()
        if existing is not None:
            if tuple(existing[:3]) != (payload["verdict"], findings_hash, post_manifest_hash):
                raise ReviewError("write-once review result differs")
            receipt_path = self.receipt_root / f"{receipt_id}.json"
            try:
                saved = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise IntegrityIncident("review receipt is missing or invalid") from exc
            if file_hash(receipt_path) != existing[3]:
                raise IntegrityIncident("review receipt content hash conflict")
            return saved
        receipt = {
            "schema_version": "ds-lite.review-sidecar.v1",
            "receipt_id": receipt_id,
            "review_id": review_id,
            "work_item_id": str(row[0]),
            "evidence_set_id": str(row[1]),
            "verifier_id": str(row[2]),
            "reviewer_thread_hash": canonical_hash(str(row[3])),
            "reviewer_turn_hash": canonical_hash(reviewer_turn_id),
            "schema_digest": str(row[5]),
            "model": str(row[6]),
            "manifest_hash": post_manifest_hash,
            "verdict": payload["verdict"],
            "finding_codes": payload["finding_codes"],
            "evidence_refs": payload["evidence_refs"],
            "previous_receipt_hash": self.store.latest_receipt_hash(),
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        receipt_path = self.receipt_root / f"{receipt_id}.json"
        content_hash = write_once(receipt_path, receipt)
        self.store.connection.execute("BEGIN IMMEDIATE")
        try:
            self.store._check_fence(str(row[0]), owner_id, fence_epoch)
            existing = self.store.connection.execute(
                "SELECT verdict,findings_hash,post_manifest_hash,evidence_hash FROM review_results "
                "WHERE review_id=?", (review_id,)
            ).fetchone()
            expected = (payload["verdict"], findings_hash, post_manifest_hash, content_hash)
            if existing is not None and tuple(existing) != expected:
                raise ReviewError("write-once review result differs")
            self.store.connection.execute(
                "INSERT OR IGNORE INTO review_results(review_id,verdict,findings_hash,sidecar_receipt_id,"
                "post_manifest_hash,evidence_hash,owner_id,fence_epoch,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (review_id, payload["verdict"], findings_hash, receipt_id, post_manifest_hash,
                 content_hash, owner_id, fence_epoch, self.store._stamp(self.store._now())),
            )
            self.store.connection.execute(
                "UPDATE review_requests SET state='terminal',reviewer_turn_id=? WHERE review_id=?",
                (reviewer_turn_id, review_id),
            )
            self.store.connection.execute(
                "INSERT OR IGNORE INTO receipt_index(receipt_id,entity_id,path,content_hash,previous_hash,"
                "owner_id,fence_epoch,entity_kind,work_item_id) VALUES(?,?,?,?,?,?,?,?,?)",
                (receipt_id, review_id, receipt_path.name, content_hash,
                 receipt["previous_receipt_hash"], owner_id, fence_epoch, "review", str(row[0])),
            )
            self.store.connection.commit()
        except Exception:
            self.store.connection.rollback()
            raise
        return receipt


class BrokerReviewRunner:
    INSTRUCTIONS = (
        "You are an independent evidence reviewer. Read only the listed frozen evidence in the "
        "current directory. Do not write or modify files, do not inspect outside the current "
        "directory, and do not infer release status. Return exactly one JSON object with keys "
        "schema_version, verdict, finding_codes, evidence_refs. schema_version must be "
        "ds-lite.review-sidecar.v1 and verdict must be accept, reject, or inconclusive."
    )

    def __init__(
        self, store: ControlStore, coordinator: ReviewCoordinator, adapter: Any, *,
        private_spool_root: Path,
    ) -> None:
        self.store = store
        self.coordinator = coordinator
        self.adapter = adapter
        self.private_spool_root = private_spool_root.resolve()

    def _request(self, review_id: str) -> Any:
        row = self.store.connection.execute(
            "SELECT q.work_item_id,q.evidence_set_id,q.verifier_id,q.state,q.reviewer_thread_id,"
            "q.reviewer_turn_id,q.model,q.pre_manifest_hash,e.artifact_root,e.manifest_path "
            "FROM review_requests q JOIN evidence_sets e ON e.evidence_set_id=q.evidence_set_id "
            "WHERE q.review_id=?", (review_id,),
        ).fetchone()
        if row is None:
            raise ReviewError("unknown review request")
        return row

    def _current_manifest_hash(self, evidence_set_id: str, artifact_root: Path,
                               frozen_hash: str) -> str:
        current: list[dict[str, Any]] = []
        unchanged = True
        for row in self.store.connection.execute(
            "SELECT relative_path,content_hash FROM evidence_members WHERE evidence_set_id=? "
            "ORDER BY relative_path", (evidence_set_id,)
        ).fetchall():
            path = artifact_root / Path(str(row[0]))
            observed = file_hash(path) if path.is_file() else "missing"
            current.append({"path": str(row[0]), "content_hash": observed})
            unchanged = unchanged and observed == row[1]
        return frozen_hash if unchanged else canonical_hash(current)

    @staticmethod
    def _agent_text(response: dict[str, Any] | None, turn_id: str) -> str:
        result = response.get("result") if isinstance(response, dict) else None
        thread = result.get("thread") if isinstance(result, dict) else None
        turns = thread.get("turns") if isinstance(thread, dict) else None
        if not isinstance(turns, list):
            raise ReviewError("thread/read did not return turns")
        messages: list[str] = []
        for turn in turns:
            if not isinstance(turn, dict) or turn.get("id") != turn_id:
                continue
            items = turn.get("items")
            if not isinstance(items, list):
                continue
            messages.extend(
                str(item["text"]) for item in items
                if isinstance(item, dict) and item.get("type") == "agentMessage"
                and isinstance(item.get("text"), str)
            )
        if not messages:
            raise ReviewError("reviewer terminal turn has no agent message")
        return messages[-1]

    def run(self, review_id: str, *, owner_id: str, fence_epoch: int,
            observe_timeout: float = 120.0) -> dict[str, Any]:
        existing = self.store.connection.execute(
            "SELECT sidecar_receipt_id FROM review_results WHERE review_id=?", (review_id,)
        ).fetchone()
        if existing is not None:
            path = self.coordinator.receipt_root / f"{existing[0]}.json"
            return json.loads(path.read_text(encoding="utf-8"))
        request = self._request(review_id)
        work_item_id = str(request[0])
        evidence_set_id = str(request[1])
        artifact_root = Path(str(request[8]))
        self.adapter.initialize(request_id=f"{review_id}:initialize")
        thread_id = str(request[4]) if request[4] else None
        if thread_id is None:
            started = self.adapter.start_thread({
                "cwd": str(artifact_root),
                "sandbox": "read-only",
                "approvalPolicy": "never",
                "model": str(request[6]),
                "developerInstructions": self.INSTRUCTIONS,
                "ephemeral": False,
            }, request_id=f"{review_id}:thread-start")
            if not started.thread_id:
                raise ReviewError("reviewer thread identity was not observed")
            thread_id = started.thread_id
            worker_threads = {
                str(row[0]) for row in self.store.connection.execute(
                    "SELECT thread_id FROM thread_bindings WHERE thread_id IS NOT NULL"
                ).fetchall()
            }
            self.coordinator.bind_thread(
                review_id, thread_id, worker_thread_ids=worker_threads,
                owner_id=owner_id, fence_epoch=fence_epoch,
            )
        request = self._request(review_id)
        turn_id = str(request[5]) if request[5] else None
        turn_request_id = f"{review_id}:turn-start"
        if turn_id is None and str(request[3]) not in {"planned", "thread-bound", "dispatching"}:
            raise ReviewError("review request cannot dispatch from its current state")
        if turn_id is None and str(request[3]) == "dispatching":
            reconcile = getattr(self.adapter, "reconcile_request", None)
            if reconcile is not None:
                observed = reconcile(turn_request_id, thread_id)
                turn_id = observed.turn_id
            if turn_id is None:
                raise ReviewError("review turn response gap is ambiguous")
        if turn_id is None:
            refs = [
                str(row[0]) for row in self.store.connection.execute(
                    "SELECT relative_path FROM evidence_members WHERE evidence_set_id=? "
                    "ORDER BY relative_path", (evidence_set_id,)
                ).fetchall()
            ]
            prompt = json.dumps({
                "review_id": review_id,
                "evidence_set_id": evidence_set_id,
                "verifier_status": "passed",
                "evidence_refs": refs,
                "required_output_schema": "ds-lite.review-sidecar.v1",
            }, ensure_ascii=True, sort_keys=True)
            self.store.connection.execute("BEGIN IMMEDIATE")
            try:
                self.store._check_fence(work_item_id, owner_id, fence_epoch)
                self.store.connection.execute(
                    "UPDATE review_requests SET state='dispatching' WHERE review_id=?", (review_id,)
                )
                self.store.connection.commit()
            except Exception:
                self.store.connection.rollback()
                raise
            try:
                started_turn = self.adapter.start_turn(
                    thread_id, [{"type": "text", "text": prompt}],
                    request_id=turn_request_id, model=str(request[6]),
                )
                turn_id = started_turn.turn_id
            except TimeoutError:
                reconcile = getattr(self.adapter, "reconcile_request", None)
                observed = reconcile(turn_request_id, thread_id) if reconcile is not None else None
                turn_id = observed.turn_id if observed is not None else None
            if not turn_id:
                raise ReviewError("review turn response gap is ambiguous")
            self.store.connection.execute("BEGIN IMMEDIATE")
            try:
                self.store._check_fence(work_item_id, owner_id, fence_epoch)
                self.store.connection.execute(
                    "UPDATE review_requests SET reviewer_turn_id=?,state='observing' WHERE review_id=?",
                    (turn_id, review_id),
                )
                self.store.connection.commit()
            except Exception:
                self.store.connection.rollback()
                raise
        terminal = self.adapter.observe_turn(thread_id, turn_id, timeout=observe_timeout)
        if terminal.disposition != "terminal":
            raise ReviewError(f"review turn is not terminal: {terminal.disposition}")
        read = self.adapter.read_thread(
            thread_id, include_turns=True, request_id=f"{review_id}:thread-read"
        )
        text = self._agent_text(read.response, turn_id)
        try:
            payload = json.loads(text.strip())
        except json.JSONDecodeError as exc:
            raise ReviewError("reviewer output is not strict JSON") from exc
        manager = EvidenceManager(
            self.store, Path(str(request[9])).parent, self.private_spool_root
        )
        manager.store_private_witness(
            work_item_id, "review-agent-message", text.encode("utf-8"),
            owner_id=owner_id, fence_epoch=fence_epoch,
        )
        post_hash = self._current_manifest_hash(
            evidence_set_id, artifact_root, str(request[7])
        )
        return self.coordinator.record_result(
            review_id, payload, post_manifest_hash=post_hash,
            reviewer_turn_id=turn_id, owner_id=owner_id, fence_epoch=fence_epoch,
        )


__all__ = ["BrokerReviewRunner", "ReviewCoordinator", "ReviewError", "ReviewSidecar"]
